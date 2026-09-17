"""商品ページのHTMLから在庫状態を判定する。

判定方法は4つ。auto は上から順に試して、最初に結論が出たものを採用する。
  1. jsonld    : schema.org の構造化データ (availability) を読む。最も確実。
  2. microdata : itemprop="availability" を読む。
  3. css       : 設定したCSSセレクタの有無で判定する。
  4. keyword   : ページ本文の文言で判定する。最後の手段。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from bs4 import BeautifulSoup

IN_STOCK = "in_stock"
OUT_OF_STOCK = "out_of_stock"
UNKNOWN = "unknown"

_IN_TOKENS = ("instock", "limitedavailability", "onlineonly", "instoreonly")
_OUT_TOKENS = ("outofstock", "soldout", "discontinued")
_SOON_TOKENS = ("preorder", "presale", "backorder")

_PRICE_RE = re.compile(r"[¥￥]\s*([\d,]+)|([\d,]+)\s*円")


@dataclass
class Detection:
    status: str
    reason: str          # どうやってその結論に至ったか (ログとメールに出す)
    price: str | None = None

    @property
    def in_stock(self) -> bool:
        return self.status == IN_STOCK


def _visible_text(soup: BeautifulSoup) -> str:
    clone = BeautifulSoup(str(soup), "lxml")
    for tag in clone(["script", "style", "noscript", "template"]):
        tag.decompose()
    return clone.get_text(" ", strip=True)


def _iter_json_nodes(node):
    """入れ子のdict/listを全部たどる。"""
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _iter_json_nodes(value)
    elif isinstance(node, list):
        for value in node:
            yield from _iter_json_nodes(value)


def _classify_availability(value: str) -> str | None:
    token = value.lower().replace("http://", "").replace("https://", "")
    token = token.split("/")[-1].replace("_", "").replace("-", "").replace(" ", "")
    if any(t in token for t in _OUT_TOKENS):
        return OUT_OF_STOCK
    if any(t in token for t in _SOON_TOKENS):
        return OUT_OF_STOCK       # 予約・入荷待ちは「まだ買えない」扱い
    if any(t in token for t in _IN_TOKENS):
        return IN_STOCK
    return None


def from_jsonld(soup: BeautifulSoup) -> Detection | None:
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        payload = script.string or script.get_text()
        if not payload:
            continue
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            continue
        for node in _iter_json_nodes(data):
            availability = node.get("availability")
            if not isinstance(availability, str):
                continue
            status = _classify_availability(availability)
            if status:
                price = node.get("price") or node.get("lowPrice")
                price_text = f"{price}" if price not in (None, "") else None
                return Detection(status, f"JSON-LD availability={availability}", price_text)
    return None


def from_microdata(soup: BeautifulSoup) -> Detection | None:
    for tag in soup.find_all(attrs={"itemprop": "availability"}):
        value = tag.get("href") or tag.get("content") or tag.get_text(strip=True)
        if not value:
            continue
        status = _classify_availability(value)
        if status:
            return Detection(status, f"microdata availability={value}")
    return None


def _selector_hit(soup: BeautifulSoup, selector: str):
    """セレクタに一致し、かつ disabled でない要素を返す。"""
    try:
        elements = soup.select(selector)
    except Exception:
        return None
    for element in elements:
        if element.has_attr("disabled"):
            continue
        if "disabled" in " ".join(element.get("class") or []):
            continue
        if element.get("aria-disabled") == "true":
            continue
        return element
    return None


def from_css(soup: BeautifulSoup, in_selector: str, out_selector: str) -> Detection | None:
    if out_selector and _selector_hit(soup, out_selector) is not None:
        return Detection(OUT_OF_STOCK, f"CSSセレクタ一致: {out_selector}")
    if in_selector:
        if _selector_hit(soup, in_selector) is not None:
            return Detection(IN_STOCK, f"CSSセレクタ一致: {in_selector}")
        # 「押せるボタンが無い」= 売り切れ。out_selector 未設定でも結論を出す。
        return Detection(OUT_OF_STOCK, f"CSSセレクタ不一致(または無効化): {in_selector}")
    return None


def from_keywords(text: str, in_keywords, out_keywords) -> Detection:
    lowered = text.lower()
    hit_out = [k for k in out_keywords if k.lower() in lowered]
    hit_in = [k for k in in_keywords if k.lower() in lowered]

    # 「再入荷通知を受け取る」のような文言は売り切れページ特有なので優先する。
    if hit_out and not hit_in:
        return Detection(OUT_OF_STOCK, f"文言一致: {', '.join(hit_out[:3])}")
    if hit_in and not hit_out:
        return Detection(IN_STOCK, f"文言一致: {', '.join(hit_in[:3])}")
    if hit_in and hit_out:
        return Detection(
            OUT_OF_STOCK,
            f"在庫あり/なしの文言が混在({', '.join(hit_out[:2])} / {', '.join(hit_in[:2])})ため"
            "安全側に倒して売り切れ扱い",
        )
    return Detection(UNKNOWN, "在庫を示す文言が見つからない")


def find_price(soup: BeautifulSoup, selector: str) -> str | None:
    if selector:
        node = soup.select_one(selector)
        if node:
            return node.get_text(" ", strip=True)
    match = _PRICE_RE.search(_visible_text(soup)[:4000])
    if match:
        number = match.group(1) or match.group(2)
        return f"¥{number}"
    return None


def visible_text(soup: BeautifulSoup) -> str:
    """スクリプト等を除いたページ本文を返す。"""
    return _visible_text(soup)


def detect(html: str, product) -> Detection:
    """product の設定に従って html を判定する。"""
    soup = BeautifulSoup(html, "lxml")
    method = (product.method or "auto").lower()

    order = {
        "auto": ("jsonld", "microdata", "css", "keyword"),
        "jsonld": ("jsonld",),
        "microdata": ("microdata",),
        "css": ("css",),
        "keyword": ("keyword",),
    }.get(method, ("jsonld", "microdata", "css", "keyword"))

    result: Detection | None = None
    for step in order:
        if step == "jsonld":
            result = from_jsonld(soup)
        elif step == "microdata":
            result = from_microdata(soup)
        elif step == "css":
            result = from_css(soup, product.in_stock_selector, product.out_of_stock_selector)
        elif step == "keyword":
            result = from_keywords(
                _visible_text(soup),
                product.in_stock_keywords,
                product.out_of_stock_keywords,
            )
        if result is not None and result.status != UNKNOWN:
            break

    if result is None:
        result = Detection(UNKNOWN, "判定方法が設定されていない")
    if not result.price:
        result.price = find_price(soup, product.price_selector)
    return result
