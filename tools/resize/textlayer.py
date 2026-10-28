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
import argparse, asyncio, base64, json, os, re, subprocess, sys, glob
import cv2, numpy as np
from playwright.async_api import async_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
FONTDIR = os.environ.get('RESIZE_FONTS', os.path.join(HERE, 'fonts'))
W, H = 2880, 2048
SAFE = (268, 508, 2612, 1834)

# 書体（@fontsource のパッケージ名）。jp＝日本語（ひらがな・カタカナ・漢字）も書ける
FONTS = {'pirata': 'pirata-one', 'vibes': 'great-vibes', 'bangers': 'bangers', 'dancing': 'dancing-script',
         'cinzel': 'cinzel-decorative', 'pacifico': 'pacifico', 'caveat': 'caveat', 'marker': 'permanent-marker',
         'lobster': 'lobster', 'fredoka': 'fredoka', 'fraktur': 'unifrakturmaguntia', 'rye': 'rye', 'luckiest': 'luckiest-guy',
         'playfair': 'playfair-display',
         'mochiy': 'mochiy-pop-one', 'zenantique': 'zen-antique', 'yuji': 'yuji-syuku', 'zenmaru': 'zen-maru-gothic',
         'hachimaru': 'hachi-maru-pop', 'dela': 'dela-gothic-one'}
JPFONTS = {'mochiy', 'zenantique', 'yuji', 'zenmaru', 'hachimaru', 'dela'}
# 小文字が無く、全部大文字に見えてしまう書体。依頼の文字は変えないので、小文字を含む文言には使わない
CAPSFONTS = {'bangers', 'cinzel', 'luckiest', 'marker'}


def changes_case(style, text):
    return STYLES[style]['font'] in CAPSFONTS and any(c.islower() for c in text)

