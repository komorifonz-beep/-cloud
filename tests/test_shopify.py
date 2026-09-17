"""Shopify在庫APIの判定テスト。ローカルにサーバーを立てて実際に通信する。"""

import http.server
import json
import socketserver
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from stockwatch import shopify                    # noqa: E402
from stockwatch.config import Product             # noqa: E402
from stockwatch.detect import IN_STOCK, OUT_OF_STOCK  # noqa: E402

UA = "stockwatch-test"

SOLD_OUT = {
    "id": 1, "title": "テストTシャツ", "available": False, "price": 1280000,
    "variants": [
        {"id": 11, "title": "M", "available": False, "price": 1280000,
         "options": ["M"], "sku": "TS-M"},
        {"id": 12, "title": "L", "available": False, "price": 1280000,
         "options": ["L"], "sku": "TS-L"},
    ],
}
M_BACK = json.loads(json.dumps(SOLD_OUT))
M_BACK["available"] = True
M_BACK["variants"][0]["available"] = True

_PAYLOAD = {"data": SOLD_OUT}


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if "notshopify" in self.path:
            body, ctype = "<html><body>ふつうのお店</body></html>".encode(), "text/html"
        elif self.path.endswith(".js"):
            body, ctype = json.dumps(_PAYLOAD["data"]).encode(), "application/json"
        else:
            body = (b'<html><head><script src="https://cdn.shopify.com/s/a.js">'
                    b"</script></head><body>Shopify.theme</body></html>")
            ctype = "text/html"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


_server = socketserver.TCPServer(("127.0.0.1", 0), _Handler)
PORT = _server.server_address[1]
threading.Thread(target=_server.serve_forever, daemon=True).start()
BASE = f"http://127.0.0.1:{PORT}/products/test"


def test_product_js_url():
    assert shopify._product_js_url("https://x.com/products/a") == "https://x.com/products/a.js"
    assert shopify._product_js_url("https://x.com/products/a?v=1") == "https://x.com/products/a.js"
    assert shopify._product_js_url("https://x.com/products/a.js") == "https://x.com/products/a.js"


def test_looks_like_shopify():
    assert shopify.looks_like_shopify('<script src="https://cdn.shopify.com/x"></script>')
    assert not shopify.looks_like_shopify("<html><body>ordinary shop</body></html>")


def test_all_variants_sold_out():
    _PAYLOAD["data"] = SOLD_OUT
    result = shopify.check(Product("t", BASE), user_agent=UA)
    assert result.status == OUT_OF_STOCK, result
    assert result.price == "¥12,800", result.price


def test_specific_variant_sold_out():
    _PAYLOAD["data"] = SOLD_OUT
    result = shopify.check(Product("t", BASE, variant="M"), user_agent=UA)
    assert result.status == OUT_OF_STOCK, result


def test_specific_variant_back_in_stock():
    _PAYLOAD["data"] = M_BACK
    assert shopify.check(Product("t", BASE, variant="M"), user_agent=UA).status == IN_STOCK


def test_other_variant_still_sold_out():
    # Mが復活してもLは売り切れのまま → Lを見張っている人には通知しない
    _PAYLOAD["data"] = M_BACK
    assert shopify.check(Product("t", BASE, variant="L"), user_agent=UA).status == OUT_OF_STOCK


def test_variant_lookup_by_sku_and_case():
    _PAYLOAD["data"] = M_BACK
    assert shopify.check(Product("t", BASE, variant="ts-m"), user_agent=UA).status == IN_STOCK


def test_missing_variant_reports_available_choices():
    _PAYLOAD["data"] = M_BACK
    result = shopify.check(Product("t", BASE, variant="XL"), user_agent=UA)
    assert result.status == OUT_OF_STOCK
    assert "M, L" in result.reason, result.reason


def test_non_shopify_url_returns_none():
    # Shopifyでなければ None を返し、HTML判定に任せる
    assert shopify.check(Product("t", f"http://127.0.0.1:{PORT}/notshopify"),
                         user_agent=UA) is None


def test_state_key_separates_variants():
    # 同じURLでもサイズが違えば別々に状態を持つ（通知の取りこぼし防止）
    base = Product("t", BASE)
    size_m = Product("t", BASE, variant="M")
    size_l = Product("t", BASE, variant="L")
    assert size_m.key != size_l.key
    assert base.key != size_m.key
    assert base.key == BASE


def _run_all():
    failed = 0
    for name, func in sorted(globals().items()):
        if name.startswith("test_") and callable(func):
            try:
                func()
                print(f"  PASS {name}")
            except AssertionError as exc:
                failed += 1
                print(f"  FAIL {name}: {exc}")
    _server.shutdown()
    print(f"\n{'すべて成功' if not failed else str(failed) + ' 件失敗'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_run_all())
