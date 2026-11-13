#!/usr/bin/env python3
"""Asanaのタスク（名前・仕様欄・説明）から、提出用フォーマットのオプション（spec・checks）を決める（2026-11-13 ユーザー指定：
リボンやデコのオプションが反映されていないことが多いので直す）。どの自動処理も spec を自分で書かず、これの出力を使う。

  python3 spec_rules.py --name 'タスク名' --field '仕様欄' --notes '説明文' [--spec '{"seal":"sl_lx_auto"}'] [--checks '[]']
  → {"spec": {...}, "checks": [...], "why": ["リボン：🎀→水色", ...]}

決まり
- タグ：タスク名に♨️、または名前・仕様・説明に「タグ」。形 ハート→heart／猫・ねこ・🐱→cat／くま・熊・🐻→bear／月・🌙タグ→moon／ボトル型→tagbody／ほか→square。
- ネックシール：白→sl_lx_white／黒→sl_lx_black／金→sl_lx_gold／銀→sl_lx_silver／ほか→sl_lx_auto（「ネックシール」の近くの色だけ見る）。
- リボン：タスク名に🎀、または仕様・説明に「リボン」。色 赤→#b3171c／ピンク→#f4a3c0／黄→#f6d93a／白→#f1f1f1／黒→#222222／ほか・指定なし→orig（水色）。
- デコ：仕様・説明に「デコ」（「デコ物」は除く）→ checks に decoChira（ボトル全体に散らす）。「ネックデコ」「ネックにデコ」→ decoNeck も。
- ネック（キャップ・塗装）の色：「ネックキャップ黒」「ネック塗装 白」など → neck nk_black／nk_white／nk_gold／nk_silver、ピンク・赤・青などは tint。
- タグシール：「タグシール黒／ピンク／白」→ tseal。
渡した spec・checks は残し、足りないものだけ足す（ただしタスクに書かれた色と違う色は書かれた方に直す）。
"""
import argparse, json, re

RIBBON = [('赤', '#b3171c'), ('レッド', '#b3171c'), ('ピンク', '#f4a3c0'), ('黄', '#f6d93a'), ('イエロー', '#f6d93a'), ('白', '#f1f1f1'), ('ホワイト', '#f1f1f1'),
          ('黒', '#222222'), ('ブラック', '#222222'), ('水色', 'orig'), ('青', 'orig'), ('ブルー', 'orig')]
SEAL = [('白', 'sl_lx_white'), ('ホワイト', 'sl_lx_white'), ('黒', 'sl_lx_black'), ('ブラック', 'sl_lx_black'), ('金', 'sl_lx_gold'), ('ゴールド', 'sl_lx_gold'),
        ('銀', 'sl_lx_silver'), ('シルバー', 'sl_lx_silver')]
NECK = [('黒', 'nk_black'), ('ブラック', 'nk_black'), ('白', 'nk_white'), ('ホワイト', 'nk_white'), ('金', 'nk_gold'), ('ゴールド', 'nk_gold'), ('銀', 'nk_silver'),
        ('シルバー', 'nk_silver'), ('ピンク', 'tint:#e8a0b4'), ('赤', 'tint:#d43a4a'), ('レッド', 'tint:#d43a4a'), ('黄', 'tint:#e9b84a'), ('緑', 'tint:#5fae6e'),
        ('水色', 'tint:#7fc4e8'), ('青', 'tint:#3d6fd1'), ('ブルー', 'tint:#3d6fd1'), ('紺', 'tint:#2b3a67'), ('ネイビー', 'tint:#2b3a67'), ('紫', 'tint:#9a6fc8'), ('パープル', 'tint:#9a6fc8')]
TSEAL = [('黒', 'tagseal_black'), ('ブラック', 'tagseal_black'), ('ピンク', 'tagseal_pink'), ('白', 'tagseal_white'), ('ホワイト', 'tagseal_white')]


def color_after(text, key, table, span=8):
    """「key」のすぐ後（span文字以内、区切り記号まで）にある色"""
    for m in re.finditer(key, text):
        seg = re.split(r'[/／、,，\n・]', text[m.end():m.end() + span])[0]
        seg = re.sub(r'^[\s（(:：]*', '', seg)
        for w, v in table:
            if w in seg: return v
    return None


def derive(name='', field='', notes='', spec=None, checks=None):
    spec = dict(spec or {}); checks = list(checks or []); why = []
    body = (field or '') + '\n' + (notes or '')
    allt = (name or '') + '\n' + body
    # タグ
    if '♨' in (name or '') or 'タグ' in allt or 'たぐ' in allt:
        if re.search(r'ハート|♡', allt): k = 'heart'
        elif re.search(r'猫|ねこ|ネコ|🐱|キャット', allt): k = 'cat'
        elif re.search(r'くま|熊|クマ|🐻|ベア', allt): k = 'bear'
        elif re.search(r'月タグ|月の?タグ|🌙タグ|ムーン', allt): k = 'moon'
        elif re.search(r'ボトル型', allt): k = 'tagbody'
        else: k = 'square'
        if spec.get('tag') in (None, '', 'none') or (k != 'square' and spec.get('tag') != k):
            why.append('タグ：%s' % k); spec['tag'] = k
    # ネックシール
    s = color_after(allt, r'ネックシール', SEAL)
    if s and spec.get('seal') != s: spec['seal'] = s; why.append('ネックシール：' + s)
    spec.setdefault('seal', 'sl_lx_auto')
    # リボン
    if '🎀' in (name or '') or re.search(r'リボン', body):
        c = color_after(body, r'リボン', RIBBON) or color_after(name or '', r'🎀', RIBBON, 3)
        if c is None and spec.get('ribbon') not in (None, '', 'none'): c = spec['ribbon']
        c = c or 'orig'
        if spec.get('ribbon') != c: spec['ribbon'] = c; why.append('リボン：' + c)
    # デコ
    if re.search(r'デコ(?!物|レーションなし)', body) or re.search(r'デコ(?!物)', name or ''):
        if re.search(r'ネック(に|の)?デコ|デコ[（(]?ネック', allt):
            if 'decoNeck' not in checks: checks.append('decoNeck'); why.append('デコ：ネック')
        if 'decoChira' not in checks: checks.append('decoChira'); why.append('デコ：チラシ')
    # ネックの色
    n = color_after(body, r'ネックキャップ', NECK) or color_after(body, r'ネック塗装', NECK) or color_after(body, r'キャップ', NECK, 4)
    if n and spec.get('neck') != n: spec['neck'] = n; why.append('ネック：' + n)
    # タグシール
    t = color_after(body, r'タグシール', TSEAL)
    if t and spec.get('tseal') != t: spec['tseal'] = t; why.append('タグシール：' + t)
    return spec, checks, why


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--name', default=''); ap.add_argument('--field', default=''); ap.add_argument('--notes', default='')
    ap.add_argument('--spec', default='{}'); ap.add_argument('--checks', default='[]')
    a = ap.parse_args()
    sp, ch, why = derive(a.name, a.field, a.notes, json.loads(a.spec or '{}'), json.loads(a.checks or '[]'))
    print(json.dumps({'spec': sp, 'checks': ch, 'why': why}, ensure_ascii=False))
