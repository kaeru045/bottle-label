#!/usr/bin/env python3
"""テスト注文 #04738 の「AI生成」を、書き込みAPIで動かす（スタッフのログイン不要）。2026-11-10〜
トークンは管理サイト（Apps Script）のスクリプトプロパティ ADMIN_WRITE_TOKEN にだけ置き、
ここからは管理サイトの action:'adminWrite'（決まったパスだけ中継）と action:'adminUpload'（参考画像）を通して使う。
読み取り（生成状況・候補画像）は今までどおり action:'admin' / 'adminImg'（読み取り用トークン）。

決まり（開発の方から）：
- 同時に動かすのは1つだけ（2つ同時だと、片方の文字・画像でもう片方が生成されることがある）。
- 生成は一度に1件ずつ。生成中（pending / running）に生成・文字の更新・画像の差し替えを送ると 409。
  必ず generated か failed になったのを確かめてから次を送る。
- 文字・要望の更新は1本ずつ順番に。
- お客様に届く操作（提案・確定）はAPIに無い。

  python3 hp_api.py status
  python3 hp_api.py gen --text 'カイト|BIRTHDAY' --bg omakase --hint '黒とシルバー' --photo src.jpg --out DIR [--count 3]
  python3 hp_api.py refine --cand 1294 --fix 'カイトBIRTHDAY' --out DIR [--layout '{"textSize":"smaller"}']
"""
import argparse, base64, json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'resize'))
from common import api  # noqa: E402
from hp_prompt import build, fix as fix_prompt, split2  # noqa: E402

ORDER = 4738


def W(method, path, body=None):
    r = api({'action': 'adminWrite', 'method': method, 'path': path, 'body': body or {}}, timeout=150)
    return r


def latest():
    it = sorted(items(), key=lambda x: x.get('requestedAt', ''))
    return it[-1] if it else None


def wait_idle(limit=900):
    """生成中なら終わるまで待つ。終わった（または何もない）最新の生成を返す"""
    t0 = time.time()
    while True:
        g = latest()
        if not g or g.get('status') not in ('pending', 'running'): return g
        if time.time() - t0 > limit: raise RuntimeError('生成が終わりません（%s）' % g.get('id'))
        time.sleep(15)


def send(method, path, body=None):
    """409（生成中）なら待ってから送り直す"""
    for _ in range(4):
        r = W(method, path, body)
        if r.get('ok'): return r['data']
        if r.get('status') == 409 and 'generation_in_progress' in json.dumps(r.get('data'), ensure_ascii=False):
            wait_idle(); continue
        raise RuntimeError('%s %s → %s %s' % (method, path, r.get('status'), json.dumps(r.get('data') or r.get('error'), ensure_ascii=False)[:300]))
    raise RuntimeError('409 が続きます')


def upload(path):
    """参考画像を送る。PNG/JPEG/WebP 以外（HEIC・PSD など）や 18MB を超えるものは JPEG にしてから送る（APIの上限 20MB）"""
    ext = path.lower().rsplit('.', 1)[-1]
    if ext not in ('png', 'jpg', 'jpeg', 'webp') or os.path.getsize(path) > 18e6:
        from PIL import Image
        try:
            import pillow_heif; pillow_heif.register_heif_opener()
        except Exception: pass
        im = Image.open(path); im.load()
        if im.mode not in ('RGB', 'L'):
            bg = Image.new('RGB', im.size, 'white'); im = im.convert('RGBA'); bg.paste(im, mask=im.split()[3]); im = bg
        if max(im.size) > 4000: im.thumbnail((4000, 4000))
        path2 = os.path.join('/tmp', 'hp_upload_%d.jpg' % os.getpid()); im.convert('RGB').save(path2, quality=92); path = path2
    ct = 'image/png' if path.lower().endswith('.png') else 'image/webp' if path.lower().endswith('.webp') else 'image/jpeg'
    r = api({'action': 'adminUpload', 'contentType': ct, 'filename': os.path.basename(path), 'data': base64.b64encode(open(path, 'rb').read()).decode()}, timeout=200)
    if not r.get('ok'): raise RuntimeError('画像アップロード失敗 ' + str(r.get('status') or '') + ' ' + str(r.get('error'))[:200])
    return r['mediaAssetId']


