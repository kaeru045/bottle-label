#!/usr/bin/env python3
"""顔が描き直されていたら、元画像の顔（頭）を貼り戻す。
2026-11-22 ユーザー指定：「顔が変わってないか毎回チェックして・変わってたら直して」（キャンディ黒崎の件）。

- 元画像の顔は check.faces（BlazeFace）で探す。
- 顔のまわり（顔の枠の約2倍）で SIFT を合わせて、元画像→完成画像の相似変換を求める（顔ごと）。
- 貼る範囲＝顔のまわりの楕円 ∩ 人物の切り抜き（rembg u2net_human_seg）。ふちはぼかす。
- 色は完成画像に合わせる（平均と幅を Lab で合わせる）。
使い方：python3 facefix.py 元画像 完成画像 出力.jpg  → JSON（fixed：直した顔の数、faces：前後の判定）
"""
import json, sys, os
import cv2, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check

_seg = None


def person_mask(img):
    global _seg
    try:
        import rembg  # noqa
    except ImportError:  # 定期実行の環境に無ければ入れる
        import subprocess
        subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', '--break-system-packages', 'rembg[cpu]'], capture_output=True, timeout=600)
    from rembg import remove, new_session  # 使えなければ例外（背景ごと貼らないように直すのをやめる）
    if _seg is None: _seg = new_session('u2net_human_seg')
    m = remove(img, session=_seg, only_mask=True).astype(np.float32) / 255
    return np.clip((m - 0.3) / 0.4, 0, 1)


def local_align(o, d, f, M0):
    """顔 f のまわりで o→d の相似変換。合わなければ全体の M0"""
    x0, y0, x1, y1 = f[:4]; w, h = x1 - x0, y1 - y0
    mo = np.zeros(o.shape[:2], np.uint8)
    mo[max(0, int(y0 - 1.2 * h)):int(y1 + 1.5 * h), max(0, int(x0 - 1.5 * w)):int(x1 + 1.5 * w)] = 255
    q = cv2.transform(np.float32([[[x0, y0], [x1, y1]]]), M0)[0]
    W2, H2 = (q[1] - q[0])
    md = np.zeros(d.shape[:2], np.uint8)
    md[max(0, int(q[0][1] - 1.5 * H2)):int(q[1][1] + 1.8 * H2), max(0, int(q[0][0] - 1.8 * W2)):int(q[1][0] + 1.8 * W2)] = 255
    sift = cv2.SIFT_create(6000)
    g = lambda x: cv2.cvtColor(x, cv2.COLOR_BGR2GRAY)
    k1, d1 = sift.detectAndCompute(g(o), mo); k2, d2 = sift.detectAndCompute(g(d), md)
    if d1 is None or d2 is None or len(k1) < 8 or len(k2) < 8: return M0
    m = cv2.BFMatcher().knnMatch(d1, d2, k=2)
    good = [a for a, b in (x for x in m if len(x) == 2) if a.distance < 0.75 * b.distance]
    if len(good) < 8: return M0
    p1 = np.float32([k1[a.queryIdx].pt for a in good]); p2 = np.float32([k2[a.trainIdx].pt for a in good])
    M, inl = cv2.estimateAffinePartial2D(p1, p2, ransacReprojThreshold=3)
    if M is None or inl.sum() < 8: return M0
    s0, s = np.hypot(*M0[:, 0]), np.hypot(*M[:, 0])
    return M if 0.85 < s / s0 < 1.15 else M0


def fix(o, d, states=('redrawn',)):
    res, _ = check.compare(o, d)
    M0, _ = check.align(o, d)
    fo = check.faces(o) or []
    todo = [fo[f['n'] - 1] for f in res['faces'] if f['state'] in states]
    if M0 is None or not todo: return d, {'fixed': 0, 'before': res['faces'], 'reason': '直す顔なし' if M0 is not None else '元画像と重ならない'}
    H, W = d.shape[:2]
    pm = person_mask(o)
    out = d.astype(np.float32)
    for f in todo:
        M = local_align(o, d, f, M0)
        x0, y0, x1, y1 = f[:4]; w, h = x1 - x0, y1 - y0
        roi = np.zeros(o.shape[:2], np.float32)
        # 頭：顔の枠より上（髪）と横（耳）まで。あごの少し下まで
        cv2.ellipse(roi, (int((x0 + x1) / 2), int(y0 + 0.35 * h)), (int(0.95 * w), int(1.05 * h)), 0, 0, 360, 1, -1)
        roi[int(y1 + 0.25 * h):, :] = 0
        roi = cv2.GaussianBlur(roi, (0, 0), max(2, w * 0.08))
        a = cv2.GaussianBlur(pm * roi, (0, 0), 1.2)
        ow = cv2.warpAffine(o, M, (W, H), flags=cv2.INTER_CUBIC).astype(np.float32)
        aw = cv2.warpAffine(a, M, (W, H))[..., None]
        # 色合わせ（顔の中心付近で Lab の平均・幅を合わせる）
        core = aw[..., 0] > 0.9
        if core.sum() > 50:
            lo = cv2.cvtColor(np.clip(ow, 0, 255).astype(np.uint8), cv2.COLOR_BGR2LAB).astype(np.float32)
            ld = cv2.cvtColor(out.astype(np.uint8), cv2.COLOR_BGR2LAB).astype(np.float32)
            for c in range(3):
                ms, ss = lo[..., c][core].mean(), lo[..., c][core].std() + 1e-3
                md, sd = ld[..., c][core].mean(), ld[..., c][core].std()
                k = np.clip(sd / ss, 0.8, 1.25)
                lo[..., c] = (lo[..., c] - ms) * k + md
            ow = cv2.cvtColor(np.clip(lo, 0, 255).astype(np.uint8), cv2.COLOR_LAB2BGR).astype(np.float32)
        out = out * (1 - aw) + ow * aw
    out = np.clip(out, 0, 255).astype(np.uint8)
    after, _ = check.compare(o, out)
    return out, {'fixed': len(todo), 'before': res['faces'], 'after': after['faces']}


if __name__ == '__main__':
    o, d = check.read(sys.argv[1]), check.read(sys.argv[2])
    out, info = fix(o, d)
    cv2.imwrite(sys.argv[3], out, [cv2.IMWRITE_JPEG_QUALITY, 95])
    print(json.dumps(info, ensure_ascii=False, default=str))
