"""オリジナルの飾り文字（2026-11-04 追加、textlayer.py から使う）。

書体で描いた文字の形（白の型）に、とげ・刃・したたり・炎・ひび・ネオン・グリッチの飾りを足し、
グラデーション・縁取り・光・ハイライトで塗る。文字そのもの（字の形・綴り）は書体のまま変えない。
"""
import cv2, numpy as np

# 塗りの組み合わせ：fill＝上→下のグラデーション、o1＝内側の縁、o2＝外側の縁、glow＝外の光、hi＝上側のハイライト
PALETTES = {
    'pink':     dict(fill=['#ffffff', '#fde6fb', '#f3a6ea', '#ffffff', '#d98ae0', '#a24bb0'], o1='#2b0b36', o2='#f6b8ee', glow='#e04ae8', hi='#ffffff'),
    'sakura':   dict(fill=['#ffffff', '#ffe4ee', '#ffb3cc', '#ff7fa8'], o1='#5a1030', o2='#ffffff', glow='#ff8fb8', hi='#ffffff'),
    'chrome':   dict(fill=['#ffffff', '#e9eef5', '#aab4c2', '#5f6b7a', '#ffffff', '#c9d2de', '#7d8796'], o1='#0d1118', o2='#c7d3e6', glow='#7fb2ff', hi='#ffffff'),
    'gold':     dict(fill=['#fffaf0', '#f8e2a6', '#d6a64a', '#8a5e15', '#fff3cf', '#c9963c', '#7a500f'], o1='#241203', o2='#f3d27a', glow='#ffb84a', hi='#ffffff'),
    'blood':    dict(fill=['#ff6a6a', '#e01b1b', '#9c0a0a', '#4a0000'], o1='#140000', o2='#ff4a4a', glow='#ff1a1a', hi='#ffc0c0'),
    'ice':      dict(fill=['#ffffff', '#dff6ff', '#8fd6ff', '#3d8fd6', '#e8f9ff'], o1='#06203a', o2='#bff0ff', glow='#4ac8ff', hi='#ffffff'),
    'purple':   dict(fill=['#ffffff', '#e8d4ff', '#b07cff', '#6a2bd0', '#2e0b6e'], o1='#12002e', o2='#d6b8ff', glow='#9b4dff', hi='#ffffff'),
    'emerald':  dict(fill=['#f2fff8', '#9ff2c8', '#2fbf7f', '#0b6b44'], o1='#02160d', o2='#c8ffe4', glow='#2fe39a', hi='#ffffff'),
    'blackgold':dict(fill=['#4a4a4a', '#1a1a1a', '#000000', '#2a2a2a'], o1='#d6a64a', o2='#fff0b8', glow='#ffcc66', hi='#8a8a8a'),
    'fire':     dict(fill=['#fffbd0', '#ffe14d', '#ff9a1a', '#ff3d00', '#a80000'], o1='#2a0500', o2='#ffcf5a', glow='#ff6a00', hi='#ffffff'),
    'holo':     dict(fill=['#ffd6f5', '#c8b6ff', '#a6e7ff', '#b8ffd9', '#fff3b0', '#ffc6e6'], o1='#1c1030', o2='#ffffff', glow='#c38cff', hi='#ffffff'),
    'neonpink': dict(fill=['#2a0020'], o1='#ffffff', o2='#ff4fd8', glow='#ff2ec4', hi='#ffffff'),
    'neonblue': dict(fill=['#001a2a'], o1='#ffffff', o2='#3de0ff', glow='#00b3ff', hi='#ffffff'),
}


def _rgb(h):
    h = h.lstrip('#'); return np.array([int(h[i:i + 2], 16) for i in (4, 2, 0)], np.float32)  # BGR


def _sw(m):
    """文字の線の太さ（px）"""
    sk = cv2.ximgproc.thinning(m)
    dt = cv2.distanceTransform(m, cv2.DIST_L2, 5)
    v = dt[sk > 0]
    return max(4.0, 2 * float(np.median(v))) if len(v) else 10.0, sk, dt


def _ends(sk, sw):
    """骨組みの端（線の先）と、その向き。短いひげは無視"""
    nb = cv2.filter2D((sk > 0).astype(np.uint8), -1, np.ones((3, 3), np.float32)) - 1
    ys, xs = np.nonzero((sk > 0) & (nb == 1))
    h, w = sk.shape; on = sk > 0; L = int(sw * 1.6); out = []
    for y, x in zip(ys, xs):
        py, px, cy, cx, n = -1, -1, y, x, 0
        while n < L:
            nx = [(cy + dy, cx + dx) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if (dy or dx) and 0 <= cy + dy < h and 0 <= cx + dx < w and on[cy + dy, cx + dx] and (cy + dy, cx + dx) != (py, px)]
            if len(nx) != 1: break
            py, px = cy, cx; cy, cx = nx[0]; n += 1
        if n < sw * 0.7: continue
        d = np.array([x - cx, y - cy], np.float32); d /= (np.linalg.norm(d) + 1e-6)
        out.append((np.array([x, y], np.float32), d))
    return out


