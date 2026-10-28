// Cloudflare Worker：横長リサイズの「背景を広げる」用の中継サーバー
// ツール（GitHub Pages）→ この Worker → Adobe Firefly API（生成拡張）
// API キーはこの Worker のシークレットにだけ置き、公開ページには書かない。
//
// シークレット（Cloudflare の設定画面で登録）
//   FIREFLY_CLIENT_ID      Adobe Developer Console のクライアント ID
//   FIREFLY_CLIENT_SECRET  同じくクライアントシークレット
//   TOOL_PASS              ツールに入れる合言葉（社内の人だけが使えるように）
//
// リクエスト：POST /expand
//   ヘッダー  X-Tool-Pass: 合言葉 / Content-Type: image/png（本文は写真の PNG）
//   クエリ    ?w=1440&h=1024&left=..&top=..&right=..&bottom=..（仕上がりの大きさと、写真の周りの余白 px）
// レスポンス：広げた画像（PNG / JPEG）そのもの

const ALLOW_ORIGINS = ['https://kaeru045.github.io', 'null']; // null = ファイル版を直接開いたとき
const IMS = 'https://ims-na1.adobelogin.com/ims/token/v3';
const FF = 'https://firefly-api.adobe.io';
let tokenCache = null; // {token, until}

function cors(req) {
  const o = req.headers.get('Origin') || '';
  const ok = ALLOW_ORIGINS.includes(o) || o.endsWith('.claudeusercontent.com') || o.endsWith('.claude.ai');
  return {
    'Access-Control-Allow-Origin': ok ? o : ALLOW_ORIGINS[0],
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, X-Tool-Pass',
    'Access-Control-Expose-Headers': 'X-Seed',
    'Vary': 'Origin',
  };
}
const fail = (req, status, msg) => new Response(JSON.stringify({error: msg}), {status, headers: {...cors(req), 'Content-Type': 'application/json; charset=utf-8'}});

async function getToken(env) {
  if (tokenCache && tokenCache.until > Date.now()) return tokenCache.token;
  const body = new URLSearchParams({
    grant_type: 'client_credentials', client_id: env.FIREFLY_CLIENT_ID, client_secret: env.FIREFLY_CLIENT_SECRET,
    scope: 'openid,AdobeID,session,additional_info,read_organizations,firefly_api,ff_apis',
  });
  const r = await fetch(IMS, {method: 'POST', headers: {'Content-Type': 'application/x-www-form-urlencoded'}, body});
  if (!r.ok) throw new Error(`Adobe のログインに失敗しました（${r.status}）。クライアント ID・シークレットを確認してください。`);
  const j = await r.json();
  tokenCache = {token: j.access_token, until: Date.now() + Math.max(60, (j.expires_in || 86400) - 600) * 1000};
  return tokenCache.token;
}

export default {
  async fetch(req, env) {
    if (req.method === 'OPTIONS') return new Response(null, {headers: cors(req)});
    const url = new URL(req.url);
    if (req.method !== 'POST' || url.pathname !== '/expand') return fail(req, 404, '使い方：POST /expand');
    if (!env.TOOL_PASS || req.headers.get('X-Tool-Pass') !== env.TOOL_PASS) return fail(req, 401, '合言葉が違います。');
    if (!env.FIREFLY_CLIENT_ID || !env.FIREFLY_CLIENT_SECRET) return fail(req, 500, 'Adobe のキーが登録されていません。');

    const q = k => Math.round(+url.searchParams.get(k) || 0);
    const w = q('w') || 1440, h = q('h') || 1024;
    const inset = {left: q('left'), top: q('top'), right: q('right'), bottom: q('bottom')};
    if (Object.values(inset).some(v => v < 0)) return fail(req, 400, '余白がマイナスです。');
    const img = await req.arrayBuffer();
    if (!img.byteLength || img.byteLength > 30e6) return fail(req, 400, '画像がありません、または大きすぎます。');

    try {
      const token = await getToken(env);
      const auth = {'Authorization': `Bearer ${token}`, 'X-Api-Key': env.FIREFLY_CLIENT_ID};
      // 1. 写真をアップロード
      const up = await fetch(`${FF}/v2/storage/image`, {method: 'POST', headers: {...auth, 'Content-Type': req.headers.get('Content-Type') || 'image/png'}, body: img});
      if (!up.ok) throw new Error(`画像のアップロードに失敗しました（${up.status}）：${(await up.text()).slice(0, 200)}`);
      const uploadId = (await up.json()).images[0].id;
      // 2. 生成拡張（写真の位置は余白で指定）
      const ex = await fetch(`${FF}/v3/images/expand-async`, {method: 'POST', headers: {...auth, 'Content-Type': 'application/json'},
        body: JSON.stringify({numVariations: 1, size: {width: w, height: h}, image: {source: {uploadId}}, placement: {inset}})});
      if (!ex.ok) throw new Error(`生成拡張の依頼に失敗しました（${ex.status}）：${(await ex.text()).slice(0, 200)}`);
      const {statusUrl} = await ex.json();
      // 3. できあがるまで待つ（2秒ごと、最大40回）。Cloudflare 無料プランは1回の呼び出しで外部への通信が50回までなので、合計44回以内に収める
      for (let i = 0; i < 40; i++) {
        await new Promise(r => setTimeout(r, 2000));
        const st = await (await fetch(statusUrl, {headers: auth})).json();
        if (st.status === 'succeeded') {
          const out = st.result.outputs[0];
          const res = await fetch(out.image.url);
          return new Response(res.body, {headers: {...cors(req), 'Content-Type': res.headers.get('Content-Type') || 'image/jpeg', 'X-Seed': String(out.seed ?? '')}});
        }
        if (st.status === 'failed' || st.status === 'canceled') throw new Error(`生成拡張が失敗しました：${JSON.stringify(st).slice(0, 200)}`);
      }
      throw new Error('80秒待ってもできあがらなかったので止めました。もう一度押してください。');
    } catch (e) {
      return fail(req, 502, String(e.message || e));
    }
  },
};
