from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    """Dev-only launcher.

    Prefer installing and running `dtt-gui` (or `python -m gui`) so imports match
    packaged execution. This script keeps a small fallback for repo checkout use.
    """
    try:
        from gui import main as gui_main
    except ImportError:
        # Repo-run fallback: add `src/` to sys.path.
        src_dir = Path(__file__).resolve().parent.parent / "src"
        sys.path.insert(0, str(src_dir))
        from gui import main as gui_main

    return gui_main()


if __name__ == "__main__":
    raise SystemExit(main())
