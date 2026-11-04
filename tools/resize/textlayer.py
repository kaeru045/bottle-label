#!/usr/bin/env python3
"""デザイン画像（2880×2048）に文字を入れる。文字は書体で描く（AIに描かせないので綴りが崩れない）。

  python3 textlayer.py DESIGN.jpg OUT.jpg --text 'Happy|Birthday' --style pirate --cx 640 --cy 700 [--width 700] [--rotate -6]

--text   … 「|」で改行
--style  … 下の STYLES のどれか（背景に合わせて選ぶ）
--cx/--cy… 文字のまとまりの中心（2880×2048 の座標）。省略すると「人物の下」（基本の位置）：
            placement.json の大事な範囲の中央の真下、白い範囲の下端（y 1834）にそろえる
--placement … place.py の出力先（placement.json）。省略時はデザイン画像と同じフォルダ
--width  … 文字のまとまりの横幅（px）。この幅に収まるよう自動で大きさを決める
--rotate … 傾き（度）
--color1/--color2 … 色を上書き（背景から拾った色を使うとき）
書体は fonts/（tools/resize/fonts、なければ npm の @fontsource から取得）を使う。
"""
import argparse, asyncio, base64, json, os, re, subprocess, sys, glob
import cv2, numpy as np
from playwright.async_api import async_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
FONTDIR = os.environ.get('RESIZE_FONTS', os.path.join(HERE, 'fonts'))
W, H = 2880, 2048
SAFE = (268, 508, 2612, 1834)

# 書体（@fontsource のパッケージ名）。jp＝日本語（ひらがな・カタカナ・漢字）も書ける
FONTS = {'pirata': 'pirata-one', 'vibes': 'great-vibes', 'bangers': 'bangers', 'dancing': 'dancing-script',
         'cinzel': 'cinzel-decorative', 'pacifico': 'pacifico', 'caveat': 'caveat', 'marker': 'permanent-marker',
         'lobster': 'lobster', 'fredoka': 'fredoka', 'fraktur': 'unifrakturmaguntia', 'rye': 'rye', 'luckiest': 'luckiest-guy',
         'playfair': 'playfair-display',
         'mochiy': 'mochiy-pop-one', 'zenantique': 'zen-antique', 'yuji': 'yuji-syuku', 'zenmaru': 'zen-maru-gothic',
         'hachimaru': 'hachi-maru-pop', 'dela': 'dela-gothic-one',
         # 高級感（2026-11-02 追加）
         'cormorant': 'cormorant-garamond', 'bodoni': 'bodoni-moda', 'cinzelr': 'cinzel', 'allura': 'allura', 'parisienne': 'parisienne',
         'italiana': 'italiana', 'marcellus': 'marcellus', 'shippori': 'shippori-mincho', 'oldmincho': 'zen-old-mincho', 'kaisei': 'kaisei-decol',
         # ヴィジュアル系・ホストの名前ロゴ風（2026-11-04 追加）
         'chokoku': 'chokokutai', 'reggae': 'reggae-one',
         # クール系（2026-11-04 追加）
         'murecho': 'murecho', 'zenkaku': 'zen-kaku-gothic-new', 'dotgothic': 'dotgothic16', 'rocknroll': 'rocknroll-one',
         'michroma': 'michroma', 'orbitron': 'orbitron', 'rajdhani': 'rajdhani'}
JPFONTS = {'mochiy', 'zenantique', 'yuji', 'zenmaru', 'hachimaru', 'dela', 'shippori', 'oldmincho', 'kaisei', 'chokoku', 'reggae', 'murecho', 'zenkaku', 'dotgothic', 'rocknroll'}
# 小文字が無く、全部大文字に見えてしまう書体。依頼の文字は変えないので、小文字を含む文言には使わない
CAPSFONTS = {'bangers', 'cinzel', 'luckiest', 'marker', 'cinzelr'}


def changes_case(style, text):
    return STYLES[style]['font'] in CAPSFONTS and any(c.islower() for c in text)

