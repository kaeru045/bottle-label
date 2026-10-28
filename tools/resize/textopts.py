#!/usr/bin/env python3
"""リサイズ候補に「文字」があるとき：文字例を3案作って管理サイトに送り、「文字案選択」にする（画面で1つ選んでもらう）。

  python3 textopts.py DIR --cand ID --text 'Happy Birthday' --styles pirate,script,pop --spec '<spec>' --checks '<checks>' [--rotate -3,-4,-3] [--no-send]

DIR は finish.py の出力先（design.jpg・placement.json）。DIR/text1.jpg〜text3.jpg（2880×2048）を作る。
書体は背景に合わせて3つ選ぶ（textlayer.py の STYLES）。位置は人物の下（基本）。
--spec があれば、3案それぞれ提出用フォーマット（compose.py）まで作って送る（DIR/opt1〜3/）。画面で「案○にする」を押すと、その場で一覧に登録される。
--spec が無いときだけ、選ばれたあとに candidates.py chosen ID DIR/design.jpg → compose.py → register.py。
"""
import argparse, json, os, subprocess, sys
import cv2
from textlayer import apply, STYLES
from common import api, b64file

NAMES = {'pirate': '海賊風', 'script': '筆記体', 'pop': 'ポップ', 'gold': 'ゴールド', 'elegant': 'エレガント'}
WIDTH = {'pirate': 1500, 'script': 1550, 'pop': 1450, 'gold': 1450, 'elegant': 1500}

ap = argparse.ArgumentParser()
ap.add_argument('dir'); ap.add_argument('--cand', default=''); ap.add_argument('--text', required=True)
ap.add_argument('--styles', default='script,pop,gold'); ap.add_argument('--rotate', default='-3,-4,-3')
ap.add_argument('--no-send', action='store_true')
ap.add_argument('--spec', default=None, help='提出用の仕様（{"tag":..,"seal":..,"ribbon":..}）。あれば3案とも提出用まで作る')
ap.add_argument('--checks', default='[]')
a = ap.parse_args()
styles = [s.strip() for s in a.styles.split(',') if s.strip()][:3]
rots = [float(v) for v in a.rotate.split(',')] + [-3] * 3
text = a.text.strip()
if '|' not in text and len(text) > 18 and ' ' in text:  # 長い文言は2行に
    sp = [i for i, c in enumerate(text) if c == ' ']; m = min(sp, key=lambda i: abs(i - len(text) / 2)); text = text[:m] + '|' + text[m + 1:]
two = '|' in text
res, opts = [], []
for i, st in enumerate(styles):
    if st not in STYLES: sys.exit('不明な飾り方：' + st)
    out = os.path.join(a.dir, f'text{i + 1}.jpg')
    w = WIDTH.get(st, 1500) * (0.62 if two else 1)
    r = apply(os.path.join(a.dir, 'design.jpg'), out, text, st, width=w, rotate=rots[i])
    for _ in range(4):  # 白い範囲からはみ出す・顔に重なるときは小さく
        if not (r['outside_safe'] or r['over_face']): break
        w *= 0.88; r = apply(os.path.join(a.dir, 'design.jpg'), out, text, st, width=w, rotate=rots[i])
    pv = os.path.join(a.dir, f'text{i + 1}_preview.jpg')
    im = cv2.imread(out); cv2.imwrite(pv, cv2.resize(im, (900, 640), interpolation=cv2.INTER_AREA), [cv2.IMWRITE_JPEG_QUALITY, 82])
    r.update(style=st, width=round(w)); res.append(r)
    nm = NAMES.get(st, st)
    op = {'style': nm, 'design': b64file(out, f'文字案{i + 1}_{nm}デザイン画像.jpg'), 'preview': b64file(pv, f'文字案{i + 1}_{nm}_小.jpg')}
    if a.spec is not None:  # 提出用フォーマットまで作る
        od = os.path.join(a.dir, f'opt{i + 1}')
        c = subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'compose.py'), out, '--spec', a.spec, '--checks', a.checks, '--out', od], capture_output=True, text=True)
        if c.returncode != 0: sys.exit('提出用が作れません：' + c.stderr[-500:])
        info = json.load(open(os.path.join(od, 'compose.json'))) if os.path.exists(os.path.join(od, 'compose.json')) else {}
        op['submission'] = b64file(os.path.join(od, 'submission.jpg'), f'文字案{i + 1}_{nm}提出用.jpg')
        op['submissionPreview'] = b64file(os.path.join(od, 'submission_preview.jpg'), f'文字案{i + 1}_{nm}提出用_小.jpg')
        if os.path.exists(os.path.join(od, 'tag.png')): op['tag'] = b64file(os.path.join(od, 'tag.png'), f'文字案{i + 1}_{nm}タグ_' + (info.get('tagName') or '') + '.png')
        r['submission'] = os.path.join(od, 'submission.jpg')
    opts.append(op)
print(json.dumps(res, ensure_ascii=False))
if a.cand and not a.no_send:
    print(json.dumps(api({'action': 'resizeTextOptions', 'id': a.cand, 'options': opts}), ensure_ascii=False))