G = lambda *c: 'linear-gradient(180deg,' + ','.join(c) + ')'
SH = lambda *d: ' '.join(f'drop-shadow({x})' for x in d)
# 飾り方。fill は文字の色（グラデーション）、stroke は縁取り（strokew は文字の大きさに対する太さ）、shadow は影・光
# jp＝日本語の名前（管理サイトに出る）、mood＝合う背景（定期実行が選ぶときの目安）
STYLES = {
    # 英字
    'pirate': dict(jp='海賊風', mood='海賊・冒険・宝・木・ヴィンテージ', font='pirata', weight=400, fill=G('#fff6c8 0%', '#ffd75a 38%', '#d49a1c 62%', '#7a4a0c 100%'),
                   stroke='#3b2108', strokew=0.055, shadow=SH('0 .06em 0 #2a1605', '0 .12em .18em rgba(0,0,0,.55)'), spacing='0.02em', line=0.95),
    'script': dict(jp='筆記体', mood='写真全般・上品・大人・空や海', font='vibes', weight=400, fill=G('#ffffff', '#fff4e0'), stroke='', strokew=0,
                   shadow=SH('0 0 .04em rgba(150,20,20,.95)', '0 .05em .06em rgba(120,15,15,.9)', '0 .12em .3em rgba(0,0,0,.45)'), spacing='0', line=0.9),
    'pop': dict(jp='ポップ', mood='子ども・元気・カラフル・アニメ風', font='bangers', weight=400, fill=G('#ff5a3c', '#d7191c 60%', '#a80d14'), stroke='#ffffff', strokew=0.11,
                shadow=SH('.05em .07em 0 #13233f', '0 .1em .2em rgba(0,0,0,.45)'), spacing='0.04em', line=0.92),
    'gold': dict(jp='ゴールド', mood='夜・ホスト・キャバ・高級・黒背景・周年', font='cinzel', weight=700, fill=G('#fffbe6 0%', '#f3d27a 35%', '#b9892c 60%', '#fff0b8 80%', '#a87a26 100%'), stroke='', strokew=0,
                 shadow=SH('0 .04em .02em rgba(60,30,0,.8)', '0 0 .25em rgba(255,220,140,.6)'), spacing='0.03em', line=1.0),
    'elegant': dict(jp='エレガント', mood='花・ピンク・女性・ウェディング', font='dancing', weight=700, fill=G('#ffffff', '#ffe3ec'), stroke='', strokew=0,
                    shadow=SH('0 0 .1em rgba(255,150,190,.95)', '0 .06em .2em rgba(80,0,40,.6)'), spacing='0', line=0.95),
    'neon': dict(jp='ネオン', mood='夜景・クラブ・ネオン・暗い背景・パーティー', font='pacifico', weight=400, fill=G('#ffffff', '#ffe6fb'), stroke='', strokew=0,
                 shadow=SH('0 0 .03em #fff', '0 0 .12em #ff3fd2', '0 0 .3em #ff2fb9', '0 0 .6em rgba(160,40,255,.8)'), spacing='0', line=1.0),
    'hand': dict(jp='手書き', mood='ナチュラル・カフェ・日常写真・やさしい', font='caveat', weight=700, fill=G('#ffffff', '#fdf6ea'), stroke='', strokew=0,
                 shadow=SH('0 .03em 0 rgba(60,40,20,.7)', '0 .08em .2em rgba(0,0,0,.45)'), spacing='0.01em', line=0.95),
    'street': dict(jp='ストリート', mood='ストリート・スポーツ・HIPHOP・コンクリート', font='marker', weight=400, fill=G('#fff36b', '#ffb400 60%', '#ff7a00'), stroke='#111111', strokew=0.07,
                   shadow=SH('.06em .06em 0 #111', '0 .1em .25em rgba(0,0,0,.5)'), spacing='0.02em', line=0.95),
    'retro': dict(jp='レトロ', mood='昭和・アメリカン・ダイナー・ヴィンテージ', font='lobster', weight=400, fill=G('#fff8e7', '#ffd9a0'), stroke='#b3261e', strokew=0.06,
                  shadow=SH('.07em .07em 0 #5a1410', '0 .12em .22em rgba(0,0,0,.4)'), spacing='0.01em', line=0.95),
    'cute': dict(jp='かわいい', mood='赤ちゃん・パステル・ゆめかわ・動物', font='fredoka', weight=700, fill=G('#ffb6d5', '#ff7fb0'), stroke='#ffffff', strokew=0.1,
                 shadow=SH('0 .05em 0 #f06aa0', '0 .1em .2em rgba(120,0,60,.35)'), spacing='0.02em', line=0.95),
    'gothic': dict(jp='ゴシック', mood='ダーク・ロック・ヴィジュアル系・教会・ハロウィン', font='fraktur', weight=400, fill=G('#ffffff', '#c9ccd3 50%', '#7c818c'), stroke='', strokew=0,
                   shadow=SH('0 .04em 0 #111', '0 0 .2em rgba(0,0,0,.9)', '0 0 .45em rgba(150,0,30,.6)'), spacing='0.01em', line=1.0),
    'western': dict(jp='ウエスタン', mood='西部劇・カウボーイ・砂漠・木目', font='rye', weight=400, fill=G('#fbe6b4', '#d9a55a 55%', '#9a5d22'), stroke='#3a1f0b', strokew=0.05,
                    shadow=SH('.05em .06em 0 #2a1508', '0 .1em .2em rgba(0,0,0,.5)'), spacing='0.03em', line=1.0),
    'comic': dict(jp='コミック', mood='漫画・ゲーム・ヒーロー・楽しい', font='luckiest', weight=400, fill=G('#fff45c', '#ffcc00'), stroke='#111111', strokew=0.09,
                  shadow=SH('.07em .08em 0 #e8390e', '.11em .12em 0 #111'), spacing='0.03em', line=0.95),
    'luxury': dict(jp='ラグジュアリー', mood='シャンパン・ホテル・黒×金・大人の高級感', font='playfair', weight=700, fill=G('#fffdf4', '#ead9a8 45%', '#b08d47'), stroke='', strokew=0,
                   shadow=SH('0 .03em 0 rgba(40,25,0,.85)', '0 .1em .25em rgba(0,0,0,.6)'), spacing='0.06em', line=1.0),
    # 日本語も書ける
    'jpop': dict(jp='和ポップ', mood='日本語・子ども・元気', font='mochiy', weight=400, fill=G('#ff7eb6', '#ff3d7f'), stroke='#ffffff', strokew=0.12,
                 shadow=SH('0 .05em 0 #c2185b', '0 .1em .2em rgba(0,0,0,.35)'), spacing='0.02em', line=1.1),
    'fude': dict(jp='筆文字', mood='日本語・和風・祭り・成人式・お正月', font='yuji', weight=400, fill=G('#1a1a1a', '#000000'), stroke='#ffffff', strokew=0.1,
                 shadow=SH('0 0 .15em rgba(255,255,255,.8)', '0 .08em .2em rgba(0,0,0,.4)'), spacing='0.02em', line=1.1),
    'wamodern': dict(jp='和モダン', mood='日本語・和柄・桜・着物・上品', font='zenantique', weight=400, fill=G('#fff6d8', '#e9c46a 50%', '#b07d2a'), stroke='#4a2a08', strokew=0.05,
                     shadow=SH('0 .05em 0 #2c1904', '0 .1em .2em rgba(0,0,0,.5)'), spacing='0.04em', line=1.1),
    'maru': dict(jp='丸ゴシック', mood='日本語・やさしい・ナチュラル・何にでも', font='zenmaru', weight=700, fill=G('#ffffff', '#fff7ef'), stroke='#ff8a3d', strokew=0.1,
                 shadow=SH('0 .05em 0 #c85a12', '0 .1em .2em rgba(0,0,0,.35)'), spacing='0.03em', line=1.1),
    'kawaii': dict(jp='手書きかわいい', mood='日本語・赤ちゃん・パステル・女の子', font='hachimaru', weight=400, fill=G('#ffffff', '#fff0f6'), stroke='#ff7fb0', strokew=0.12,
                   shadow=SH('0 .05em 0 #e0568f', '0 .1em .2em rgba(0,0,0,.3)'), spacing='0.02em', line=1.15),
    'gokubuto': dict(jp='極太', mood='日本語・インパクト・スポーツ・お祝い', font='dela', weight=400, fill=G('#ffe14d', '#ffb800'), stroke='#d7191c', strokew=0.1,
                     shadow=SH('.05em .06em 0 #7a0a0c', '0 .1em .2em rgba(0,0,0,.45)'), spacing='0.02em', line=1.1),
}