G = lambda *c: 'linear-gradient(180deg,' + ','.join(c) + ')'
SH = lambda *d: ' '.join(f'drop-shadow({x})' for x in d)
# 飾り方。fill は文字の色（グラデーション）、stroke は縁取り（strokew は文字の大きさに対する太さ）、shadow は影・光
# jp＝日本語の名前（管理サイトに出る）、mood＝合う背景（定期実行が選ぶときの目安）
STYLES = {
    # 英字
    'pirate': dict(jp='海賊風', mood='海賊・冒険・宝・木・ヴィンテージ', font='pirata', weight=400, fill=G('#fff6c8 0%', '#ffd75a 38%', '#d49a1c 62%', '#7a4a0c 100%'),
                   stroke='#3b2108', strokew=0.055, shadow=SH('0 .06em 0 #2a1605', '0 .12em .18em rgba(0,0,0,.55)'), spacing='0.02em', line=0.95),
    'script': dict(jp='筆記体', mood='写真全般・上品・大人・空や海', font='vibes', weight=400, fill=G('#ffffff', '#fff4e0'), stroke='', strokew=0,
                   shadow=SH('0 0 .04em rgba(150,20,20,.95)', '0 .05em .06em rgba(120,15,15,.9)', '0 .12em .3em rgba(0,0,0,.45)'), spacing='0', line=0.9),
    'pop': dict(jp='ポップ', mood='子ども・元気・カラフル・アニメ風', font='bangers', weight=400, fill=G('#ff5a3c', '#d7191c 60%', '#a80d14'), stroke='#ffffff', strokew=0.11,
                shadow=SH('.05em .07em 0 #13233f', '0 .1em .2em rgba(0,0,0,.45)'), spacing='0.04em', line=0.92),
    'gold': dict(jp='ゴールド', mood='夜・ホスト・キャバ・高級・黒背景・周年', font='cinzel', weight=700, fill=G('#fffbe6 0%', '#f3d27a 35%', '#b9892c 60%', '#fff0b8 80%', '#a87a26 100%'), stroke='', strokew=0,
                 shadow=SH('0 .04em .02em rgba(60,30,0,.8)', '0 0 .25em rgba(255,220,140,.6)'), spacing='0.03em', line=1.0),
    'elegant': dict(jp='エレガント', mood='花・ピンク・女性・ウェディング', font='dancing', weight=700, fill=G('#ffffff', '#ffe3ec'), stroke='', strokew=0,
                    shadow=SH('0 0 .1em rgba(255,150,190,.95)', '0 .06em .2em rgba(80,0,40,.6)'), spacing='0', line=0.95),
    'neon': dict(jp='ネオン', mood='夜景・クラブ・ネオン・暗い背景・パーティー', font='pacifico', weight=400, fill=G('#ffffff', '#ffe6fb'), stroke='', strokew=0,
                 shadow=SH('0 0 .03em #fff', '0 0 .12em #ff3fd2', '0 0 .3em #ff2fb9', '0 0 .6em rgba(160,40,255,.8)'), spacing='0', line=1.0),
    'hand': dict(jp='手書き', mood='ナチュラル・カフェ・日常写真・やさしい', font='caveat', weight=700, fill=G('#ffffff', '#fdf6ea'), stroke='', strokew=0,
                 shadow=SH('0 .03em 0 rgba(60,40,20,.7)', '0 .08em .2em rgba(0,0,0,.45)'), spacing='0.01em', line=0.95),
    'street': dict(jp='ストリート', mood='ストリート・スポーツ・HIPHOP・コンクリート', font='marker', weight=400, fill=G('#fff36b', '#ffb400 60%', '#ff7a00'), stroke='#111111', strokew=0.07,
                   shadow=SH('.06em .06em 0 #111', '0 .1em .25em rgba(0,0,0,.5)'), spacing='0.02em', line=0.95),
    'retro': dict(jp='レトロ', mood='昭和・アメリカン・ダイナー・ヴィンテージ', font='lobster', weight=400, fill=G('#fff8e7', '#ffd9a0'), stroke='#b3261e', strokew=0.06,
                  shadow=SH('.07em .07em 0 #5a1410', '0 .12em .22em rgba(0,0,0,.4)'), spacing='0.01em', line=0.95),
    'cute': dict(jp='かわいい', mood='赤ちゃん・パステル・ゆめかわ・動物', font='fredoka', weight=700, fill=G('#ffb6d5', '#ff7fb0'), stroke='#ffffff', strokew=0.1,
                 shadow=SH('0 .05em 0 #f06aa0', '0 .1em .2em rgba(120,0,60,.35)'), spacing='0.02em', line=0.95),
    'gothic': dict(jp='ゴシック', mood='ダーク・ロック・ヴィジュアル系・教会・ハロウィン', font='fraktur', weight=400, fill=G('#ffffff', '#c9ccd3 50%', '#7c818c'), stroke='', strokew=0,
                   shadow=SH('0 .04em 0 #111', '0 0 .2em rgba(0,0,0,.9)', '0 0 .45em rgba(150,0,30,.6)'), spacing='0.01em', line=1.0),
    'western': dict(jp='ウエスタン', mood='西部劇・カウボーイ・砂漠・木目', font='rye', weight=400, fill=G('#fbe6b4', '#d9a55a 55%', '#9a5d22'), stroke='#3a1f0b', strokew=0.05,
                    shadow=SH('.05em .06em 0 #2a1508', '0 .1em .2em rgba(0,0,0,.5)'), spacing='0.03em', line=1.0),
    'comic': dict(jp='コミック', mood='漫画・ゲーム・ヒーロー・楽しい', font='luckiest', weight=400, fill=G('#fff45c', '#ffcc00'), stroke='#111111', strokew=0.09,
                  shadow=SH('.07em .08em 0 #e8390e', '.11em .12em 0 #111'), spacing='0.03em', line=0.95),
    'luxury': dict(jp='ラグジュアリー', mood='シャンパン・ホテル・黒×金・大人の高級感', font='playfair', weight=700, fill=G('#fffdf4', '#ead9a8 45%', '#b08d47'), stroke='', strokew=0,
                   shadow=SH('0 .03em 0 rgba(40,25,0,.85)', '0 .1em .25em rgba(0,0,0,.6)'), spacing='0.06em', line=1.0),
    # 高級感（2026-11-02 追加。影・光・浮き彫りなどの効果つき）
    'champagne': dict(jp='シャンパンゴールド', mood='高級・シャンパン・ホスト・キャバ・黒や濃い背景', font='cormorant', weight=700,
                      fill=G('#fffaf0 0%', '#f6e3b0 30%', '#d4af62 55%', '#fff3cf 75%', '#b88a3e 100%'), stroke='', strokew=0,
                      shadow=SH('0 .025em 0 rgba(70,45,10,.9)', '0 .08em .12em rgba(0,0,0,.65)', '0 0 .3em rgba(255,225,160,.45)'), spacing='0.05em', line=1.0),
    'platinum': dict(jp='プラチナ', mood='高級・モノトーン・黒×銀・クール・大人', font='bodoni', weight=700,
                     fill=G('#ffffff 0%', '#e9edf2 35%', '#a9b1bb 55%', '#f7f9fb 75%', '#8b939d 100%'), stroke='', strokew=0,
                     shadow=SH('0 .03em 0 rgba(20,24,30,.9)', '0 .1em .18em rgba(0,0,0,.7)'), spacing='0.04em', line=1.0),
    'royal': dict(jp='ロイヤル', mood='高級・周年・王冠・黒×金・重厚（大文字だけの文言のみ）', font='cinzelr', weight=700,
                  fill=G('#fff8dc 0%', '#f1cf72 40%', '#a8771f 62%', '#ffe9a8 82%', '#8a5e15 100%'), stroke='#2b1a05', strokew=0.035,
                  shadow=SH('0 .12em .2em rgba(0,0,0,.65)'), tshadow='0 .015em 0 #5a3b0a, 0 .03em 0 #4a3008, 0 .045em 0 #3a2506, 0 .06em 0 #2b1a05', spacing='0.06em', line=1.0),
    'allura': dict(jp='ゴールド筆記体', mood='高級・上品・女性・誕生日・ピンクや黒', font='allura', weight=400,
                   fill=G('#fffaf0', '#f3d58b 50%', '#c99a3e'), stroke='', strokew=0,
                   shadow=SH('0 .02em 0 rgba(80,50,10,.9)', '0 0 .12em rgba(255,230,170,.75)', '0 .08em .2em rgba(0,0,0,.55)'), spacing='0', line=0.95),
    'rosegold': dict(jp='ローズゴールド', mood='高級・ピンク・女性・キャバ・ゆめかわ大人', font='parisienne', weight=400,
                     fill=G('#fff1ee', '#f2b8a8 45%', '#b9705e'), stroke='', strokew=0,
                     shadow=SH('0 .02em 0 rgba(90,35,30,.85)', '0 0 .14em rgba(255,200,190,.7)', '0 .08em .2em rgba(0,0,0,.5)'), spacing='0', line=0.95),
    'mode': dict(jp='モード', mood='高級・ファッション・雑誌・ハイブランド・白や淡い背景', font='italiana', weight=400,
                 fill=G('#ffffff', '#f4f1ea'), stroke='', strokew=0,
                 shadow=SH('0 0 .02em rgba(0,0,0,.9)', '0 .05em .1em rgba(0,0,0,.6)', '0 0 .35em rgba(0,0,0,.35)'), spacing='0.12em', line=1.05),
    'engrave': dict(jp='彫刻ゴールド', mood='高級・クラシック・ホテル・大理石・重厚', font='marcellus', weight=400,
                    fill=G('#fdf3d6', '#d9b46a 50%', '#9c7330'), stroke='', strokew=0,
                    shadow=SH('-.02em -.02em 0 rgba(255,250,230,.8)', '.03em .04em 0 rgba(40,25,5,.9)', '0 .1em .2em rgba(0,0,0,.55)'), spacing='0.05em', line=1.0),
    # 日本語も書ける高級感
    'jgold': dict(jp='金の明朝', mood='日本語・高級・ホスト・キャバ・和モダン・黒背景', font='shippori', weight=800,
                  fill=G('#fffaf0 0%', '#f6dc9a 35%', '#c8963c 60%', '#fff0c0 80%', '#a87a26 100%'), stroke='#2a1a06', strokew=0.03,
                  shadow=SH('0 .02em 0 rgba(60,35,5,.9)', '0 .08em .16em rgba(0,0,0,.65)', '0 0 .25em rgba(255,220,150,.4)'), spacing='0.06em', line=1.15),
    'jplatinum': dict(jp='銀の明朝', mood='日本語・高級・モノトーン・クール', font='oldmincho', weight=700,
                      fill=G('#ffffff', '#dfe4ea 45%', '#9aa3ae'), stroke='#15181d', strokew=0.03,
                      shadow=SH('0 .02em 0 rgba(10,12,16,.9)', '0 .08em .16em rgba(0,0,0,.65)'), spacing='0.06em', line=1.15),
    'jrose': dict(jp='ローズの明朝', mood='日本語・高級・ピンク・女性・上品', font='kaisei', weight=700,
                  fill=G('#fff3f0', '#f0b3a5 50%', '#b06a5a'), stroke='#ffffff', strokew=0.05,
                  shadow=SH('0 .03em 0 rgba(120,50,40,.8)', '0 .08em .18em rgba(0,0,0,.45)'), spacing='0.05em', line=1.15),
    # 名前ロゴ風（2026-11-04 追加）：1行目＝日本語の名前をとがった書体でメタリック、2行目以降＝ローマ字を太い斜体で小さく。
    # 例 --text '如月サク|Saku Kisaragi'。sub は2行目以降の書体（1行だけなら使われない）
    'vkei': dict(jp='ヴィジュアル系ネーム', mood='日本語の名前＋ローマ字・ホスト・ヴィジュアル系・夜桜・紫やピンクの暗い背景', font='reggae', weight=400,
                 fill=G('#ffffff 0%', '#fde6fb 28%', '#f3a6ea 50%', '#ffffff 68%', '#d98ae0 84%', '#b45bbd 100%'), stroke='#2b0b36', strokew=0.055,
                 shadow=SH('0 0 .03em rgba(255,170,245,.9)', '0 0 .1em rgba(200,60,220,.55)', '0 .05em .08em rgba(0,0,0,.8)'),
                 tshadow='0 .02em 0 #4a1458, 0 .04em 0 #2b0b36', spacing='0.02em', line=1.0,
                 sub=dict(font='playfair', weight=800, italic=True, scale=0.36, fill=G('#ffffff', '#fff2fd'), stroke='#b0389f', strokew=0.09, spacing='0.01em')),
    'vkeiblue': dict(jp='ヴィジュアル系ネーム（青銀）', mood='日本語の名前＋ローマ字・ホスト・クール・青や黒の背景', font='chokoku', weight=400,
                     fill=G('#ffffff 0%', '#e6f1ff 28%', '#9fc4f3 50%', '#ffffff 68%', '#8fb0dd 84%', '#4f6fa8 100%'), stroke='#0b1636', strokew=0.055,
                     shadow=SH('0 0 .05em rgba(150,200,255,.95)', '0 0 .22em rgba(70,120,230,.75)', '0 .06em .12em rgba(0,0,0,.75)'),
                     tshadow='0 .02em 0 #14285a, 0 .04em 0 #0b1636', spacing='0.02em', line=1.0,
                     sub=dict(font='playfair', weight=800, italic=True, scale=0.36, fill=G('#ffffff', '#eef5ff'), stroke='#2f5fae', strokew=0.09, spacing='0.01em')),
    'vkeigold': dict(jp='ヴィジュアル系ネーム（金）', mood='日本語の名前＋ローマ字・ホスト・高級・黒や赤の背景', font='chokoku', weight=400,
                     fill=G('#fffaf0 0%', '#f8e2a6 28%', '#d6a64a 50%', '#fff3cf 68%', '#c9963c 84%', '#8a5e15 100%'), stroke='#2a1505', strokew=0.055,
                     shadow=SH('0 0 .05em rgba(255,220,150,.9)', '0 0 .22em rgba(230,160,60,.6)', '0 .06em .12em rgba(0,0,0,.75)'),
                     tshadow='0 .02em 0 #5a3b0a, 0 .04em 0 #2a1505', spacing='0.02em', line=1.0,
                     sub=dict(font='playfair', weight=800, italic=True, scale=0.36, fill=G('#ffffff', '#fff7e6'), stroke='#9a6a1c', strokew=0.09, spacing='0.01em')),
    # 日本語も書ける
    'jpop': dict(jp='和ポップ', mood='日本語・子ども・元気', font='mochiy', weight=400, fill=G('#ff7eb6', '#ff3d7f'), stroke='#ffffff', strokew=0.12,
                 shadow=SH('0 .05em 0 #c2185b', '0 .1em .2em rgba(0,0,0,.35)'), spacing='0.02em', line=1.1),
    'fude': dict(jp='筆文字', mood='日本語・和風・祭り・成人式・お正月', font='yuji', weight=400, fill=G('#1a1a1a', '#000000'), stroke='#ffffff', strokew=0.1,
                 shadow=SH('0 0 .15em rgba(255,255,255,.8)', '0 .08em .2em rgba(0,0,0,.4)'), spacing='0.02em', line=1.1),
    'wamodern': dict(jp='和モダン', mood='日本語・和柄・桜・着物・上品', font='zenantique', weight=400, fill=G('#fff6d8', '#e9c46a 50%', '#b07d2a'), stroke='#4a2a08', strokew=0.05,
                     shadow=SH('0 .05em 0 #2c1904', '0 .1em .2em rgba(0,0,0,.5)'), spacing='0.04em', line=1.1),
    'maru': dict(jp='丸ゴシック', mood='日本語・やさしい・ナチュラル・何にでも', font='zenmaru', weight=700, fill=G('#ffffff', '#fff7ef'), stroke='#ff8a3d', strokew=0.1,
                 shadow=SH('0 .05em 0 #c85a12', '0 .1em .2em rgba(0,0,0,.35)'), spacing='0.03em', line=1.1),
    'kawaii': dict(jp='手書きかわいい', mood='日本語・赤ちゃん・パステル・女の子', font='hachimaru', weight=400, fill=G('#ffffff', '#fff0f6'), stroke='#ff7fb0', strokew=0.12,
                   shadow=SH('0 .05em 0 #e0568f', '0 .1em .2em rgba(0,0,0,.3)'), spacing='0.02em', line=1.15),
    'gokubuto': dict(jp='極太', mood='日本語・インパクト・スポーツ・お祝い', font='dela', weight=400, fill=G('#ffe14d', '#ffb800'), stroke='#d7191c', strokew=0.1,
                     shadow=SH('.05em .06em 0 #7a0a0c', '0 .1em .2em rgba(0,0,0,.45)'), spacing='0.02em', line=1.1),
}

