# stockwatch — 売り切れ商品の再入荷をメールで知らせる

売り切れている商品ページを定期的に見に行き、買える状態になった瞬間にメールを送ります。
設定すれば、再入荷時にブラウザを自動操作して**カートに入れるところまで**代行します。

```
売り切れ検知 → 定期チェック → 再入荷 → 誤報チェック → メール送信 (→ カート投入)
```

---

## 1. できること

| 機能 | 説明 |
|---|---|
| 再入荷メール | 買える状態になったらHTMLメールで通知。商品名・価格・判定理由・リンク付き |
| 誤報の抑制 | 在庫ありを検知したら20秒後にもう一度確認してから送る |
| 重複防止 | 在庫がある間ずっとメールが来ることはない。売り切れ→再入荷のたびに1通 |
| 5通りの判定 | Shopify在庫API / 構造化データ / microdata / CSSセレクタ / ページの文言 |
| サイズ別監視 | Shopifyなら「Mサイズだけ」「27.0cmだけ」の在庫を見張れる |
| カート投入代行 | 再入荷時にログイン〜カート投入まで自動。注文確定だけ自分で押す |
| 無人運用 | GitHub Actions で1時間おきに自動チェック（PCを起動しておく必要なし） |

---

## 2. セットアップ

やり方は2通りあります。**Aだけで全部完結します。** PCに何もインストールせず、
ターミナル（黒い画面）も使いません。ブラウザだけです。

---

### A. ブラウザだけで始める（おすすめ）

#### A-1. Gmailの「アプリパスワード」を取る（5分）

普段のGmailパスワードは使えません（Googleが拒否します）。専用の16桁を発行します。

1. Googleアカウントで**2段階認証を有効**にする（未設定ならこれが先）
2. https://myaccount.google.com/apppasswords を開く
3. アプリ名に `stockwatch` と入れて作成
4. 表示された**16桁**をコピーする（この画面を閉じると二度と見られません）

#### A-2. GitHubに登録する（2分）

1. このリポジトリのページを開く
2. 上部の **Settings** タブ
3. 左メニューの **Secrets and variables** → **Actions**
4. 緑の **New repository secret** ボタン
5. 入力して **Add secret**
   - Name: `SMTP_PASSWORD`
   - Secret: さっきの16桁

> ここに入れた値はGitHubが暗号化して保管し、画面上でも二度と表示されません。
> ログにも出ない仕組みになっています。

#### A-3. 動作確認する（1分）

1. 上部の **Actions** タブ
2. 左のリストから **「1. 動作確認」**
3. 右の **Run workflow** ボタン → 「テストメールも送る」に**チェックを入れて** → 緑の Run workflow

1〜2分で終わります。実行中の行をクリックすると結果が表示されます。

こう出れば成功です。

```
Shopify  : はい。在庫APIを使って判定します
選べる種類（variant に書ける値）:
    × 在庫なし  "M"  ¥12,800
    × 在庫なし  "L"  ¥12,800
→ 判定    : － 売り切れ
```

同時にテストメールも届きます。**ここまで来たら設定完了です。**
あとは1時間おきに自動でチェックし、再入荷したらメールが届きます。

> `判定    : ? 判定できませんでした` と出た場合は、その画面の内容をコピーして
> 相談してください。サイトに合わせて設定を直します。

#### A-4. 商品を追加・変更する

`config.yml` をブラウザ上で直接編集できます。

1. リポジトリのファイル一覧から **config.yml** をクリック
2. 右上の**鉛筆アイコン**（Edit this file）
3. `products:` の下に追記する

```yaml
  - name: "商品の名前（自分が分かればなんでもOK）"
    url: "https://qlia.store/products/XXXXX"
    method: auto
```

4. 下の **Commit changes** ボタンで保存

サイズを指定したいときは、A-3の「選べる種類」に出た値をそのまま書きます。

```yaml
  - name: "あの商品 Mサイズだけ"
    url: "https://qlia.store/products/1s015"
    method: shopify
    variant: "M"
```

同じURLをサイズ違いで何個でも登録できます。それぞれ独立して通知されます。

---

### B. 自分のPCで動かす（反応を速くしたい場合）

GitHubの定期実行は混雑時に数分〜十数分遅れたり、まれにスキップされることがあります。分刻みで売り切れる商品を
狙うなら、PCで動かしたほうが確実です。**Aと併用もできます。**

Python 3.9以上が必要です。ターミナル（Macは「ターミナル」、Windowsは「PowerShell」）で:

```bash
git clone https://github.com/komorifonz-beep/-cloud.git
cd -cloud
pip install -r requirements.txt
```

アプリパスワードを環境変数に入れます。

```bash
# Mac / Linux
export SMTP_PASSWORD="ここに16桁"

# Windows (PowerShell)
$env:SMTP_PASSWORD="ここに16桁"
```

確認して、監視を開始します。

