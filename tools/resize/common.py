"""横長リサイズ（管理サイトの「リサイズ候補」）の共通部品。

フォーマット（ユーザー指定・必ず守る）：仕上がり 1440×1024px。
  上の帯 0〜254px・下の帯 917〜1024px … 顔や重要なデザインを入れない
  左右の帯 0〜134px・1306〜1440px     … 背面になる部分。背景のみ
作業は 2倍（2880×2048）で行い、デザイン画像として 2880×2048 の JPEG を作る。

管理サイト（Apps Script ウェブアプリ）の URL と登録用キーは環境変数で渡す（リポジトリには書かない）：
  ORISHAN_URL, ORISHAN_KEY
"""
import base64, json, os, sys
import requests

K = 2
W, H = 1440 * K, 1024 * K
SAFE = dict(x0=134 * K, x1=1306 * K, y0=254 * K, y1=917 * K)
# ボトルを正面から見たときに見える横の範囲（提出用フォーマットの「前」のボトル。仕上がり約 505〜935px、中心は720）。
# ロゴ・文字はこの中に全部入れる（2026-11-05 ユーザー指定：正面から見てロゴや文字が全部見えるように）
# 2026-11-10：以前は 475〜915（中心695）で、ロゴ・文字が25pxほど左に寄り、ボトル正面で左が切れていた（ユーザー指摘）。
#   提出用フォーマットで実測（真ん中の線＝ボトル正面の中心、見える幅＝約504〜929）して中心720にそろえた。
FRONT = dict(x0=1010, x1=1870)
CA = '/root/.ccr/ca-bundle.crt'


def verify():
    return CA if os.path.exists(CA) else True


def api(body, timeout=300):
    url, key = os.environ.get('ORISHAN_URL'), os.environ.get('ORISHAN_KEY')
    if not url or not key:
        sys.exit('ORISHAN_URL と ORISHAN_KEY を環境変数で渡してください')
    r = requests.post(url, data=json.dumps(dict(body, key=key)).encode('utf-8'),
                      headers={'Content-Type': 'text/plain;charset=utf-8'}, timeout=timeout, verify=verify())
    try:
        return r.json()
    except Exception:
        return {'ok': False, 'status': r.status_code, 'body': r.text[:300]}


def b64file(path, name=None):
    with open(path, 'rb') as f:
        return {'name': name or os.path.basename(path), 'data': base64.b64encode(f.read()).decode()}
