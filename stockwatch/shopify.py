"""Shopify ストア専用の在庫チェック。

Shopify は商品ページのURLに `.js` を付けると、在庫状況を JSON で返す。
    https://example.com/products/abc      → 商品ページ(HTML)
    https://example.com/products/abc.js   → 在庫データ(JSON)

HTMLの文言を読むより確実で、しかも
  - サイズ/色ごと(variant)の在庫が分かる
  - JavaScriptで描画するテーマでも正しく取れる
  - 転送量が1/20以下でサイトへの負荷が軽い
という利点がある。これは Shopify が公開している通常のストアフロント機能で、
ブラウザが商品ページを表示するときに使っているのと同じもの。
"""

from __future__ import annotations

import json

from .detect import IN_STOCK, OUT_OF_STOCK, Detection
from .fetch import FetchError, get_html

# Shopify テーマなら必ずどれかが埋め込まれている
_MARKERS = ("cdn.shopify.com", "Shopify.theme", "shopify-section", "/cdn/shop/")


def looks_like_shopify(html: str) -> bool:
    head = html[:200_000]
    return any(marker in head for marker in _MARKERS)


def _product_js_url(url: str) -> str:
    base = url.split("?")[0].split("#")[0].rstrip("/")
    return base if base.endswith(".js") else base + ".js"


def _format_price(cents) -> str | None:
    """Shopify は価格を「銭」単位の整数で返す (12800円 → 1280000)。"""
    try:
        return f"¥{int(cents) // 100:,}"
    except (TypeError, ValueError):
        return None


def _match_variant(variants: list, wanted: str):
    wanted_norm = wanted.strip().lower()
    for variant in variants:
        title = str(variant.get("title", "")).strip().lower()
        options = [str(o).strip().lower() for o in (variant.get("options") or [])]
        sku = str(variant.get("sku", "")).strip().lower()
        if wanted_norm in (title, sku) or wanted_norm in options:
            return variant
    # 完全一致しなければ部分一致で探す
    for variant in variants:
        if wanted_norm in str(variant.get("title", "")).lower():
            return variant
    return None


def check(product, *, user_agent: str, timeout: int = 20) -> Detection | None:
    """在庫を判定する。Shopifyでない/取得失敗なら None を返して呼び出し元に任せる。"""
    try:
        payload = get_html(
            _product_js_url(product.url),
            user_agent=user_agent,
            timeout=timeout,
            extra_headers={"Accept": "application/json", **product.headers},
            retries=2,
        )
        data = json.loads(payload)
    except (FetchError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or "available" not in data:
        return None

    title = data.get("title") or product.name
    variants = data.get("variants") or []
    price = _format_price(data.get("price"))

    # サイズ・色を指定している場合はその1つだけを見る
    if product.variant:
        variant = _match_variant(variants, product.variant)
        if variant is None:
            available = [str(v.get("title")) for v in variants]
            return Detection(
                OUT_OF_STOCK,
                f"指定した '{product.variant}' が見つからない"
                f"（存在する選択肢: {', '.join(available) or 'なし'}）",
                price,
            )
        status = IN_STOCK if variant.get("available") else OUT_OF_STOCK
        return Detection(
            status,
            f"Shopify在庫API: {title} / {variant.get('title')} → "
            f"{'在庫あり' if status == IN_STOCK else '在庫なし'}",
            _format_price(variant.get("price")) or price,
        )

    # 指定なしなら、どれか1つでも買えれば在庫ありとする
    in_stock = [v for v in variants if v.get("available")]
    if data.get("available") and in_stock:
        names = ", ".join(str(v.get("title")) for v in in_stock[:5])
        return Detection(IN_STOCK, f"Shopify在庫API: 購入可能な選択肢 → {names}", price)
    return Detection(OUT_OF_STOCK, f"Shopify在庫API: 全{len(variants)}種すべて在庫なし", price)
