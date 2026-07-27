from __future__ import annotations

import sys
from pathlib import Path


PIT_ROOT = Path(__file__).resolve().parents[1]
V2_ROOT = PIT_ROOT.parent
REPOSITORY_ROOT = V2_ROOT.parents[1]

for path in (PIT_ROOT / "src", V2_ROOT / "src", REPOSITORY_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
