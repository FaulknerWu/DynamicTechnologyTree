from __future__ import annotations

import locale
from typing import Any

from localization import LOCALIZATION_STRINGS


def t(key: str, lang: str | None = None, **kwargs: Any) -> str:
    """Translate a string key using LOCALIZATION_STRINGS.

    - Falls back to English when the language/key is missing.
    - Never raises for missing keys or bad .format() placeholders.
    """

    lang_code = (lang or "english").strip().lower() or "english"
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


def map_locale_to_language_key(locale_name: str | None) -> str | None:
    """Map an OS locale (e.g. 'en_US', 'pt_BR.UTF-8') to a Stellaris language key.

    Returns None when no mapping is known.
    """

    if not locale_name:
        return None

    raw = str(locale_name).strip()
    if not raw:
        return None

    # Common non-localized locales.
    if raw.upper() in {"C", "POSIX"}:
        return "english"

    # Strip encoding / variants, normalize separators.
    normalized = raw.split(".", 1)[0].split("@", 1)[0].replace("-", "_")
    parts = [p for p in normalized.split("_") if p]

    language = parts[0].lower() if parts else ""
    region = parts[1].upper() if len(parts) >= 2 else ""

    # Region-specific overrides.
    if language == "pt" and region == "BR":
        return "braz_por"

    language_map = {
        # Required minimum coverage.
        "en": "english",
        "zh": "simp_chinese",
        "fr": "french",
        "de": "german",
        "es": "spanish",
        "ru": "russian",
        "pl": "polish",
        "ja": "japanese",
        "ko": "korean",
        # Commonly useful extra.
        "pt": "braz_por",
    }

    # Sometimes locale strings are words (e.g. 'English_United States').
    if language not in language_map and len(language) > 2:
        language = language[:2]

    return language_map.get(language)


def default_language_from_system(locale_name: str | None = None) -> str:
    """Return a default GUI language key derived from OS locale.

    If the mapped language has no GUI ('ui_*') keys, prefer 'english' so the UI is
    consistent (missing keys fall back per-string, but a global choice is clearer).
    """

    system_locale = locale_name or _get_system_locale_name()
    mapped = map_locale_to_language_key(system_locale) or "english"

    if mapped not in LOCALIZATION_STRINGS:
        mapped = "english"

    if not _has_ui_keys(mapped):
        return "english"
    return mapped


def _get_system_locale_name() -> str | None:
    """Best-effort locale name (e.g. 'en_US')."""

    # Prefer UI/message locale where available.
    try:
        loc = locale.getlocale(locale.LC_MESSAGES)  # type: ignore[attr-defined]
    except Exception:
        loc = None
    if loc and loc[0]:
        return loc[0]

    # Fallback to the process-wide locale.
    try:
        loc = locale.getlocale()
    except Exception:
        loc = None
    if loc and loc[0]:
        return loc[0]

    # As a last resort (deprecated but still available on 3.10), use default locale.
    try:
        default = locale.getdefaultlocale()  # type: ignore[deprecated]
    except Exception:
        default = (None, None)
    if default and default[0]:
        return default[0]
    return None


def _has_ui_keys(lang: str) -> bool:
    lang_dict = LOCALIZATION_STRINGS.get(lang, {})
    return any(k.startswith("ui_") for k in lang_dict)