# オリジナルの飾り文字（2026-11-04 ユーザー指定「こうゆうオリジナルの書体沢山増やして」）。deco.py で1行目の字にとげ・刃・炎・したたり・ひび・ネオン・グリッチを足して塗る。
# 1行目＝名前（日本語も可）、2行目以降＝ローマ字など（sub の書体で小さく）。例 --text '如月サク|Saku Kisaragi'
_SUBI = lambda c: dict(font='playfair', weight=800, italic=True, fill=G('#ffffff', '#f4f4f4'), stroke=c, strokew=0.09, spacing='0.01em', wr=0.78)
_SUBC = lambda c: dict(font='cormorant', weight=700, fill=G('#ffffff', '#f2f2f2'), stroke=c, strokew=0.08, spacing='0.06em', wr=0.8)  # 小文字のある書体（文言の大文字小文字を変えない）
_SUBS = lambda c: dict(font='vibes', weight=400, fill=G('#ffffff', '#fff6fb'), stroke=c, strokew=0.06, spacing='0', wr=0.7)
_D = lambda jp, mood, font, deco, pal, sub, weight=400, spacing='0.02em', **k: dict(jp=jp, mood=mood, font=font, weight=weight, deco=deco, pal=pal, sub=sub,
                                                               fill='', stroke='', strokew=0, shadow='', spacing=spacing, line=1.0, **k)
