"""商品ページの取得。リトライとサイトへの配慮(間隔・UA)込み。"""

from __future__ import annotations

import random
import time

import requests

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class FetchError(RuntimeError):
    pass


def get_html(url: str, *, user_agent: str, timeout: int = 20,
             extra_headers: dict | None = None, retries: int = 3) -> str:
    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache",
    }
    headers.update(extra_headers or {})

    last_error = ""
    for attempt in range(retries):
        try:
            response = requests.get(url, headers=headers, timeout=timeout)
            if response.status_code in RETRYABLE_STATUS:
                last_error = f"HTTP {response.status_code}"
            else:
                response.raise_for_status()
                response.encoding = response.apparent_encoding or response.encoding
                return response.text
        except requests.RequestException as exc:
            last_error = str(exc)
        # 2秒 → 4秒 → 8秒 (+ゆらぎ) で待つ
        if attempt < retries - 1:
            time.sleep(2 ** (attempt + 1) + random.uniform(0, 1.5))
    raise FetchError(f"{url} の取得に失敗しました: {last_error}")
