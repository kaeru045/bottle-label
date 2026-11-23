#!/usr/bin/env python3
"""店ごとの決まり（提出用）。
- BACK_LOGO：裏（ロゴの位置＝デザイン画像の左右端）に必ず入れる店のロゴ。店名・Asanaのタスク名に鍵の文字が入っていれば使う。
  2026-11-23 ユーザー指定「ミルドラは必ず裏にロゴ入れる仕様にして」（MILDROUS のロゴ、logos/mildrous.png）。
使い方：python3 shop_rules.py '<店名やタスク名>' → ロゴのパス（無ければ空）
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
BACK_LOGO = {
    ('ミルドラ', 'ミルドラス', 'MILDROUS', 'mildrous'): 'logos/mildrous.png',
}


def back_logo(*texts):
    s = ' '.join(t for t in texts if t)
    for keys, p in BACK_LOGO.items():
        if any(k.lower() in s.lower() for k in keys): return os.path.join(HERE, p)
    return ''


if __name__ == '__main__':
    print(back_logo(*sys.argv[1:]))