STYLES.update({
    'thornpink': _D('とげ（ピンク）', '名前ロゴ・ヴィジュアル系・ホスト・夜桜・ピンクや紫の暗い背景', 'reggae', 'thorn', 'pink', _SUBI('#b0389f')),
    'thornsilver': _D('とげ（銀）', '名前ロゴ・ホスト・クール・黒や青の背景', 'chokoku', 'thorn', 'chrome', _SUBI('#3a4a66')),
    'thorngold': _D('とげ（金）', '名前ロゴ・ホスト・高級・黒や赤の背景', 'dela', 'thorn', 'gold', _SUBC('#7a500f')),
    'thornpurple': _D('とげ（紫）', '名前ロゴ・ヴィジュアル系・ダーク・紫の背景', 'reggae', 'thorn', 'purple', _SUBI('#5a22b0')),
    'thornholo': _D('とげ（オーロラ）', '名前ロゴ・地雷系・パステル・ゆめかわ', 'chokoku', 'thorn', 'holo', _SUBS('#7a4ac0')),
    'bladeice': _D('刃（氷）', '名前ロゴ・クール・青や白の背景・冬', 'oldmincho', 'blade', 'ice', _SUBC('#1f5a8f'), weight=900),
    'bladered': _D('刃（紅）', '名前ロゴ・和・侍・赤や黒の背景', 'shippori', 'blade', 'blood', _SUBC('#7a0a0a'), weight=800),
    'bladegold': _D('刃（黒金）', '名前ロゴ・高級・黒背景・周年', 'shippori', 'blade', 'blackgold', _SUBC('#8a5e15'), weight=800),
    'flamefire': _D('炎', '名前ロゴ・熱い・赤やオレンジ・祭り・スポーツ', 'dela', 'flame', 'fire', _SUBI('#a83000')),
    'flamepurple': _D('炎（紫）', '名前ロゴ・ダーク・紫や黒の背景', 'reggae', 'flame', 'purple', _SUBI('#5a22b0')),
    'flameblue': _D('炎（青）', '名前ロゴ・クール・青や黒の背景', 'chokoku', 'flame', 'ice', _SUBI('#1f5a8f')),
    'dripblood': _D('したたり（赤）', '名前ロゴ・ホラー・ハロウィン・黒や赤の背景', 'dela', 'drip', 'blood', _SUBI('#7a0a0a')),
    'dripgold': _D('したたり（金）', '名前ロゴ・とろける金・高級・黒背景', 'zenantique', 'drip', 'gold', _SUBC('#7a500f')),
    'dripsakura': _D('したたり（ピンク）', '名前ロゴ・地雷系・かわいい・ピンクの背景', 'mochiy', 'drip', 'sakura', _SUBS('#c2185b')),
    'crackchrome': _D('ひび割れ（銀）', '名前ロゴ・ロック・メタル・灰色や黒の背景', 'reggae', 'crack', 'chrome', _SUBC('#3a4a66')),
    'crackgold': _D('ひび割れ（金）', '名前ロゴ・ワイルド・黒や茶の背景', 'zenantique', 'crack', 'gold', _SUBC('#7a500f')),
    'thorncrack': _D('とげ＋ひび（紅）', '名前ロゴ・ヴィジュアル系・ダーク・黒や赤の背景', 'reggae', 'thorn+crack', 'blood', _SUBI('#7a0a0a')),
    'neonpink2': _D('ネオン管（ピンク）', '名前ロゴ・夜・ネオン街・暗い背景', 'mochiy', 'plain', 'neonpink', _SUBS('#ff2ec4'), neon=True),
    'neonblue2': _D('ネオン管（青）', '名前ロゴ・夜・クラブ・暗い背景', 'zenmaru', 'plain', 'neonblue', _SUBI('#00b3ff'), weight=700, neon=True),
    'glitchholo': _D('グリッチ', '名前ロゴ・ゲーム・配信・サイバー・暗い背景', 'dela', 'plain', 'holo', _SUBI('#7a4ac0'), glitch=True),
    'glitchthorn': _D('グリッチ＋とげ', '名前ロゴ・サイバー・ヴィジュアル系・暗い背景', 'chokoku', 'thorn', 'neonblue', _SUBI('#00b3ff'), glitch=True),
    'emeraldblade': _D('刃（エメラルド）', '名前ロゴ・緑の背景・誕生石', 'kaisei', 'blade', 'emerald', _SUBC('#0b6b44'), weight=700),
})
# かっこいい系（2026-11-04 ユーザー指定「かっこいい文字も追加して」）：斬り・スピード・角ばり・立体・メタル
_SUBB = lambda c: dict(font='bodoni', weight=800, italic=True, fill=G('#ffffff', '#e8e8e8'), stroke=c, strokew=0.08, spacing='0.03em', wr=0.8)
STYLES.update({
    'slashsteel': _D('斬り（鋼）', 'かっこいい・侍・刀・黒や灰色の背景', 'shippori', 'slash', 'steel', _SUBB('#2e353d'), weight=800),
    'slashred': _D('斬り（紅）', 'かっこいい・和・赤や黒の背景', 'reggae', 'slash', 'crimson', _SUBB('#6a0010')),
    'katana': _D('刀（銀の刃＋斬り）', 'かっこいい・侍・クール・暗い背景', 'oldmincho', 'blade+slash', 'chrome', _SUBC('#3a4a66'), weight=900),
    'speedchrome': _D('スピード（クローム立体）', 'かっこいい・車・バイク・スポーツ・ストリート', 'dela', 'skew+speed', 'chrome', _SUBI('#3a4a66'), extrude=True),
    'speedfire': _D('スピード（炎）', 'かっこいい・熱い・スポーツ・赤やオレンジ', 'dela', 'skew+speed', 'fire', _SUBI('#a83000'), extrude=True),
    'speedblue': _D('スピード（雷）', 'かっこいい・クール・青や黒の背景・ゲーム', 'reggae', 'skew+speed', 'electric', _SUBI('#1f5a8f')),
    'edgesteel': _D('角ばり（鋼の立体）', 'かっこいい・メタル・ロック・灰色や黒の背景', 'zenantique', 'angular', 'steel', _SUBC('#2e353d'), extrude=True),
    'edgegold': _D('角ばり（金の立体）', 'かっこいい・高級・王者・黒背景・周年', 'chokoku', 'angular', 'gold', _SUBC('#7a500f'), extrude=True),
    'carbon': _D('カーボン（黒×赤）', 'かっこいい・車・ダーク・黒や赤の背景', 'dela', 'angular+skew', 'carbon', _SUBI('#e0141e'), extrude=True),
    'metal3d': _D('メタル立体', 'かっこいい・インパクト・何にでも・暗めの背景', 'dela', 'plain', 'steel', _SUBB('#2e353d'), extrude=True),
    'gold3d': _D('ゴールド立体', 'かっこいい・高級・ホスト・黒や赤の背景', 'dela', 'plain', 'gold', _SUBB('#7a500f'), extrude=True),
    'titanthorn': _D('チタン（とげ＋角ばり）', 'かっこいい・ワイルド・茶や黒の背景', 'shippori', 'angular+thorn', 'titanium', _SUBC('#3d372d'), weight=800, extrude=True),
    'darkknight': _D('ダーク（黒金の刃＋斬り）', 'かっこいい・ダーク・高級・黒背景', 'shippori', 'blade+slash', 'blackgold', _SUBB('#8a5e15'), weight=800),
    'thunder': _D('雷（とげ＋グリッチ）', 'かっこいい・ゲーム・サイバー・青や黒の背景', 'chokoku', 'skew+thorn', 'electric', _SUBI('#1f5a8f'), glitch=True),
})


