#!/usr/bin/env python3
"""デザイン画像（2880×2048）に文字を入れる。文字は書体で描く（AIに描かせないので綴りが崩れない）。

  python3 textlayer.py DESIGN.jpg OUT.jpg --text 'Happy|Birthday' --style pirate --cx 640 --cy 700 [--width 700] [--rotate -6]

--text   … 「|」で改行
--style  … 下の STYLES のどれか（背景に合わせて選ぶ）
--cx/--cy… 文字のまとまりの中心（2880×2048 の座標）。省略すると「人物の下」（基本の位置）：
            placement.json の大事な範囲の中央の真下、白い範囲の下端（y 1834）にそろえる
--placement … place.py の出力先（placement.json）。省略時はデザイン画像と同じフォルダ
--width  … 文字のまとまりの横幅（px）。この幅に収まるよう自動で大きさを決める
--rotate … 傾き（度）
--color1/--color2 … 色を上書き（背景から拾った色を使うとき）
書体は fonts/（tools/resize/fonts、なければ npm の @fontsource から取得）を使う。
"""
import argparse, asyncio, base64, json, os, subprocess, sys, glob
import cv2, numpy as np
from playwright.async_api import async_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
FONTDIR = os.environ.get('RESIZE_FONTS', os.path.join(HERE, 'fonts'))
W, H = 2880, 2048
SAFE = (268, 508, 2612, 1834)

# 書体（@fontsource のパッケージ名）
FONTS = {'pirata': 'pirata-one', 'vibes': 'great-vibes', 'bangers': 'bangers', 'dancing': 'dancing-script',
         'cinzel': 'cinzel-decorative', 'mochiy': 'mochiy-pop-one', 'zenantique': 'zen-antique', 'yuji': 'yuji-syuku'}

# 飾り方。fill は CSS の背景（文字の形で切り抜く）、stroke は縁取り、shadow は影・光
STYLES = {
    'pirate': dict(font='pirata', weight=400, fill='linear-gradient(180deg,#fff6c8 0%,#ffd75a 38%,#d49a1c 62%,#7a4a0c 100%)',
                   stroke='#3b2108', strokew=0.055, shadow='drop-shadow(0 .06em 0 #2a1605) drop-shadow(0 .12em .18em rgba(0,0,0,.55))', spacing='0.02em', line=0.95),
    'script': dict(font='vibes', weight=400, fill='linear-gradient(180deg,#ffffff,#fff4e0)', stroke='', strokew=0,
                   shadow='drop-shadow(0 0 .04em rgba(150,20,20,.95)) drop-shadow(0 .05em .06em rgba(120,15,15,.9)) drop-shadow(0 .12em .3em rgba(0,0,0,.45))', spacing='0', line=0.9),
    'pop': dict(font='bangers', weight=400, fill='linear-gradient(180deg,#ff5a3c,#d7191c 60%,#a80d14)', stroke='#ffffff', strokew=0.11,
                shadow='drop-shadow(.05em .07em 0 #13233f) drop-shadow(0 .1em .2em rgba(0,0,0,.45))', spacing='0.04em', line=0.92),
    'gold': dict(font='cinzel', weight=700, fill='linear-gradient(180deg,#fffbe6 0%,#f3d27a 35%,#b9892c 60%,#fff0b8 80%,#a87a26 100%)', stroke='', strokew=0,
                 shadow='drop-shadow(0 .04em .02em rgba(60,30,0,.8)) drop-shadow(0 0 .25em rgba(255,220,140,.6))', spacing='0.03em', line=1.0),
    'elegant': dict(font='dancing', weight=700, fill='linear-gradient(180deg,#ffffff,#ffe3ec)', stroke='', strokew=0,
                    shadow='drop-shadow(0 0 .1em rgba(255,150,190,.95)) drop-shadow(0 .06em .2em rgba(80,0,40,.6))', spacing='0', line=0.95),
}


def font_file(key, weight):
    name = FONTS[key]
    os.makedirs(FONTDIR, exist_ok=True)
    pat = os.path.join(FONTDIR, f'{name}-latin-{weight}-normal.woff2')
    if not os.path.exists(pat):  # npm から取る
        subprocess.run(['npm', 'pack', f'@fontsource/{name}', '--silent'], cwd=FONTDIR, check=True, capture_output=True)
        tgz = sorted(glob.glob(os.path.join(FONTDIR, f'fontsource-{name}-*.tgz')))[-1]
        subprocess.run(['tar', '-xzf', tgz, '-C', FONTDIR, f'package/files/{name}-latin-{weight}-normal.woff2'], check=True)
        os.rename(os.path.join(FONTDIR, 'package', 'files', f'{name}-latin-{weight}-normal.woff2'), pat)
    return pat


