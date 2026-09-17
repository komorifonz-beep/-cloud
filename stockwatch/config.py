"""config.yml の読み込みと既定値の解決。"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 stockwatch/1.0"
)

# 売り切れを示す文言。サイトごとに config.yml で上書きできる。
DEFAULT_OUT_KEYWORDS = [
    "売り切れ", "売切れ", "在庫切れ", "在庫なし", "品切れ", "完売",
    "入荷待ち", "入荷未定", "再入荷のお知らせ", "再入荷通知",
    "取り扱いできません", "販売終了",
    "sold out", "soldout", "out of stock", "currently unavailable",
]

# 在庫ありを示す文言。
DEFAULT_IN_KEYWORDS = [
    "カートに入れる", "カートに追加", "かごに入れる", "買い物かごに入れる",
    "今すぐ購入", "ご購入手続きへ", "注文手続きへ", "在庫あり", "在庫:", "お届け日",
    "add to cart", "add to bag", "buy now", "in stock",
]


@dataclass
class EmailConfig:
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    use_tls: bool = True
    user: str = ""
    password: str = ""
    sender: str = ""
    to: list[str] = field(default_factory=list)

    @property
    def is_configured(self) -> bool:
        return bool(self.smtp_host and self.user and self.password and self.to)


@dataclass
class Product:
    name: str
    url: str
    method: str = "auto"                 # auto | shopify | jsonld | css | keyword
    variant: str = ""                    # サイズ・色など (Shopifyのみ。例: "M", "27.0")
    in_stock_selector: str = ""          # 在庫ありのときだけ現れる要素 (例: button.add-cart)
    out_of_stock_selector: str = ""      # 売り切れのときだけ現れる要素
    in_stock_keywords: list[str] = field(default_factory=list)
    out_of_stock_keywords: list[str] = field(default_factory=list)
    price_selector: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    enabled: bool = True
    notify_once: bool = True             # 在庫ありが続く間、通知は最初の1回だけ
    cart_assist: bool = False            # 再入荷時にブラウザでカート投入まで代行するか
    cart_profile: str = ""               # cart_profiles のキー

    def __post_init__(self) -> None:
        self.in_stock_keywords = self.in_stock_keywords or list(DEFAULT_IN_KEYWORDS)
        self.out_of_stock_keywords = self.out_of_stock_keywords or list(DEFAULT_OUT_KEYWORDS)

    @property
    def key(self) -> str:
        """状態を記録するときの識別子。

        同じURLをサイズ違いで複数監視できるよう、variant まで含めて区別する。
        URLだけで区別すると、Mサイズの通知でLサイズが通知済み扱いになってしまう。
        """
        return f"{self.url}#variant={self.variant}" if self.variant else self.url


@dataclass
class Settings:
    email: EmailConfig
    products: list[Product]
    interval_seconds: int = 600
    timeout_seconds: int = 20
    user_agent: str = DEFAULT_USER_AGENT
    confirm_recheck: bool = True         # 在庫ありを検知したら数秒後にもう一度確認する
    recheck_delay_seconds: int = 20
    jitter_seconds: int = 30             # アクセス時刻をばらけさせて負荷を避ける
    state_path: str = "state.json"
    cart_profiles: dict = field(default_factory=dict)


def _env(value, default=""):
    """'${VAR}' 形式なら環境変数から読む。それ以外はそのまま返す。"""
    if not isinstance(value, str):
        return value if value is not None else default
    text = value.strip()
    if text.startswith("${") and text.endswith("}"):
        return os.environ.get(text[2:-1], default)
    return text


def load(path: str | Path = "config.yml") -> Settings:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"設定ファイルが見つかりません: {path}\n"
            "config.example.yml をコピーして config.yml を作ってください。"
        )
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    mail_raw = raw.get("email") or {}
    email = EmailConfig(
        smtp_host=_env(mail_raw.get("smtp_host"), "smtp.gmail.com"),
        smtp_port=int(_env(mail_raw.get("smtp_port"), 587) or 587),
        use_tls=bool(mail_raw.get("use_tls", True)),
        user=_env(mail_raw.get("user")),
        password=_env(mail_raw.get("password")),
        sender=_env(mail_raw.get("sender")),
        to=[t for t in (mail_raw.get("to") or []) if t],
    )
    if not email.sender:
        email.sender = email.user

    defaults = raw.get("defaults") or {}
    products: list[Product] = []
    for item in raw.get("products") or []:
        if not item.get("url"):
            continue
        products.append(
            Product(
                name=item.get("name") or item["url"],
                url=item["url"],
                method=item.get("method", "auto"),
                variant=str(item.get("variant", "") or ""),
                in_stock_selector=item.get("in_stock_selector", ""),
                out_of_stock_selector=item.get("out_of_stock_selector", ""),
                in_stock_keywords=item.get("in_stock_keywords") or [],
                out_of_stock_keywords=item.get("out_of_stock_keywords") or [],
                price_selector=item.get("price_selector", ""),
                headers=item.get("headers") or {},
                enabled=item.get("enabled", True),
                notify_once=item.get("notify_once", True),
                cart_assist=item.get("cart_assist", False),
                cart_profile=item.get("cart_profile", ""),
            )
        )

    return Settings(
        email=email,
        products=products,
        interval_seconds=int(defaults.get("interval_seconds", 600)),
        timeout_seconds=int(defaults.get("timeout_seconds", 20)),
        user_agent=defaults.get("user_agent") or DEFAULT_USER_AGENT,
        confirm_recheck=bool(defaults.get("confirm_recheck", True)),
        recheck_delay_seconds=int(defaults.get("recheck_delay_seconds", 20)),
        jitter_seconds=int(defaults.get("jitter_seconds", 30)),
        state_path=defaults.get("state_path", "state.json"),
        cart_profiles=raw.get("cart_profiles") or {},
    )