```bash
python -m stockwatch probe        # 設定が正しいか確認
python -m stockwatch test-mail    # メールが届くか確認
python -m stockwatch watch        # 監視開始（Ctrl+C で停止）
```

`watch` はPCを閉じると止まります。つけっぱなしにできない場合はAを使ってください。

## 3. 実行コストについて（Claudeのトークンは消費しません）

**このツールはClaudeを一切呼びません。** ただのPythonスクリプトで、やっているのは
「ページを取得する → 在庫を判定する → メールを送る」だけです。
何回動かしても、何ヶ月動かしても、AIの利用料は **0円・0トークン** です。

トークンを消費するのは、僕（Claude）とこうして会話しているときだけです。
設定の相談や不具合の修正を頼むときは消費しますが、監視そのものは無関係です。

実際にかかるコストはこれだけです。

| 動かす場所 | 料金 | 備考 |
|---|---|---|
| GitHub Actions（公開リポジトリ） | **無料** | 実行時間の上限なし |
| GitHub Actions（非公開リポジトリ） | **実質無料** | 無料枠2,000分/月に対し、4商品1時間おきで月約15〜25分 |
| 自分のPC（watchモード） | **無料** | 電気代だけ |

4商品を1時間おきにチェックした場合の1回あたりの処理は、HTTPリクエスト4〜8回、
実行時間は10秒ほどです。通信量も1回あたり数百KB程度で、負荷はごくわずかです。

## 4. 判定を手で教える（`unknown` になったとき）

### Shopifyのお店なら、ほぼ設定不要

`method: auto` のままで大丈夫です。ページを読んだ時点でShopifyだと分かると、
自動的に**在庫API**（商品URLの末尾に `.js` を付けたもの）に切り替わります。
HTMLの文言を読むより確実で、JavaScriptで在庫を描画するテーマでも正しく取れます。

サイズや色を指定したいときは `variant` を足してください。

```yaml
  - name: "あの商品 Mサイズ"
    url: "https://qlia.store/products/1s015"
    method: shopify
    variant: "M"        # probe を実行すると、選べる値の一覧が出ます
```

同じURLをサイズ違いで複数登録できます。それぞれ独立して通知されるので、
「Mが復活したせいでLの通知が来なくなる」ようなことは起きません。

### Shopify以外のお店

商品ページをブラウザで開き、「カートに入れる」ボタンを**右クリック → 検証**します。
出てきたHTMLの `class` や `id` を `config.yml` に書きます。

```html
<!-- 例: こういうHTMLが見えたら -->
<button class="btn btn-primary add-cart-button">カートに入れる</button>
<div class="stock-status soldout">SOLD OUT</div>
```

```yaml
  - name: "欲しいスニーカー 27.0cm"
    url: "https://shop.example.com/products/12345"
    method: css
    in_stock_selector: "button.add-cart-button"     # 押せる状態なら在庫あり
    out_of_stock_selector: ".stock-status.soldout"  # これがあれば売り切れ
```

セレクタが分からない場合は、文言で判定する手もあります。

```yaml
    method: keyword
    out_of_stock_keywords: ["入荷次第出荷", "再入荷をお知らせ"]
    in_stock_keywords: ["カートに入れる"]
```

書き換えたら `probe` でもう一度確認してください。

> **JavaScriptで在庫を描画するサイト**（ページのHTMLに在庫情報が無い）は、この方法では
> 判定できません。その場合は `cart_assist` と同じ Playwright を使う必要があるので、
> 対象サイトを教えてもらえれば個別に対応を追加します。

---

## 5. コマンドと設定の調整

### コマンド一覧（PCで動かす場合）

| コマンド | 用途 |
|---|---|
| `python -m stockwatch probe` | config.yml の全商品の判定結果を表示（設定確認用） |
| `python -m stockwatch probe "URL"` | 指定URLだけ調べる。登録前の下見にも使える |
| `python -m stockwatch test-mail` | メール設定の確認 |
| `python -m stockwatch check` | 1回だけチェック（cronやタスクスケジューラから呼ぶ用） |
| `python -m stockwatch check --only "商品名"` | 対象を名前で絞ってチェック |
| `python -m stockwatch watch` | 間隔をあけてチェックし続ける |

### チェック間隔を変える

- **GitHub Actions**: `.github/workflows/stock-watch.yml` の `cron: "0 * * * *"` を編集
  （`"0 */2 * * *"` で2時間おき、`"*/30 * * * *"` で30分おき。
  GitHubの最短は5分ですが、短くしても混雑時の遅延やスキップは避けられません）
- **PCのwatchモード**: `config.yml` の `interval_seconds`（秒数）を編集

### 一時的に止める

商品ごとに `enabled: false` を足すと、その商品だけ見張らなくなります。

```yaml
  - name: "もう要らない商品"
    url: "https://qlia.store/products/XXXXX"
    enabled: false
```

全部止めたいときは、Actionsタブ →「2. 自動チェック」→ 右上の `...` → **Disable workflow**。

