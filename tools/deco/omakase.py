#!/usr/bin/env python3
"""おまかせ（テンプレ番号もリサイズ指定も無い依頼）のデザインを、HP（Decolino管理画面）の「AI生成・完全オリジナル」で作り、
提出用フォーマットと合成して管理サイトに登録する（2026-11-13 ユーザー指定：お任せも自動で作る）。
生成はテスト注文 #04738 の書き込みAPI（hp_api.py と同じ。同時に1件だけ・generated/failed を確かめてから次）。提案・確定はしない。
登録はテンプレ欄「おまかせ」、元画像ID「hp-<候補id>」（修正はこの候補をもとに refine で作り直す）。

  python3 omakase.py make --photo URLかパス --text '名前|BIRTHDAY' [--hint '雰囲気・色'] --order 注文 --shop 店名 --name 名前 --due 期日 --asana URL \
      --spec '{"tag":..,"seal":..}' [--checks '[]'] [--back '..' --back-opt '{}'] --out DIR
  python3 omakase.py fix --id <一覧のID> --out DIR      … 管理サイトの修正依頼（fixes omakase）を、今の候補をもとに作り直して新しい版にする
"""
import argparse, json, os, subprocess, sys, urllib.request
HERE = os.path.dirname(os.path.abspath(__file__))
RZ = os.path.join(HERE, '..', 'resize')
sys.path.insert(0, RZ); sys.path.insert(0, HERE)
from common import api  # noqa: E402
import hp_api  # noqa: E402
from hp_prompt import build, split2, FORMAT  # noqa: E402

PY = sys.executable


def to_jpg(src, dst):
    import cv2
    im = cv2.imread(src, cv2.IMREAD_UNCHANGED)
    if im is None: raise RuntimeError('画像が読めません: ' + src)
    if im.ndim == 3 and im.shape[2] == 4: im = im[:, :, :3]
    cv2.imwrite(dst, im, [cv2.IMWRITE_JPEG_QUALITY, 95])


def fit_photo(src, out):
    """長辺3000px超・3.5MB超はAIが受け付けないことがあるので縮小（check.js fitPhoto と同じ）"""
    import cv2
    im = cv2.imread(src)
    if im is None: raise RuntimeError('写真が読めません')
    k = min(1, 3000 / max(im.shape[:2]))
    p = os.path.join(out, 'photo.jpg')
    cv2.imwrite(p, cv2.resize(im, (round(im.shape[1] * k), round(im.shape[0] * k)), interpolation=cv2.INTER_AREA) if k < 1 else im, [cv2.IMWRITE_JPEG_QUALITY, 90])
    return p


def finish(cand_path, cand_id, a, fix=''):
    d = a.out
    to_jpg(cand_path, os.path.join(d, 'design.jpg'))
    c = [PY, os.path.join(RZ, 'compose.py'), os.path.join(d, 'design.jpg'), '--spec', a.spec, '--checks', a.checks, '--out', d]
    if a.back: c += ['--back', a.back, '--back-opt', a.back_opt or '{}']
    subprocess.run(c, check=True)
    r = [PY, os.path.join(RZ, 'register.py'), '--dir', d, '--order', a.order, '--shop', a.shop, '--name', a.name, '--due', a.due, '--asana', a.asana,
         '--spec', a.spec, '--checks', a.checks, '--template', 'おまかせ', '--asset', 'hp-%s' % cand_id,
         '--base-spec', json.dumps({'confirmed': 'hp-%s' % cand_id, 'logo': ''}), '--file-base', a.file_base or '%s_%s_おまかせ' % (a.shop, a.name),
         '--memo', 'おまかせ：HPの完全オリジナルで自動生成（テスト注文#04738・未提案）。' + (a.hint and ('雰囲気：' + a.hint) or '')]
    if a.back: r += ['--back', a.back, '--back-opt', a.back_opt or '{}']
    if fix: r += ['--fix', fix]
    out = subprocess.run(r, capture_output=True, text=True); print(out.stdout); print(out.stderr, file=sys.stderr)
    if out.returncode: raise RuntimeError('登録できませんでした: ' + out.stdout[-300:])


