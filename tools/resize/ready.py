#!/usr/bin/env python3
"""リサイズが要らない画像か見分ける。すでに横長1440×1024と同じ比率（±2%）で、横幅が1440px以上なら「リサイズ不要」。

  python3 ready.py SRC [--out DIR]

リサイズ不要なら（--out があれば）背景を広げずに 2880×2048 にそろえた DIR/design.jpg を作る（ほんの少しずれた比率は中央で切りそろえる）。
出力：{"ready": true|false, "w", "h", "ratio", "reason"}
"""
import argparse, json, os, sys
import cv2
from common import W, H

R = 1440 / 1024


def check(w, h):
    r = w / h
    if abs(r / R - 1) > 0.02: return False, f'比率が違う（{w}×{h}）'
    if w < 1440: return False, f'横幅が足りない（{w}px、1440px以上が必要）'
    return True, f'横長1440×1024と同じ比率（{w}×{h}）'


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('src'); ap.add_argument('--out', default='')
    a = ap.parse_args()
    im = cv2.imread(a.src, cv2.IMREAD_COLOR)
    if im is None: sys.exit('画像が読めません: ' + a.src)
    h, w = im.shape[:2]; ok, why = check(w, h)
    if ok and a.out:
        if w / h > R: cw = round(h * R); im = im[:, (w - cw) // 2:(w - cw) // 2 + cw]
        else: ch = round(w / R); im = im[(h - ch) // 2:(h - ch) // 2 + ch]
        os.makedirs(a.out, exist_ok=True)
        im = cv2.resize(im, (W, H), interpolation=cv2.INTER_AREA if im.shape[1] > W else cv2.INTER_CUBIC)
        cv2.imwrite(os.path.join(a.out, 'design.jpg'), im, [cv2.IMWRITE_JPEG_QUALITY, 95])
    print(json.dumps({'ready': ok, 'w': w, 'h': h, 'ratio': round(w / h, 4), 'reason': why}, ensure_ascii=False))
