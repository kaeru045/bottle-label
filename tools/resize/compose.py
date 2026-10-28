#!/usr/bin/env python3
"""提出用フォーマット（このリポジトリの index.html）をヘッドレスブラウザで動かし、提出用 JPG・プレビュー・タグ画像を作る。
管理サイトの自動登録（registerToSite）と同じ手順：デザイン画像を入れる → 仕様のラジオを押す → チェックを入れる → 書き出す。

  python3 compose.py DESIGN.jpg --spec '{"tag":"heart","seal":"sl_lx_white"}' [--checks '["decoNeck"]'] --out DIR [--html ../../index.html]

出力：DIR/submission.jpg、DIR/submission_preview.jpg（長辺1100）、DIR/tag.png（タグがあるとき）、DIR/compose.json
"""
import argparse, asyncio, base64, json, os, sys
from playwright.async_api import async_playwright

ap = argparse.ArgumentParser()
ap.add_argument('design'); ap.add_argument('--spec', default='{}'); ap.add_argument('--checks', default='[]'); ap.add_argument('--out', required=True)
ap.add_argument('--html', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'index.html'))
a = ap.parse_args()
spec, checks = json.loads(a.spec), json.loads(a.checks)
os.makedirs(a.out, exist_ok=True)

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={'width': 1400, 'height': 1000})
        errs = []; pg.on('pageerror', lambda e: errs.append(str(e)))
        await pg.goto('file://' + os.path.abspath(a.html)); await pg.wait_for_timeout(2500)
        await pg.set_input_files('#fileDesign', a.design); await pg.wait_for_timeout(2500)
        for n, v in spec.items():
            loc = pg.locator(f'input[name="{n}"][value="{v}"]')
            if not await loc.count():
                sys.exit(f'仕様なし {n}={v}')
            await loc.first.evaluate('el => el.click()'); await pg.wait_for_timeout(500)
        for i in checks:
            await pg.evaluate("id => { const el = document.getElementById(id); if (el && !el.checked) el.click(); }", i); await pg.wait_for_timeout(300)
        await pg.wait_for_timeout(2000)
        if 'サンプル表示中' in await pg.inner_text('#badge'):
            sys.exit('デザインが反映されませんでした')
        res = await pg.evaluate("""async () => {
          const out = document.getElementById('out');
          const shrink = (src, max) => { const k = Math.min(1, max / Math.max(src.width, src.height)); const c = document.createElement('canvas');
            c.width = Math.round(src.width * k); c.height = Math.round(src.height * k); c.getContext('2d').drawImage(src, 0, 0, c.width, c.height); return c; };
          const url = (c, t, q) => c.toDataURL(t, q).split(',')[1];
          const tc = window.__buildTagCanvas && window.__buildTagCanvas(), tk = (document.querySelector('input[name=tag]:checked') || {}).value;
          return { submission: url(out, 'image/jpeg', 0.92), subPrev: url(shrink(out, 1100), 'image/jpeg', 0.82),
            tag: tc ? url(tc, 'image/png') : null, tagName: tc ? ((window.__TAGNAME || {})[tk] || tk) : null };
        }""")
        for k, fn in [('submission', 'submission.jpg'), ('subPrev', 'submission_preview.jpg'), ('tag', 'tag.png')]:
            if res.get(k):
                open(os.path.join(a.out, fn), 'wb').write(base64.b64decode(res[k]))
        info = {'tagName': res.get('tagName'), 'errors': errs}
        json.dump(info, open(os.path.join(a.out, 'compose.json'), 'w'), ensure_ascii=False)
        print(json.dumps(info, ensure_ascii=False))
        await b.close()

asyncio.run(main())
