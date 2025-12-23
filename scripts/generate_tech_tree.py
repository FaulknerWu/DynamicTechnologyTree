from __future__ import annotations

import os
import sys
from pathlib import Path
import configparser

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

from generator import TechTreeGenerator
from localization import LOCALIZATION_STRINGS


def main() -> None:
    frozen = getattr(sys, "frozen", False)
    application_path = os.path.dirname(sys.executable) if frozen else os.path.dirname(os.path.abspath(__file__))

    config_path = os.path.join(application_path, "config.ini")

    try:
        os.chdir(application_path)
    except OSError:
        pass

    def _early_lang() -> str:
        cfg = configparser.ConfigParser()
        try:
            if Path(config_path).exists():
                cfg.read(config_path, encoding='utf-8')
                if cfg.has_section('localization') and cfg.has_option('localization', 'language'):
                    lang = cfg.get('localization', 'language').strip()
                    if lang and lang in LOCALIZATION_STRINGS:
                        return lang
            if 'simp_chinese' in LOCALIZATION_STRINGS:
                return 'simp_chinese'
            return 'english'
        except Exception:
            if 'simp_chinese' in LOCALIZATION_STRINGS:
                return 'simp_chinese'
            return 'english'

    if not Path(config_path).exists():
        detected_lang = _early_lang()
        lang_dict = LOCALIZATION_STRINGS.get(detected_lang, LOCALIZATION_STRINGS['english'])
        print(lang_dict.get('error_missing_config', 'Error: config file {path} not found').format(path=config_path))
        print(lang_dict.get('error_config_paths', 'Ensure config.ini exists with correct path settings'))
        if frozen:
            print(f"\n{lang_dict.get('prompt_press_enter', 'Press Enter to exit.')}")
            input()
        return

    generator = TechTreeGenerator(config_path)
    generator.run_generation_process()

    if frozen:
        print(f"\n{generator._l('prompt_press_enter')}")
        input()


if __name__ == "__main__":
    main()