def items():
    """生成の一覧（読み取りAPI）。一時的な失敗は3回まで送り直す"""
    for i in range(3):
        try:
            r = api({'action': 'admin', 'path': '/ai-generations?orderId=%d' % ORDER}, timeout=150)
            if r.get('ok'): return r['data'].get('items', [])
            err = '読み取りAPI ' + str(r.get('status')) + ' ' + str(r.get('error'))[:150]
            if r.get('status') in (401, 403): raise RuntimeError(err + '（トークンが無効の可能性）')
        except RuntimeError: raise
        except Exception as e: err = str(e)
        time.sleep(10 * (i + 1))
    raise RuntimeError(err)


def run_and_fetch(start, out):
    """生成を始めて（start は応答）、終わるまで待ち、候補画像を out に保存して [(候補id, パス)] を返す"""
    gid = start['id']
    t0 = time.time()
    while True:
        time.sleep(15)
        g = next((x for x in items() if x.get('id') == gid), None)
        st = (g or {}).get('status')
        if st == 'generated': break
        if st == 'failed': raise RuntimeError('生成に失敗しました（%s）' % gid)
        if time.time() - t0 > 900: raise RuntimeError('生成が終わりません（%s）' % gid)
    cands = api({'action': 'admin', 'path': '/ai-generations/%d/candidates' % gid}, timeout=150)['data'].get('items', [])
    os.makedirs(out, exist_ok=True); res = []
    for i, c in enumerate([c for c in cands if c.get('imageUrl')], 1):
        r = api({'action': 'adminImg', 'url': c['imageUrl']}, timeout=200)  # imageUrl は10分で切れるのですぐ保存
        p = os.path.join(out, 'c%d.png' % i); open(p, 'wb').write(base64.b64decode(r['data'])); res.append((c['id'], p))
    return gid, res


def main():
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest='cmd')
    sub.add_parser('status')
    g = sub.add_parser('gen'); g.add_argument('--text', default=''); g.add_argument('--bg', default='keep', choices=['keep', 'omakase']); g.add_argument('--hint', default='')
    g.add_argument('--photo', required=True); g.add_argument('--kind', default='photo'); g.add_argument('--count', type=int, default=3); g.add_argument('--out', required=True)
    g.add_argument('--layout', default=''); g.add_argument('--instruction', default='')
    f = sub.add_parser('refine'); f.add_argument('--cand', type=int, required=True); f.add_argument('--fix', default=''); f.add_argument('--instruction', default='')
    f.add_argument('--layout', default=''); f.add_argument('--count', type=int, default=3); f.add_argument('--out', required=True)
    a = ap.parse_args()
    if a.cmd == 'status':
        print(json.dumps({'latest': latest(), 'brief': W('GET', '/brief')}, ensure_ascii=False, indent=1)[:2000]); return
    wait_idle()
    if a.cmd == 'gen':
        t = split2(a.text)
        send('PATCH', '/brief', {'requiredTexts': '\n'.join(t) if t else 'なし', 'requestText': build(a.text, a.bg, a.hint)})
        mid = upload(a.photo)
        send('PUT', '/reference-images', {'items': [{'mediaAssetId': mid, 'kind': a.kind}]})
        body = {'candidateCount': a.count, 'kind': 'initial', 'generationMode': 'original'}
        if a.instruction: body['instruction'] = a.instruction
        if a.layout: body['layoutAdjust'] = json.loads(a.layout)
        st = send('POST', '/generations', body)
    else:
        b = {'candidateId': a.cand, 'instruction': a.instruction or fix_prompt(a.fix)}
        if a.layout: b['layoutAdjust'] = json.loads(a.layout)
        st = send('POST', '/refine', {'bases': [b], 'imageCount': a.count})
    gid, res = run_and_fetch(st, a.out)
    print(json.dumps({'generation': gid, 'candidates': [{'id': i, 'path': p} for i, p in res]}, ensure_ascii=False))


if __name__ == '__main__':
    main()