# クール系（2026-11-04 ユーザー指定「可愛い系に寄っちゃってるのでクールな文字も追加して」）：光らせない・色数少なめ・細い縁と落ち影・字間広め
_SUBW = lambda c='#0b0d10', f='michroma', w=400: dict(font=f, weight=w, fill=G('#ffffff', '#e9ecef'), stroke=c, strokew=0.05, spacing='0.28em', wr=0.7,
                                                      shadow=SH('0 .05em .08em rgba(0,0,0,.85)'))
_K = lambda *a, **k: _D(*a, cool=True, **k)
STYLES.update({
    'coolsilver': _K('クール（銀）', 'クール・大人・モノトーン・ホスト・何にでも', 'murecho', 'plain', 'mono', _SUBW(), weight=900, spacing='0.08em'),
    'coolline': _K('クール（銀＋線）', 'クール・シンプル・高級・暗い背景', 'zenkaku', 'lines', 'mono', _SUBW(), weight=900, spacing='0.12em'),
    'coolblack': _K('クール（黒×白縁）', 'クール・明るい背景・白や灰色・シンプル', 'zenkaku', 'plain', 'matteblack', _SUBW('#ffffff'), weight=900, spacing='0.08em'),
    'coolice': _K('クール（氷）', 'クール・青や白の背景・冬・静か', 'oldmincho', 'lines', 'icecool', _SUBW('#0a1622', 'cormorant', 700), weight=900, spacing='0.1em'),
    'coolmincho': _K('クール明朝', 'クール・和・大人・黒や紺の背景', 'shippori', 'plain', 'mono', _SUBW('#0b0d10', 'cormorant', 700), weight=800, spacing='0.12em'),
    'coolhollow': _K('クール（白抜き線）', 'クール・シンプル・写真を見せたいとき・暗い背景', 'murecho', 'plain', 'mono', _SUBW(), weight=900, spacing='0.1em', hollow=True),
    'coolred': _K('クール（黒×赤）', 'クール・ダーク・黒や赤の背景・ロック', 'murecho', 'lines', 'blackred', _SUBW('#d0101c', 'rajdhani', 700), weight=900, spacing='0.08em'),
    'coolgold': _K('クール（金・つや消し）', 'クール・高級・紺や黒の背景・周年', 'shippori', 'lines', 'navygold', _SUBW('#0b1226', 'cormorant', 700), weight=800, spacing='0.12em'),
    'coolsplit': _K('クール（クローム）', 'クール・メタル・車・暗い背景', 'zenkaku', 'skew', 'split', _SUBW('#05070a', 'orbitron', 700), weight=900, spacing='0.06em'),
    'coolsteel': _K('クール（鋼の斬り）', 'クール・侍・鋭い・暗い背景', 'murecho', 'angular+slash', 'steel', _SUBW('#07090c', 'rajdhani', 700), weight=900, spacing='0.06em'),
    'cool3d': _K('クール（立体）', 'クール・インパクト・スポーツ・暗めの背景', 'rocknroll', 'plain', 'mono', _SUBW('#0b0d10', 'orbitron', 700), extrude=True),
    'cyber': _K('サイバー（ドット）', 'クール・ゲーム・配信・デジタル・暗い背景', 'dotgothic', 'lines', 'icecool', _SUBW('#0a1622', 'orbitron', 700), spacing='0.12em'),
    'coolglitch': _K('クール（グリッチ）', 'クール・サイバー・モノトーン・暗い背景', 'murecho', 'plain', 'mono', _SUBW('#0b0d10', 'orbitron', 700), weight=900, spacing='0.08em', glitch=True),
    'coolnavy': _K('クール（紺×銀）', 'クール・紺や青の背景・スーツ・大人', 'zenkaku', 'lines', 'icecool', _SUBW('#0a1622', 'rajdhani', 700), weight=900, spacing='0.1em'),
})

