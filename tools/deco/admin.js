// Decolino管理画面（https://admin.reserve-viva-decolino.com/ai）の「AI生成」でできた画像を、
// オリシャン完成デザイン管理（管理サイト）に登録する。2026-11-05 ユーザー指定：最新の生成案すべて・定期で自動。
// 使い方：admin のページ（ログイン済み）で、先に check.js を読み込んでから（__W / __K が必要）このファイルを読み込み、
//   JSON.stringify(await adminSync({ max: 10 }))        … 未登録の生成案を最大10件登録
//   JSON.stringify(await adminSync({ dry: true }))      … 登録せずに対象だけ表示
// 案の画像ID（candidate id）を「元画像ID」に 'adm-<id>' で記録するので、同じ案は二度登録しない。
// 同じ注文番号＋名前＋テンプレの案件がすでにあれば、新しい版として更新される（修正前は履歴に残る）。
// 個人情報（メール・電話・住所）は管理サイトに送らない。
if (typeof registerToSite !== 'function') throw new Error('先に check.js を読み込んでください');

window.adminSpec = c => {
  const t = [c.tagShape, ...(c.details || []).map(d => d.tagShape)].filter(Boolean).join(' ');
  const hasTag = !!t || (c.details || []).some(d => d.hasTagOption);
  const tag = /ハート|heart/i.test(t) ? 'heart' : /猫|ねこ|cat/i.test(t) ? 'cat' : /くま|熊|bear/i.test(t) ? 'bear' : /月|moon/i.test(t) ? 'moon'
    : /ボトル|bottle/i.test(t) ? 'tagbody' : hasTag ? 'square' : '';
  const n = String(c.neckSeal || '');
  const seal = /白|ホワイト|white/i.test(n) ? 'sl_lx_white' : /黒|ブラック|black/i.test(n) ? 'sl_lx_black' : /金|ゴールド|gold/i.test(n) ? 'sl_lx_gold'
    : /銀|シルバー|silver/i.test(n) ? 'sl_lx_silver' : 'sl_lx_auto';
  return Object.assign({ seal }, tag ? { tag } : {});
};

// 取り込まない案（試作など）。2026-11-06 ユーザー指定：#04719 の完全オリジナル試作（生成603の案1〜3）は消す
window.ADMIN_SKIP = new Set([1061, 1062, 1063, 1064, 1065, 1066, 1076, 1077, 1078, 1079, 1080, 1081]); // 1064〜1066：2026-11-06 プロンプトのサンプル（生成604）
window.adminSync = async ({ max = 10, days = 30, dry = false } = {}) => {
  const J = u => fetch(u).then(r => r.ok ? r.json() : Promise.reject(new Error(u + ' ' + r.status)));
  if (!/admin\.reserve-viva-decolino\.com/.test(location.host)) return ['admin のページで実行してください'];
  const tpls = Object.fromEntries((await J('/api/ai-generations/templates')).items.map(t => [t.id, t.code]));
  const src = await siteApi({ action: 'sources' }); if (!src.ok) return ['管理サイトに接続できません ' + (src.error || src.status)];
  const have = new Set(src.items.map(x => String(x.asset || '')));
  // 2026-11-06 ユーザー指定：LINEで案を選んで確定したら、ほかの案は一覧から消える。消えた案を取り込み直さないよう、
  // 同じ注文・名前で確定（確認OK・入稿済み・完了）した案件があれば、その注文・名前の案は取り込まない
  const picked = new Set(src.items.filter(x => /確認OK|入稿済み|完了/.test(String(x.status || ''))).map(x => String(x.order) + '|' + String(x.name || '').replace(/（案\d+）$/, '')));
  const since = Date.now() - days * 864e5;
  const orders = (await J('/api/orders?limit=100')).items.filter(o => !o.canceledAt && o.orderKind === 'original_champagne'
    && !/complete|delivered|cancel|closed/.test(String(o.status)) && Date.parse(o.placedAt || o.createdAt) > since
    && !/テスト|test/i.test([o.customerName, o.customerCompanyName].join(' '))); // テスト注文は対象外
  const res = []; let done = 0;
  for (const o of orders) {
    if (done >= max) break;
    let gens; try { gens = (await J('/api/ai-generations?orderId=' + o.id)).items || []; } catch (e) { continue; }
    gens = gens.filter(g => g.status === 'generated'); if (!gens.length) continue;
    const od = await J('/api/orders/' + o.id);
    const latest = {}; // 中身（orderContent）ごとに最新の生成
    gens.forEach(g => { const k = String(g.orderContentId); if (!latest[k] || Date.parse(g.requestedAt) > Date.parse(latest[k].requestedAt)) latest[k] = g; });
    for (const [cid, g] of Object.entries(latest)) {
      if (done >= max) break;
      const c = (od.contents || []).find(x => String(x.id) === cid) || (od.contents || [])[0] || {};
      if (c.canceledAt) continue;
      const cands = ((await J('/api/ai-generations/' + g.id + '/candidates')).items || []).filter(x => x.imageUrl);
      for (const cd of cands) {
        if (done >= max) break;
        const asset = 'adm-' + cd.id; if (have.has(asset) || ADMIN_SKIP.has(cd.id)) continue;
        const tcode = tpls[cd.aiTemplateId] || (c.customerDesign && c.customerDesign.templateCode) || '';
        const label = String((c.lettering && !c.lettering.noText && c.lettering.label) || od.customerCompanyName || od.customerName || '').replace(/\s*\n\s*/g, ' ').trim();
        const base = label + ((od.contents || []).length > 1 ? '（' + c.branchNo + '）' : '');
        if (picked.has(String(o.displayOrderNumber) + '|' + base)) continue;
        const name = (base + (cands.length > 1 ? '（案' + cd.candidateNo + '）' : '')).slice(0, 80);
        const spec = adminSpec(c);
        if (dry) { res.push([o.displayOrderNumber, name, tcode, JSON.stringify(spec), cd.status].join(' ')); continue; }
        const mat = (c.materialImages || []).find(m => m.previewUrl);
        const asana = (od.asanaTasks || [])[0];
        let r;
        try {
          r = await registerToSite({ webappUrl: __W, key: __K, assetPath: cd.imageUrl, asset, confirmed: asset,
            order: o.displayOrderNumber, shop: od.customerCompanyName || od.customerName || '', name, template: tcode,
            due: c.shippingDueDate || '', asana: asana ? 'https://app.asana.com/0/0/' + asana.asanaGid : '',
            decolino: location.origin + '/ai/' + o.id + '/generate', memo: '管理画面のAI生成から自動で登録（' + (cd.status || '') + '）',
            spec, checks: [], srcUrl: mat && mat.previewUrl, tplUrl: cd.aiTemplateId ? '/api/ai-generations/templates/' + cd.aiTemplateId + '/image' : '',
            note: '管理画面のAI生成の新しい案', fileBase: (o.displayOrderNumber + '_' + name + '_' + tcode).replace(/[\\/:*?"<>|#]/g, '') });
        } catch (e) { r = { ok: false, error: String(e && e.message || e) }; }
        res.push(o.displayOrderNumber + ' ' + name + '（' + tcode + '）：' + (r.ok ? (r.unchanged ? '変更なし' : r.updated ? 'v' + r.version + ' に更新' : '登録') : '失敗 ' + (r.error || r.status)));
        have.add(asset); done++;
      }
    }
  }
  return res.length ? res : ['新しい生成案なし'];
};
'admin loaded';
