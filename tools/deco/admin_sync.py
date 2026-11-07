#!/usr/bin/env python3
"""Decolino管理画面の「AI生成」でできた画像を、オリシャン完成デザイン管理に取り込む（ログイン不要版）。
2026-11-08 ユーザー指定：スタッフのログインではなく、開発の方に発行してもらった読み取り専用トークンを使う。
トークンは管理サイト（Apps Script）のスクリプトプロパティ ADMIN_API_TOKEN にだけ置き、ここからは管理サイトの
action:'admin'（GETの中継）と action:'adminImg'（画像）を通して読む。外部API：https://api.reserve-viva-decolino.com/external/v1

  python3 admin_sync.py --dry            … 登録せずに対象だけ表示
  python3 admin_sync.py [--max 10]       … 未登録の生成案を最大10件登録（提出用フォーマットは tools/resize/compose.py で作る）

ルールは tools/deco/admin.js（ブラウザ版）と同じ：
- 案の画像ID（candidate id）を「元画像ID」に 'adm-<id>' で記録し、同じ案は二度登録しない
- 同じ注文番号＋名前で確定（確認OK・入稿済み・完了）した案件があれば、その注文・名前の案は取り込まない（LINEで選んで消した案を戻さない）
- ADMIN_SKIP の案・SKIP_ORDERS の注文（テスト注文）は取り込まない
- 外部APIにはお客様の名前・連絡先・金額が入っていない。店名は、管理サイトに同じ注文の案件があればその店名を使う
- 候補の imageUrl は10分で切れるので、候補一覧を取ったらすぐ画像を保存する
"""
import argparse, base64, json, os, re, subprocess, sys, tempfile, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'resize'))
from common import api, b64file  # noqa: E402

ADMIN_SKIP = {1061, 1062, 1063, 1064, 1065, 1066, 1076, 1077, 1078, 1079, 1080, 1081}  # 試作・サンプル（admin.js と同じ）
SKIP_ORDERS = {4688}  # テスト注文（外部APIには名前が無いので番号で除く）
# 2026-11-08 ユーザー指定：取り込みが止まっていた間に溜まった案（47件）は取り込まず、これより後に生成された案だけ取り込む
SINCE = '2026-11-07T15:20:00Z'


def A(path):
    r = api({'action': 'admin', 'path': path}, timeout=150)
    if not r.get('ok'):
        raise RuntimeError('管理画面API ' + path + ' ' + str(r.get('status') or '') + ' ' + str(r.get('error') or '')[:150])
    return r['data']


def img(url, path):
    r = api({'action': 'adminImg', 'url': url}, timeout=200)
    if not r.get('ok'):
        raise RuntimeError('画像取得失敗 ' + str(r.get('status') or r.get('error')))
    open(path, 'wb').write(base64.b64decode(r['data']))
    return path


def spec_of(c):
    t = ' '.join([x for x in [c.get('tagShape')] + [d.get('tagShape') for d in (c.get('details') or [])] if x])
    has_tag = bool(t) or any(d.get('hasTagOption') for d in (c.get('details') or []))
    tag = ('heart' if re.search('ハート|heart', t, re.I) else 'cat' if re.search('猫|ねこ|cat', t, re.I) else 'bear' if re.search('くま|熊|bear', t, re.I)
           else 'moon' if re.search('月|moon', t, re.I) else 'tagbody' if re.search('ボトル|bottle', t, re.I) else 'square' if has_tag else '')
    n = str(c.get('neckSeal') or '')
    seal = ('sl_lx_white' if re.search('白|ホワイト|white', n, re.I) else 'sl_lx_black' if re.search('黒|ブラック|black', n, re.I)
            else 'sl_lx_gold' if re.search('金|ゴールド|gold', n, re.I) else 'sl_lx_silver' if re.search('銀|シルバー|silver', n, re.I) else 'sl_lx_auto')
    s = {'seal': seal}
    if tag: s['tag'] = tag
    return s


