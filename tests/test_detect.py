"""在庫判定のテスト。`python -m pytest tests/` または `python tests/test_detect.py`。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from stockwatch.config import Product          # noqa: E402
from stockwatch.detect import IN_STOCK, OUT_OF_STOCK, detect  # noqa: E402
from stockwatch.notify import build_message    # noqa: E402
from stockwatch.config import EmailConfig      # noqa: E402
from stockwatch.state import State             # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_jsonld_out_of_stock():
    result = detect(load("jsonld_out.html"), Product("t", "http://x"))
    assert result.status == OUT_OF_STOCK, result
    assert result.price == "12800"


def test_jsonld_in_stock():
    result = detect(load("jsonld_in.html"), Product("t", "http://x"))
    assert result.status == IN_STOCK, result


def test_microdata_in_stock():
    result = detect(load("microdata_in.html"), Product("t", "http://x"))
    assert result.status == IN_STOCK, result


def test_preorder_counts_as_unavailable():
    # 予約受付中は「まだ買えない」= 売り切れ扱い
    result = detect(load("preorder.html"), Product("t", "http://x"))
    assert result.status == OUT_OF_STOCK, result


def test_css_disabled_button_is_out_of_stock():
    product = Product("t", "http://x", method="css",
                      in_stock_selector="button.add-to-cart",
                      out_of_stock_selector=".sold-out-label")
    assert detect(load("css_out.html"), product).status == OUT_OF_STOCK


def test_css_enabled_button_is_in_stock():
    product = Product("t", "http://x", method="css",
                      in_stock_selector="button.add-to-cart")
    result = detect(load("css_in.html"), product)
    assert result.status == IN_STOCK, result
    assert result.price == "￥12,800" or "12,800" in (result.price or "")


def test_keyword_out_of_stock():
    result = detect(load("keyword_out.html"), Product("t", "http://x", method="keyword"))
    assert result.status == OUT_OF_STOCK, result


def test_mixed_keywords_falls_back_to_out_of_stock():
    # 在庫あり/なしの文言が両方あるときは、誤報を避けて売り切れ扱いにする
    result = detect(load("mixed_keywords.html"), Product("t", "http://x", method="keyword"))
    assert result.status == OUT_OF_STOCK, result


def test_auto_prefers_jsonld_over_keywords():
    # 本文に「カートに入れる」があっても JSON-LD が OutOfStock なら売り切れ
    html = load("jsonld_out.html").replace("</body>", "<button>カートに入れる</button></body>")
    assert detect(html, Product("t", "http://x")).status == OUT_OF_STOCK


def test_state_roundtrip(tmp_path=None):
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "state.json"
        state = State(path)
        assert state.last_status("http://x") == "unknown"
        state.record("http://x", IN_STOCK, notified=True, reason="test")
        state.save()
        assert State(path).last_status("http://x") == IN_STOCK


def test_build_message_has_subject_and_link():
    product = Product("スニーカー<script>", "https://shop.example/p/1")
    result = detect(load("jsonld_in.html"), product)
    cfg = EmailConfig(user="a@example.com", sender="a@example.com", to=["b@example.com"])
    message = build_message(cfg, product, result)
    body = message.get_payload()[1].get_content()
    assert "再入荷" in message["Subject"]
    assert "https://shop.example/p/1" in body
    assert "<script>" not in body           # HTMLエスケープされている


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
    print(f"\n{'すべて成功' if not failed else str(failed) + ' 件失敗'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_run_all())
