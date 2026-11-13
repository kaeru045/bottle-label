#!/usr/bin/env python3
"""提出用フォーマット（このリポジトリの index.html）をヘッドレスブラウザで動かし、提出用 JPG・プレビュー・タグ画像を作る。
管理サイトの自動登録（registerToSite）と同じ手順：デザイン画像を入れる → 仕様のラジオを押す → チェックを入れる → 書き出す。

  python3 compose.py DESIGN.jpg --spec '{"tag":"heart","seal":"sl_lx_white"}' [--checks '["decoNeck"]'] [--back '酒を飲むなら、|粋に飲め'] --out DIR [--html ../../index.html]

出力：DIR/submission.jpg、DIR/submission_preview.jpg（長辺1100）、DIR/tag.png（タグがあるとき）、DIR/compose.json
--back（Asanaの「裏：〇〇」の文字。一字も変えない。「|」で改行）があると、提出用の裏（ロゴの位置）に文字を入れ、
--back-opt '{"dir":"v|h|r|auto","font":"<書体キー>","color1":"#..","color2":"#..","stroke":"#.."}'（省略可。色を省くとデザインの色から自動、書体キーは提出用ツールの BACKFONTS）。
同じ文字が入ったデザイン画像を DIR/design_back.jpg に書く（register.py はこれがあれば design.jpg の代わりに送る）。
--tag-adj '{"x":0,"y":0,"z":50,"r":270}' … タグ内の画像の位置（提出用ツールの「タグ内の画像の位置」と同じ：x 左右・y 上下 -50〜50〈＋で右・上〉、z 大きさ% 10〜150〈50＝枠をちょうど覆う〉、r 回転 0／90／180／270〈「タグ画像は横で」＝横長のデザインを横向きのまま入れる→270〉）。
  修正依頼「タグに人物が収まるように」などで使う。DIR/tag.png を見て人物（頭〜体）がタグの形に入るよう x・z を決める。
"""
import argparse, asyncio, base64, json, os, sys
from playwright.async_api import async_playwright

ap = argparse.ArgumentParser()
ap.add_argument('design'); ap.add_argument('--spec', default='{}'); ap.add_argument('--checks', default='[]'); ap.add_argument('--back', default=''); ap.add_argument('--back-opt', default='{}'); ap.add_argument('--out', required=True)
ap.add_argument('--task', default='', help='Asanaのタスク {"name":..,"field":仕様欄,"notes":説明}。あれば spec_rules.py でリボン・デコ・タグなどの足りないオプションを足す（2026-11-13）')
ap.add_argument('--tag-adj', default='', help='タグ内の画像の位置 {"x":左右,"y":上下,"z":大きさ%%}')
ap.add_argument('--html', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'index.html'))
a = ap.parse_args()
spec, checks = json.loads(a.spec), json.loads(a.checks)
why = []
if a.task.strip():
    from spec_rules import derive
    _t = json.loads(a.task); spec, checks, why = derive(_t.get('name', ''), _t.get('field', ''), _t.get('notes', ''), spec, checks)
os.makedirs(a.out, exist_ok=True)

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={'width': 1400, 'height': 1000})
        errs = []; pg.on('pageerror', lambda e: errs.append(str(e)))
        # 裏の文字の書体（@fontsource を jsdelivr から読む）は、手元の npm パッケージから返す（クラウドから jsdelivr に出られないため）
        async def fonts(route):
            import re as _re
            from textlayer import _pkg
            m = _re.match(r'https://cdn\.jsdelivr\.net/npm/@fontsource/([^@/]+)@[^/]+/(.+)$', route.request.url)
            try:
                fp = os.path.join(_pkg(m.group(1)), m.group(2)) if m else ''
                if fp and os.path.exists(fp):
                    ct = 'text/css' if fp.endswith('.css') else 'font/woff2' if fp.endswith('.woff2') else 'font/woff'
                    return await route.fulfill(status=200, body=open(fp, 'rb').read(), headers={'Content-Type': ct, 'Access-Control-Allow-Origin': '*'})
            except Exception as e:
                errs.append('font ' + str(e))
            await route.fulfill(status=404, body='')
        await pg.route('https://cdn.jsdelivr.net/npm/@fontsource/**', fonts)
        await pg.goto('file://' + os.path.abspath(a.html)); await pg.wait_for_timeout(2500)
        await pg.set_input_files('#fileDesign', a.design); await pg.wait_for_timeout(2500)
        for n, v in spec.items():
            loc = pg.locator(f'input[name="{n}"][value="{v}"]')
            if not await loc.count():
                sys.exit(f'仕様なし {n}={v}')
            await loc.first.evaluate('el => el.click()'); await pg.wait_for_timeout(500)
        for i in checks:
            await pg.evaluate("id => { const el = document.getElementById(id); if (el && !el.checked) el.click(); }", i); await pg.wait_for_timeout(300)
        if a.tag_adj.strip():
            t = json.loads(a.tag_adj)
            ok = await pg.evaluate("""t => { const k = (document.querySelector('input[name=tag]:checked') || {}).value, el = document.getElementById('tagAdj');
              if (!k || !el || el.hidden) return false;
              const set = (id, v) => { if (v === undefined) return; const e = document.getElementById(id); e.value = v; e.dispatchEvent(new Event('input')); };
              set('tx', t.x); set('ty', t.y); set('tz', t.z);
              const n = {0: 0, 270: 1, 180: 2, 90: 3}[((t.r || 0) % 360 + 360) % 360] || 0; // r：回転（90／270＝横向き）。ボタン1回で270°
              for (let i = 0; i < n; i++) document.getElementById('tagRot').click(); return true; }""", t)
            if not ok:
                sys.exit('--tag-adj：タグが選ばれていないか、位置を変えられないタグです')
            await pg.wait_for_timeout(1500)
        back = None
        if a.back.strip():
            back = await pg.evaluate("([t, o]) => window.__setBackText(t, o)", [a.back.strip(), json.loads(a.back_opt or '{}')]); await pg.wait_for_timeout(2500)
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
            tag: tc ? url(tc, 'image/png') : null, tagName: tc ? ((window.__TAGNAME || {})[tk] || tk) : null,
            design: document.getElementById('useLogo').checked && window.__designJpeg ? window.__designJpeg(0.95) : null };
        }""")
        bp = os.path.join(a.out, 'design_back.jpg')
        if os.path.exists(bp): os.remove(bp)
        if not back: res['design'] = None
        for k, fn in [('submission', 'submission.jpg'), ('subPrev', 'submission_preview.jpg'), ('tag', 'tag.png'), ('design', 'design_back.jpg')]:
            if res.get(k):
                open(os.path.join(a.out, fn), 'wb').write(base64.b64decode(res[k]))
        info = {'tagName': res.get('tagName'), 'back': back, 'errors': errs, 'spec': spec, 'checks': checks, 'specWhy': why}
        json.dump(info, open(os.path.join(a.out, 'compose.json'), 'w'), ensure_ascii=False)
        print(json.dumps(info, ensure_ascii=False))
        await b.close()

asyncio.run(main())