def _pkg(name):
    """@fontsource のパッケージを npm から取ってきて展開（fonts/pkg/<name>/ にためる）"""
    d = os.path.join(FONTDIR, 'pkg', name)
    if not os.path.exists(os.path.join(d, 'package.json')):
        os.makedirs(d, exist_ok=True)
        subprocess.run(['npm', 'pack', f'@fontsource/{name}', '--silent', '--pack-destination', d], check=True, capture_output=True)
        tgz = sorted(glob.glob(os.path.join(d, f'fontsource-{name}-*.tgz')))[-1]
        subprocess.run(['tar', '-xzf', tgz, '-C', d, '--strip-components=1'], check=True)
        os.remove(tgz)
    return d


def _ranges(ur):
    out = []
    for part in ur.split(','):
        part = part.strip().replace('U+', '')
        if not part: continue
        if '-' in part: a, b = part.split('-'); out.append((int(a, 16), int(b, 16)))
        elif '?' in part: out.append((int(part.replace('?', '0'), 16), int(part.replace('?', 'F'), 16)))
        else: v = int(part, 16); out.append((v, v))
    return out


def font_css(key, weight, text):
    """文字に必要な分だけの @font-face（データを埋め込み）。英字だけの書体で使えない文字があれば止める"""
    name = FONTS[key]
    latin = os.path.join(FONTDIR, f'{name}-latin-{weight}-normal.woff2')
    chars = {ord(c) for c in text if not c.isspace() and c != '|'}
    if all(c < 0x250 or 0x2000 <= c <= 0x206F for c in chars) and os.path.exists(latin):  # 英字だけならリポジトリの書体で足りる
        return f"@font-face{{font-family:F;src:url(data:font/woff2;base64,{base64.b64encode(open(latin, 'rb').read()).decode()}) format('woff2');font-weight:{weight}}}"
    d = _pkg(name); css = open(os.path.join(d, f'{weight}.css')).read()
    out, covered = [], set()
    for m in re.finditer(r'@font-face\s*{([^}]*)}', css):
        body = m.group(1); f = re.search(r"url\(\./files/([^)]+\.woff2)\)", body); u = re.search(r'unicode-range:\s*([^;]+);', body)
        if not f or not u: continue
        rg = _ranges(u.group(1)); need = {c for c in chars if any(a <= c <= b for a, b in rg)}
        if not need: continue
        covered |= need
        data = base64.b64encode(open(os.path.join(d, 'files', f.group(1)), 'rb').read()).decode()
        out.append(f"@font-face{{font-family:F;src:url(data:font/woff2;base64,{data}) format('woff2');font-weight:{weight};unicode-range:{u.group(1)}}}")
    miss = chars - covered
    if miss: raise SystemExit(f'書体「{STYLES_BY_FONT.get(key, key)}」では書けない文字があります：' + ''.join(sorted(chr(c) for c in miss)) + '（日本語は jpop / fude / wamodern / maru / kawaii / gokubuto）')
    return ''.join(out)


