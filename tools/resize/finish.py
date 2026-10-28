#!/usr/bin/env python3
"""生成拡張の結果に元の画素を重ね直して、デザイン画像（2880×2048）と確認用画像を作る。

  python3 finish.py DIR GEN.jpg [--feather 24]

DIR は place.py の出力先（input.png・placement.json）。
出力：DIR/design.jpg（2880×2048）、DIR/check.jpg（帯と大事な範囲を重ねた確認用・縮小）
"""
import argparse, json, os, sys
import cv2, numpy as np
from common import W, H, SAFE

ap = argparse.ArgumentParser(); ap.add_argument('dir'); ap.add_argument('gen'); ap.add_argument('--feather', type=int, default=24)
a = ap.parse_args()
pl = json.load(open(os.path.join(a.dir, 'placement.json')))
inp = cv2.imread(os.path.join(a.dir, 'input.png')).astype(np.float32)
g = cv2.imread(a.gen)
if g is None:
    sys.exit('生成結果が読めません')
if g.shape[1] != W or g.shape[0] != H:
    g = cv2.resize(g, (W, H), interpolation=cv2.INTER_AREA if g.shape[1] > W else cv2.INTER_CUBIC)
g = g.astype(np.float32)
x0, y0, x1, y1 = pl['dst']
reg = g[y0:y1, x0:x1]
diff = float(np.abs(reg - inp).mean())

# ふちをなじませるマスク（キャンバスの端に接している辺はなじませない）
h, w = inp.shape[:2]; f = a.feather
m = np.ones((h, w), np.float32)
ramp = (np.arange(f, dtype=np.float32) + 1) / (f + 1)
if x0 > 0: m[:, :f] = np.minimum(m[:, :f], ramp[None, :])
if x1 < W: m[:, -f:] = np.minimum(m[:, -f:], ramp[::-1][None, :])
if y0 > 0: m[:f, :] = np.minimum(m[:f, :], ramp[:, None])
if y1 < H: m[-f:, :] = np.minimum(m[-f:, :], ramp[::-1][:, None])
g[y0:y1, x0:x1] = reg * (1 - m[..., None]) + inp * m[..., None]
out = np.clip(g, 0, 255).astype(np.uint8)
cv2.imwrite(os.path.join(a.dir, 'design.jpg'), out, [cv2.IMWRITE_JPEG_QUALITY, 95])

c = out.copy(); ov = c.copy()
cv2.rectangle(ov, (0, 0), (W, SAFE['y0']), (140, 150, 255), -1); cv2.rectangle(ov, (0, SAFE['y1']), (W, H), (140, 150, 255), -1)
cv2.rectangle(ov, (0, SAFE['y0']), (SAFE['x0'], SAFE['y1']), (180, 250, 255), -1); cv2.rectangle(ov, (SAFE['x1'], SAFE['y0']), (W, SAFE['y1']), (180, 250, 255), -1)
c = cv2.addWeighted(ov, 0.4, c, 0.6, 0)
b = pl['box']; cv2.rectangle(c, (b[0], b[1]), (b[2], b[3]), (0, 0, 255) if pl['ng'] else (60, 200, 60), 6)
cv2.imwrite(os.path.join(a.dir, 'check.jpg'), cv2.resize(c, (W // 2, H // 2), interpolation=cv2.INTER_AREA), [cv2.IMWRITE_JPEG_QUALITY, 88])
print(json.dumps({'design': os.path.join(a.dir, 'design.jpg'), 'check': os.path.join(a.dir, 'check.jpg'), 'diff_before_overlay': round(diff, 2),
                  'aligned': diff < 8, 'ng': pl['ng']}, ensure_ascii=False))
