// Decolino 定期実行（オリシャン修正版の自動反映）のチェック処理。Decolino のタブで読み込む。
// 管理サイトのURL（window.__W）と合言葉（window.__K）は定期実行の指示文の側で先に入れる（ここには書かない）。
if (!window.__W || !window.__K) throw new Error('__W / __K が未設定');
window.siteApi = async body => { const r = await fetch(__W, { method: 'POST', headers: { 'Content-Type': 'text/plain;charset=utf-8' }, body: JSON.stringify(Object.assign({ key: __K }, body)) }); const t = await r.text(); try { return JSON.parse(t); } catch (e) { return { ok: false, status: r.status, body: t.slice(0, 200) }; } };
window.confirmedAsset = async decolinoUrl => {
  const path = new URL(decolinoUrl).pathname.replace(/\/(order|generate|refine|export)$/, '');
  const h = await fetch(path + '/export').then(r => r.text());
  const doc = new DOMParser().parseFromString(h, 'text/html');
  const imgs = [...doc.querySelectorAll('img')].filter(i => /\/api\/assets\//.test(i.getAttribute('src') || '') && (i.alt || '').trim() && !/\.(png|jpe?g|webp|heic)$/i.test(i.alt));
  return imgs.length ? { asset: imgs[0].getAttribute('src').split('/').pop(), label: imgs[0].alt } : null;
};
// 店のロゴ（宝石箱など）を決まった位置に銀色で入れる。ロゴは管理サイト側に保存（公開ページには置かない）
window.addLogo = async (canvas, key) => {
  const r = await siteApi({ action: 'logo', logo: key }); if (!r.ok) throw new Error('ロゴ取得失敗 ' + (r.error || r.status));
  const bm = await createImageBitmap(await (await fetch('data:image/png;base64,' + r.data)).blob());
  const W = canvas.width, H = canvas.height, R = [0.4197, 0.8270, 0.5736, 0.9284];
  const lw = Math.round((R[2] - R[0]) * W), lh = Math.round(lw * bm.height / bm.width);
  const m = new OffscreenCanvas(lw, lh), mx = m.getContext('2d'); mx.drawImage(bm, 0, 0, lw, lh);
  const id = mx.getImageData(0, 0, lw, lh), p = id.data;
  for (let y = 0; y < lh; y++) { const c = Math.round(250 - 45 * Math.abs(((y / lh) * 2) % 2 - 1)); for (let x = 0; x < lw; x++) { const i = (y * lw + x) * 4, a = p[i]; p[i] = c; p[i + 1] = c; p[i + 2] = Math.min(255, c + 4); p[i + 3] = a; } }
  mx.putImageData(id, 0, 0);
  const ctx = canvas.getContext('2d'); ctx.save(); ctx.shadowColor = 'rgba(60,40,40,0.7)'; ctx.shadowBlur = lw * 0.02; ctx.shadowOffsetX = ctx.shadowOffsetY = lw * 0.006;
  ctx.drawImage(m, Math.round(R[0] * W), Math.round(R[1] * H)); ctx.restore();
};
// 選んだテンプレートの見本画像（比較用）
window.tplFor = async (decolino, template) => {
  const p = new URL(decolino, location.origin).pathname.replace(/\/(order|generate|refine|export)$/, '');
  const h = await fetch(p + '/generate').then(r => r.text()); const d = new DOMParser().parseFromString(h, 'text/html');
  const m = String(template).match(/([A-Za-z]+)\s*-?\s*(\d+)/); if (!m) return null; const L = m[1].toUpperCase(), n = String(Number(m[2]));
  const cands = [L + '-' + n, L + '-' + n.padStart(2, '0'), L + '-' + n.padStart(3, '0')];
  const img = [...d.querySelectorAll('img')].find(i => /api\/assets/.test(i.getAttribute('src') || '') && cands.includes((i.alt || '').trim().toUpperCase()));
  return img ? img.getAttribute('src') : null;
};
window.tplJpeg = async src => { const bm = await createImageBitmap(await fetch(src).then(r => r.blob())); const k = Math.min(1, 1000 / Math.max(bm.width, bm.height)); const c = new OffscreenCanvas(Math.round(bm.width * k), Math.round(bm.height * k)); c.getContext('2d').drawImage(bm, 0, 0, c.width, c.height); const b = await c.convertToBlob({ type: 'image/jpeg', quality: 0.85 }); const u = new Uint8Array(await b.arrayBuffer()); let s = ''; for (let i = 0; i < u.length; i += 32768) s += String.fromCharCode.apply(null, u.subarray(i, i + 32768)); return btoa(s); };
window.registerToSite = async function (o) {
  const wait = ms => new Promise(r => setTimeout(r, ms));
  const b64 = async blob => { const u = new Uint8Array(await blob.arrayBuffer()); let s = ''; for (let i = 0; i < u.length; i += 32768) s += String.fromCharCode.apply(null, u.subarray(i, i + 32768)); return btoa(s); };
  const shrink = async (blob, max) => { const bm = await createImageBitmap(blob); const k = Math.min(1, max / Math.max(bm.width, bm.height)); const c = new OffscreenCanvas(Math.round(bm.width * k), Math.round(bm.height * k)); c.getContext('2d').drawImage(bm, 0, 0, c.width, c.height); return c.convertToBlob({ type: 'image/jpeg', quality: 0.82 }); };
  const raw = await fetch(o.assetPath).then(r => { if (!r.ok) throw new Error('画像取得失敗 ' + r.status); return r.blob(); });
  const bm = await createImageBitmap(raw); const c = new OffscreenCanvas(bm.width, bm.height); c.getContext('2d').drawImage(bm, 0, 0);
  if (o.logo) await addLogo(c, o.logo);
  const design = await c.convertToBlob({ type: 'image/jpeg', quality: 0.95 });
  const html = window.__bl || (window.__bl = await fetch('https://kaeru045.github.io/bottle-label/').then(r => r.text()));
  const fr = document.createElement('iframe'); fr.style.cssText = 'position:fixed;left:-3000px;top:0;width:1400px;height:1000px'; document.body.appendChild(fr);
  try {
    await new Promise(ok => { fr.onload = ok; fr.srcdoc = html.replace(/<head[^>]*>/i, m => m + '<script>window.requestAnimationFrame=cb=>setTimeout(()=>cb(performance.now()),16);<\/script>'); });
    const w = fr.contentWindow, d = fr.contentDocument; await wait(2500);
    const dt = new w.DataTransfer(); dt.items.add(new w.File([design], 'design.jpg', { type: 'image/jpeg' }));
    const inp = d.getElementById('fileDesign'); inp.files = dt.files; inp.dispatchEvent(new w.Event('change', { bubbles: true }));
    await wait(2500);
    for (const [n, v] of Object.entries(o.spec || {})) { const r = d.querySelector(`input[name=${n}][value="${v}"]`); if (!r) throw new Error('仕様なし ' + n + '=' + v); r.click(); await wait(500); }
    for (const id of (o.checks || [])) { const el = d.getElementById(id); if (el && !el.checked) el.click(); await wait(300); }
    if (o.back) { if (!w.__setBackText) throw new Error('提出用ツールが古い（裏の文字なし）'); w.__setBackText(o.back); await wait(2500); }
    await wait(2000);
    if (/サンプル表示中/.test(d.body.innerText)) throw new Error('デザイン未反映');
    const submission = await new Promise(r => d.getElementById('out').toBlob(r, 'image/jpeg', 0.92));
    const dOut = o.back ? await (await fetch('data:image/jpeg;base64,' + w.__designJpeg(0.95))).blob() : design;
    const tc = w.__buildTagCanvas && w.__buildTagCanvas(), tk = (d.querySelector('input[name=tag]:checked') || {}).value;
    const tagBlob = tc ? await new Promise(r => tc.toBlob(r, 'image/png')) : null;
    const body = JSON.stringify({ key: o.key, order: o.order, shop: o.shop, name: o.name, template: o.template, due: o.due, asana: o.asana, decolino: o.decolino, memo: o.memo || '',
      asset: o.asset || '', note: o.note || '', fixDone: !!o.fixDone, spec: { spec: o.spec || {}, checks: o.checks || [], shop: o.shop, template: o.template, confirmed: o.confirmed || o.asset || '', logo: o.logo || '', back: o.back || '' },
      design: { name: o.fileBase + 'デザイン画像.jpg', data: await b64(dOut) }, submission: { name: o.fileBase + '提出用.jpg', data: await b64(submission) },
      designPreview: { name: o.fileBase + 'デザイン_プレビュー.jpg', data: await b64(await shrink(dOut, 900)) }, submissionPreview: { name: o.fileBase + '提出用_プレビュー.jpg', data: await b64(await shrink(submission, 1100)) },
      tpl: await (async () => { try { const s = o.decolino && o.template && await tplFor(o.decolino, o.template); return s ? { name: o.fileBase + 'テンプレ.jpg', data: await tplJpeg(s) } : null; } catch (e) { return null; } })(),
      tag: tagBlob ? { name: o.fileBase + 'タグ_' + ((w.__TAGNAME || {})[tk] || tk) + '.png', data: await b64(tagBlob) } : null });
    const res = await fetch(o.webappUrl, { method: 'POST', headers: { 'Content-Type': 'text/plain;charset=utf-8' }, body });
    const t = await res.text(); try { return JSON.parse(t); } catch (e) { return { ok: false, status: res.status, body: t.slice(0, 200) }; }
  } finally { fr.remove(); }
};
window.checkUpdates = async ({ dry = false, max = 1 } = {}) => {
  const src = await siteApi({ action: 'sources' }); if (!src.ok) return src;
  const res = []; let done = 0;
  for (const it of src.items) {
    const tag = it.order + ' ' + it.name;
    if (!it.decolino) { res.push(tag + '：Decolinoリンクなし'); continue; }
    const c = await confirmedAsset(it.decolino);
    if (!c) { res.push(tag + '：Decolinoで未確定'); continue; }
    let sp = null; try { sp = JSON.parse(it.spec || 'null'); } catch (e) {}
    if (c.asset === ((sp && sp.confirmed) || it.asset)) { res.push(tag + '：変更なし'); continue; }
    if (!sp) { res.push(tag + '：仕様が未登録のためスキップ'); continue; }
    if (dry || done >= max) { res.push(tag + '：更新あり（未反映）'); continue; }
    const r = await registerToSite({ webappUrl: __W, key: __K, assetPath: '/api/assets/' + c.asset, asset: c.asset, order: it.order, name: it.name,
      shop: sp.shop, template: sp.template, spec: sp.spec, checks: sp.checks, logo: sp.logo || '', back: sp.back || (window.__backFor || {})[it.id] || '', confirmed: c.asset, note: 'Decolinoで確定した修正版',
      fileBase: (it.order + '_' + it.name + '_v' + (it.version + 1)).replace(/[\\/:*?"<>|#]/g, '') });
    res.push(tag + '：' + (r.ok ? 'v' + r.version + ' に更新' : '失敗 ' + (r.error || r.status))); done++;
  }
  return res;
};
window.setFix = async (order, fix, name) => siteApi({ action: 'setFix', order, name, fix });
window.listFixes = async () => { const r = await siteApi({ action: 'fixes' }); return r.ok ? r.items : r; };
window.__imgs = () => [...document.querySelectorAll('img')].filter(i => /\/api\/assets\//.test(i.src));
window.startFix = async id => {
  const it = (await listFixes()).find(x => x.id === id); if (!it) return '対象なし';
  if (!/\/generate$/.test(location.pathname)) return 'generateページではありません: ' + location.pathname;
  const ta = document.querySelector('textarea[placeholder^="もっと金箔"]') || [...document.querySelectorAll('textarea')].find(t => /要望|フィードバック/.test(t.closest('div,section')?.innerText || ''));
  const btn = [...document.querySelectorAll('button')].find(b => b.innerText.trim() === 'この内容で再生成する');
  if (!ta || !btn) { await siteApi({ action: 'fixState', id, state: 'エラー:Decolinoの入力欄が見つかりません' }); return '入力欄なし'; }
  const before = __imgs().map(i => i.src.split('/').pop());
  Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set.call(ta, it.fix);
  ta.dispatchEvent(new Event('input', { bubbles: true }));
  await new Promise(r => setTimeout(r, 600)); btn.click();
  await siteApi({ action: 'fixState', id, state: '生成中|' + Date.now() + '|' + before.join(',') });
  return '再生成を開始: ' + it.order + ' ' + it.name;
};
window.finishFix = async id => {
  const it = (await listFixes()).find(x => x.id === id); if (!it) return '対象なし';
  const [, at, bef] = String(it.state).split('|'); const before = (bef || '').split(',');
  for (let i = 0; i < 7 && /生成待機中|生成中/.test(document.body.innerText); i++) await new Promise(r => setTimeout(r, 5000));
  const fresh = __imgs().filter(i => /^案\d+$/.test((i.alt || '').trim()) && !before.includes(i.src.split('/').pop()));
  if (!fresh.length) {
    if (Date.now() - Number(at || 0) > 20 * 60 * 1000) { await siteApi({ action: 'fixState', id, state: 'エラー:20分たっても生成されませんでした' }); return 'タイムアウト'; }
    return 'まだ生成中';
  }
  const asset = fresh[0].src.split('/').pop();
  let sp = null; try { sp = JSON.parse(it.spec || 'null'); } catch (e) {}
  if (!sp) { await siteApi({ action: 'fixState', id, state: 'エラー:仕様が未登録です' }); return '仕様なし'; }
  const cf = await confirmedAsset(it.decolino);
  const r = await registerToSite({ webappUrl: __W, key: __K, assetPath: '/api/assets/' + asset, asset, order: it.order, name: it.name,
    shop: sp.shop, template: sp.template, spec: sp.spec, checks: sp.checks, logo: sp.logo || '', back: sp.back || (window.__backFor || {})[id] || '', confirmed: (cf && cf.asset) || 'none', fixDone: true,
    note: '修正指示「' + it.fix + '」で作り直し（Decolinoは未確定）',
    fileBase: (it.order + '_' + it.name + '_v' + (it.version + 1)).replace(/[\\/:*?"<>|#]/g, '') });
  if (!r.ok) await siteApi({ action: 'fixState', id, state: 'エラー:' + (r.error || r.status) });
  return r.ok ? 'v' + r.version + ' に更新' : '失敗 ' + (r.error || r.status);
};
window.decolinoHasTag = async tag => {
  const h = await fetch('/projects?q=' + encodeURIComponent(tag)).then(r => r.text());
  const d = new DOMParser().parseFromString(h, 'text/html');
  return [...d.querySelectorAll('a[href^="/projects/"]')].some(a => a.textContent.includes(tag));
};
// 大きすぎる写真（長辺3000px超・3.5MB超・HEICなど）はAIが受け付けないので、長辺3000pxのJPEGにする
window.fitPhoto = async b => {
  let bm; try { bm = await createImageBitmap(b); } catch (e) { return { blob: b, changed: false }; }
  if (b.size <= 3.5e6 && Math.max(bm.width, bm.height) <= 3000 && /jpe?g|png|webp/.test(b.type)) return { blob: b, changed: false };
  const k = Math.min(1, 3000 / Math.max(bm.width, bm.height)); const c = new OffscreenCanvas(Math.round(bm.width * k), Math.round(bm.height * k));
  c.getContext('2d').drawImage(bm, 0, 0, c.width, c.height); return { blob: await c.convertToBlob({ type: 'image/jpeg', quality: 0.9 }), changed: true };
};
// 「Invalid input image」で失敗した既存案件：/order ページで、保存済みの写真を縮小版に入れ替えて「保存して次へ」（/generate に移る）
window.fixPhotos = async () => {
  const wait = ms => new Promise(r => setTimeout(r, ms));
  if (!/\/order$/.test(location.pathname)) return { ok: false, error: '/order を開いてから実行してください' };
  for (let i = 0; i < 12 && !document.querySelector('input[type=file][name=files]'); i++) await wait(800);
  window.confirm = () => true;
  const dels = [...document.querySelectorAll('button')].filter(b => /を削除$/.test(b.getAttribute('aria-label') || ''));
  const dt = new DataTransfer(), drop = [];
  for (const d of dels) {
    const name = d.getAttribute('aria-label').replace(/を削除$/, '');
    const img = [...document.querySelectorAll('img')].find(i => (i.alt || '').trim() === name && /\/api\/assets\//.test(i.src)); if (!img) continue;
    const s = await fitPhoto(await fetch(img.src).then(r => r.blob()));
    if (s.changed) { dt.items.add(new File([s.blob], name.replace(/\.\w+$/, '') + '_s.jpg', { type: 'image/jpeg' })); drop.push(d); }
  }
  if (!dt.files.length) return { ok: false, error: '縮小が必要な写真なし' };
  const inp = document.querySelector('input[type=file][name=files]'); inp.files = dt.files; inp.dispatchEvent(new Event('change', { bubbles: true }));
  await wait(3000); for (const d of drop) { d.click(); await wait(1500); }
  [...document.querySelectorAll('button')].find(b => b.innerText.trim() === '保存して次へ').click();
  for (let i = 0; i < 25 && !/generate$/.test(location.pathname); i++) await wait(1000);
  return { ok: /generate$/.test(location.pathname), replaced: dt.files.length };
};
window.makeProject = async o => {
  const wait = ms => new Promise(r => setTimeout(r, ms));
  if (!/\/projects\/new$/.test(location.pathname)) return { ok: false, error: '/projects/new を開いてから実行してください' };
  for (let i = 0; i < 12 && !document.querySelector('#customerName'); i++) await wait(800);
  const setV = (el, v) => { const p = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : el.tagName === 'SELECT' ? HTMLSelectElement.prototype : HTMLInputElement.prototype; Object.getOwnPropertyDescriptor(p, 'value').set.call(el, v); el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); };
  const q = s => document.querySelector(s);
  setV(q('#customerName'), o.customer || 'オリシャン');
  const sel = q('select'), opts = [...sel.options].map(x => x.value);
  if (opts.includes(o.purpose) && o.purpose !== 'その他') setV(sel, o.purpose);
  else { setV(sel, 'その他'); await wait(300); const f = q('input[placeholder^="用途を入力"]'); if (f) setV(f, (o.purpose && o.purpose !== 'その他') ? o.purpose : 'オリシャン'); }
  setV(q('#title'), (o.title + ' ' + o.tag).slice(0, 120));
  setV(q('#orderedAt'), o.ordered); if (o.due) setV(q('#dueDate'), o.due);
  setV(q('#champagneName'), o.name || '');
  setV(q('#champagneRequiredTexts'), o.texts || 'なし');
  setV(q('#requestText'), o.request || '');
  await wait(500);
  [...document.querySelectorAll('button')].find(b => b.innerText.trim() === '案件を作成').click();
  for (let i = 0; i < 25 && /\/new$/.test(location.pathname); i++) await wait(1000);
  if (/\/new$/.test(location.pathname)) return { ok: false, error: '案件を作れませんでした：' + ((document.body.innerText.match(/[^\n]*(入力してください|エラー)[^\n]*/) || [''])[0]) };
  for (let i = 0; i < 12 && !q('input[type=file][name=files]'); i++) await wait(800);
  const dt = new DataTransfer();
  for (const p of (o.photos || [])) { const b = await fetch(p.url).then(r => r.blob()); const s = await fitPhoto(b); dt.items.add(new File([s.blob], s.changed ? (p.name || 'photo.jpg').replace(/\.\w+$/, '') + '_s.jpg' : (p.name || 'photo.jpg'), { type: s.blob.type || 'image/jpeg' })); }
  if (!dt.files.length) return { ok: false, project: location.href.replace(/\/order$/, ''), error: '写真がありません' };
  const inp = q('input[type=file][name=files]'); inp.files = dt.files; inp.dispatchEvent(new Event('change', { bubbles: true }));
  await wait(3000);
  const m = String(o.template).match(/([A-Za-z]+)\s*-?\s*(\d+)/); if (!m) return { ok: false, error: 'テンプレート番号が読めません' };
  const L = m[1].toUpperCase(), n = String(Number(m[2]));
  const cands = [L + '-' + n, L + '-' + n.padStart(2, '0'), L + '-' + n.padStart(3, '0')];
  const btns = [...document.querySelectorAll('button')].filter(b => /^テンプレート /.test(b.innerText.trim()));
  const tb = btns.find(b => cands.some(c => b.innerText.trim().split('\n')[0].trim().toUpperCase() === 'テンプレート ' + c));
  if (!tb) return { ok: false, project: location.href.replace(/\/order$/, ''), error: 'Decolinoにテンプレート ' + o.template + ' がありません' };
  tb.scrollIntoView(); tb.click(); await wait(1000);
  if (!/1件選択中/.test(document.body.innerText)) return { ok: false, error: 'テンプレートを選べませんでした' };
  [...document.querySelectorAll('button')].find(b => b.innerText.trim() === '保存して次へ').click();
  for (let i = 0; i < 20 && !/generate$/.test(location.pathname); i++) await wait(1000);
  return { ok: /generate$/.test(location.pathname), project: location.href.replace(/\/(order|generate)$/, ''), template: o.template };
};
window.waitResult = async () => {
  for (let i = 0; i < 7 && /生成待機中|生成中/.test(document.body.innerText); i++) await new Promise(r => setTimeout(r, 5000));
  const f = document.body.innerText.match(/生成に失敗[^\n]*/); if (f) return { state: 'failed', msg: f[0].slice(0, 80) };
  const img = [...document.querySelectorAll('img')].find(i => /\/api\/assets\//.test(i.src) && /^案\d+$/.test((i.alt || '').trim()));
  if (img) return { state: 'done', asset: img.src.split('/').pop() };
  return { state: 'generating' };
};
// 安全フィルターなどで失敗したとき、同じ内容で作り直す（n=2 のときは追加の要望に穏やかな指示を入れる）
window.retryGenerate = async n => {
  const ta = document.querySelector('textarea[placeholder^="もっと金箔"]');
  if (ta && n >= 2) { Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set.call(ta, '人物は写真の雰囲気のまま、上品で落ち着いた仕上がりに'); ta.dispatchEvent(new Event('input', { bubbles: true })); await new Promise(r => setTimeout(r, 600)); }
  const btn = [...document.querySelectorAll('button')].find(b => b.innerText.trim() === 'この内容で再生成する');
  if (!btn) return { ok: false, error: '再生成ボタンなし' };
  btn.click(); await new Promise(r => setTimeout(r, 2000)); return { ok: true };
};
'loaded';
