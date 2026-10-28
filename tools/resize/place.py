#!/usr/bin/env python3
"""元画像をフォーマットどおりに 2880×2048 のキャンバスへ置き、生成拡張に渡す入力画像と広げる量を作る。

  python3 place.py SRC --box x0,y0,x1,y1 --kind head|content [--pos center|left|right] --out DIR

--box は元画像の座標で、必ず白い範囲に入れたいもの：
  head    … 人物写真。髪のてっぺん〜あごの四角。頭の上端を 540px（仕上がり270px）、高さを 720px（360px）にそろえる。
  content … デザイン画像など。顔・文字・ロゴなど大事なものを全部囲む四角。白い範囲いっぱい（4% 余白）に収める。
出力：DIR/input.png（キャンバスに入る部分だけ、縮小済み）と DIR/placement.json（広げる量など）
"""
import argparse, json, os, sys
import cv2, numpy as np
from common import W, H, SAFE, K

ap = argparse.ArgumentParser()
ap.add_argument('src'); ap.add_argument('--box', required=True); ap.add_argument('--kind', choices=['head', 'content'], required=True)
ap.add_argument('--pos', choices=['center', 'left', 'right'], default='center'); ap.add_argument('--out', required=True)
ap.add_argument('--zoom', type=float, default=1.0, help='大きさの調整（1.15＝15%大きく）。修正依頼「人物をもっと大きく」など')
ap.add_argument('--dx', type=float, default=0, help='左右に動かす量（仕上がりのpx、＋で右）'); ap.add_argument('--dy', type=float, default=0, help='上下に動かす量（仕上がりのpx、＋で下）')
a = ap.parse_args()

im = cv2.imread(a.src, cv2.IMREAD_COLOR)
if im is None:
    sys.exit('画像が読めません: ' + a.src)
ih, iw = im.shape[:2]
x0, y0, x1, y1 = [float(v) for v in a.box.split(',')]
bw, bh = x1 - x0, y1 - y0
if bw <= 0 or bh <= 0:
    sys.exit('--box が不正です')

sw, sh = SAFE['x1'] - SAFE['x0'], SAFE['y1'] - SAFE['y0']
if a.kind == 'head':
    s = 360 * K / bh
    if bw * s > sw * 0.96:  # 横に広い頭（帽子など）は幅で縮める
        s = sw * 0.96 / bw
    y = 270 * K - y0 * s
    cx = {'center': W / 2, 'left': SAFE['x0'] + 66 * K + bw * s / 2, 'right': SAFE['x1'] - 66 * K - bw * s / 2}[a.pos]
else:
    m = 0.04
    s = min(sw * (1 - 2 * m) / bw, sh * (1 - 2 * m) / bh)
    y = (SAFE['y0'] + SAFE['y1']) / 2 - (y0 + bh / 2) * s
    cx = {'center': W / 2, 'left': SAFE['x0'] + sw * m + bw * s / 2, 'right': SAFE['x1'] - sw * m - bw * s / 2}[a.pos]
x = cx - (x0 + bw / 2) * s
if a.zoom != 1.0:  # 大事な範囲の中心を軸に拡大・縮小
    ccx, ccy = x + (x0 + bw / 2) * s, y + (y0 + bh / 2) * s
    s *= a.zoom
    x, y = ccx - (x0 + bw / 2) * s, ccy - (y0 + bh / 2) * s
x += a.dx * K; y += a.dy * K

# 画像のうちキャンバスに入る部分（キャンバス座標）
dx0, dy0 = max(0, round(x)), max(0, round(y))
dx1, dy1 = min(W, round(x + iw * s)), min(H, round(y + ih * s))
if dx1 - dx0 < 64 or dy1 - dy0 < 64:
    sys.exit('画像がキャンバスの外に出ます。--box を見直してください')
# それに当たる元画像の範囲で切り出して縮小
sx0, sy0, sx1, sy1 = (dx0 - x) / s, (dy0 - y) / s, (dx1 - x) / s, (dy1 - y) / s
M = np.float32([[s, 0, x - dx0], [0, s, y - dy0]])
interp = cv2.INTER_AREA if s < 1 else cv2.INTER_CUBIC
inp = cv2.warpAffine(im, M, (dx1 - dx0, dy1 - dy0), flags=interp, borderMode=cv2.BORDER_REPLICATE)
os.makedirs(a.out, exist_ok=True)
cv2.imwrite(os.path.join(a.out, 'input.png'), inp)

bx = [x + x0 * s, y + y0 * s, x + x1 * s, y + y1 * s]  # 大事な範囲（キャンバス座標）
ng = [n for n, bad in [('上の帯', bx[1] < SAFE['y0']), ('下の帯', bx[3] > SAFE['y1']), ('左の帯', bx[0] < SAFE['x0']), ('右の帯', bx[2] > SAFE['x1'])] if bad]
pl = {'canvas': [W, H], 's': s, 'x': x, 'y': y, 'dst': [dx0, dy0, dx1, dy1], 'box': [round(v) for v in bx], 'kind': a.kind, 'pos': a.pos,
      'expand': {'left': dx0, 'top': dy0, 'right': W - dx1, 'bottom': H - dy1}, 'upscale': round(s, 3), 'ng': ng}
json.dump(pl, open(os.path.join(a.out, 'placement.json'), 'w'), ensure_ascii=False, indent=1)
print(json.dumps({'input': [dx1 - dx0, dy1 - dy0], 'expand': pl['expand'], 'scale': round(s, 3), 'ng': ng}, ensure_ascii=False))
if s > 3:
    print('注意：元画像が小さく、3倍以上に拡大しています（ぼやける可能性）', file=sys.stderr)
