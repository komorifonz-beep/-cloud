"""stockwatch のコマンドライン。

  python -m stockwatch check        1回だけ全商品をチェックする (cron / GitHub Actions 向き)
  python -m stockwatch watch        指定間隔で回し続ける (自分のPCで動かす向き)
  python -m stockwatch test-mail    メール設定の確認
  python -m stockwatch probe URL    そのURLをどう判定するか試す (セレクタ調整用)
"""

from __future__ import annotations

import argparse
import random
import sys
import time
import traceback

from . import config as config_module
from . import detect, fetch, notify, shopify
from .state import State


def _log(message: str) -> None:
    print(message, flush=True)


def analyze(settings, product) -> detect.Detection:
    """1商品の在庫状態を判定する。Shopifyなら在庫APIを優先して使う。"""
    if product.method == "shopify":
        result = shopify.check(product, user_agent=settings.user_agent,
                               timeout=settings.timeout_seconds)
        if result is not None:
            return result
        _log(f"    (Shopify在庫APIが使えないためHTMLで判定します: {product.name})")

    html = fetch.get_html(
        product.url,
        user_agent=settings.user_agent,
        timeout=settings.timeout_seconds,
        extra_headers=product.headers,
    )
    # auto かつ Shopify のストアなら、HTMLより確実な在庫APIに切り替える。
    if product.method in ("auto", "shopify") and shopify.looks_like_shopify(html):
        result = shopify.check(product, user_agent=settings.user_agent,
                               timeout=settings.timeout_seconds)
        if result is not None:
            return result
    return detect.detect(html, product)


def check_product(settings, product, state: State) -> bool:
    """1商品をチェックし、通知したら True を返す。"""
    result = analyze(settings, product)

    # 一瞬だけ在庫ありに見えるケース(キャッシュ・描画途中)を弾くため、もう一度確認する。
    if result.in_stock and settings.confirm_recheck:
        time.sleep(settings.recheck_delay_seconds)
        recheck = analyze(settings, product)
        if not recheck.in_stock:
            _log(f"  △ {product.name}: 再確認で在庫なしに戻ったため通知しません")
            state.record(product.key, recheck.status, reason=recheck.reason, price=recheck.price)
            return False
        result = recheck

    previous = state.last_status(product.key)
    _log(f"  - {product.name}: {result.status} ({result.reason})")

    if result.status == detect.UNKNOWN:
        state.record(product.key, result.status, reason=result.reason, price=result.price)
        return False

    already_notified = product.notify_once and previous == detect.IN_STOCK
    if not result.in_stock or already_notified:
        state.record(product.key, result.status, reason=result.reason, price=result.price)
        return False

    cart_note, screenshot = "", None
    if product.cart_assist:
        from . import cart
        profile = settings.cart_profiles.get(product.cart_profile, {})
        outcome = cart.add_to_cart(product, profile, user_agent=settings.user_agent)
        cart_note, screenshot = outcome.note, outcome.screenshot
        _log(f"    カート: {outcome.note}")

    message = notify.build_message(settings.email, product, result,
                                   cart_note=cart_note, screenshot=screenshot)
    notify.send(settings.email, message)
    _log(f"  ★ {product.name}: 再入荷を通知しました → {', '.join(settings.email.to)}")
    state.record(product.key, result.status, notified=True,
                 reason=result.reason, price=result.price)
    return True


def run_once(settings, only: str | None = None) -> int:
    state = State(settings.state_path)
    targets = [p for p in settings.products if p.enabled]
    if only:
        targets = [p for p in targets if only.lower() in p.name.lower() or only in p.url]
    if not targets:
        _log("チェック対象の商品がありません。config.yml の products を確認してください。")
        return 1

    _log(f"{len(targets)} 件をチェックします")
    failures = 0
    for index, product in enumerate(targets):
        try:
            check_product(settings, product, state)
        except Exception as exc:
            failures += 1
            _log(f"  × {product.name}: {exc}")
        # サイトに連続アクセスしないよう少し待つ
        if index < len(targets) - 1:
            time.sleep(random.uniform(1.0, 3.0))
    state.save()
    return 0 if failures == 0 else 2


def run_forever(settings) -> int:
    _log(f"監視を開始します（約{settings.interval_seconds}秒間隔・Ctrl+C で停止）")
    while True:
        try:
            run_once(settings)
        except KeyboardInterrupt:
            _log("停止しました")
            return 0
        except Exception:
            traceback.print_exc()
        wait = settings.interval_seconds + random.uniform(0, settings.jitter_seconds)
        try:
            time.sleep(wait)
        except KeyboardInterrupt:
            _log("停止しました")
            return 0


