from __future__ import annotations

from typing import Any

from localization import LOCALIZATION_STRINGS, require_supported_language_code


def t(key: str, lang: str | None = None, /, **kwargs: Any) -> str:
    """基于 LOCALIZATION_STRINGS 的最小翻译入口。"""

    if lang is None:
        lang_code = "english"
    else:
        lang_code = require_supported_language_code(lang, field_name="lang")

    lang_dict = LOCALIZATION_STRINGS.get(lang_code) or LOCALIZATION_STRINGS.get(
        "english", {}
    )

    base = lang_dict.get(key)
    if base is None:
        base = LOCALIZATION_STRINGS.get("english", {}).get(key, key)

    try:
        return base.format(**kwargs)
    except Exception:
        return base


__all__ = ["t"]
