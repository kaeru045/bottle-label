#!/usr/bin/env python3
"""リサイズ候補の登録・取得・状態変更（管理サイトの「リサイズ候補」）。

  python3 candidates.py known                     … 登録済みの候補ID一覧
  python3 candidates.py add ITEMS.json            … 候補を登録（Asanaの添付写真をダウンロードしてサムネと一緒に送る）
      ITEMS.json: [{"id":"<タスクgid>-<添付gid>","order","shop","name","due","asana","notes","spec":{...},"photo_url","photo_name"}, ...]
  python3 candidates.py queue                     … 「リサイズする」が押された候補
  python3 candidates.py src ID OUTPATH            … 候補の元画像をダウンロード
  python3 candidates.py state ID 状態 [エラー文]   … 状態を変える（作成中・エラー など）
"""
import io, json, os, sys
import cv2, numpy as np, requests
from common import api, verify


def enc(img, max_side, q, name):
    h, w = img.shape[:2]; k = min(1, max_side / max(h, w))
    if k < 1: img = cv2.resize(img, (round(w * k), round(h * k)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, q])
    import base64
    return {'name': name, 'data': base64.b64encode(buf.tobytes()).decode()}


def load_url(url):
    r = requests.get(url, timeout=120, verify=verify()); r.raise_for_status()
    a = np.frombuffer(r.content, np.uint8)
    im = cv2.imdecode(a, cv2.IMREAD_UNCHANGED)
    if im is None: raise RuntimeError('画像として読めません')
    if im.ndim == 2: im = cv2.cvtColor(im, cv2.COLOR_GRAY2BGR)
    if im.shape[2] == 4:  # 透過は白で埋める
        al = im[:, :, 3:4].astype(np.float32) / 255
        im = (im[:, :, :3].astype(np.float32) * al + 255 * (1 - al)).astype(np.uint8)
    return im


cmd = sys.argv[1] if len(sys.argv) > 1 else ''
if cmd == 'known':
    print(json.dumps(api({'action': 'resizeKnown'}), ensure_ascii=False))
elif cmd == 'add':
    items = json.load(open(sys.argv[2])); known = set(api({'action': 'resizeKnown'}).get('ids', []))
    added = 0
    for it in items:
        if it['id'] in known: continue
        try:
            im = load_url(it.pop('photo_url')); stem = os.path.splitext(it.pop('photo_name', 'photo'))[0]
            it['photo'] = enc(im, 4000, 92, f'リサイズ元_{stem}.jpg'); it['thumb'] = enc(im, 700, 80, f'リサイズ元_{stem}_小.jpg')
            r = api({'action': 'resizeAdd', 'items': [it]}); added += r.get('added', 0)
            print(it['id'], r)
        except Exception as e:
            print(it['id'], 'エラー', e)
    print(json.dumps({'added': added}))
elif cmd == 'fill':  # 手動の依頼（AsanaのURLだけ）に、Asanaの添付写真と仕様などを入れる
    # python3 candidates.py fill ID PHOTO_URL PHOTO_NAME ['{"spec":{...},"checks":[...]}'] ['{"店名":..,"名前":..,"期日":..,"注文":..}']
    im = load_url(sys.argv[3]); stem = os.path.splitext(sys.argv[4])[0]
    body = {'action': 'resizeUpdate', 'id': sys.argv[2], 'photo': enc(im, 4000, 92, f'リサイズ元_{stem}.jpg'), 'thumb': enc(im, 700, 80, f'リサイズ元_{stem}_小.jpg')}
    if len(sys.argv) > 5 and sys.argv[5]: body['spec'] = json.loads(sys.argv[5])
    if len(sys.argv) > 6 and sys.argv[6]: body.update(json.loads(sys.argv[6]))
    print(json.dumps(api(body), ensure_ascii=False))
elif cmd == 'queue':
    print(json.dumps(api({'action': 'resizeQueue'}), ensure_ascii=False))
elif cmd == 'src':
    r = api({'action': 'resizeSrc', 'id': sys.argv[2]})
    if not r.get('ok'): sys.exit(json.dumps(r, ensure_ascii=False))
    import base64
    open(sys.argv[3], 'wb').write(base64.b64decode(r['data'])); print(sys.argv[3], r.get('name'))
elif cmd == 'state':
    print(json.dumps(api({'action': 'resizeState', 'id': sys.argv[2], 'state': sys.argv[3], 'error': sys.argv[4] if len(sys.argv) > 4 else ''}), ensure_ascii=False))
else:
    sys.exit(__doc__)
