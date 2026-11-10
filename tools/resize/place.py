#!/usr/bin/env python3
"""元画像をフォーマットどおりに 2880×2048 のキャンバスへ置き、生成拡張に渡す入力画像と広げる量を作る。

  python3 place.py SRC --box x0,y0,x1,y1 --kind head|content [--pos center|left|right] --out DIR

--box は元画像の座標で、必ず白い範囲に入れたいもの：
  head    … 人物写真。髪のてっぺん〜あごの四角。頭の上端を 540px（仕上がり270px）、高さを HEAD_H（標準 605px＝仕上がり、432pxの1.4倍）にそろえる。顔のアップの写真で写真が切れるときは、写真が丸ごと入る大きさまで小さくする（432px相当より小さくはしない）。
  content … デザイン画像など。顔・文字・ロゴなど大事なものを全部囲む四角。ボトルを正面から見て全部見えるように、
            横はボトル正面の幅（FRONT）、縦は白い範囲に（4% 余白で）収める（2026-11-05 ユーザー指定）。--wide で以前の白い範囲いっぱい。
出力：DIR/input.png（キャンバスに入る部分だけ、縮小済み）と DIR/placement.json（広げる量など）
"""
import argparse, json, os, sys
import cv2, numpy as np
from common import W, H, SAFE, K, FRONT

ap = argparse.ArgumentParser()
ap.add_argument('src'); ap.add_argument('--box', required=True); ap.add_argument('--kind', choices=['head', 'content'], required=True)
ap.add_argument('--pos', choices=['center', 'left', 'right'], default='center'); ap.add_argument('--out', required=True)
ap.add_argument('--zoom', type=float, default=1.0, help='大きさの調整（1.15＝15%大きく）。修正依頼「人物をもっと大きく」など')
ap.add_argument('--size', choices=['リメイク', '小さめ', '標準', '大きめ', '特大'], default='標準', help='管理サイトの「人物の大きさ」（zoom に掛ける：リメイク＝最初のリサイズの大きさ（頭360px）・小さめ0.87・大きめ1.15・特大1.3）')
ap.add_argument('--wide', action='store_true', help='content を白い範囲いっぱいに置く（以前の置き方。正面からは端が見えなくなる）')
ap.add_argument('--no-refine', action='store_true', help='--box の自動補正をしない')
ap.add_argument('--dx', type=float, default=0, help='左右に動かす量（仕上がりのpx、＋で右）'); ap.add_argument('--dy', type=float, default=0, help='上下に動かす量（仕上がりのpx、＋で下）')
a = ap.parse_args()

im = cv2.imread(a.src, cv2.IMREAD_COLOR)
if im is None:
    sys.exit('画像が読めません: ' + a.src)
ih, iw = im.shape[:2]
x0, y0, x1, y1 = [float(v) for v in a.box.split(',')]
if x1 <= x0 or y1 <= y0:
    sys.exit('--box が不正です')


def refine(im, box, kind):
    """目で決めた --box は数十px ずれることが多く、ボトル正面でロゴ・人物が左に寄って端が切れていた（2026-11-10 ユーザー指摘：ガルバジューシー）。
    content：四角を少し広げた範囲で、ふちの色（背景）と違う画素の範囲に四角を合わせる。
    head：四角の中に顔が1つだけ見つかれば、横の中心を顔の中心にする（高さ・幅はそのまま）。"""
    x0, y0, x1, y1 = box; ih, iw = im.shape[:2]
    if kind == 'content':
        # 範囲を少しずつ広げ、ふちの色と違う画素（ロゴ・文字・人物）が範囲のふちに当たらなくなったところで、その画素の範囲に合わせる。
        # 何度広げてもふちに当たる側は、背景に柄がある（または画像の端まで続く）ので元の四角のまま。
        nb = list(box); hit = [True] * 4
        for k in (0.08, 0.2, 0.35):
            px, py = (x1 - x0) * k, (y1 - y0) * k
            X0, Y0, X1, Y1 = int(max(0, x0 - px)), int(max(0, y0 - py)), int(min(iw, x1 + px)), int(min(ih, y1 + py))
            reg = cv2.cvtColor(im[Y0:Y1, X0:X1], cv2.COLOR_BGR2LAB).astype(np.float32)
            ring = np.concatenate([reg[:3].reshape(-1, 3), reg[-3:].reshape(-1, 3), reg[:, :3].reshape(-1, 3), reg[:, -3:].reshape(-1, 3)])
            mask = (np.linalg.norm(reg - np.median(ring, 0), axis=2) > 60).astype(np.uint8)
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
            if not (0.003 < mask.mean() < 0.9): return box, ''
            ys, xs = np.nonzero(mask)
            c = [np.percentile(xs, 0.3) + X0, np.percentile(ys, 0.3) + Y0, np.percentile(xs, 99.7) + X0, np.percentile(ys, 99.7) + Y0]
            rw, rh = X1 - X0, Y1 - Y0
            t = [c[0] - X0 < rw * 0.02 and X0 > 0, c[1] - Y0 < rh * 0.02 and Y0 > 0, X1 - c[2] < rw * 0.02 and X1 < iw, Y1 - c[3] < rh * 0.02 and Y1 < ih]
            for i in range(4):
                if hit[i] and not t[i]: nb[i] = c[i]; hit[i] = False
            if not any(hit): break
        # 画像の端まで広がった側は、背景の柄やふちの線を拾っていることが多いので、元の四角が端から離れていれば元のまま
        for i, (edge, lim) in enumerate([(0, iw), (0, ih), (iw, iw), (ih, ih)]):
            if abs(nb[i] - edge) <= 3 and abs(box[i] - edge) > lim * 0.03: nb[i] = box[i]
        if nb[2] - nb[0] < (x1 - x0) * 0.3 or nb[3] - nb[1] < (y1 - y0) * 0.3: return box, ''
        return tuple(nb), 'content'
    try:
        from check import faces  # 完成画像チェックと同じ顔検出（face-detection-tflite）
        X0, Y0, X1, Y1 = int(max(0, x0)), int(max(0, y0)), int(min(iw, x1)), int(min(ih, y1 + (y1 - y0) * 0.1))
        f = [q for q in (faces(im[Y0:Y1, X0:X1]) or []) if (q[2] - q[0]) > (x1 - x0) * 0.25]
    except Exception:
        return box, ''
    if len(f) != 1: return box, ''
    c = X0 + (f[0][0] + f[0][2]) / 2; half = (x1 - x0) / 2
    if abs(c - (x0 + half)) > half * 0.5: return box, ''
    return (c - half, y0, c + half, y1), 'face'


