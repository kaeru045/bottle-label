# CLAUDE.md — ボトルラベル提出フォーマット

ユーザー向けの説明・依頼履歴は README.md。ここは開発メモ。

## 構成
- `src/index.html` が本体（1ファイル、素材は `src/assets/` を相対パスで読む）。編集はここだけ。
- `index.html`（ルート）は `python3 tools/build.py` で生成する公開用。素材を data URI、jsPDF/JSZip を `tools/vendor/` から埋め込み、保存は `<a download>` に差し替える。直接編集しない。
- 公開：GitHub Pages（main / root）→ https://kaeru045.github.io/bottle-label/ 。push 後数分で反映、CDN キャッシュで最大10分古い版が出る。
- 同じ `src/index.html` は claude.ai の Artifact（保存は `downloads` capability）としても公開している。Artifact では外部 fetch 不可・`<a download>` 不可なので、保存は `window.claude.use('downloads')`。
- 画面の `<span class="ver">ver …</span>` を更新のたびに書き換える（ユーザーが最新版か確認するため）。

## 合成のしくみ（compose）
- 出力は A4・300dpi（2481×3508px）。座標系は PDF pt（595.276×841.89）→ px は `S = 300/72`。
- `base.jpg`：背景＋説明文だけを描いた下地（デザイン部分は黒で描画）。
- `map.png`：R = デザインの透過量 T（白で描画−黒で描画）、G = どの配置か（1〜4：ボトル3か所＋デザイン枠、5：ボトル型タグ、6：スクエア、7：ハート型、8：猫、9：月、10：くま）。
- 各画素：`出力 = 下地 + T × デザイン色(u,v)`。(u,v) は `PLACE[i] = [a,b,c,d,e,f]`（画像の単位正方形 → PDF 座標のアフィン、Do 演算子の cm と同じ）の逆変換で求める。乗算レイヤー（GS11 Multiply）はこの式で再現できることを確認済み。
- 猫・くま・月のタグはユーザー提供の PNG（中のデザインは使わない）の透過部分だけを形として使い、ハート型と同じ大きさの枠に収めて `tag-cat/bear/moon` を作った。
- タグは `tag-<k>.png`（下地パッチ）と `tag-<k>-t.png`（T と G）で map を部分的に差し替える。位置調整は `TAGRECT` を基準に `PLACE` を作り直す（大きさ 50% = 枠をちょうど覆う）。枠外は白。
- タグの文字切り出し（makeCut）：範囲のふちで多い色を背景色とし、ふちから色の近い画素をたどって透明に（すき間も消すオプション）。タップした色も背景に追加。`tagDesign` は元の文字部分を周りの色で埋めたデザインで、合成ループで G>4（タグ）のときだけ使う。文字は drawTagText でタグの PLACE と同じ変換＋ユーザー調整で描き、タグの形で切り抜く。
- 上に重なる部品は `ov-*.png`（透過PNG、`OVL` に左上座標）：ネック色 `nk_*`、ネックシール `sl_lx_*`／`sl_cl_*`、デコ、リボン、タグシール、`nashi`（タグなし）、`note`（旧ネック説明・現在非表示）。
- ネック色の追加色は `nk_white` に乗算で着色、リボンの色違いは水色リボンの明度を保って色を置き換え（`recolorRibbon`）。

## 素材の取り出し（tools/extract/、参考用・パスは作業時のまま）
- 元データ：`a_提出用フォーマット.ai`（サブレイヤーを全部表示して保存し直したもの。リポジトリには入れていない・約145MB）。
- .ai の PDF 互換部分を pikepdf で読み、コンテンツストリームを `BDC /OC /MCn` ごとのレイヤー、さらに `q…Q` のグループに分割。
- 不要な描画演算子を `n` に置き換えて部品ごとに pypdfium2 でレンダリング（デザイン画像を黒・白・UV グラデーションに差し替えて3回描き、T と (u,v) を逆算）。
- 非表示のサブレイヤーは PDF 互換部分に入らないので、Illustrator 側で全部表示して保存し直してもらう必要がある。

## ユーザーの好み・決めごと
- 返答は日本語、短く。名称はユーザー指定を優先（スクエア、ハート型、ネック、Pピンク、SPL青、Pパープル、ロゴを裏に入れる など）。
- 保存名：`<名前>提出用.jpg/pdf`、`<名前>デザイン画像.jpg`、`<名前>タグ_<種類>.png`。
- 手動リサイズは開発中：`#resizeDev` ブロック、URL に `#dev` を付けたときだけ表示。公開側は ChatGPT プロンプトの案内文のみ。
- タグの文字切り出し（`#cutFeature`）も開発中扱いで、`#dev` のときだけ表示。
- 横長リサイズ（`#wideDev` → `#wideModal`）も開発中扱いで、`#dev` のときだけ表示。帯の数値（上下254/917px・左右134/1306px）はユーザーが「必ず守る」と指定したフォーマット。頭は上端270px・高さ360pxに置く（自動リサイズ tools/resize は標準414px＝ひと回り大きく、ユーザー指定 2026-10-28）。背景の描き足しは Photoshop のみ（ユーザー指定、ChatGPT 用のプロンプト・白余白の書き出しは削除済み）。生成した画像の位置合わせは、写真の内側の明るさ（平均を引いた差）が最小になる拡大・位置を 1/8→1/4→1/2 の解像度で探す。貼り付けは既存の `pick`／`pasteTargets` を使い、開いたら貼り付け先を写真（読み込み後は生成画像）に切り替える。
- 横長リサイズの自動背景拡張：`worker/firefly-proxy.js`（Cloudflare Worker）が Firefly API（IMS client_credentials → `/v2/storage/image` → `/v3/images/expand-async`、`placement.inset` で位置指定 → statusUrl をポーリング）を呼ぶ。シークレット `FIREFLY_CLIENT_ID`／`FIREFLY_CLIENT_SECRET`／`TOOL_PASS`。無料プランの外部通信50回/リクエストに収めるため、ポーリングは2秒×最大40回。ツール側の URL・合言葉は localStorage（`wideApi`／`widePass`）。Artifact 版は外部 fetch 不可なので自動は GitHub Pages 版のみ。
- 公開ページにお客様のロゴ等のサンプルを入れない。
