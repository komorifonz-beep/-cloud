"""前回どういう状態だったかを state.json に覚えておく。

これが無いと在庫がある間じゅうメールが飛び続ける。

なお save() は、在庫状態に変化が無ければファイルを書き換えない。
チェック時刻だけが変わった状態を毎回保存すると、GitHub Actions が毎回
「変更あり」と判断してコミットを積んでしまい、履歴が意味のない差分で埋まるため。
"""

from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path

# 変化の判定から除外する項目（毎回必ず変わるので比較する意味がない）
_VOLATILE_FIELDS = ("checked_at",)


def _meaningful(data: dict) -> dict:
    """変化を判定したい項目だけを取り出す。"""
    return {
        url: {k: v for k, v in entry.items() if k not in _VOLATILE_FIELDS}
        for url, entry in data.items()
    }


class State:
    def __init__(self, path: str | Path = "state.json"):
        self.path = Path(path)
        self.data: dict = {}
        if self.path.exists():
            try:
                self.data = json.loads(self.path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                self.data = {}
        self._original = copy.deepcopy(self.data)

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

    def has_changes(self) -> bool:
        """在庫状態に意味のある変化があったか。"""
        return _meaningful(self.data) != _meaningful(self._original)

    def save(self) -> bool:
        """変化があったときだけ保存する。保存したら True を返す。"""
        if self.path.exists() and not self.has_changes():
            return False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        self._original = copy.deepcopy(self.data)
        return True
