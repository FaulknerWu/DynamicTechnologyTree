from __future__ import annotations

import locale
import os
from typing import Any

from localization import LOCALIZATION_STRINGS
from localization import require_supported_language_code


def t(key: str, lang: str | None = None, /, **kwargs: Any) -> str:
    """Translate a string key using LOCALIZATION_STRINGS.

    - Falls back to English when a translation key is missing.
    - Raises ValueError for unsupported explicit language codes.
    - Never raises for bad .format() placeholders.
    """

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

    # Windows sometimes returns a display-name locale (e.g. "Chinese (Simplified)_China").
    # Prefer mapping by name to an ISO language code, rather than truncating.
    language_name_map = {
        "chinese": "zh",
        "portuguese": "pt",
        "spanish": "es",
        "polish": "pl",
    }
    for prefix, code in language_name_map.items():
        if language.startswith(prefix):
            language = code
            break

    # Similar Windows-style region display names.
    region_name_map = {
        "BRAZIL": "BR",
        "BRASIL": "BR",
    }
    region = region_name_map.get(region, region)

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

    for candidate in _iter_locale_candidates(locale_name):
        mapped = map_locale_to_language_key(candidate)
        if not mapped:
            continue
        if mapped not in LOCALIZATION_STRINGS:
            continue
        if _has_ui_keys(mapped):
            return mapped

    return "english"


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


def _iter_locale_candidates(locale_name: str | None) -> list[str]:
    """Return locale identifiers in preference order.

    We intentionally try multiple sources because Windows/Python can report display-name
    locales (e.g. "Chinese (Simplified)_China") that do not map cleanly to ISO codes.
    """

    candidates: list[str] = []
    if locale_name:
        candidates.append(locale_name)
    else:
        # Qt's system UI preference list is generally the most reliable (Qt 6's
        # QLocale::uiLanguages includes fallbacks like zh-Hans-CN -> zh -> ...).
        candidates.extend(_get_qt_ui_languages())

        # On Windows, the UI language can differ from the numeric/formatting locale.
        win_ui = _get_windows_ui_locale_name()
        if win_ui:
            candidates.append(win_ui)

        env = _get_env_locale_name()
        if env:
            candidates.append(env)

        sys_locale = _get_system_locale_name()
        if sys_locale:
            candidates.append(sys_locale)

    # De-dupe while preserving order.
    seen: set[str] = set()
    out: list[str] = []
    for c in candidates:
        s = str(c).strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def _get_env_locale_name() -> str | None:
    # On POSIX, LANGUAGE can contain a preference list (e.g. "zh_CN:en_US").
    for key in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(key)
        if value:
            return value.split(":", 1)[0]
    return None


def _get_windows_ui_locale_name() -> str | None:
    if os.name != "nt":
        return None

    try:
        import ctypes
    except Exception:
        return None

    try:
        lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
    except Exception:
        return None

    try:
        windows_locale = getattr(locale, "windows_locale", {})
        return windows_locale.get(lang_id)
    except Exception:
        return None


def _get_qt_ui_languages() -> list[str]:
    try:
        from PyQt6.QtCore import QLocale
    except Exception:
        return []

    try:
        langs = QLocale.system().uiLanguages()
    except Exception:
        try:
            langs = QLocale().uiLanguages()
        except Exception:
            return []

    out: list[str] = []
    for lang in langs:
        s = str(lang).strip()
        if s:
            out.append(s)
    return out


def _has_ui_keys(lang: str) -> bool:
    lang_dict = LOCALIZATION_STRINGS.get(lang, {})
    if not isinstance(lang_dict, dict):
        return False

    settings_metadata_prefixes = (
        "ui_label_",
        "ui_help_",
        "ui_tab_",
        "ui_action_",
    )
    return any(
        isinstance(key, str)
        and key.startswith("ui_")
        and not key.startswith(settings_metadata_prefixes)
        for key in lang_dict
    )