# 足せる効果（2026-11-02 ユーザー指定）。--effect shadow,glow など、または --style 'luxury:shadow+glow'
EFFECTS = {
    'shadow': ('影', SH('.04em .06em .05em rgba(0,0,0,.75)', '0 .14em .3em rgba(0,0,0,.5)')),
    'glow': ('光', SH('0 0 .06em rgba(255,240,200,.95)', '0 0 .25em rgba(255,210,130,.7)')),
    'emboss': ('浮き彫り', SH('-.02em -.025em 0 rgba(255,255,255,.75)', '.025em .035em 0 rgba(0,0,0,.75)')),
    '3d': ('立体', SH('0 .16em .25em rgba(0,0,0,.5)'), '.012em .016em 0 #2a1a06, .024em .032em 0 #24170a, .036em .048em 0 #1e1308, .048em .064em 0 #191006, .06em .08em 0 #140c04'),
    'neon': ('ネオン', SH('0 0 .12em #ffd36b', '0 0 .35em rgba(255,150,0,.75)')),
    'outline': ('縁取り', ''),
}


def with_effect(st, effects):
    st = dict(st)
    for e in [x for x in re.split(r'[+,\s]+', effects or '') if x]:
        if e not in EFFECTS: raise SystemExit(f'効果「{e}」はありません（{", ".join(EFFECTS)}）')
        if e == 'outline':
            if not st['strokew']: st['stroke'], st['strokew'] = '#1a1206', 0.05
            continue
        st['shadow'] = (st['shadow'] + ' ' + EFFECTS[e][1]).strip()
        if len(EFFECTS[e]) > 2: st['tshadow'] = ', '.join(x for x in [st.get('tshadow', ''), EFFECTS[e][2]] if x)
    return st


def _pkg(name):
    """@fontsource のパッケージを npm から取ってきて展開（fonts/pkg/<name>/ にためる）"""
    d = os.path.join(FONTDIR, 'pkg', name)
    if not os.path.exists(os.path.join(d, 'package.json')):
        os.makedirs(d, exist_ok=True)
        subprocess.run(['npm', 'pack', f'@fontsource/{name}', '--silent', '--pack-destination', d], check=True, capture_output=True)
        tgz = sorted(glob.glob(os.path.join(d, f'fontsource-{name}-*.tgz')))[-1]
        subprocess.run(['tar', '-xzf', tgz, '-C', d, '--strip-components=1'], check=True)
        os.remove(tgz)
    return d


def _ranges(ur):
    out = []
    for part in ur.split(','):
        part = part.strip().replace('U+', '')
        if not part: continue
        if '-' in part: a, b = part.split('-'); out.append((int(a, 16), int(b, 16)))
        elif '?' in part: out.append((int(part.replace('?', '0'), 16), int(part.replace('?', 'F'), 16)))
        else: v = int(part, 16); out.append((v, v))
    return out


def font_css(key, weight, text, family='F', italic=False):
    """文字に必要な分だけの @font-face（データを埋め込み）。英字だけの書体で使えない文字があれば止める"""
    name = FONTS[key]
    latin = os.path.join(FONTDIR, f'{name}-latin-{weight}-normal.woff2')
    chars = {ord(c) for c in text if not c.isspace() and c != '|'}
    if not italic and all(c < 0x250 or 0x2000 <= c <= 0x206F for c in chars) and os.path.exists(latin):  # 英字だけならリポジトリの書体で足りる
        return f"@font-face{{font-family:{family};src:url(data:font/woff2;base64,{base64.b64encode(open(latin, 'rb').read()).decode()}) format('woff2');font-weight:{weight}}}"
    d = _pkg(name); css = open(os.path.join(d, f'{weight}-italic.css' if italic else f'{weight}.css')).read()
    out, covered = [], set()
    for m in re.finditer(r'@font-face\s*{([^}]*)}', css):
        body = m.group(1); f = re.search(r"url\(\./files/([^)]+\.woff2)\)", body); u = re.search(r'unicode-range:\s*([^;]+);', body)
        if not f or not u: continue
        rg = _ranges(u.group(1)); need = {c for c in chars if any(a <= c <= b for a, b in rg)}
        if not need: continue
        covered |= need
        data = base64.b64encode(open(os.path.join(d, 'files', f.group(1)), 'rb').read()).decode()
        out.append(f"@font-face{{font-family:{family};src:url(data:font/woff2;base64,{data}) format('woff2');font-weight:{weight};font-style:{'italic' if italic else 'normal'};unicode-range:{u.group(1)}}}")
    miss = chars - covered
    if miss: raise SystemExit(f'書体「{STYLES_BY_FONT.get(key, key)}」では書けない文字があります：' + ''.join(sorted(chr(c) for c in miss)) + '（日本語は jpop / fude / wamodern / maru / kawaii / gokubuto / jgold / jplatinum / jrose）')
    return ''.join(out)


