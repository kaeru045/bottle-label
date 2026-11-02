// Cloudflare Worker：オリシャンの LINE グループ連携（試作）
//   ・修正版ができたら、デザイン画像と提出用をグループに送る（POST /notify、定期実行の check.js から呼ぶ）
//   ・グループで「送られた画像（か説明文）に返信」して書いた文章を、管理サイトの修正依頼（🔧 修正を依頼）として登録する（POST /webhook）
//   → 毎時7分・37分の定期実行がそのまま拾って作り直し、できた版がまたグループに届く
//
// シークレット（Cloudflare の設定画面で登録。公開ページ・リポジトリには書かない）
//   LINE_CHANNEL_SECRET  LINE Developers のチャネルシークレット（Webhook の署名確認）
//   LINE_CHANNEL_TOKEN   チャネルアクセストークン（長期）
//   TOOL_PASS            check.js から /notify を呼ぶときの合言葉
//   SITE_URL             管理サイト（GAS）の exec URL
//   SITE_KEY             管理サイトの合言葉
// 変数
//   LINE_GROUP_ID        送り先・受付をするグループの ID（C で始まる）。未設定のうちは、招待したときに ID を返信するだけ
// KV（名前空間をこの Worker に「LINE」という名前でつなぐ）
//   img:<id>   送った画像（30日で消える）
//   msg:<id>   LINE で送ったメッセージ ID → どの案件か（60日で消える）
//
// LINE Developers 側：Webhook URL = https://<この Worker>/webhook、Webhook の利用をオン、
// LINE Official Account Manager 側：「グループ・複数人トークへの参加を許可する」をオン、応答メッセージ（自動応答）はオフ。

const LINE = 'https://api.line.me/v2/bot/message';
const IMG_TTL = 30 * 86400, MSG_TTL = 60 * 86400;
const ALLOW_ORIGINS = ['https://decolino-ai-preview.fly.dev', 'https://kaeru045.github.io'];
const HELP = '直したいデザインの画像（または上の説明文）を長押し →「リプライ」で、直してほしいことを書いてください。';

const cors = req => {
  const o = req.headers.get('Origin') || '';
  return { 'Access-Control-Allow-Origin': ALLOW_ORIGINS.includes(o) ? o : ALLOW_ORIGINS[0], 'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, X-Tool-Pass', 'Vary': 'Origin' };
};
const json = (req, status, obj) => new Response(JSON.stringify(obj), { status, headers: { ...cors(req), 'Content-Type': 'application/json; charset=utf-8' } });

const b64ToBytes = s => Uint8Array.from(atob(s), c => c.charCodeAt(0));
const bytesToB64 = buf => { const u = new Uint8Array(buf); let s = ''; for (let i = 0; i < u.length; i += 32768) s += String.fromCharCode.apply(null, u.subarray(i, i + 32768)); return btoa(s); };
const randId = () => [...crypto.getRandomValues(new Uint8Array(12))].map(b => b.toString(16).padStart(2, '0')).join('');