def make(a):
    os.makedirs(a.out, exist_ok=True)
    src = a.photo
    if src.startswith('http'):
        src = os.path.join(a.out, 'src_raw'); urllib.request.urlretrieve(a.photo, src)
    ph = fit_photo(src, a.out)
    hp_api.wait_idle()
    t = split2(a.text)
    hp_api.send('PATCH', '/brief', {'requiredTexts': '\n'.join(t) if t else 'なし', 'requestText': build(a.text, 'omakase', a.hint)
                + '\n・名前・必ず入れる文字は1つも見落とさず全部入れる。\n・依頼に無い人物・写真・イラストなど、装飾やデザイン以外の画像を付け足さない。'})
    mid = hp_api.upload(ph)
    hp_api.send('PUT', '/reference-images', {'items': [{'mediaAssetId': mid, 'kind': 'photo'}]})
    st = hp_api.send('POST', '/generations', {'candidateCount': a.count, 'kind': 'initial', 'generationMode': 'original'})
    gid, res = hp_api.run_and_fetch(st, os.path.join(a.out, 'cands'))
    if not res: raise RuntimeError('候補画像がありません')
    print(json.dumps({'generation': gid, 'candidates': [{'id': i, 'path': p} for i, p in res]}, ensure_ascii=False))
    pick = res[a.pick - 1] if 0 < a.pick <= len(res) else res[0]
    finish(pick[1], pick[0], a)


def fix(a):
    os.makedirs(a.out, exist_ok=True)
    it = next((x for x in (api({'action': 'fixes', 'omakase': True}).get('items') or []) if x['id'] == a.id), None)
    if not it: raise SystemExit('修正依頼が見つかりません: ' + a.id)
    sp = json.loads(it.get('spec') or '{}'); cand = str(sp.get('confirmed', '')).replace('hp-', '')
    if not cand.isdigit():
        api({'action': 'fixState', 'id': a.id, 'state': 'エラー:元の候補（hp-）が分かりません'}); raise SystemExit('候補不明')
    # これまでの修正指示もまとめて渡す（check.js fixText と同じ考え方。refine は今の候補が土台なので、今回の指示を主にする）
    instr = ('参考画像のデザインをもとに、次の修正だけ行う。人物の顔・髪型・服装は描き直さない。指示に無い所は変えない。\n' + '・' + FORMAT + '\n' +
             '今回の修正：' + str(it['fix']).strip())
    api({'action': 'fixState', 'id': a.id, 'state': '生成中|%d|' % int(__import__('time').time() * 1000)})
    try:
        hp_api.wait_idle()
        st = hp_api.send('POST', '/refine', {'bases': [{'candidateId': int(cand), 'instruction': instr}], 'imageCount': 1})
        gid, res = hp_api.run_and_fetch(st, os.path.join(a.out, 'cands'))
        if not res: raise RuntimeError('候補画像がありません')
        ns = argparse.Namespace(out=a.out, spec=json.dumps(sp.get('spec') or {}), checks=json.dumps(sp.get('checks') or []), back=sp.get('back') or '',
                                back_opt=json.dumps(sp.get('backOpt') or {}), order=it['order'], shop=it.get('shop') or sp.get('shop') or '', name=it['name'],
                                due=it.get('due') or '', asana=it.get('asana') or '', file_base='%s_%s_おまかせ_v%d' % (it.get('shop') or '', it['name'], int(it.get('version') or 1) + 1), hint='')
        finish(res[0][1], res[0][0], ns, fix=str(it['fix']))
    except Exception as e:
        api({'action': 'fixState', 'id': a.id, 'state': 'エラー:' + str(e)[:200]}); raise


def main():
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest='cmd', required=True)
    m = sub.add_parser('make')
    for k in ['photo', 'out']: m.add_argument('--' + k, required=True)
    for k in ['text', 'hint', 'order', 'shop', 'name', 'due', 'asana', 'back', 'file-base']: m.add_argument('--' + k, default='')
    m.add_argument('--spec', default='{"seal":"sl_lx_auto"}'); m.add_argument('--checks', default='[]'); m.add_argument('--back-opt', default='{}')
    m.add_argument('--count', type=int, default=1); m.add_argument('--pick', type=int, default=1)
    f = sub.add_parser('fix'); f.add_argument('--id', required=True); f.add_argument('--out', required=True)
    a = ap.parse_args()
    try:
        make(a) if a.cmd == 'make' else fix(a)
    except SystemExit:
        raise
    except Exception as e:  # 2026-11-13 ユーザー指定：作れなかった理由はLINEへ（修正の失敗は fixState エラーで管理サイトが送る）
        if a.cmd == 'make':
            try: api({'action': 'failNote', 'text': '⚠️ デザインを作れませんでした（おまかせ）：%s %s\n理由：%s' % (a.shop, a.name, str(e)[:200]), 'key2': 'om' + a.asana + str(e)[:80]})
            except Exception: pass
        raise


if __name__ == '__main__':
    main()
