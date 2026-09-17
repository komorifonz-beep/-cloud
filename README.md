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
| 4通りの判定 | 構造化データ / microdata / CSSセレクタ / ページの文言 |
| カート投入代行 | 再入荷時にログイン〜カート投入まで自動。注文確定だけ自分で押す |
| 無人運用 | GitHub Actions で15分おきに自動チェック（PCを起動しておく必要なし） |

---

## 2. セットアップ（15分くらい）

### 2-1. 取ってきて動かす準備

```bash
git clone https://github.com/komorifonz-beep/-cloud.git
cd -cloud
pip install -r requirements.txt
cp config.example.yml config.yml
```

### 2-2. Gmailの「アプリパスワード」を取る

普段のGmailパスワードは使えません（Googleが拒否します）。専用の16桁パスワードを発行します。

1. Googleアカウントで**2段階認証を有効**にする（未設定なら先にこれ）
2. https://myaccount.google.com/apppasswords を開く
3. アプリ名に `stockwatch` と入れて作成
4. 表示された**16桁**を控える（この画面を閉じると二度と見られません）

控えた16桁を環境変数に入れます。

```bash
# Mac / Linux
export SMTP_PASSWORD="abcdefghijklmnop"

# Windows (PowerShell)
$env:SMTP_PASSWORD="abcdefghijklmnop"
```

毎回打つのが面倒なら `.env` ファイルに書いておくか、シェルの設定ファイルに追記してください。

### 2-3. メールが届くか確認する

```bash
python -m stockwatch test-mail
```

受信箱にテストメールが届けば成功です。届かない場合は「よくある詰まりどころ」へ。

### 2-4. 見張りたい商品を登録する

`config.yml` の `products:` を書き換えます。まずは名前とURLだけでOKです。

```yaml
products:
  - name: "欲しいスニーカー 27.0cm"
    url: "https://shop.example.com/products/12345"
    method: auto
```

### 2-5. 判定が正しいか確かめる

**ここを飛ばさないでください。** 商品ページの作りはサイトごとに違うので、
自動判定が効かないことがあります。

```bash
python -m stockwatch probe "https://shop.example.com/products/12345"
```

こう表示されれば正しく判定できています。

```
→ 総合判定: Detection(status='out_of_stock', reason='JSON-LD availability=.../OutOfStock', price='¥12,800')
```

`unknown` や、明らかに実際と違う結果が出た場合は次の「判定を手で教える」へ。

---

## 3. 判定を手で教える（`unknown` になったとき）

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

## 4. 動かす

### A. 自分のPCで回し続ける（反応が速い）

```bash
python -m stockwatch watch
```

`config.yml` の `interval_seconds`（既定600秒＝10分）ごとにチェックします。
止めるときは `Ctrl + C`。PCを閉じると止まります。

### B. GitHub Actions で無人運用（PCを閉じてOK・おすすめ）

1. `config.yml` をコミットして push する（パスワードは `${SMTP_PASSWORD}` のままにすること）
2. GitHubリポジトリの **Settings → Secrets and variables → Actions → New repository secret**
   - Name: `SMTP_PASSWORD`
   - Secret: 控えた16桁
3. **Actions** タブ → `stock-watch` → **Run workflow** で手動実行して動作確認

以降は15分おきに自動でチェックします。間隔を変えたいときは
`.github/workflows/stock-watch.yml` の `cron: "*/15 * * * *"` を編集してください。

> GitHubの定期実行は混雑時に**5〜15分遅れる**ことがあります。分刻みで売り切れる商品には
> 向きません。その場合は A のPC常駐を使ってください。

### C. 1回だけチェックする（Macの`cron`やタスクスケジューラから呼ぶ用）

```bash
python -m stockwatch check
python -m stockwatch check --only "スニーカー"    # 名前で絞る
```

---

## 5. 自動購入について（正直な話）

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

## 6. よくある詰まりどころ

| 症状 | 原因と対処 |
|---|---|
| `Username and Password not accepted` | 普段のGmailパスワードを使っている。アプリパスワード16桁を発行し直す |
| テストメールが届かない | 迷惑メールフォルダを確認。`config.yml` の `to:` のアドレス誤りも多い |
| `unknown` としか出ない | JavaScript描画のサイト。上記「判定を手で教える」か、個別対応が必要 |
| 売り切れなのに在庫ありと判定 | 関連商品の「カートに入れる」を拾っている。`in_stock_selector` で範囲を絞る |
| メールが来すぎる | `notify_once: true` になっているか確認 |
| `HTTP 403` で取得できない | アクセスをブロックされている。`interval_seconds` を長くする |
| Actionsが動かなくなった | 60日リポジトリ放置で定期実行が自動停止する。手動実行すれば再開 |

---

## 7. 運用の心得

- **間隔を短くしすぎない。** 10〜15分で十分です。1分間隔は相手のサーバーに迷惑ですし、
  IPごとブロックされて元も子もありません。
- **見張る商品は絞る。** 1商品につき1リクエストです。50件登録すれば50回叩きます。
- **`browser-state.json` は絶対にコミットしない。** ログインCookieそのものです（.gitignore済み）。

---

## 8. ファイル構成

```
stockwatch/
  cli.py       コマンドライン・メインの流れ
  config.py    config.yml の読み込み
  fetch.py     ページ取得（リトライ付き）
  detect.py    在庫判定（JSON-LD / microdata / CSS / 文言）
  notify.py    メール作成と送信
  state.py     前回の状態の記録（重複通知の防止）
  cart.py      ブラウザ自動操作でカート投入
tests/         判定ロジックのテスト
config.example.yml
.github/workflows/stock-watch.yml
```

テストの実行:

```bash
python tests/test_detect.py
```