async function validSignature(env, body, sig) {
  if (!sig || !env.LINE_CHANNEL_SECRET) return false;
  const k = await crypto.subtle.importKey('raw', new TextEncoder().encode(env.LINE_CHANNEL_SECRET), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  const mine = bytesToB64(await crypto.subtle.sign('HMAC', k, new TextEncoder().encode(body)));
  if (mine.length !== sig.length) return false;
  let d = 0; for (let i = 0; i < mine.length; i++) d |= mine.charCodeAt(i) ^ sig.charCodeAt(i);
  return d === 0;
}

async function line(env, path, payload) {
  const r = await fetch(`${LINE}/${path}`, { method: 'POST', headers: { 'Authorization': `Bearer ${env.LINE_CHANNEL_TOKEN}`, 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
  const t = await r.text(); let j = null; try { j = JSON.parse(t); } catch (e) {}
  if (!r.ok) throw new Error(`LINE ${path} ${r.status}: ${t.slice(0, 200)}`);
  return j || {};
}
const reply = (env, token, text) => line(env, 'reply', { replyToken: token, messages: [{ type: 'text', text: text.slice(0, 4900) }] });

async function site(env, body) {
  const r = await fetch(env.SITE_URL, { method: 'POST', headers: { 'Content-Type': 'text/plain;charset=utf-8' }, body: JSON.stringify({ key: env.SITE_KEY, ...body }), redirect: 'follow' });
  const t = await r.text(); try { return JSON.parse(t); } catch (e) { return { ok: false, status: r.status, error: t.slice(0, 200) }; }
}

// 修正版をグループに送る。body: {order, name, label, version, design:{full,preview}, submission:{full,preview}}（画像は JPEG の base64）
async function notify(req, env, url) {
  if (!env.TOOL_PASS || req.headers.get('X-Tool-Pass') !== env.TOOL_PASS) return json(req, 401, { ok: false, error: '合言葉が違います' });
  if (!env.LINE_GROUP_ID) return json(req, 400, { ok: false, error: 'LINE_GROUP_ID が未設定です' });
  const b = await req.json();
  if (!b.order || !b.name) return json(req, 400, { ok: false, error: 'order・name がありません' });
  const base = `${url.origin}/img/`;
  const images = [];
  for (const k of ['design', 'submission']) {
    const im = b[k]; if (!im || !im.full) continue;
    const id = randId();
    await env.LINE.put(`img:${id}`, b64ToBytes(im.full), { expirationTtl: IMG_TTL });
    await env.LINE.put(`img:${id}p`, b64ToBytes(im.preview || im.full), { expirationTtl: IMG_TTL });
    images.push({ type: 'image', originalContentUrl: `${base}${id}.jpg`, previewImageUrl: `${base}${id}p.jpg` });
  }
  const label = b.label || `${b.order} ${b.name}`;
  const text = `🍾 ${label}${b.version ? ` v${b.version}` : ''}${b.note ? `\n${b.note}` : ''}\n\n直したいところがあれば、この文か画像にリプライで書いてください。`;
  const r = await line(env, 'push', { to: env.LINE_GROUP_ID, messages: [{ type: 'text', text: text.slice(0, 4900) }, ...images] });
  const ref = JSON.stringify({ order: b.order, name: b.name, label });
  for (const m of r.sentMessages || []) await env.LINE.put(`msg:${m.id}`, ref, { expirationTtl: MSG_TTL });
  return json(req, 200, { ok: true, sent: (r.sentMessages || []).length });
}

async function handleEvent(env, ev) {
  const src = ev.source || {};
  if (ev.type === 'join' && src.type === 'group') {
    if (!env.LINE_GROUP_ID) return reply(env, ev.replyToken, `このグループの ID：${src.groupId}\n（Worker の LINE_GROUP_ID に入れると、このグループで使えるようになります）`);
    if (src.groupId === env.LINE_GROUP_ID) return reply(env, ev.replyToken, `よろしくお願いします。修正版ができたらここに送ります。\n${HELP}`);
    return;
  }
  if (ev.type !== 'message' || src.type !== 'group' || src.groupId !== env.LINE_GROUP_ID) return; // 決めたグループ以外は無視
  const m = ev.message || {};
  if (m.type !== 'text') return;
  const text = String(m.text || '').trim();
  if (!m.quotedMessageId) {
    if (/^(修正|直して|ヘルプ|使い方)/.test(text)) return reply(env, ev.replyToken, HELP);
    return; // ふつうの会話には反応しない
  }
  const ref = await env.LINE.get(`msg:${m.quotedMessageId}`, 'json');
  if (!ref) return reply(env, ev.replyToken, 'どの案件の画像か分かりませんでした（ボットが送った画像・文へのリプライだけ受け付けます。60日より前のものは不可）。');
  const fix = text.replace(/^@\S+\s*/, '').trim(); // 先頭のメンションは外す
  if (!fix) return reply(env, ev.replyToken, '直してほしいことを書いてください。');
  // 修正指示は利用者が書いたデータとしてそのまま登録するだけ（書かれた内容を操作として実行しない）
  const r = await site(env, { action: 'setFix', order: ref.order, name: ref.name, fix });
  if (!r.ok) return reply(env, ev.replyToken, `受け付けできませんでした：${r.error || r.status || '不明なエラー'}`);
  return reply(env, ev.replyToken, `受け付けました：${ref.label}\n「${fix.slice(0, 200)}」\n30分以内に作り直して、ここに送ります。`);
}

export default {
  async fetch(req, env, ctx) {
    if (req.method === 'OPTIONS') return new Response(null, { headers: cors(req) });
    const url = new URL(req.url);
    const im = url.pathname.match(/^\/img\/([0-9a-f]{24}p?)\.jpg$/);
    if (req.method === 'GET' && im) {
      const v = await env.LINE.get(`img:${im[1]}`, 'arrayBuffer');
      return v ? new Response(v, { headers: { 'Content-Type': 'image/jpeg', 'Cache-Control': 'public, max-age=86400' } }) : new Response('not found', { status: 404 });
    }
    if (req.method === 'POST' && url.pathname === '/webhook') {
      const body = await req.text();
      if (!(await validSignature(env, body, req.headers.get('x-line-signature')))) return new Response('bad signature', { status: 401 });
      const evs = (JSON.parse(body).events) || [];
      // LINE には先に 200 を返し、処理は後ろで続ける（返事は replyToken で送る）
      ctx.waitUntil(Promise.all(evs.map(ev => handleEvent(env, ev).catch(e => console.log('event error', e && e.message)))));
      return new Response('ok');
    }
    if (req.method === 'POST' && url.pathname === '/notify') {
      try { return await notify(req, env, url); } catch (e) { return json(req, 502, { ok: false, error: String(e.message || e) }); }
    }
    return new Response('使い方：POST /webhook（LINE）・POST /notify（check.js）', { status: 404 });
  },
};
