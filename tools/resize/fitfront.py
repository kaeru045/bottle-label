#!/usr/bin/env python3
"""名前などの文字のまとまりが正面（横506〜923px、1440換算）からはみ出していたら、文字のまとまりだけを縮めて正面に収める。
2026-11-19 ユーザー指定：「正面から見た時に名前収まるようにして・今後必ず」。

- 文字の検出は fronttext.py（PP-OCR）。正面にかかる行と、その上下の行（Birthday など）を1つのまとまりにする。
- 文字と飾り（金・白・銀の明るい部分）をまとめて切り出し、縦横同じ比率で縮めて、横の中心を 715px に置く。縦の中心は元のまま。
- 元の場所は周りの色で埋める（inpaint）。人物・背景はそのまま。
使い方：python3 fitfront.py in.jpg out.jpg  → JSON（changed・scale・before・after）
"""
import json, sys
import cv2, numpy as np
import fronttext

FRONT = fronttext.FRONT
TARGET = (545, 885)   # 縮めたあとに収める範囲（ボトルの丸みで端が欠けないよう内側に余白）
CX = 715


group = fronttext.group


def fit(img):
    h0, w0 = img.shape[:2]
    I = cv2.resize(img, (1440, 1024), interpolation=cv2.INTER_AREA) if (w0, h0) != (1440, 1024) else img.copy()
    bs = fronttext.boxes(I)
    g = group(bs)
    if not g: return img, {'changed': False, 'reason': '文字なし'}
    L, T, R, B = g
    if L >= FRONT[0] - fronttext.TOL and R <= FRONT[1] + fronttext.TOL:  # 正面（506〜923）に入っていれば触らない（ロゴなどを崩さないため）
        return img, {'changed': False, 'before': [L, R]}
    s = min(1.0, (TARGET[1] - TARGET[0]) / (R - L))
    if s >= 0.97: return img, {'changed': False, 'before': [L, R], 'reason': 'ほぼ収まっている（ずらすだけの修正はしない）'}
    # 文字と飾り：明るい金・白・銀（赤いバラや暗い背景は入れない）
    y0, y1 = max(T - 45, 0), min(B + 110, 1024)
    x0, x1 = max(L - 120, 0), min(R + 120, 1440)
    hsv = cv2.cvtColor(I, cv2.COLOR_BGR2HSV)
    Hh, S, V = hsv[..., 0].astype(int), hsv[..., 1].astype(int), hsv[..., 2].astype(int)
    gold = (Hh >= 8) & (Hh <= 40) & (S > 50) & (V > 90)
    white = (S < 70) & (V > 150)
    med = cv2.medianBlur(I, 31).astype(np.int16)
    diff = np.abs(I.astype(np.int16) - med).max(2) > 22
    m = np.zeros((1024, 1440), np.uint8)
    win = np.zeros_like(m); win[y0:y1, x0:x1] = 1
    m[((gold | white) & diff) & (win > 0)] = 1
    # 文字の四角の中は強めに（細い影・縁も含める）
    core = np.zeros_like(m)
    for b in bs:
        if L <= (b[0] + b[2]) / 2 <= R and T <= (b[1] + b[3]) / 2 <= B: core[b[1]:b[3], b[0]:b[2]] = 1
    m = np.maximum(m, (core & diff).astype(np.uint8))
    # 文字の近くにつながる部分だけ残す（離れた飾り・人物の服は除く）
    near = cv2.dilate(core, np.ones((61, 61), np.uint8))
    n, lab, st, _ = cv2.connectedComponentsWithStats(cv2.dilate(m, np.ones((5, 5), np.uint8)))
    keep = np.zeros_like(m)
    for i in range(1, n):
        comp = lab == i
        if (near[comp] > 0).any(): keep[comp] = 1
    m = (keep & cv2.dilate(m, np.ones((3, 3), np.uint8))).astype(np.uint8)
    ys, xs = np.nonzero(m)
    gx0, gx1, gy0, gy1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    cy = (T + B) / 2
    gcx = (L + R) / 2
    # 背景：元の文字の場所を埋める
    hole = cv2.dilate(m, np.ones((7, 7), np.uint8))
    bg = cv2.inpaint(I, hole * 255, 7, cv2.INPAINT_TELEA)
    # 縮めて置く（置いたあとに文字を検出し直して、はみ出していれば縮め直す・最大4回）
    am = cv2.GaussianBlur(m.astype(np.float32), (0, 0), 0.8)
    cx = CX
    for _ in range(4):
        M = np.float32([[s, 0, cx - s * gcx], [0, s, cy - s * cy]])
        Is = cv2.warpAffine(I, M, (1440, 1024), flags=cv2.INTER_AREA)
        a = cv2.warpAffine(am, M, (1440, 1024))[..., None]
        out = np.clip(Is * a + bg * (1 - a), 0, 255).astype(np.uint8)
        after = fronttext.check(out)
        l2, r2 = after.get('left'), after.get('right')
        if l2 is None or (l2 >= TARGET[0] - 8 and r2 <= TARGET[1] + 8): break
        k = min(1.0, (TARGET[1] - TARGET[0]) / (r2 - l2))
        cx += (CX - (l2 + r2) / 2) + (cx - (l2 + r2) / 2) * (k - 1)
        s *= k
    if (w0, h0) != (1440, 1024): out = cv2.resize(out, (w0, h0), interpolation=cv2.INTER_CUBIC)
    return out, {'changed': True, 'scale': round(s, 3), 'before': [int(L), int(R)], 'after': [after.get('left'), after.get('right')], 'msg': after.get('msg', '')}


if __name__ == '__main__':
    o, info = fit(cv2.imread(sys.argv[1]))
    cv2.imwrite(sys.argv[2], o, [cv2.IMWRITE_JPEG_QUALITY, 95])
    print(json.dumps(info, ensure_ascii=False))