def _spike(m, p, d, base, length, bend=0.0):
    n = np.array([-d[1], d[0]], np.float32)
    b0 = p - d * base * 0.8
    tip = p + d * length + n * bend * length
    mid = p + d * length * 0.45 + n * bend * length * 0.35
    pts = [b0 + n * base, mid + n * base * 0.45, tip, mid - n * base * 0.45, b0 - n * base]
    cv2.fillPoly(m, [np.round(np.array(pts) * 4).astype(np.int32)], 255, cv2.LINE_AA, shift=2)


def _thorn(m, sw, sk, rng, k=1.0, bend=0.0, up=False):
    out = m.copy()
    for p, d in _ends(sk, sw):
        if up and d[1] > -0.2: continue
        _spike(out, p, d, sw * 0.5, sw * k * rng.uniform(1.4, 2.4), bend * rng.choice([-1, 1]) if bend else 0)
    return out


def _flame(m, sw, rng):
    """上向きの炎：上の縁から細い炎の舌を出し、線の先もとがらせる"""
    out = _thorn(m, sw, cv2.ximgproc.thinning(m), rng, 1.1, 0.25)
    h, w = m.shape; top = (m > 128) & (np.roll(m, sw.__int__() // 3 + 1, axis=0) < 128)
    ys, xs = np.nonzero(top); step = int(sw * 0.9); last = -10 ** 9
    for i in np.argsort(xs):
        x, y = xs[i], ys[i]
        if x - last < step or rng.random() < 0.3: continue
        last = x; d = np.array([rng.uniform(-0.35, 0.35), -1], np.float32); d /= np.linalg.norm(d)
        _spike(out, np.array([x, y + sw * 0.2], np.float32), d, sw * 0.32, sw * rng.uniform(0.7, 1.6), rng.uniform(-0.3, 0.3))
    return out


def _drip(m, sw, rng):
    """下にしたたる"""
    out = m.copy(); h, w = m.shape; s = int(sw * 0.25) + 1
    bot = (m > 128) & (np.roll(m, -s, axis=0) < 128)
    ys, xs = np.nonzero(bot); step = int(sw * 1.1); last = -10 ** 9
    for i in np.argsort(xs):
        x, y = xs[i], ys[i]
        if x - last < step or rng.random() < 0.2: continue
        r = sw * rng.uniform(0.2, 0.34); ln = sw * rng.uniform(0.9, 3.2)
        # 字の中のすき間には垂らさない（下に別の線がある所はつぶれて読めなくなる）
        if m[y + s:min(h, int(y + ln * 1.6 + r * 3)), max(0, int(x - r * 2)):int(x + r * 2) + 1].any(): continue
        last = x
        cv2.rectangle(out, (int(x - r), int(y - r)), (int(x + r), int(y + ln)), 255, -1, cv2.LINE_AA)
        cv2.circle(out, (int(x), int(y + ln)), int(r * 1.35), 255, -1, cv2.LINE_AA)
        # 根もとをなめらかに
        cv2.ellipse(out, (int(x), int(y)), (int(r * 2.2), int(r * 1.2)), 0, 0, 180, 255, -1, cv2.LINE_AA)
    return out


def _crack(m, sw, rng):
    """ひび割れ：ギザギザの細い線で割る"""
    out = m.copy(); h, w = m.shape; ys, xs = np.nonzero(m > 128)
    if not len(xs): return out
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    for _ in range(int((x1 - x0) / (sw * 1.6)) + 2):
        x = rng.uniform(x0, x1); y = y0 - sw; pts = []
        while y < y1 + sw:
            pts.append((x, y)); y += sw * rng.uniform(0.3, 0.7); x += sw * rng.uniform(-0.6, 0.6)
        cv2.polylines(out, [np.array(pts, np.int32)], False, 0, max(1, int(sw * 0.07)), cv2.LINE_AA)
    return out


def shape(mask, kind, seed=7):
    """白の型（uint8）に飾りを足す。kind は thorn / blade / flame / drip / crack / plain"""
    rng = np.random.default_rng(seed); m = (mask > 128).astype(np.uint8) * 255
    sw, sk, _ = _sw(m)
    for k in kind.split('+'):
        if k == 'thorn': m = _thorn(m, sw, sk, rng)
        elif k == 'blade': m = _thorn(m, sw, sk, rng, 1.9, 0.18)
        elif k == 'flame': m = _flame(m, sw, rng)
        elif k == 'drip': m = _drip(m, sw, rng)
        elif k == 'crack': m = _crack(m, sw, rng)
        sk = cv2.ximgproc.thinning(m)
    return m, sw


def _grad(h, w, y0, y1, stops):
    c = np.array([_rgb(s) for s in stops]); t = np.clip((np.arange(h) - y0) / max(1, y1 - y0), 0, 1) * (len(c) - 1)
    i = np.minimum(t.astype(int), len(c) - 2) if len(c) > 1 else np.zeros(h, int)
    f = (t - i)[:, None] if len(c) > 1 else np.zeros((h, 1))
    row = c[i] * (1 - f) + c[np.minimum(i + 1, len(c) - 1)] * f
    return np.repeat(row[:, None, :], w, axis=1)


def _over(dst, rgb, a):
    a = a[..., None]; da = dst[..., 3:4]
    oa = a + da * (1 - a)
    dst[..., :3] = np.where(oa > 0, (rgb * a + dst[..., :3] * da * (1 - a)) / np.maximum(oa, 1e-6), 0)
    dst[..., 3:4] = oa


def _dil(a, r):
    r = max(1, int(r)); return cv2.dilate(a, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1)))


