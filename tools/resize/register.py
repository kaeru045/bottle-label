#!/usr/bin/env python3
"""できたデザインと提出用を管理サイトの一覧に登録し、リサイズ候補を「作成済み」にする。

  python3 register.py --cand ID --dir DIR --order 注文 --shop 店名 --name 名前 --due 期日 --asana URL --spec JSON [--checks JSON] [--file-base 名前]

DIR には finish.py の design.jpg と compose.py の submission.jpg・submission_preview.jpg・tag.png があること。
"""
import argparse, json, os, re, sys
import cv2
from common import api, b64file

ap = argparse.ArgumentParser()
for k in ['cand', 'dir', 'order', 'shop', 'name', 'due', 'asana']: ap.add_argument('--' + k, default='')
ap.add_argument('--spec', default='{}'); ap.add_argument('--checks', default='[]'); ap.add_argument('--file-base', default='')
ap.add_argument('--fix', default='', help='修正依頼で作り直したときの修正内容（修正指示を消して「修正済み」にする）')
ap.add_argument('--memo', default='Asanaのリサイズ依頼から自動作成（Adobe生成拡張で背景を広げ、元の画像は描き直していません）')
a = ap.parse_args()
d = a.dir
base = re.sub(r'[\\/:*?"<>|#]', '', a.file_base or f'{a.shop}_{a.name}_リサイズ')

dp = os.path.join(d, 'design_preview.jpg')
im = cv2.imread(os.path.join(d, 'design.jpg')); k = 900 / max(im.shape[:2])
cv2.imwrite(dp, cv2.resize(im, (round(im.shape[1] * k), round(im.shape[0] * k)), interpolation=cv2.INTER_AREA), [cv2.IMWRITE_JPEG_QUALITY, 82])
info = json.load(open(os.path.join(d, 'compose.json'))) if os.path.exists(os.path.join(d, 'compose.json')) else {}
tagp = os.path.join(d, 'tag.png')
spec, checks = json.loads(a.spec), json.loads(a.checks)
body = {'order': a.order, 'shop': a.shop, 'name': a.name, 'template': 'リサイズ', 'due': a.due, 'asana': a.asana, 'decolino': '', 'memo': a.memo,
        'asset': '', 'note': ('修正指示「' + a.fix + '」でリサイズを作り直し') if a.fix else 'リサイズで作り直し', 'fixDone': bool(a.fix), 'spec': {'spec': spec, 'checks': checks, 'shop': a.shop, 'template': 'リサイズ', 'confirmed': '', 'logo': ''},
        'design': b64file(os.path.join(d, 'design.jpg'), base + 'デザイン画像.jpg'),
        'submission': b64file(os.path.join(d, 'submission.jpg'), base + '提出用.jpg'),
        'designPreview': b64file(dp, base + 'デザイン_プレビュー.jpg'),
        'submissionPreview': b64file(os.path.join(d, 'submission_preview.jpg'), base + '提出用_プレビュー.jpg'),
        'tag': b64file(tagp, base + 'タグ_' + (info.get('tagName') or '') + '.png') if os.path.exists(tagp) else None}
r = api(body)
print(json.dumps({k: v for k, v in r.items() if k != 'data'}, ensure_ascii=False))
if not r.get('ok'):
    if a.cand: api({'action': 'resizeState', 'id': a.cand, 'state': 'エラー', 'error': '管理サイトに登録できませんでした：' + str(r.get('error') or r.get('status'))})
    sys.exit(1)
if a.cand and not a.fix:
    print(json.dumps(api({'action': 'resizeState', 'id': a.cand, 'state': '作成済み', 'result': r.get('id', '')}), ensure_ascii=False))