## 6. 自動購入について（正直な話）

「再入荷したら自動で買う」は**技術的には可能**ですが、このツールは**注文の確定だけは
あえて自動化していません**。理由は3つあります。

1. **規約違反のリスク** — Amazon・楽天・ヨドバシをはじめ多くのECサイトは、利用規約で
   自動購入プログラム(bot)の利用を禁止しています。発覚するとアカウント停止＝
   過去の購入履歴やポイントごと失う可能性があります。
2. **事故が止められない** — 型番違い、転売業者の高額出品、価格改定。人間が0.5秒
   見れば気づくものが、全自動だと気づかないまま決済まで走ります。
3. **そもそも止められる** — 人気商品ほどCAPTCHAやbot検知が入ります。無理に突破する
   仕組みは上記1のリスクを跳ね上げるだけで、安定もしません。

### 代わりにこうしています

`cart_assist: true` を設定すると、再入荷を検知した瞬間に自動で**ログイン → サイズ選択
→ カート投入**まで済ませ、カート画面のスクリーンショット付きでメールを送ります。
届いたメールから開いて**「注文を確定する」を押すだけ**です。

実質的な所要時間はほとんど変わらず、リスクだけが無くなります。

```yaml
products:
  - name: "欲しいスニーカー 27.0cm"
    url: "https://shop.example.com/products/12345"
    cart_assist: true
    cart_profile: my_shop

cart_profiles:
  my_shop:
    login_url: "https://shop.example.com/login"
    login_steps:
      - fill: "#email"
        value: ${SHOP_USER}
      - fill: "#password"
        value: ${SHOP_PASSWORD}
      - click: "button[type=submit]"
      - wait_for: ".account-menu"
    add_to_cart_steps:
      - select: "select#size"
        value: "27.0"
      - click: "button.add-to-cart"
      - wait_for: ".cart-count"
    cart_url: "https://shop.example.com/cart"
```

使うには Playwright が必要です。

```bash
pip install playwright
playwright install chromium
```

### 完全自動にしてよいケース

**発注APIが公式に提供されている場合**は、話がまったく別です。規約上も問題なく、
動作も安定します。業務用食材の卸（アスクル、Amazonビジネス、各社のEDI/発注システム）
なら、在庫が戻ったら自動発注まで一気通貫で組めます。

沢村さんの食材発注でそういう用途があれば、対象のサイト／システムを教えてください。
API方式で組み直します。

---

## 7. よくある詰まりどころ

| 症状 | 原因と対処 |
|---|---|
| `Username and Password not accepted` | 普段のGmailパスワードを使っている。アプリパスワード16桁を発行し直す |
| テストメールが届かない | 迷惑メールフォルダを確認。`config.yml` の `to:` のアドレス誤りも多い |
| `unknown` としか出ない | JavaScript描画のサイト。上記「判定を手で教える」か、個別対応が必要 |
| 売り切れなのに在庫ありと判定 | 関連商品の「カートに入れる」を拾っている。`in_stock_selector` で範囲を絞る |
| メールが来すぎる | `notify_once: true` になっているか確認 |
| `HTTP 403` で取得できない | アクセスをブロックされている。`interval_seconds` を長くする |
| Actionsが動かなくなった | 60日リポジトリ放置で定期実行が自動停止する。手動実行すれば再開 |
| Actionsタブが見当たらない | Settings → Actions → General で Actions が有効か確認 |
| `SMTP_PASSWORD が未登録` と出る | READMEのA-2を実施。Secret名のスペルも確認（大文字） |

---

## 8. 運用の心得

- **間隔を短くしすぎない。** 1時間で十分です。1分間隔は相手のサーバーに迷惑ですし、
  IPごとブロックされて元も子もありません。
- **見張る商品は絞る。** 1商品につき1リクエストです。50件登録すれば50回叩きます。
- **チェックしても履歴は汚れない。** `state.json` が更新されるのは在庫状態が
  変わったときだけです。売り切れのままの回はコミットを作りません。
- **`browser-state.json` は絶対にコミットしない。** ログインCookieそのものです（.gitignore済み）。

---

## 9. ファイル構成

```
stockwatch/
  cli.py       コマンドライン・メインの流れ
  config.py    config.yml の読み込み
  fetch.py     ページ取得（リトライ付き）
  detect.py    在庫判定（JSON-LD / microdata / CSS / 文言）
  shopify.py   Shopify在庫APIでの判定（サイズ別対応）
  notify.py    メール作成と送信
  state.py     前回の状態の記録（重複通知の防止）
  cart.py      ブラウザ自動操作でカート投入
tests/         判定ロジックのテスト
config.example.yml
.github/workflows/stock-watch.yml
```

テストの実行:

```bash
python tests/test_detect.py     # 在庫判定・メール生成（11件）
python tests/test_shopify.py    # Shopify在庫API（10件）
```