refined = ''
if not a.no_refine:
    (x0, y0, x1, y1), refined = refine(im, (x0, y0, x1, y1), a.kind)
bw, bh = x1 - x0, y1 - y0

sw, sh = SAFE['x1'] - SAFE['x0'], SAFE['y1'] - SAFE['y0']
HEAD_H = 605  # 仕上がりpxでの頭の高さ（標準）。2026-10-28 に 360 → 432、2026-10-29 に 432 → 605（さらに1.4倍、ユーザー指定）
# リメイク（店名）は人物を大きくしすぎない：一番最初のリサイズの大きさ（頭の高さ360px）。2026-11-03 ユーザー指定
a.zoom *= {'リメイク': 360 / HEAD_H, '小さめ': 0.87, '標準': 1.0, '大きめ': 1.15, '特大': 1.3}[a.size]
FLOOR = min(432, 360) if a.size == 'リメイク' else 432  # 顔のアップを丸ごと入れるときの下限（頭の高さ）
if a.kind == 'head':
    s = HEAD_H * K / bh * a.zoom  # 頭の上端は 270 のまま、下に向かって大きくする
    a.zoom = 1.0
    if bw * s > sw * 0.96:  # 横に広い頭（帽子など）は幅で縮める
        s = sw * 0.96 / bw
    # 顔のアップの写真は、標準の大きさだと写真の上下・左右（髪・手・肩）が切れてぼやけるので、
    # 写真が丸ごと入る大きさまで小さくする（ただし前の標準 432px の大きさより小さくはしない）。2026-10-29 ディセントで発生
    fit = min(H / ih, W / iw) * a.zoom
    if s > fit:
        s = max(fit, HEAD_H * K / bh * FLOOR / HEAD_H) if a.size == 'リメイク' else max(fit, s * 432 / HEAD_H)
    y = 270 * K - y0 * s
    cx = {'center': W / 2, 'left': SAFE['x0'] + 66 * K + bw * s / 2, 'right': SAFE['x1'] - 66 * K - bw * s / 2}[a.pos]
else:
    m = 0.04
    fx0, fx1 = (SAFE['x0'], SAFE['x1']) if a.wide else (FRONT['x0'], FRONT['x1'])
    fw = fx1 - fx0
    s = min(fw * (1 - 2 * m) / bw, sh * (1 - 2 * m) / bh)
    y = (SAFE['y0'] + SAFE['y1']) / 2 - (y0 + bh / 2) * s
    cx = {'center': (fx0 + fx1) / 2, 'left': fx0 + fw * m + bw * s / 2, 'right': fx1 - fw * m - bw * s / 2}[a.pos]
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
      'expand': {'left': dx0, 'top': dy0, 'right': W - dx1, 'bottom': H - dy1}, 'upscale': round(s, 3), 'ng': ng, 'refined': refined, 'srcbox': [round(v) for v in (x0, y0, x1, y1)]}
json.dump(pl, open(os.path.join(a.out, 'placement.json'), 'w'), ensure_ascii=False, indent=1)
print(json.dumps({'input': [dx1 - dx0, dy1 - dy0], 'expand': pl['expand'], 'scale': round(s, 3), 'ng': ng, 'refined': refined, 'box': pl['srcbox']}, ensure_ascii=False))
if s > 3:
    print('注意：元画像が小さく、3倍以上に拡大しています（ぼやける可能性）', file=sys.stderr)