def probe_one(settings, url: str) -> int:
    """指定URLをどう判定するか表示する。セレクタやvariantを詰めるときに使う。"""
    product = next((p for p in settings.products if p.url == url), None)
    if product is None:
        product = config_module.Product(name=url, url=url)

    _log("")
    _log("=" * 62)
    _log(f"URL      : {url}")
    try:
        html = fetch.get_html(url, user_agent=settings.user_agent,
                              timeout=settings.timeout_seconds,
                              extra_headers=product.headers)
    except fetch.FetchError as exc:
        _log(f"取得失敗 : {exc}")
        return 1
    _log(f"取得サイズ: {len(html):,} バイト")

    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    if shopify.looks_like_shopify(html):
        _log("Shopify  : はい。在庫APIを使って判定します")
        variants = shopify.list_variants(product, user_agent=settings.user_agent,
                                         timeout=settings.timeout_seconds)
        if variants:
            _log("選べる種類（variant に書ける値）:")
            for v in variants:
                mark = "○ 在庫あり" if v["available"] else "× 在庫なし"
                sku = f" / SKU:{v['sku']}" if v["sku"] else ""
                _log(f"    {mark}  \"{v['title']}\"  {v['price'] or ''}{sku}")
        else:
            _log("           在庫APIの取得に失敗しました（HTML判定に切り替わります）")
    else:
        _log("Shopify  : いいえ。HTMLの中身から判定します")
        _log(f"JSON-LD  : {detect.from_jsonld(soup)}")
        _log(f"microdata: {detect.from_microdata(soup)}")
        if product.in_stock_selector or product.out_of_stock_selector:
            _log(f"CSS      : {detect.from_css(soup, product.in_stock_selector, product.out_of_stock_selector)}")
        _log(f"文言     : {detect.from_keywords(detect.visible_text(soup), product.in_stock_keywords, product.out_of_stock_keywords)}")

    result = analyze(settings, product)
    label = {"in_stock": "★ 在庫あり（いま買えます）",
             "out_of_stock": "－ 売り切れ",
             "unknown": "? 判定できませんでした"}.get(result.status, result.status)
    _log(f"→ 判定    : {label}")
    _log(f"→ 根拠    : {result.reason}")
    _log(f"→ 価格    : {result.price or '取得できず'}")
    return 0 if result.status != detect.UNKNOWN else 1


def probe(settings, url: str | None) -> int:
    """URL指定があればそれを、無ければ config.yml の全商品を調べる。"""
    if url:
        return probe_one(settings, url)
    if not settings.products:
        _log("config.yml に商品が登録されていません。URLを直接指定してください。")
        return 1
    _log(f"config.yml の {len(settings.products)} 商品を調べます")
    worst = 0
    for product in settings.products:
        worst = max(worst, probe_one(settings, product.url))
    _log("")
    _log("=" * 62)
    if worst == 0:
        _log("すべて正しく判定できています。このまま監視を始められます。")
    else:
        _log("判定できなかった商品があります。この出力を貼って相談してください。")
    return worst


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="stockwatch", description="再入荷をメールで知らせる")
    parser.add_argument("-c", "--config", default="config.yml", help="設定ファイル (既定: config.yml)")
    sub = parser.add_subparsers(dest="command")

    check_cmd = sub.add_parser("check", help="1回だけチェックする")
    check_cmd.add_argument("--only", help="商品名またはURLの一部で対象を絞る")
    sub.add_parser("watch", help="間隔をあけてチェックし続ける")
    sub.add_parser("test-mail", help="テストメールを送る")
    probe_cmd = sub.add_parser("probe", help="判定結果を表示する（設定の確認用）")
    probe_cmd.add_argument("url", nargs="?", help="省略すると config.yml の全商品を調べます")

    args = parser.parse_args(argv)
    command = args.command or "check"

    try:
        settings = config_module.load(args.config)
    except FileNotFoundError as exc:
        if command != "probe":
            _log(str(exc))
            return 1
        # probe は設定を詰める前の動作確認に使うので、既定値で動かす。
        _log(f"（{args.config} が無いため既定設定で判定します）")
        settings = config_module.Settings(email=config_module.EmailConfig(), products=[])

    if command == "check":
        return run_once(settings, only=getattr(args, "only", None))
    if command == "watch":
        return run_forever(settings)
    if command == "test-mail":
        notify.send_test(settings.email)
        _log(f"テストメールを送信しました → {', '.join(settings.email.to)}")
        return 0
    if command == "probe":
        return probe(settings, getattr(args, "url", None))
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
