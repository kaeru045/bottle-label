#!/usr/bin/env python3
"""管理サイト（オリシャン完成デザイン管理）のデザインを呼び出す・修正依頼を出す（Asanaは使わない）。2026-11-10〜
社内アカウントで「デザインの呼び出し・修正」だけに使う（スキル orishan-design-fix）。

  python3 design.py find ジューシー            … 店名・名前・注文・IDで探す（部分一致、新しい順）
  python3 design.py get 248becdf --out DIR     … デザイン画像・提出用・タグ・元写真を保存し、DIR/info.json に案件の情報（仕様・版など）
  python3 design.py fixreq 248becdf '文字を白に' … サイトの「🔧 修正を依頼」と同じ（作り直しは個人アカウントの自動処理が行う）

環境変数 ORISHAN_URL / ORISHAN_KEY（管理サイトのURLと合言葉）が要る。
"""
import argparse, base64, json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'resize'))
from common import api  # noqa: E402

COLS = ['ID', '注文', '店名', '名前', 'テンプレ', '版', 'ステータス', '期日', '登録日時']


def items():
    r = api({'action': 'ui', 'fn': 'list', 'args': []}, timeout=150)
    if not r.get('ok'): sys.exit('管理サイトのエラー: ' + str(r.get('error')))
    return r['v']


def find(q):
    q = q.strip().lower()
    hit = [x for x in items() if q in ' '.join(str(x.get(k, '')) for k in ('ID', '注文', '店名', '名前', 'テンプレ')).lower()]
    return sorted(hit, key=lambda x: x.get('登録日時', ''), reverse=True)


def save(fid, path):
    r = api({'action': 'ui', 'fn': 'getFile', 'args': [fid]}, timeout=200)
    if not r.get('ok'): return None
    v = r['v']; ext = os.path.splitext(v.get('name') or '')[1] or '.jpg'
    p = path + ext; open(p, 'wb').write(base64.b64decode(v['data'])); return p


def get(id_, out):
    x = next((i for i in items() if i.get('ID') == id_), None)
    if not x: sys.exit('見つかりません: ' + id_)
    os.makedirs(out, exist_ok=True)
    files = {}
    for col, nm in [('デザイン画像', 'design'), ('提出用', 'submission'), ('タグ画像', 'tag'), ('元写真', 'photo')]:
        fid = str(x.get(col) or '').strip()
        if fid and not fid.startswith('http'):
            p = save(fid, os.path.join(out, nm))
            if p: files[nm] = p
    try: spec = json.loads(x.get('仕様') or '{}')
    except Exception: spec = {}
    info = {k: x.get(k, '') for k in COLS + ['Asana', 'Decolino', 'メモ', '修正指示', '修正状態']}
    info['仕様'] = spec; info['files'] = files
    json.dump(info, open(os.path.join(out, 'info.json'), 'w'), ensure_ascii=False, indent=1)
    return info


def main():
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest='cmd', required=True)
    f = sub.add_parser('find'); f.add_argument('q')
    g = sub.add_parser('get'); g.add_argument('id'); g.add_argument('--out', required=True)
    r = sub.add_parser('fixreq'); r.add_argument('id'); r.add_argument('fix')
    a = ap.parse_args()
    if a.cmd == 'find':
        for x in find(a.q)[:30]: print(json.dumps({k: x.get(k, '') for k in COLS}, ensure_ascii=False))
    elif a.cmd == 'get':
        print(json.dumps(get(a.id, a.out), ensure_ascii=False, indent=1))
    else:
        x = next((i for i in items() if i.get('ID') == a.id), None)
        if not x: sys.exit('見つかりません: ' + a.id)
        print(json.dumps(api({'action': 'setFix', 'order': x.get('注文'), 'name': x.get('名前'), 'fix': a.fix}, timeout=150), ensure_ascii=False))


if __name__ == '__main__':
    main()
