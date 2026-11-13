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
ap.add_argument('--back', default='', help='裏の文字（compose.py --back と同じ）。仕様に残して、修正の作り直しでも入れる')
ap.add_argument('--back-opt', default='{}', help='裏の文字の向き・書体・色（compose.py --back-opt と同じ）')
ap.add_argument('--template', default='リサイズ', help='テンプレ欄（Decolino・HPの案件を直すときは元のテンプレのまま）')
ap.add_argument('--base-spec', default='', help='元の案件の「仕様」（design.py get の info.json の 仕様）。confirmed・logo などを引き継ぐ')
ap.add_argument('--decolino', default='', help='Decolino欄（元の案件のURLのまま）')
ap.add_argument('--asset', default='', help='元画像ID（おまかせのHP候補は hp-<候補id>）')
ap.add_argument('--fix', default='', help='修正依頼で作り直したときの修正内容（修正指示を消して「修正済み」にする）')
ap.add_argument('--memo', default='Asanaのリサイズ依頼から自動作成（Adobe生成拡張で背景を広げ、元の画像は描き直していません）')
a = ap.parse_args()
d = a.dir
base = re.sub(r'[\\/:*?"<>|#]', '', a.file_base or f'{a.shop}_{a.name}_リサイズ')

dj = os.path.join(d, 'design_back.jpg') if os.path.exists(os.path.join(d, 'design_back.jpg')) else os.path.join(d, 'design.jpg')  # 裏の文字入り（compose.py --back）があればそれを送る
dp = os.path.join(d, 'design_preview.jpg')
im = cv2.imread(dj); k = 900 / max(im.shape[:2])
cv2.imwrite(dp, cv2.resize(im, (round(im.shape[1] * k), round(im.shape[0] * k)), interpolation=cv2.INTER_AREA), [cv2.IMWRITE_JPEG_QUALITY, 82])
info = json.load(open(os.path.join(d, 'compose.json'))) if os.path.exists(os.path.join(d, 'compose.json')) else {}
tagp = os.path.join(d, 'tag.png')
spec, checks = json.loads(a.spec), json.loads(a.checks)
rz = a.template == 'リサイズ'
body = {'order': a.order, 'shop': a.shop, 'name': a.name, 'template': a.template, 'due': a.due, 'asana': a.asana, 'decolino': a.decolino, 'memo': a.memo,
        'asset': a.asset, 'note': ('修正指示「' + a.fix + '」で' + ('リサイズを' if rz else '') + '作り直し') if a.fix else ('リサイズで作り直し' if rz else '作り直し'), 'fixDone': bool(a.fix), 'spec': {**(json.loads(a.base_spec) if a.base_spec else {'confirmed': '', 'logo': ''}), 'spec': spec, 'checks': checks, 'shop': a.shop, 'template': a.template, 'back': a.back, 'backOpt': json.loads(a.back_opt or '{}')},
        'design': b64file(dj, base + 'デザイン画像.jpg'),
        'submission': b64file(os.path.join(d, 'submission.jpg'), base + '提出用.jpg'),
        'designPreview': b64file(dp, base + 'デザイン_プレビュー.jpg'),
        'submissionPreview': b64file(os.path.join(d, 'submission_preview.jpg'), base + '提出用_プレビュー.jpg'),
        'tag': b64file(tagp, base + 'タグ_' + (info.get('tagName') or '') + '.png') if os.path.exists(tagp) else None}
r = api(body)
print(json.dumps({k: v for k, v in r.items() if k != 'data'}, ensure_ascii=False))
if not r.get('ok'):
    if a.cand: api({'action': 'resizeState', 'id': a.cand, 'state': 'エラー', 'error': '管理サイトに登録できませんでした：' + str(r.get('error') or r.get('status'))})
    sys.exit(1)
# 2026-11-07 ユーザー指定：LINEで送る前に元画像との違いのチェック（check.py）。失敗しても登録はそのまま
try:
    import subprocess
    subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'check.py'), 'id', r.get('id', '')], timeout=600)
except Exception as e: print('チェックできませんでした:', e)
if a.cand and not a.fix:
    print(json.dumps(api({'action': 'resizeState', 'id': a.cand, 'state': '作成済み', 'result': r.get('id', '')}), ensure_ascii=False))