STYLES_BY_FONT = {v['font']: v['jp'] for v in STYLES.values()}


def has_jp(text):
    return any(ord(c) >= 0x3000 for c in text)


async def render(text, st, width, rotate, c1, c2):
    ffcss = font_css(st['font'], st['weight'], text)
    fill = st['fill'] if not c1 else f'linear-gradient(180deg,{c1},{c2 or c1})'
    import html as _h
    # 1行＝縁取りの層（下）と色の層（上）を同じ位置に重ねる
    lines = ''.join(f'<div class="l">' + (f'<span class="s">{_h.escape(l)}</span>' if st['strokew'] else '') + f'<span class="f">{_h.escape(l)}</span></div>'
                    for l in text.split('|'))
    html = f"""<html><head><style>
    {ffcss}
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


def _box(design, placement):
    pj = os.path.join(placement or os.path.dirname(os.path.abspath(design)), 'placement.json')
    return json.load(open(pj))['box'] if os.path.exists(pj) else None


def _place(t, design, placement, cx, cy):
    """文字の左上。cx/cy が無ければ人物の下（白い範囲の下端）"""
    th, tw = t.shape[:2]; ys, xs = np.nonzero(t[:, :, 3] > 40)
    if cx is None or cy is None:
        b = _box(design, placement) or [SAFE[0], SAFE[1], SAFE[2], SAFE[1]]
        vw = xs.max() - xs.min()
        c = min(max((b[0] + b[2]) / 2, SAFE[0] + vw / 2 + 20), SAFE[2] - vw / 2 - 20)
        cx = c - ((xs.min() + xs.max()) / 2 - tw / 2) if cx is None else cx
        cy = (SAFE[3] - 30 - ys.max()) + th / 2 if cy is None else cy
    return int(round(cx - tw / 2)), int(round(cy - th / 2))


def _contrast(im, t, x0, y0):
    """(文字の中の明るさ, 文字の下の背景の明るさ)"""
    th, tw = t.shape[:2]
    sx0, sy0, sx1, sy1 = max(0, x0), max(0, y0), min(W, x0 + tw), min(H, y0 + th)
    if sx1 <= sx0 or sy1 <= sy0: return None
    sub = t[sy0 - y0:sy1 - y0, sx0 - x0:sx1 - x0]; bg = im[sy0:sy1, sx0:sx1]
    core = sub[:, :, 3] > 230
    if core.sum() < 50: return None
    lum = lambda a: (0.114 * a[..., 0] + 0.587 * a[..., 1] + 0.299 * a[..., 2])
    ring = cv2.dilate(core.astype(np.uint8), np.ones((25, 25), np.uint8)).astype(bool)
    return float(lum(sub[..., :3].astype(np.float32))[core].mean()), float(lum(bg.astype(np.float32))[ring].mean())


def apply(design, out_path, text, style, cx=None, cy=None, width=1500, rotate=0, placement='', color1='', color2=''):
    """文字を入れて out_path に書き出す。cx/cy が無ければ人物の下（白い範囲の下端）。"""
    style = {v['jp']: k for k, v in STYLES.items()}.get(style, style)
    if changes_case(style, text): raise SystemExit(f'「{STYLES[style]["jp"]}」は全部大文字に見える書体なので、小文字を含む「{text}」には使えません（文字は依頼のまま変えない）')
    im = cv2.imread(design); assert im is not None and im.shape[1] == W, 'デザイン画像は 2880×2048'
    st = dict(STYLES[style])
    t = asyncio.run(render(text, st, width, rotate, color1, color2))
    th, tw = t.shape[:2]
    for _ in range(2):  # 背景に埋もれないように：文字と下の背景の明るさが近ければ、縁に影（または光）を足して描き直す
        x0, y0 = _place(t, design, placement, cx, cy)
        c = _contrast(im, t, x0, y0)
        if c is None or abs(c[0] - c[1]) >= 100: break
        glow = 'rgba(0,0,0,.9)' if c[0] > c[1] else 'rgba(255,255,255,.9)'
        st['shadow'] = f'drop-shadow(0 0 .035em {glow}) drop-shadow(0 0 .09em {glow}) ' + st['shadow']
        t = asyncio.run(render(text, st, width, rotate, color1, color2)); th, tw = t.shape[:2]
    al = t[:, :, 3] > 40; ys, xs = np.nonzero(al)
    box = _box(design, placement)
    x0, y0 = _place(t, design, placement, cx, cy)
    bx = [x0 + xs.min(), y0 + ys.min(), x0 + xs.max(), y0 + ys.max()]
    ng = bx[0] < SAFE[0] or bx[1] < SAFE[1] or bx[2] > SAFE[2] or bx[3] > SAFE[3]
    over = bool(box and bx[1] < box[3] and bx[0] < box[2] and bx[2] > box[0])  # 顔（大事な範囲）に重なる
    out = im.astype(np.float32)
    sx0, sy0, sx1, sy1 = max(0, x0), max(0, y0), min(W, x0 + tw), min(H, y0 + th)
    sub = t[sy0 - y0:sy1 - y0, sx0 - x0:sx1 - x0].astype(np.float32)
    a_ = sub[:, :, 3:4] / 255
    out[sy0:sy1, sx0:sx1] = out[sy0:sy1, sx0:sx1] * (1 - a_) + sub[:, :, :3] * a_
    cv2.imwrite(out_path, np.clip(out, 0, 255).astype(np.uint8), [cv2.IMWRITE_JPEG_QUALITY, 95])
    return {'out': out_path, 'text_box': [int(v) for v in bx], 'outside_safe': bool(ng), 'over_face': over}


def main():
    if '--list' in sys.argv:
        for k, v in STYLES.items(): print(f"{k:10s} {v['jp']}{'（日本語可）' if v['font'] in JPFONTS else ''}{'（大文字だけの文言のみ）' if v['font'] in CAPSFONTS else ''}：{v['mood']}")
        return
    ap = argparse.ArgumentParser()
    ap.add_argument('design'); ap.add_argument('out'); ap.add_argument('--text', required=True); ap.add_argument('--style', required=True, help='STYLES のキー（pirate など）か日本語の名前（海賊風など）。python3 textlayer.py --list で一覧')
    ap.add_argument('--cx', type=float); ap.add_argument('--cy', type=float); ap.add_argument('--placement', default='')
    ap.add_argument('--width', type=float, default=1500); ap.add_argument('--rotate', type=float, default=0)
    ap.add_argument('--color1', default=''); ap.add_argument('--color2', default='')
    a = ap.parse_args()
    print(json.dumps(apply(a.design, a.out, a.text, a.style, a.cx, a.cy, a.width, a.rotate, a.placement, a.color1, a.color2), ensure_ascii=False))


if __name__ == '__main__':
    main()