STYLES_BY_FONT = {v['font']: v['jp'] for v in STYLES.values()}


def has_jp(text):
    return any(ord(c) >= 0x3000 for c in text)


async def render(text, st, width, rotate, c1, c2):
    sub = st.get('sub') if '|' in text else None
    parts = text.split('|')
    ffcss = font_css(st['font'], st['weight'], parts[0] if sub else text, 'F', st.get('italic', False))
    if sub: ffcss += font_css(sub['font'], sub['weight'], '|'.join(parts[1:]), 'F2', sub.get('italic', False))
    fill = st['fill'] if not c1 else f'linear-gradient(180deg,{c1},{c2 or c1})'
    import html as _h
    # 1行＝縁取りの層（下）と色の層（上）を同じ位置に重ねる
    # 立体の重ねた影（tshadow）は filter だと重いので、下の層の text-shadow で描く
    lines = ''.join(f'<div class="l{" sb" if sub and i else ""}">' + (f'<span class="s">{_h.escape(l)}</span>' if st['strokew'] or st.get('tshadow') or (sub and i) else '') + f'<span class="f">{_h.escape(l)}</span></div>'
                    for i, l in enumerate(text.split('|')))
    subcss = (f".sb{{font-family:F2;font-weight:{sub['weight']};font-style:{'italic' if sub.get('italic') else 'normal'};font-size:{sub['scale']}em;letter-spacing:{sub.get('spacing', '0')};margin-top:-.05em}}"
              f".sb .s{{color:{sub['stroke']};-webkit-text-stroke:{sub['strokew'] * 2}em {sub['stroke']};text-shadow:none}} .sb .f{{background:{sub['fill']};-webkit-background-clip:text;background-clip:text;color:transparent}}") if sub else ''
    html = f"""<html><head><style>
    {ffcss}
    html,body{{margin:0;background:transparent}}
    #w{{position:absolute;left:0;top:0;display:inline-block;padding:.35em .45em;transform-origin:center}}
    .t{{font-family:F;font-weight:{st['weight']};font-style:{'italic' if st.get('italic') else 'normal'};font-size:200px;line-height:{st['line']};letter-spacing:{st['spacing']};text-align:center;white-space:nowrap;filter:{st['shadow']}}}
    .l{{display:grid;justify-items:center}} .l>span{{grid-area:1/1;padding:.35em .5em;margin:-.35em -.5em}}
    .s{{color:{st['stroke'] or 'transparent'};-webkit-text-stroke:{st['strokew'] * 2}em {st['stroke'] or 'transparent'};text-shadow:{st.get('tshadow') or 'none'}}}
    .f{{background:{fill};-webkit-background-clip:text;background-clip:text;color:transparent}}
    {subcss}
    </style></head><body><div id="w"><div class="t">{lines}</div></div></body></html>"""
    async with async_playwright() as p:
        b = await p.chromium.launch(); pg = await b.new_page(viewport={'width': 4000, 'height': 3000})
        await pg.set_content(html); await pg.evaluate('document.fonts.ready')
        bw = await pg.evaluate("document.getElementById('w').getBoundingClientRect().width")
        k = width / bw
        await pg.evaluate(f"document.querySelector('.t').style.fontSize = '{200 * k}px'")
        await pg.evaluate(f"document.getElementById('w').style.transform = 'rotate({rotate}deg)'")
        r = await pg.evaluate("(() => { const r = document.getElementById('w').getBoundingClientRect(); return [r.left, r.top, r.width, r.height]; })()")
        pad = 200
        await pg.evaluate(f"document.getElementById('w').style.left = '{pad - r[0]}px'; document.getElementById('w').style.top = '{pad - r[1]}px'")
        png = await pg.screenshot(timeout=180000, omit_background=True, clip={'x': 0, 'y': 0, 'width': r[2] + 2 * pad, 'height': r[3] + 2 * pad})
        await b.close()
    return cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_UNCHANGED)


def render_deco(text, st, width, rotate, c1, c2):
    """オリジナルの飾り文字（deco.py）。1行目を飾り、2行目以降は sub の書体で下に重ねる"""
    import deco
    parts = text.split('|')
    mst = dict(font=st['font'], weight=st['weight'], fill=G('#ffffff', '#ffffff'), stroke='', strokew=0, shadow='none', spacing=st['spacing'], line=1.0)
    t = asyncio.run(render(parts[0], mst, width * 0.86, 0, '', ''))
    m, sw = deco.shape(t[..., 3], st['deco'], st.get('seed', 7))
    pal = dict(deco.PALETTES[st['pal']], **({'fill': [c1, c2 or c1]} if c1 else {}))
    main = deco.paint(m, sw, pal, st.get('neon', False), st.get('glitch', False), extrude=st.get('extrude', False), cool=st.get('cool', False), hollow=st.get('hollow', False))
    sub = None
    if len(parts) > 1:
        sb = st['sub']; mw = np.nonzero(main[..., 3].max(0) > 8)[0]; mw = mw.max() - mw.min()
        sst = dict(font=sb['font'], weight=sb['weight'], italic=sb.get('italic', False), fill=sb['fill'], stroke=sb['stroke'], strokew=sb['strokew'],
                   shadow=sb.get('shadow', SH('0 0 .05em ' + sb['stroke'], '0 .05em .08em rgba(0,0,0,.75)')), spacing=sb['spacing'], line=1.0)
        sub = asyncio.run(render('|'.join(parts[1:]), sst, mw * sb.get('wr', 0.75), 0, '', ''))
    out = deco.stack(main, sub, int(sw * (0.4 if st.get('cool') else 0.05)))
    if rotate:
        h, w = out.shape[:2]; M = cv2.getRotationMatrix2D((w / 2, h / 2), -rotate, 1)
        c, s_ = abs(M[0, 0]), abs(M[0, 1]); nw, nh = int(h * s_ + w * c), int(h * c + w * s_)
        M[0, 2] += nw / 2 - w / 2; M[1, 2] += nh / 2 - h / 2
        out = cv2.warpAffine(out, M, (nw, nh), flags=cv2.INTER_CUBIC)
    return out


def _box(design, placement):
    pj = os.path.join(placement or os.path.dirname(os.path.abspath(design)), 'placement.json')
    return json.load(open(pj))['box'] if os.path.exists(pj) else None


