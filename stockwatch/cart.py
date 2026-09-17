"""再入荷を検知したら、ブラウザを自動操作してカートに入れるところまでやる。

【方針】最後の「注文を確定する」だけは押さない。
理由は3つ。
  1. 多くのECサイトは利用規約で自動購入(bot)を禁止しており、アカウント停止の
     リスクがある。カート投入までなら通常の操作と変わらない。
  2. 型番違い・価格改定・転売業者の出品などを人間が0.5秒見れば防げる事故が、
     全自動だと防げない。
  3. カートに入った状態でメールが届けば、スマホで開いて「注文確定」を押すだけ。
     再入荷から購入までの実時間は十分に短くできる。

業務発注(卸・業務用食材など)で発注APIが提供されている場合は、ブラウザ自動化
ではなくそのAPIを使うこと。規約上も動作の安定性でも圧倒的に有利。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

SCREENSHOT_DIR = Path("screenshots")


@dataclass
class CartResult:
    ok: bool
    note: str
    screenshot: str | None = None


def _resolve(value):
    """'${VAR}' 形式なら環境変数から読む。"""
    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        return os.environ.get(value[2:-1], "")
    return value


def _run_steps(page, steps, timeout_ms: int) -> None:
    for step in steps or []:
        if "goto" in step:
            page.goto(_resolve(step["goto"]), timeout=timeout_ms, wait_until="domcontentloaded")
        elif "fill" in step:
            page.fill(step["fill"], str(_resolve(step.get("value", ""))), timeout=timeout_ms)
        elif "click" in step:
            page.click(step["click"], timeout=timeout_ms)
        elif "select" in step:
            page.select_option(step["select"], str(_resolve(step.get("value", ""))),
                               timeout=timeout_ms)
        elif "press" in step:
            page.keyboard.press(step["press"])
        elif "wait_for" in step:
            page.wait_for_selector(step["wait_for"], timeout=timeout_ms)
        elif "wait_ms" in step:
            page.wait_for_timeout(int(step["wait_ms"]))
        else:
            raise ValueError(f"不明なステップです: {step}")


def add_to_cart(product, profile: dict, *, user_agent: str, headless: bool = True,
                timeout_ms: int = 30000) -> CartResult:
    """profile の手順に従ってログイン → カート投入 → スクリーンショット。"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return CartResult(False, "Playwright が未インストールのためカート投入をスキップしました")

    if not profile:
        return CartResult(False, f"cart_profile '{product.cart_profile}' が設定にありません")

    SCREENSHOT_DIR.mkdir(exist_ok=True)
    shot_path = SCREENSHOT_DIR / f"cart-{abs(hash(product.url))}.png"
    storage_path = profile.get("storage_state", "browser-state.json")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        context_args = {"user_agent": user_agent, "locale": "ja-JP"}
        if Path(storage_path).exists():
            # 前回のログインCookieを再利用する (毎回ログインしない)
            context_args["storage_state"] = storage_path
        context = browser.new_context(**context_args)
        page = context.new_page()
        try:
            if profile.get("login_url") and not Path(storage_path).exists():
                page.goto(profile["login_url"], timeout=timeout_ms,
                          wait_until="domcontentloaded")
                _run_steps(page, profile.get("login_steps"), timeout_ms)
                context.storage_state(path=storage_path)

            page.goto(product.url, timeout=timeout_ms, wait_until="domcontentloaded")
            _run_steps(page, profile.get("add_to_cart_steps"), timeout_ms)

            cart_url = profile.get("cart_url")
            if cart_url:
                page.goto(cart_url, timeout=timeout_ms, wait_until="domcontentloaded")
            page.screenshot(path=str(shot_path), full_page=False)

            note = f"カートに入れました（{cart_url or page.url} を開いて注文を確定してください）"
            return CartResult(True, note, str(shot_path))
        except Exception as exc:
            try:
                page.screenshot(path=str(shot_path), full_page=False)
            except Exception:
                shot_path = None
            return CartResult(False, f"カート投入に失敗しました: {exc}",
                              str(shot_path) if shot_path else None)
        finally:
            context.close()
            browser.close()