async def render(text, st, width, rotate, c1, c2):
    ff = base64.b64encode(open(font_file(st['font'], st['weight']), 'rb').read()).decode()
    fill = st['fill'] if not c1 else f'linear-gradient(180deg,{c1},{c2 or c1})'
    import html as _h
    # 1行＝縁取りの層（下）と色の層（上）を同じ位置に重ねる
    lines = ''.join(f'<div class="l">' + (f'<span class="s">{_h.escape(l)}</span>' if st['strokew'] else '') + f'<span class="f">{_h.escape(l)}</span></div>'
                    for l in text.split('|'))
    html = f"""<html><head><style>
    @font-face{{font-family:F;src:url(data:font/woff2;base64,{ff}) format('woff2');font-weight:{st['weight']}}}
    html,body{{margin:0;background:transparent}}
    #w{{position:absolute;left:0;top:0;display:inline-block;padding:.35em .45em;transform-origin:center}}
    .t{{font-family:F;font-weight:{st['weight']};font-size:200px;line-height:{st['line']};letter-spacing:{st['spacing']};text-align:center;white-space:nowrap;filter:{st['shadow']}}}
    .l{{display:grid;justify-items:center}} .l>span{{grid-area:1/1;padding:.35em .5em;margin:-.35em -.5em}}
    .s{{color:{st['stroke'] or 'transparent'};-webkit-text-stroke:{st['strokew'] * 2}em {st['stroke'] or 'transparent'}}}
    .f{{background:{fill};-webkit-background-clip:text;background-clip:text;color:transparent}}
    </style></head><body><div id="w"><div class="t">{lines}</div></div></body></html>"""
    async with async_playwright() as p:
        b = await p.chromium.launch(); pg = await b.new_page(viewport={'width': 4000, 'height': 3000})
        await pg.set_content(html); await pg.evaluate('document.fonts.ready')
        bw = await pg.evaluate("document.getElementById('w').getBoundingClientRect().width")
        k = width / bw
        await pg.evaluate(f"document.querySelector('.t').style.fontSize = '{200 * k}px'")
        await pg.evaluate(f"document.getElementById('w').style.transform = 'rotate({rotate}deg)'")
        r = await pg.evaluate("(() => { const r = document.getElementById('w').getBoundingClientRect(); return [r.left, r.top, r.width, r.height]; })()")
        pad = 200
        await pg.evaluate(f"document.getElementById('w').style.left = '{pad - r[0]}px'; document.getElementById('w').style.top = '{pad - r[1]}px'")
        png = await pg.screenshot(omit_background=True, clip={'x': 0, 'y': 0, 'width': r[2] + 2 * pad, 'height': r[3] + 2 * pad})
        await b.close()
    return cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_UNCHANGED)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('design'); ap.add_argument('out'); ap.add_argument('--text', required=True); ap.add_argument('--style', choices=list(STYLES), required=True)
    ap.add_argument('--cx', type=float); ap.add_argument('--cy', type=float); ap.add_argument('--placement', default='')
    ap.add_argument('--width', type=float, default=700); ap.add_argument('--rotate', type=float, default=0)
    ap.add_argument('--color1', default=''); ap.add_argument('--color2', default='')
    a = ap.parse_args()
    im = cv2.imread(a.design); assert im is not None and im.shape[1] == W, 'デザイン画像は 2880×2048'
    t = asyncio.run(render(a.text, STYLES[a.style], a.width, a.rotate, a.color1, a.color2))
    th, tw = t.shape[:2]
    if a.cx is None or a.cy is None:  # 基本：人物の下
        al0 = t[:, :, 3] > 40; ys0, xs0 = np.nonzero(al0)
        pj = os.path.join(a.placement or os.path.dirname(os.path.abspath(a.design)), 'placement.json')
        bx0 = json.load(open(pj))['box'] if os.path.exists(pj) else [SAFE[0], SAFE[1], SAFE[2], SAFE[1]]
        vw = xs0.max() - xs0.min()
        cx = min(max((bx0[0] + bx0[2]) / 2, SAFE[0] + vw / 2 + 20), SAFE[2] - vw / 2 - 20)
        a.cx = cx - ((xs0.min() + xs0.max()) / 2 - tw / 2) if a.cx is None else a.cx
        a.cy = (SAFE[3] - 30 - ys0.max()) + th / 2 if a.cy is None else a.cy
    x0, y0 = int(round(a.cx - tw / 2)), int(round(a.cy - th / 2))
    # 文字の見える部分が白い範囲に入っているか
    al = t[:, :, 3] > 40; ys, xs = np.nonzero(al)
    bx = [x0 + xs.min(), y0 + ys.min(), x0 + xs.max(), y0 + ys.max()]
    ng = bx[0] < SAFE[0] or bx[1] < SAFE[1] or bx[2] > SAFE[2] or bx[3] > SAFE[3]
    out = im.astype(np.float32)
    sx0, sy0, sx1, sy1 = max(0, x0), max(0, y0), min(W, x0 + tw), min(H, y0 + th)
    sub = t[sy0 - y0:sy1 - y0, sx0 - x0:sx1 - x0].astype(np.float32)
    a_ = sub[:, :, 3:4] / 255
    out[sy0:sy1, sx0:sx1] = out[sy0:sy1, sx0:sx1] * (1 - a_) + sub[:, :, :3] * a_
    cv2.imwrite(a.out, np.clip(out, 0, 255).astype(np.uint8), [cv2.IMWRITE_JPEG_QUALITY, 95])
    print(json.dumps({'out': a.out, 'text_box': [int(v) for v in bx], 'outside_safe': bool(ng)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
