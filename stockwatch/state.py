"""前回どういう状態だったかを state.json に覚えておく。

これが無いと在庫がある間じゅうメールが飛び続ける。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


class State:
    def __init__(self, path: str | Path = "state.json"):
        self.path = Path(path)
        self.data: dict = {}
        if self.path.exists():
            try:
                self.data = json.loads(self.path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                self.data = {}

    def get(self, url: str) -> dict:
        return self.data.get(url, {})

    def last_status(self, url: str) -> str:
        return self.get(url).get("status", "unknown")

    def record(self, url: str, status: str, *, notified: bool = False,
               reason: str = "", price: str | None = None) -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        entry = self.get(url).copy()
        entry.update({"status": status, "reason": reason, "price": price, "checked_at": now})
        if notified:
            entry["notified_at"] = now
        self.data[url] = entry

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
