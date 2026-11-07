#!/usr/bin/env python3
"""完成画像のチェック（2026-11-07 ユーザー指定：LINEで送る完成画像に「元画像とどこが違うか・顔が描き直されていないか・生成されているか」を付ける）。

  python3 check.py one ORIG DESIGN OUTDIR     … 2枚を比べて OUTDIR/check.jpg と check.json を作る（試すとき）
  python3 check.py todo [--limit N]           … 管理サイトでLINE未送信の案件を全部チェックして登録（action:checkTodo/checkGet/setCheck）
  python3 check.py id 一覧のID                 … 1件だけチェックして登録（register.py が登録直後に呼ぶ）

しくみ
  1. 元画像と完成画像の特徴点（SIFT）を合わせ、元画像が完成画像のどこに・どの大きさで入っているかを求める
     （合わなければ「全体が生成＝描き直し」）。
  2. 元画像を完成画像の位置に重ね、明るさ・色の全体の差をならしてから画素ごとの差を見る。
     元画像の範囲で差が大きい所＝変更（文字入れ・描き直し）、元画像の外＝生成で描き足した所。
  3. 元画像の顔を見つけ（BlazeFace）、完成画像の同じ場所と比べる（形の似かた SSIM と変わった画素の割合）。
チェック画像：左＝元画像（顔に番号）、右＝完成画像に印（赤＝元から変わった所、青＝生成で描き足した所、
緑の線＝元画像の範囲、顔の枠：緑＝そのまま・黄＝少し変化・赤＝描き直し）。

顔の検出には face-detection-tflite（モデル同梱）と ai-edge-litert を使う：
  pip install --break-system-packages --no-deps face-detection-tflite && pip install --break-system-packages ai-edge-litert
"""
import base64, json, os, sys, types
import cv2, numpy as np
from PIL import Image, ImageDraw, ImageFont

FONT = next((p for p in ['/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc', '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
                         '/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc'] if os.path.exists(p)), None)


# ---------- 顔の検出 ----------
_fd = None


def faces(img):
    """顔の枠 [(x0,y0,x1,y1,score)]（画素）。検出器が使えなければ None"""
    global _fd
    if _fd is None:
        try:
            if 'tensorflow' not in sys.modules:  # fdlite は tf.lite.Interpreter だけ使うので LiteRT で代用
                tf = types.ModuleType('tensorflow'); sys.modules['tensorflow'] = tf
                try:
                    from ai_edge_litert.interpreter import Interpreter
                    tf.lite = types.SimpleNamespace(Interpreter=Interpreter)
                except ImportError: pass
            import math, importlib.util, subprocess
            if not importlib.util.find_spec('fdlite') or not importlib.util.find_spec('ai_edge_litert'):  # 新しい環境では入れる
                subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', '--break-system-packages', '--no-deps', 'face-detection-tflite'], capture_output=True, timeout=300)
                subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', '--break-system-packages', 'ai-edge-litert'], capture_output=True, timeout=300)
                from ai_edge_litert.interpreter import Interpreter
                sys.modules['tensorflow'].lite = types.SimpleNamespace(Interpreter=Interpreter)
            if not hasattr(np, 'math'): np.math = math  # fdlite が古い numpy の np.math を使う
            from fdlite import FaceDetection, FaceDetectionModel
            _fd = (FaceDetection(model_type=FaceDetectionModel.FULL), FaceDetection(model_type=FaceDetectionModel.SHORT))
        except Exception as e:
            print('顔の検出が使えません:', e, file=sys.stderr); _fd = False
    if not _fd: return None
    h, w = img.shape[:2]; out = []
    pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    # 全体＋大きい画像は 2×2 に分けても探す（小さい顔のため）
    tiles = [(0, 0, w, h)]
    if max(w, h) > 900:
        for ty in range(2):
            for tx in range(2):
                tiles.append((tx * w // 2 - (w // 8 if tx else 0), ty * h // 2 - (h // 8 if ty else 0), (tx + 1) * w // 2 + (w // 8 if not tx else 0), (ty + 1) * h // 2 + (h // 8 if not ty else 0)))
    for (x0, y0, x1, y1) in tiles:
        crop = pil.crop((x0, y0, x1, y1)); cw, ch = crop.size
        for det in _fd:
            try: ds = det(crop)
            except Exception: continue
            for d in ds:
                b = d.bbox
                if d.score < 0.6: continue
                out.append((x0 + b.xmin * cw, y0 + b.ymin * ch, x0 + b.xmax * cw, y0 + b.ymax * ch, float(d.score)))
    # 重なりをまとめる
    out.sort(key=lambda f: -f[4]); keep = []
    for f in out:
        if f[2] - f[0] < 12: continue
        if all(iou(f, k) < 0.3 for k in keep): keep.append(f)
    return [tuple(int(round(v)) if i < 4 else v for i, v in enumerate(f)) for f in keep]


def iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0])); iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    i = ix * iy; u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - i
    return i / u if u > 0 else 0