def paint(m, sw, pal, neon=False, glitch=False, seed=7):
    """型を塗って BGRA（uint8）にする"""
    P = PALETTES[pal] if isinstance(pal, str) else pal; pad = int(sw * 2.5)
    m = cv2.copyMakeBorder(m, pad, pad, pad, pad, cv2.BORDER_CONSTANT, 0)
    a = cv2.GaussianBlur(m.astype(np.float32) / 255, (0, 0), 0.8); h, w = a.shape
    ys = np.nonzero(a.max(1) > .5)[0]; y0, y1 = ys.min(), ys.max()
    sw = min(sw, (y1 - y0) * 0.075)  # 太い書体でも縁でつぶれないように、縁・光の太さは字の高さに合わせて抑える
    out = np.zeros((h, w, 4), np.float32)
    col = lambda c: np.broadcast_to(_rgb(c), (h, w, 3))
    if neon:
        ring = np.clip(_dil(a, sw * 0.1) - cv2.erode(a, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (int(sw * .2) * 2 + 1,) * 2)), 0, 1)
        _over(out, col(P['glow']), np.clip(cv2.GaussianBlur(_dil(a, sw * .2), (0, 0), sw * .9) * .9, 0, 1))
        _over(out, _grad(h, w, y0, y1, P['fill']), a * .3)
        _over(out, col(P['o2']), np.clip(cv2.GaussianBlur(ring, (0, 0), sw * .12) * 1.6, 0, 1))
        _over(out, col(P['o1']), np.clip(cv2.GaussianBlur(cv2.erode(ring, np.ones((3, 3))), (0, 0), sw * .04) * 1.2, 0, 1) * .95)
    else:
        _over(out, col(P['glow']), np.clip(cv2.GaussianBlur(_dil(a, sw * .3), (0, 0), sw * .7) * .85, 0, 1))
        _over(out, col(P['o2']), _dil(a, sw * .3))
        _over(out, col(P['o1']), _dil(a, sw * .18))
        _over(out, _grad(h, w, y0, y1, P['fill']), a)
        s = max(1, int(sw * .09))
        top = np.clip(a - np.roll(a, s, axis=0), 0, 1); bot = np.clip(a - np.roll(a, -s, axis=0), 0, 1)
        _over(out, col(P['hi']), cv2.GaussianBlur(top, (0, 0), sw * .05) * .8)
        _over(out, col(P['o1']), cv2.GaussianBlur(bot, (0, 0), sw * .05) * .35)
    if glitch:
        rng = np.random.default_rng(seed); o = out.copy(); d = int(sw * .18)
        out[..., 2] = np.roll(o[..., 2], -d, axis=1); out[..., 0] = np.roll(o[..., 0], d, axis=1)
        out[..., 3] = np.maximum.reduce([o[..., 3], np.roll(o[..., 3], -d, axis=1), np.roll(o[..., 3], d, axis=1)])
        for _ in range(7):
            yy = int(rng.uniform(y0, y1)); hh = int(sw * rng.uniform(.12, .45)); dx = int(sw * rng.uniform(-.6, .6))
            out[yy:yy + hh] = np.roll(out[yy:yy + hh], dx, axis=1)
    out[..., :3] = np.clip(out[..., :3], 0, 255); out[..., 3] *= 255
    return out.astype(np.uint8)


def stack(main, sub, gap):
    """1行目（飾り文字）の下に2行目以降（ローマ字）を中央そろえで重ねる"""
    def crop(t):
        ys, xs = np.nonzero(t[..., 3] > 8); return t[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    main = crop(main)
    if sub is None: return cv2.copyMakeBorder(main, 120, 120, 120, 120, cv2.BORDER_CONSTANT, 0)
    sub = crop(sub)
    w = max(main.shape[1], sub.shape[1]); h = main.shape[0] + sub.shape[0] + gap
    out = np.zeros((h + 240, w + 240, 4), np.float32)
    def put(t, y):
        x = 120 + (w - t.shape[1]) // 2; tt = t.astype(np.float32); a = tt[..., 3:4] / 255
        reg = out[y:y + t.shape[0], x:x + t.shape[1]]
        oa = a + reg[..., 3:4] / 255 * (1 - a)
        reg[..., :3] = np.where(oa > 0, (tt[..., :3] * a + reg[..., :3] * reg[..., 3:4] / 255 * (1 - a)) / np.maximum(oa, 1e-6), 0)
        reg[..., 3:4] = oa * 255
    put(main, 120); put(sub, 120 + main.shape[0] + gap)
    return out.astype(np.uint8)