def _place(t, design, placement, cx, cy):
    """文字の左上。cx/cy が無ければ人物の下（白い範囲の下端）"""
    th, tw = t.shape[:2]; ys, xs = np.nonzero(t[:, :, 3] > 40)
    if cx is None or cy is None:
        b = _box(design, placement) or [SAFE[0], SAFE[1], SAFE[2], SAFE[1]]
        vw = xs.max() - xs.min()
        c = min(max((b[0] + b[2]) / 2, SAFE[0] + vw / 2 + 20), SAFE[2] - vw / 2 - 20)
        cx = c - ((xs.min() + xs.max()) / 2 - tw / 2) if cx is None else cx
        cy = (SAFE[3] - 30 - ys.max()) + th / 2 if cy is None else cy
    return int(round(cx - tw / 2)), int(round(cy - th / 2))


def _contrast(im, t, x0, y0):
    """(文字の中の明るさ, 文字の下の背景の明るさ)"""
    th, tw = t.shape[:2]
    sx0, sy0, sx1, sy1 = max(0, x0), max(0, y0), min(W, x0 + tw), min(H, y0 + th)
    if sx1 <= sx0 or sy1 <= sy0: return None
    sub = t[sy0 - y0:sy1 - y0, sx0 - x0:sx1 - x0]; bg = im[sy0:sy1, sx0:sx1]
    core = sub[:, :, 3] > 230
    if core.sum() < 50: return None
    lum = lambda a: (0.114 * a[..., 0] + 0.587 * a[..., 1] + 0.299 * a[..., 2])
    ring = cv2.dilate(core.astype(np.uint8), np.ones((25, 25), np.uint8)).astype(bool)
    return float(lum(sub[..., :3].astype(np.float32))[core].mean()), float(lum(bg.astype(np.float32))[ring].mean())


def apply(design, out_path, text, style, cx=None, cy=None, width=1800, rotate=0, placement='', color1='', color2='', effect=''):
    """文字を入れて out_path に書き出す。cx/cy が無ければ人物の下（白い範囲の下端）。"""
    style, _, eff = style.partition(':'); effect = '+'.join(x for x in [eff, effect] if x)
    style = {v['jp']: k for k, v in STYLES.items()}.get(style, style)
    if changes_case(style, text): raise SystemExit(f'「{STYLES[style]["jp"]}」は全部大文字に見える書体なので、小文字を含む「{text}」には使えません（文字は依頼のまま変えない）')
    im = cv2.imread(design); assert im is not None and im.shape[1] == W, 'デザイン画像は 2880×2048'
    st = with_effect(STYLES[style], effect)
    isdeco = 'deco' in st
    t = render_deco(text, st, width, rotate, color1, color2) if isdeco else asyncio.run(render(text, st, width, rotate, color1, color2))
    th, tw = t.shape[:2]
    for _ in range(0 if isdeco else 2):  # 背景に埋もれないように：文字と下の背景の明るさが近ければ、縁に影（または光）を足して描き直す
        x0, y0 = _place(t, design, placement, cx, cy)
        c = _contrast(im, t, x0, y0)
        if c is None or abs(c[0] - c[1]) >= 100: break
        glow = 'rgba(0,0,0,.9)' if c[0] > c[1] else 'rgba(255,255,255,.9)'
        st['shadow'] = f'drop-shadow(0 0 .035em {glow}) drop-shadow(0 0 .09em {glow}) ' + st['shadow']
        t = asyncio.run(render(text, st, width, rotate, color1, color2)); th, tw = t.shape[:2]
    al = t[:, :, 3] > 40; ys, xs = np.nonzero(al)
    box = _box(design, placement)
    x0, y0 = _place(t, design, placement, cx, cy)
    bx = [x0 + xs.min(), y0 + ys.min(), x0 + xs.max(), y0 + ys.max()]
    ng = bx[0] < SAFE[0] or bx[1] < SAFE[1] or bx[2] > SAFE[2] or bx[3] > SAFE[3]
    over = bool(box and bx[1] < box[3] and bx[0] < box[2] and bx[2] > box[0])  # 顔（大事な範囲）に重なる
    out = im.astype(np.float32)
    sx0, sy0, sx1, sy1 = max(0, x0), max(0, y0), min(W, x0 + tw), min(H, y0 + th)
    sub = t[sy0 - y0:sy1 - y0, sx0 - x0:sx1 - x0].astype(np.float32)
    a_ = sub[:, :, 3:4] / 255
    out[sy0:sy1, sx0:sx1] = out[sy0:sy1, sx0:sx1] * (1 - a_) + sub[:, :, :3] * a_
    cv2.imwrite(out_path, np.clip(out, 0, 255).astype(np.uint8), [cv2.IMWRITE_JPEG_QUALITY, 95])
    return {'out': out_path, 'text_box': [int(v) for v in bx], 'outside_safe': bool(ng), 'over_face': over}


def main():
    if '--list' in sys.argv:
        for k, v in STYLES.items(): print(f"{k:10s} {v['jp']}{'（日本語可）' if v['font'] in JPFONTS else ''}{'（大文字だけの文言のみ）' if v['font'] in CAPSFONTS else ''}：{v['mood']}")
        print('効果（--effect、または --style 名前:効果）：' + '／'.join(f'{k} {v[0]}' for k, v in EFFECTS.items()))
        return
    ap = argparse.ArgumentParser()
    ap.add_argument('design'); ap.add_argument('out'); ap.add_argument('--text', required=True); ap.add_argument('--style', required=True, help='STYLES のキー（pirate など）か日本語の名前（海賊風など）。python3 textlayer.py --list で一覧')
    ap.add_argument('--cx', type=float); ap.add_argument('--cy', type=float); ap.add_argument('--placement', default='')
    ap.add_argument('--width', type=float, default=1800); ap.add_argument('--rotate', type=float, default=0)
    ap.add_argument('--color1', default=''); ap.add_argument('--color2', default='')
    ap.add_argument('--effect', default='', help='足す効果：' + '／'.join(f'{k} {v[0]}' for k, v in EFFECTS.items()) + '（「shadow+glow」のように重ねられる）')
    a = ap.parse_args()
    print(json.dumps(apply(a.design, a.out, a.text, a.style, a.cx, a.cy, a.width, a.rotate, a.placement, a.color1, a.color2, a.effect), ensure_ascii=False))


if __name__ == '__main__':
    main()
