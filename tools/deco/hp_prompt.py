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


def build(text='', bg='keep', hint=''):
    """text：入れる文字（そのまま・一字も変えない。2行なら「|」か改行）。bg：keep＝元の背景をそのまま自然に広げる／omakase＝背景お任せ。hint：背景の色や雰囲気（Asanaの指定など）"""
    lines = ['リサイズ用。']
    lines.append('・人物は本人写真のまま使う。顔・髪型・表情・服装・ポーズ・体型を描き直さない、足さない。人物を増やさない。')
    lines.append('・' + FORMAT)
    lines.append('・人物は横の中央。頭のてっぺんからあごまでが画像の高さの約3割の大きさ。')
    if bg == 'omakase':
        lines.append('・背景は新しく作る。' + (hint + 'を基調に、' if hint else '') + '写真の人物の服や色に合う、自然で上品な背景。')
    else:
        lines.append('・背景は元の写真の背景をそのまま横に自然に広げる（同じ色・柄・質感・光のまま続ける）。元に無い物や形を足さない。' + (hint if hint else ''))
    lines.append('・帯・枠・リボン・プレート・ラベル・文字の下地など、背景に飾りを足さない。')
    t = [x.strip() for x in str(text or '').replace('|', '\n').split('\n') if x.strip()]
    if t:
        q = '」「'.join(t)
        lines.append('・文字「' + q + '」を一字も変えずに入れる。ほかの文字は入れない。')
        lines.append('・文字はボトルの正面から全部見えるように、横の中央（左右の端から幅の33%より内側）に収め、文字の横幅は画像の幅の3割以内。長い文言は2段にしてよい（例：名前／Happy Birthday）。')
        lines.append('・文字は人物の顔にかけない。基本は人物の下（胸より下）。文字の飾り（縁取り・光・立体感など）はデザインに合わせてよい。')
    else:
        lines.append('・文字は入れない。')
    return '\n'.join(lines)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--text', default=''); ap.add_argument('--bg', default='keep', choices=['keep', 'omakase']); ap.add_argument('--hint', default='')
    a = ap.parse_args(); print(build(a.text, a.bg, a.hint))
