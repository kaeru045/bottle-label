#!/usr/bin/env python3
"""src/index.html と src/assets/ から、1ファイルで動く HTML を作る。

  python3 tools/build.py            -> index.html（GitHub Pages 公開用）
  python3 tools/build.py --out PATH -> 任意の場所に書き出し（配布用ファイル版など）

素材画像は data URI として埋め込み、jsPDF / JSZip は tools/vendor/ の中身を埋め込むので、
できあがった HTML はネットにつながっていなくても動く。
"""
import base64, json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'src', 'index.html')
ASSETS = os.path.join(ROOT, 'src', 'assets')
VENDOR = os.path.join(ROOT, 'tools', 'vendor')
out = os.path.join(ROOT, 'index.html')
if '--out' in sys.argv:
    out = sys.argv[sys.argv.index('--out') + 1]

s = open(SRC, encoding='utf-8').read()

# 素材を埋め込む
assets = {}
for f in sorted(os.listdir(ASSETS)):
    if f.endswith(('.png', '.jpg')):
        mime = 'image/png' if f.endswith('.png') else 'image/jpeg'
        assets[f] = f'data:{mime};base64,' + base64.b64encode(open(os.path.join(ASSETS, f), 'rb').read()).decode()
s = s.replace("  const load = src => new Promise(", "  const ASSETS = " + json.dumps(assets) + ";\n  const load = src => new Promise(", 1)
s = s.replace("i.src = src; });", "i.src = ASSETS[src] || src; });", 1)

# claude.ai の保存機能の代わりに、ふつうのブラウザのダウンロードを使う
s, n = re.subn(r"  \(async \(\) => \{ try \{ downloads = await window\.claude.*?\n    if \(!downloads\).*?\n",
               "  downloads = { save: async ({filename, data}) => { const url = URL.createObjectURL(data); const a = document.createElement('a'); a.href = url; a.download = filename; document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 4000); } };\n",
               s, flags=re.S)
assert n == 1, 'downloads の差し替え位置が見つかりません'
s = s.replace("status(`${filename} を保存しました。`)", "status(`${filename} をダウンロードしました。`)")

# ライブラリを埋め込む
for tag, fn in [('<script src="https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js"></script>', 'jspdf.umd.min.js'),
                ('<script src="https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/jszip.min.js"></script>', 'jszip.min.js')]:
    assert tag in s, tag
    js = open(os.path.join(VENDOR, fn), encoding='utf-8').read().replace('</script>', '<\\/script>')
    s = s.replace(tag, '<script>' + js + '</script>')

doc = ('<!doctype html><html lang="ja"><head><meta charset="utf-8">'
       '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
       '<style>:root{color-scheme:light}body{margin:0;font:14px system-ui,sans-serif}img{max-width:100%}[hidden]{display:none!important}</style>'
       '</head><body>\n' + s + '\n</body></html>')
open(out, 'w', encoding='utf-8').write(doc)
print(f'built {out} ({len(doc)/1e6:.2f} MB)')
