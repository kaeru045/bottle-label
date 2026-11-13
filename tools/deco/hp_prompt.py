#!/usr/bin/env python3
"""HP（Decolino管理画面）の「AI生成・完全オリジナル」でリサイズを作るときに、毎回「顧客の要望」へ入れる決まった文面。
2026-11-08 ユーザー指定：以前作ったリサイズ用のプロンプトを、HPで作るときも毎回入れる。
中身は今までのルール（必ず守るフォーマット・正面から文字が全部見える・帯や枠を足さない・人物は描き直さない）をまとめたもの。

  python3 hp_prompt.py --text 'カイトBIRTHDAY' [--bg omakase|keep] [--hint '黒とシルバー']   … 文面を表示
  from hp_prompt import build; build(text, bg='keep', hint='')

「必ず入れる文字」欄には文字だけ（行が分かれていれば改行）、「顧客の要望」欄にはこの文面を入れる。
"""
import argparse

# 仕上がり1440×1024で必ず守るフォーマット（tools/resize/common.py・CLAUDE.md と同じ数値）
FORMAT = ('横長（1440×1024）。上の帯（上端から254px＝高さの約25%）と下の帯（917px より下＝下端から約10%）には顔・文字を入れない。'
          '左右の端（それぞれ134px＝幅の約9%）は背景だけにする（ボトルの裏側になる部分）。頭のてっぺんは上端から270pxくらい。')


PHRASE = r'(Happy\s*Birthday|HAPPY\s*BIRTHDAY|BIRTHDAY|Birthday|Happy\s*Wedding|Wedding|Anniversary|Congratulations|Thank\s*you|Love)'


def split2(text):
    """2026-11-08 ユーザー指定：長い文言は「名前」と「BIRTHDAY」などを分けて2段にする。文字は一字も変えない（区切るだけ）。"""
    import re
    s = str(text or '').strip()
    if '|' in s or '\n' in s:
        return [x.strip() for x in s.replace('|', '\n').split('\n') if x.strip()]
    if len(s) <= 8:
        return [s] if s else []
    m = re.search(PHRASE, s)
    if m and 0 < m.start():
        return [s[:m.start()].strip(), s[m.start():].strip()]
    if m and m.end() < len(s):
        return [s[:m.end()].strip(), s[m.end():].strip()]
    m = re.search(r'(?<=[^\x00-\x7f])(?=[A-Za-z])|(?<=[A-Za-z])(?=[^\x00-\x7f])', s)  # 日本語と英字の境目
    return [s[:m.start()], s[m.start():]] if m else [s]


def size_rule(t):
    import re
    if len(t) >= 2:
        nm = next((x for x in t if not re.search(PHRASE, x)), t[0])
        return ('・文字は2段：上の段「' + t[0] + '」、下の段「' + t[1] + '」。名前の「' + nm + '」を大きく、もう一方の段は名前より小さく。'
                '2段まとめた横幅は画像の幅の3割以内（約430px）、2段まとめた高さは画像の高さの2割以内。長い段に合わせて全体を小さくする。')
    return '・文字の横幅は画像の幅の3割以内（約430px）。はみ出すなら文字を小さくする。'


def build(text='', bg='keep', hint=''):
    """text：入れる文字（そのまま・一字も変えない。2行なら「|」か改行）。bg：keep＝元の背景をそのまま自然に広げる／omakase＝背景お任せ。hint：背景の色や雰囲気（Asanaの指定など）"""
    lines = ['おまかせのオリジナルデザイン（新しく作る）。' if bg == 'omakase' else 'リサイズ用。']
    lines.append('・人物は本人写真のまま使う。顔・髪型・表情・服装・ポーズ・体型を描き直さない、足さない。人物を増やさない。')
    lines.append('・' + FORMAT)
    lines.append('・人物は横の中央。頭のてっぺんからあごまでが画像の高さの約3割の大きさ。')
    if bg == 'omakase':
        lines.append('・背景は新しく作る。' + (hint + 'を基調に、' if hint else '') + '写真の人物の服や色に合う、自然で上品な背景。')
    else:
        lines.append('・背景は元の写真の背景をそのまま横に自然に広げる（同じ色・柄・質感・光のまま続ける）。元に無い物や形を足さない。' + (hint if hint else ''))
    lines.append('・帯・枠・リボン・プレート・ラベル・文字の下地など、背景に飾りを足さない。')
    t = split2(text)
    if t:
        q = '」「'.join(t)
        lines.append('・文字「' + q + '」を一字も変えずに入れる。ほかの文字は入れない。')
        lines.append('・文字はボトルの正面から全部見えるように、横の中央（左右の端から幅の33%より内側＝475〜965px）に収める。')
        lines.append(size_rule(t))
        lines.append('・文字は人物の顔にかけない。基本は人物の下（胸より下）で、文字の下の端は917pxより上。文字の飾り（縁取り・光・立体感など）はデザインに合わせてよい。')
    else:
        lines.append('・文字は入れない。')
    return '\n'.join(lines)


def fix(text):
    """生成済みの画像を参考画像にして、文字だけ直すときの「顧客の要望」。"""
    t = split2(text)
    return '\n'.join(['文字だけの修正。参考画像のデザインをそのまま使う。',
                      '・人物・顔・背景・色・構図は一切変えない。描き直さない。',
                      '・' + FORMAT,
                      '・今の文字を消し、文字「' + '」「'.join(t) + '」を一字も変えずに入れ直す。書体・色・飾りは今の文字に合わせる。',
                      '・横の中央（475〜965px の内側）に収める。',
                      size_rule(t),
                      '・文字は顔にかけない。文字の下の端は917pxより上。'])


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--text', default=''); ap.add_argument('--bg', default='keep', choices=['keep', 'omakase']); ap.add_argument('--hint', default='')
    ap.add_argument('--fix', action='store_true', help='文字だけ直す文面')
    a = ap.parse_args(); print(fix(a.text) if a.fix else build(a.text, a.bg, a.hint))
