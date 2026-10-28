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
