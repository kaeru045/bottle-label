#!/usr/bin/env python3
"""デザイン画像（横長1440×1024）の文字が、ボトルを正面から見たときに全部見えるかを調べる。

2026-11-18 ユーザー指定：正面から見たときに毎回文字がはみ出ていたので、LINEに送る前のチェック（check.py）で知らせる。
- 文字の検出は PP-OCRv3 の文字検出（tools/deco/models/text_det.onnx）。
- 正面の範囲は横 506〜923px（1440換算）。少しの誤差は許す（±8px）。
- 上下の帯（〜254px・917px〜）にかかる文字も知らせる。
使い方：python3 fronttext.py design.jpg  → JSON（boxes・left・right・msg）
"""
import json, os, sys
import cv2, numpy as np

MODEL = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'deco', 'models', 'text_det.onnx')
FRONT = (506, 923)
TOL = 8
_sess = None


def _session():
    global _sess
    if _sess is None:
        import onnxruntime as ort
        _sess = ort.InferenceSession(MODEL, providers=['CPUExecutionProvider'])
    return _sess


def boxes(img):
    """文字のまとまりの四角（1440×1024 換算の [x0,y0,x1,y1]）"""
    h0, w0 = img.shape[:2]
    W, H = 960, 672  # 32の倍数
    x = cv2.resize(img, (W, H))[:, :, ::-1].astype(np.float32) / 255.0
    x = (x - np.array([0.485, 0.456, 0.406])) / np.array([0.229, 0.224, 0.225])
    x = x.transpose(2, 0, 1)[None].astype(np.float32)
    s = _session()
    p = s.run(None, {s.get_inputs()[0].name: x})[0][0, 0]
    m = (p > 0.3).astype(np.uint8)
    m = cv2.dilate(m, np.ones((3, 3), np.uint8))
    n, lab, st, _ = cv2.connectedComponentsWithStats(m)
    sx, sy = 1440 / W, 1024 / H
    out = []
    for i in range(1, n):
        x0, y0, w, h, a = st[i]
        if a < 40 or h < 6: continue
        if float(p[lab == i].mean()) < 0.55: continue  # 模様などの弱い反応は除く
        out.append([int(x0 * sx), int(y0 * sy), int((x0 + w) * sx), int((y0 + h) * sy)])
    return out


def group(bs):
    main = [b for b in bs if b[0] < FRONT[1] and b[2] > FRONT[0] and (b[2] - b[0]) > 40 and b[1] > 254 - 40]
    if not main: return None
    L, T, R, B = max(main, key=lambda b: b[2] - b[0])
    T0, B0, L0, R0 = T, B, L, R
    for b in bs:
        c = (b[0] + b[2]) / 2
        if L0 - 20 <= c <= R0 + 20 and b[1] >= T0 - 70 and b[3] <= B0 + 110 and (b[2] - b[0]) > 20:
            L, R, T, B = min(L, b[0]), max(R, b[2]), min(T, b[1]), max(B, b[3])
    return L, T, R, B


def check(img):
    if img.shape[1] != 1440: img = cv2.resize(img, (1440, 1024), interpolation=cv2.INTER_AREA)
    bs = boxes(img)
    # 名前の行（正面にかかるいちばん幅の広い行）と、その上下の近い行だけを見る（背景の飾り文字・指輪などの小さな反応・端のロゴは対象外）
    g = group(bs)
    if not g: return {'boxes': bs, 'msg': ''}
    L, T, R, B = g
    msg = []
    if L < FRONT[0] - TOL or R > FRONT[1] + TOL:
        msg.append(f'⚠️ 文字が正面からはみ出しています（左{max(0, FRONT[0] - L)}px・右{max(0, R - FRONT[1])}px）')
    if B > 917 + TOL: msg.append(f'⚠️ 文字が下の帯にかかっています（{B - 917}px）')
    if T < 254 - TOL: msg.append(f'⚠️ 文字が上の帯にかかっています（{254 - T}px）')
    return {'boxes': bs, 'left': L, 'right': R, 'top': T, 'bottom': B, 'msg': '\n'.join(msg)}


if __name__ == '__main__':
    print(json.dumps(check(cv2.imread(sys.argv[1])), ensure_ascii=False))