def safe(s):
    return re.sub(r'[\\/:*?"<>|#]', '', s)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--max', type=int, default=10); ap.add_argument('--days', type=int, default=30); ap.add_argument('--dry', action='store_true')
    a = ap.parse_args()
    tpls = {t['id']: t.get('code') for t in A('/ai-generations/templates').get('items', [])}
    src = api({'action': 'sources'}, timeout=150)
    if not src.get('ok'): sys.exit('管理サイトに接続できません ' + str(src.get('error')))
    items = src.get('items', [])
    have = {str(x.get('asset') or '') for x in items}
    picked = {str(x.get('order')) + '|' + re.sub(r'（案\d+）$', '', str(x.get('name') or '')) for x in items if re.search('確認OK|入稿済み|完了', str(x.get('status') or ''))}
    shop_of = {}
    for x in items:
        if x.get('order') and x.get('shop'): shop_of.setdefault(str(x['order']), x['shop'])
    since = time.time() - a.days * 86400
    orders = []
    for o in A('/orders?limit=100&orderKind=original_champagne&sortBy=createdAt&sortDirection=desc').get('items', []):
        if o.get('canceledAt') or o.get('orderKind') != 'original_champagne' or o.get('id') in SKIP_ORDERS: continue
        if re.search('complete|delivered|cancel|closed', str(o.get('status'))): continue
        t = o.get('placedAt') or o.get('createdAt') or ''
        try:
            if time.mktime(time.strptime(t[:19], '%Y-%m-%dT%H:%M:%S')) < since: continue
        except Exception: pass
        orders.append(o)
    res, done = [], 0
    tmp = tempfile.mkdtemp(prefix='adm_')
    for o in orders:
        if done >= a.max: break
        try: gens = [g for g in A('/ai-generations?orderId=%d' % o['id']).get('items', []) if g.get('status') == 'generated' and str(g.get('requestedAt') or '') > SINCE]
        except Exception: continue
        if not gens: continue
        od = A('/orders/%d' % o['id'])
        latest = {}
        for g in gens:
            k = str(g.get('orderContentId'))
            if k not in latest or g.get('requestedAt', '') > latest[k].get('requestedAt', ''): latest[k] = g
        contents = od.get('contents') or []
        dues = {x.get('contentCode'): x.get('shippingDueDate') for x in ((od.get('boardSummary') or {}).get('shippingDueCases') or [])}
        for cid, g in latest.items():
            if done >= a.max: break
            c = next((x for x in contents if str(x.get('id')) == cid), contents[0] if contents else {})
            if c.get('canceledAt'): continue
            cands = [x for x in A('/ai-generations/%d/candidates' % g['id']).get('items', []) if x.get('imageUrl')]
            for cd in cands:
                if done >= a.max: break
                asset = 'adm-%s' % cd['id']
                if asset in have or cd['id'] in ADMIN_SKIP: continue
                # テンプレが分からない案（完全オリジナルなど）は「HP生成」とする。空のままだと管理サイトで同じ注文・名前のほかの案件（リサイズなど）を上書きしてしまう（2026-11-08 実際に起きた）
                tcode = tpls.get(cd.get('aiTemplateId')) or ((c.get('customerDesign') or {}).get('templateCode')) or 'HP生成'
                let = c.get('lettering') or {}
                label = re.sub(r'\s*\n\s*', ' ', str((not let.get('noText') and let.get('label')) or c.get('title') or '')).strip()
                base = label + ('（%s）' % c.get('branchNo') if len(contents) > 1 else '')
                order_no = o.get('displayOrderNumber') or ''
                if order_no + '|' + base in picked: continue
                name = (base + ('（案%s）' % cd.get('candidateNo') if len(cands) > 1 else ''))[:80]
                spec = spec_of(c)
                shop = shop_of.get(order_no, '')
                if a.dry:
                    res.append(' '.join([order_no, name, tcode, json.dumps(spec, ensure_ascii=False), str(cd.get('status')), shop])); continue
                d = os.path.join(tmp, str(cd['id'])); os.makedirs(d, exist_ok=True)
                try:
                    raw = img(cd['imageUrl'], os.path.join(d, 'raw.png'))  # 10分で切れるのですぐ保存
                    import cv2
                    im = cv2.imread(raw); cv2.imwrite(os.path.join(d, 'design.jpg'), im, [cv2.IMWRITE_JPEG_QUALITY, 95])
                    cv2.imwrite(os.path.join(d, 'dp.jpg'), cv2.resize(im, None, fx=900 / max(im.shape[:2]), fy=900 / max(im.shape[:2]), interpolation=cv2.INTER_AREA), [cv2.IMWRITE_JPEG_QUALITY, 82])
                    p = subprocess.run([sys.executable, os.path.join(HERE, '..', 'resize', 'compose.py'), os.path.join(d, 'design.jpg'), '--spec', json.dumps(spec), '--out', d],
                                       capture_output=True, text=True, timeout=600)
                    if p.returncode != 0 or not os.path.exists(os.path.join(d, 'submission.jpg')): raise RuntimeError('提出用の合成に失敗 ' + (p.stderr or p.stdout)[-200:])
                    fb = safe(order_no + '_' + name + '_' + tcode)
                    body = {'order': order_no, 'shop': shop, 'name': name, 'template': tcode, 'due': dues.get(c.get('contentCode')) or '', 'asana': '',
                            'decolino': 'https://admin.reserve-viva-decolino.com/ai/%d/generate' % o['id'], 'memo': '管理画面のAI生成から自動で登録（%s）' % (cd.get('status') or ''),
                            'asset': asset, 'note': '管理画面のAI生成の新しい案', 'fixDone': False, 'force': False,
                            'spec': {'spec': spec, 'checks': [], 'shop': shop, 'template': tcode, 'confirmed': asset, 'logo': '', 'logoPos': None, 'back': '', 'backOpt': {}},
                            'design': b64file(os.path.join(d, 'design.jpg'), fb + 'デザイン画像.jpg'), 'submission': b64file(os.path.join(d, 'submission.jpg'), fb + '提出用.jpg'),
                            'designPreview': b64file(os.path.join(d, 'dp.jpg'), fb + 'デザイン_プレビュー.jpg'),
                            'submissionPreview': b64file(os.path.join(d, 'submission_preview.jpg'), fb + '提出用_プレビュー.jpg')}
                    tg = os.path.join(d, 'tag.png')
                    if os.path.exists(tg): body['tag'] = b64file(tg, fb + 'タグ.png')
                    r = api(body, timeout=290)
                except Exception as e:
                    r = {'ok': False, 'error': str(e)}
                res.append('%s %s（%s）：%s' % (order_no, name, tcode, ('変更なし' if r.get('unchanged') else ('v%s に更新' % r.get('version')) if r.get('updated') else '登録') if r.get('ok') else '失敗 ' + str(r.get('error') or r.get('status'))[:150]))
                have.add(asset); done += 1
    print(json.dumps(res or ['新しい生成案なし'], ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
