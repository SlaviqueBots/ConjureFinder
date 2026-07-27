from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bot.core.config import CFG

_DEFAULT_COINS = ("🐽", "🐷", "🐖")
_DEFAULT_FORMS = [
    {"weight": 28, "singular": "пятачок", "few": "пятачка", "many": "пятачков"},
    {"weight": 30, "singular": "хрюнделька", "few": "хрюндельки", "many": "хрюндельков"},
    {"weight": 18, "singular": "хряквеня", "few": "хряквени", "many": "хряквеней"},
    {"weight": 4, "singular": "хрюндель-бугель", "few": "хрюнделя-бугеля", "many": "хрюнделей-бугелей"},
]

_cache: dict[str, Any] | None = None


@dataclass(frozen=True)
class MoneyStyle:
    singular: str
    few: str
    many: str
    coin: str

    @classmethod
    def from_form(cls, form: dict[str, Any], coin: str) -> MoneyStyle:
        return cls(
            singular=str(form["singular"]),
            few=str(form["few"]),
            many=str(form["many"]),
            coin=coin,
        )


def reload() -> None:
    global _cache
    _cache = None
    _load()


def _path() -> Path:
    return CFG.root / "data" / "currency.ru.json"


def _load() -> dict[str, Any]:
    global _cache
    if _cache is not None:
        return _cache
    p = _path()
    if p.exists():
        try:
            _cache = json.loads(p.read_text(encoding="utf-8"))
            return _cache
        except Exception:
            pass
    _cache = {"coins": list(_DEFAULT_COINS), "forms": _DEFAULT_FORMS}
    return _cache


def _coins() -> list[str]:
    data = _load()
    coins = data.get("coins")
    if isinstance(coins, list) and coins:
        return [str(c) for c in coins]
    legacy = data.get("coin")
    if legacy:
        return [str(legacy)]
    return list(_DEFAULT_COINS)


def coin() -> str:
    return random.choice(_coins())


def _forms() -> list[dict[str, Any]]:
    raw = _load().get("forms") or _DEFAULT_FORMS
    out = []
    for f in raw:
        if not isinstance(f, dict):
            continue
        if f.get("singular") and f.get("few") and f.get("many"):
            out.append(f)
    return out or _DEFAULT_FORMS


def _decline(n: int, form: dict[str, Any] | MoneyStyle) -> str:
    n = abs(int(n))
    mod10, mod100 = n % 10, n % 100
    if mod10 == 1 and mod100 != 11:
        return str(form["singular"] if isinstance(form, dict) else form.singular)
    if mod10 in (2, 3, 4) and mod100 not in (12, 13, 14):
        return str(form["few"] if isinstance(form, dict) else form.few)
    return str(form["many"] if isinstance(form, dict) else form.many)


def _coin_for_form(form: dict[str, Any]) -> str:
    fixed = form.get("coin")
    if fixed:
        return str(fixed)
    return coin()


def _form_by_id(form_id: str) -> dict[str, Any] | None:
    needle = str(form_id).strip()
    if not needle:
        return None
    for form in _forms():
        if str(form.get("id") or "") == needle:
            return form
    return None


def _pick_form() -> dict[str, Any]:
    forms = _forms()
    weights = [max(1, int(f.get("weight") or 1)) for f in forms]
    return random.choices(forms, weights=weights, k=1)[0]


def pick_money_style(*, form_id: str | None = None) -> MoneyStyle:
    if form_id:
        form = _form_by_id(form_id)
        if form:
            return MoneyStyle.from_form(form, _coin_for_form(form))
    form = _pick_form()
    return MoneyStyle.from_form(form, _coin_for_form(form))


def format_with_style(n: int, style: MoneyStyle) -> str:
    word = _decline(n, style)
    return f"{n} {word} {style.coin}"


def format_money(n: int) -> str:
    """Random currency name + declension, e.g. '100 хрюндельков 🐽'."""
    return format_with_style(n, pick_money_style())


def format_balance_compact(n: int) -> str:
    """Short balance for card captions — amount + random coin, e.g. '123🐷'."""
    return f"{int(n)}{coin()}"


def money_label_many(style: MoneyStyle | None = None) -> str:
    """Plural label without amount — for 'not enough' messages."""
    if style is None:
        style = pick_money_style()
    return f"{style.many} {style.coin}"


def insufficient_money(style: MoneyStyle | None = None) -> str:
    from bot.texts.loader import t

    return t("errors.insufficient_money", money=money_label_many(style))


def user_display_name(user) -> str:
    if not user:
        return "?"
    name = (getattr(user, "full_name", None) or getattr(user, "first_name", None) or "").strip()
    if name:
        return name
    username = getattr(user, "username", None)
    if username:
        return f"@{username}"
    return str(getattr(user, "id", "?"))


def pig_working_notice() -> str:
    from bot.texts.loader import t_pick

    return t_pick("floaters.pig_working")
