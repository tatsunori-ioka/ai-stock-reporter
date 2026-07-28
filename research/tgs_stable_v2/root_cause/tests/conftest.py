from __future__ import annotations

import sys
from pathlib import Path


ROOT_CAUSE_ROOT = Path(__file__).resolve().parents[1]
V2_ROOT = ROOT_CAUSE_ROOT.parent
REPOSITORY_ROOT = V2_ROOT.parents[1]
for source in (
    ROOT_CAUSE_ROOT / "src",
    V2_ROOT / "pit_lite" / "src",
    V2_ROOT / "src",
    REPOSITORY_ROOT,
):
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))
