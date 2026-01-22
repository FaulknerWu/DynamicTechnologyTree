from __future__ import annotations

import sys
from pathlib import Path


# Allow `import generator` etc without requiring an editable install.
SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))
