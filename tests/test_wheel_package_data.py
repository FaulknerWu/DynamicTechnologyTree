# pyright: reportMissingImports=false

from __future__ import annotations

import subprocess
import sys
import zipfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]


def test_wheel_includes_bundled_gui_font_asset(tmp_path: Path) -> None:
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir(parents=True, exist_ok=True)

    subprocess.check_call(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            str(ROOT_DIR),
            "--no-deps",
            "--no-build-isolation",
            "--no-index",
            "--no-cache-dir",
            "-w",
            str(dist_dir),
        ],
        cwd=ROOT_DIR,
    )

    wheels = sorted(dist_dir.glob("*.whl"))
    assert len(wheels) == 1, f"expected 1 wheel, found {len(wheels)}: {wheels}"

    with zipfile.ZipFile(wheels[0]) as archive:
        names = set(archive.namelist())

    assert "gui/fonts/NotoSansSC-Regular.otf" in names