# ---------- 位置合わせ ----------
def align(o, d):
    """元画像 o を完成画像 d に重ねる 2×3 の変換（相似変換）。合わなければ None"""
    def g(x, m):
        k = m / max(x.shape[:2]); return cv2.cvtColor(cv2.resize(x, None, fx=k, fy=k, interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY), k
    go, ko = g(o, 1200); gd, kd = g(d, 1200)
    sift = cv2.SIFT_create(6000)
    k1, d1 = sift.detectAndCompute(go, None); k2, d2 = sift.detectAndCompute(gd, None)
    if d1 is None or d2 is None or len(k1) < 20 or len(k2) < 20: return None, 0
    m = cv2.BFMatcher(cv2.NORM_L2).knnMatch(d1, d2, k=2)
    good = [a for a, b in (x for x in m if len(x) == 2) if a.distance < 0.75 * b.distance]
    if len(good) < 20: return None, len(good)
    p1 = np.float32([k1[x.queryIdx].pt for x in good]) / ko; p2 = np.float32([k2[x.trainIdx].pt for x in good]) / kd
    M, inl = cv2.estimateAffinePartial2D(p1, p2, method=cv2.RANSAC, ransacReprojThreshold=4 / kd, maxIters=5000, confidence=0.999)
    n = int(inl.sum()) if inl is not None else 0
    if M is None or n < 25 or n < 0.15 * len(good): return None, n
    s = float(np.hypot(M[0, 0], M[1, 0]))
    if not 0.05 < s < 20: return None, n
    return M, n


# ---------- 比較 ----------
def compare(o, d):
    """o=元画像, d=完成画像（BGR）。結果の dict とチェック画像（BGR）"""
    H, W = d.shape[:2]
    M, ninl = align(o, d)
    fo = faces(o)
    res = {'aligned': M is not None, 'inliers': ninl, 'faces': [], 'detector': fo is not None}
    if M is None:
        fd = faces(d)
        res.update(changed=None, generated=None, newFaces=len(fd or []))
        res['summary'] = summary(res, len(fo or []))
        return res, sheet(o, d, None, None, None, fo or [], [], fd or [])
    ow = cv2.warpAffine(o, M, (W, H), flags=cv2.INTER_AREA if M[0, 0] < 1 else cv2.INTER_LINEAR)
    mask = cv2.warpAffine(np.full(o.shape[:2], 255, np.uint8), M, (W, H), flags=cv2.INTER_NEAREST) > 0
    mask = cv2.erode(mask.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    # 全体の明るさ・色の違い（トーン補正）はならす：チャンネルごとに d ≈ a*ow + b を当てはめる
    lo = cv2.cvtColor(ow, cv2.COLOR_BGR2LAB).astype(np.float32); ld = cv2.cvtColor(d, cv2.COLOR_BGR2LAB).astype(np.float32)
    adj = lo.copy()
    sel = mask
    if sel.sum() > 1000:
        for c in range(3):
            x, y = lo[..., c][sel], ld[..., c][sel]
            idx = np.random.default_rng(0).choice(len(x), min(len(x), 200000), replace=False); x, y = x[idx], y[idx]
            A = np.vstack([x, np.ones_like(x)]).T; a, b = np.linalg.lstsq(A, y, rcond=None)[0]
            r = np.abs(a * x + b - y); k = r < np.percentile(r, 70)  # 変わった所に引っぱられないように2回目は差の小さい所だけで
            a, b = np.linalg.lstsq(A[k], y[k], rcond=None)[0]
            adj[..., c] = a * lo[..., c] + b
    blur = lambda x: cv2.GaussianBlur(x, (0, 0), 1.5)
    diff = np.abs(blur(adj) - blur(ld)); dl = diff[..., 0] + 0.6 * (diff[..., 1] + diff[..., 2])
    ch = (dl > 22) & mask
    ch = cv2.morphologyEx(ch.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    ch = cv2.morphologyEx(ch, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    n, lab, st, _ = cv2.connectedComponentsWithStats(ch)
    minA = W * H * 0.0004
    ch = np.isin(lab, [i for i in range(1, n) if st[i, cv2.CC_STAT_AREA] >= minA]) & mask
    res['changed'] = round(float(ch.sum()) / max(1, mask.sum()) * 100, 1)  # 元画像の範囲のうち変わった割合
    res['generated'] = round(float((~mask).sum()) / (W * H) * 100, 1)       # 完成画像のうち描き足した割合
    res['scale'] = round(float(np.hypot(M[0, 0], M[1, 0])), 3)
    # 顔
    gw, gd = cv2.cvtColor(adj.clip(0, 255).astype(np.uint8), cv2.COLOR_LAB2BGR), d
    fmapped = []
    for i, f in enumerate(fo or []):
        pts = np.float32([[f[0], f[1]], [f[2], f[1]], [f[2], f[3]], [f[0], f[3]]])
        q = cv2.transform(pts[None], M)[0]; x0, y0 = q.min(0); x1, y1 = q.max(0)
        x0, y0, x1, y1 = [int(round(v)) for v in (x0, y0, x1, y1)]
        bx = (max(0, x0), max(0, y0), min(W, x1), min(H, y1))
        if bx[2] - bx[0] < 8 or bx[3] - bx[1] < 8:
            res['faces'].append({'n': i + 1, 'state': 'cut', 'box': bx}); fmapped.append(bx + ('cut',)); continue
        inside = (bx[2] - bx[0]) * (bx[3] - bx[1]) / max(1, (x1 - x0) * (y1 - y0))
        a = cv2.cvtColor(gw[bx[1]:bx[3], bx[0]:bx[2]], cv2.COLOR_BGR2GRAY).astype(np.float32)
        b = cv2.cvtColor(gd[bx[1]:bx[3], bx[0]:bx[2]], cv2.COLOR_BGR2GRAY).astype(np.float32)
        s = ssim(a, b); cr = float(ch[bx[1]:bx[3], bx[0]:bx[2]].mean()) * 100
        state = 'same' if s >= 0.80 and cr < 8 else ('slight' if s >= 0.55 and cr < 35 else 'redrawn')
        if inside < 0.6: state = 'cut'
        res['faces'].append({'n': i + 1, 'state': state, 'ssim': round(s, 2), 'changed': round(cr, 1), 'box': bx})
        fmapped.append(bx + (state,))
    # 元画像に無い顔（生成で増えた顔）
    fd = faces(d) or []
    newf = [f for f in fd if all(iou(f, m) < 0.2 for m in fmapped) and not mask[min(H - 1, (f[1] + f[3]) // 2), min(W - 1, (f[0] + f[2]) // 2)]]
    res['newFaces'] = len(newf)
    res['summary'] = summary(res, len(fo or []))
    return res, sheet(o, d, M, mask, ch, fo or [], res['faces'], newf)


def ssim(a, b):
    if a.shape[0] < 7 or a.shape[1] < 7: return 0.0
    k = 96 / max(a.shape); a = cv2.resize(a, None, fx=k, fy=k, interpolation=cv2.INTER_AREA); b = cv2.resize(b, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
    C1, C2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2; g = lambda x: cv2.GaussianBlur(x, (7, 7), 1.5)
    ma, mb = g(a), g(b); va, vb, cv = g(a * a) - ma * ma, g(b * b) - mb * mb, g(a * b) - ma * mb
    return float((((2 * ma * mb + C1) * (2 * cv + C2)) / ((ma * ma + mb * mb + C1) * (va + vb + C2))).mean())


def summary(r, nface):
    """LINEに付ける短い文"""
    L = []
    if not r['aligned']:
        L.append('⚠️ 元画像と重なりません＝全体が生成（描き直し）です' + (f'（顔{nface}人→完成{r["newFaces"]}人）' if r['detector'] else ''))
        return '\n'.join(L)
    fs = r['faces']; red = [f for f in fs if f['state'] == 'redrawn']; yel = [f for f in fs if f['state'] == 'slight']; cut = [f for f in fs if f['state'] == 'cut']
    if not r['detector']: L.append('顔：判定できませんでした')
    elif not fs: L.append('顔：元画像に顔が見つかりません')
    elif red: L.append('⚠️ 顔が描き直されています：' + '・'.join(f'{f["n"]}' for f in red) + f'（{len(fs)}人中{len(red)}人）')
    elif yel: L.append(f'△ 顔は残っていますが少し変化：' + '・'.join(f'{f["n"]}' for f in yel) + f'（{len(fs)}人中）')
    else: L.append(f'✅ 顔はそのまま（{len(fs)}人）')
    if cut: L.append('⚠️ 顔が切れています：' + '・'.join(str(f['n']) for f in cut))
    if r.get('newFaces'): L.append(f'⚠️ 元画像に無い顔が{r["newFaces"]}人生成されています')
    c = r['changed']
    L.append(f'元画像から変わった所：{c}%' + ('（ほぼそのまま）' if c < 3 else '（文字入れなど・赤の所）' if c < 15 else '（大きく変更・赤の所）'))
    L.append(f'生成で描き足した所：{r["generated"]}%（青の所）')
    return '\n'.join(L)


COL = {'same': (60, 200, 60), 'slight': (0, 200, 255), 'redrawn': (40, 40, 255), 'cut': (200, 0, 200)}


def sheet(o, d, M, mask, ch, fo, fres, newf):
    """チェック画像：左に元画像、右に印つきの完成画像、下に凡例"""
    H, W = d.shape[:2]; k = 1100 / H if H > 1100 else 1.0
    dv = d.astype(np.float32)
    if M is not None:
        gen = ~mask
        dv[gen] = dv[gen] * 0.55 + np.array([255, 120, 0], np.float32) * 0.45       # 青＝描き足し
        dv[ch] = dv[ch] * 0.45 + np.array([0, 0, 255], np.float32) * 0.55           # 赤＝変更
        cs, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    right = dv.clip(0, 255).astype(np.uint8)
    if M is not None: cv2.drawContours(right, cs, -1, (0, 220, 0), max(2, int(3 / k)))
    t = max(2, int(4 / k))
    for i, f in enumerate(fres):
        b = f['box']; cv2.rectangle(right, b[:2], b[2:], COL[f['state']], t)
        cv2.putText(right, str(f['n']), (b[0], max(0, b[1] - 6)), cv2.FONT_HERSHEY_SIMPLEX, 1.2 / k * 0.8, COL[f['state']], t)
    for f in newf: cv2.rectangle(right, f[:2], f[2:4], (40, 40, 255), t); cv2.putText(right, 'NEW', (f[0], max(0, f[1] - 6)), cv2.FONT_HERSHEY_SIMPLEX, 1.0 / k * 0.8, (40, 40, 255), t)
    right = cv2.resize(right, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
    ko = right.shape[0] / o.shape[0]; left = cv2.resize(o, None, fx=ko, fy=ko, interpolation=cv2.INTER_AREA).copy()
    for i, f in enumerate(fo):
        st = fres[i]['state'] if i < len(fres) else 'same'
        p0, p1 = (int(f[0] * ko), int(f[1] * ko)), (int(f[2] * ko), int(f[3] * ko))
        cv2.rectangle(left, p0, p1, COL[st] if M is not None else (200, 200, 200), 3)
        cv2.putText(left, str(i + 1), (p0[0], max(0, p0[1] - 6)), cv2.FONT_HERSHEY_SIMPLEX, 1.0, COL[st] if M is not None else (200, 200, 200), 3)
    if left.shape[1] > right.shape[1]:  # 横長の元画像は幅を合わせる
        left = cv2.resize(left, (right.shape[1], int(left.shape[0] * right.shape[1] / left.shape[1])), interpolation=cv2.INTER_AREA)
    gap = 24; hh = max(left.shape[0], right.shape[0])
    can = np.full((hh + 90, left.shape[1] + gap + right.shape[1], 3), 255, np.uint8)
    can[:left.shape[0], :left.shape[1]] = left; can[:right.shape[0], left.shape[1] + gap:] = right
    if FONT:
        pil = Image.fromarray(cv2.cvtColor(can, cv2.COLOR_BGR2RGB)); dr = ImageDraw.Draw(pil); fnt = ImageFont.truetype(FONT, 30); y = hh + 26
        items = [('元画像', None)] if M is None else []
        if M is None: items = [('元画像と重ならない＝全体が生成', (255, 40, 40))]
        else: items = [('赤：元から変わった所', (255, 40, 40)), ('青：生成で描き足した所', (0, 120, 255)), ('緑線：元画像の範囲', (0, 200, 0)),
                       ('顔枠 緑＝そのまま 黄＝少し変化 赤＝描き直し', (40, 40, 40))]
        x = 20; dr.text((x, y), '左：元画像', font=fnt, fill=(40, 40, 40)); x += 190
        for s, c in items:
            dr.text((x, y), s, font=fnt, fill=c); x += int(dr.textlength(s, font=fnt)) + 36
        can = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
    if can.shape[1] > 2400: can = cv2.resize(can, None, fx=2400 / can.shape[1], fy=2400 / can.shape[1], interpolation=cv2.INTER_AREA)
    return can


def read(path_or_bytes):
    a = np.frombuffer(path_or_bytes, np.uint8) if isinstance(path_or_bytes, (bytes, bytearray)) else np.fromfile(path_or_bytes, np.uint8)
    im = cv2.imdecode(a, cv2.IMREAD_UNCHANGED)
    if im is None: raise RuntimeError('画像として読めません')
    if im.ndim == 2: im = cv2.cvtColor(im, cv2.COLOR_GRAY2BGR)
    if im.shape[2] == 4:
        al = im[:, :, 3:4].astype(np.float32) / 255; im = (im[:, :, :3].astype(np.float32) * al + 255 * (1 - al)).astype(np.uint8)
    if max(im.shape[:2]) > 3000: k = 3000 / max(im.shape[:2]); im = cv2.resize(im, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
    return im


def run_id(api, rid, v=None):
    g = api({'action': 'checkGet', 'id': rid}, timeout=200)
    if not g.get('ok'): return {'id': rid, 'error': g.get('error') or g.get('body')}
    v = v or g.get('v')
    if not g.get('orig'):
        r = api({'action': 'setCheck', 'id': rid, 'v': v, 'text': '元画像が無いのでチェックなし'}); return {'id': rid, 'text': '元画像なし', 'ok': r.get('ok')}
    try:
        res, img = compare(read(base64.b64decode(g['orig'])), read(base64.b64decode(g['design'])))
    except Exception as e:
        api({'action': 'setCheck', 'id': rid, 'v': v, 'text': 'チェックできませんでした（' + str(e)[:80] + '）'}); return {'id': rid, 'error': str(e)}
    ok, buf = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 85])
    r = api({'action': 'setCheck', 'id': rid, 'v': v, 'text': res['summary'], 'image': {'name': (g.get('base') or rid) + 'チェック.jpg', 'data': base64.b64encode(buf.tobytes()).decode()}})
    return {'id': rid, 'name': g.get('name'), 'text': res['summary'], 'ok': r.get('ok'), 'error': r.get('error')}


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    if cmd == 'one':
        os.makedirs(sys.argv[4], exist_ok=True)
        res, img = compare(read(sys.argv[2]), read(sys.argv[3]))
        cv2.imwrite(os.path.join(sys.argv[4], 'check.jpg'), img, [cv2.IMWRITE_JPEG_QUALITY, 85])
        json.dump(res, open(os.path.join(sys.argv[4], 'check.json'), 'w'), ensure_ascii=False, indent=1, default=str)
        print(res['summary'])
    elif cmd in ('todo', 'id'):
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from common import api
        if cmd == 'id': print(json.dumps(run_id(api, sys.argv[2]), ensure_ascii=False))
        else:
            lim = int(sys.argv[sys.argv.index('--limit') + 1]) if '--limit' in sys.argv else 20
            t = api({'action': 'checkTodo'})
            if not t.get('ok'): sys.exit(json.dumps(t, ensure_ascii=False))
            items = t.get('items', [])[:lim]
            print(json.dumps({'todo': len(t.get('items', [])), 'run': len(items)}, ensure_ascii=False))
            for it in items: print(json.dumps(run_id(api, it['id'], it.get('v')), ensure_ascii=False), flush=True)
    else:
        sys.exit(__doc__)
