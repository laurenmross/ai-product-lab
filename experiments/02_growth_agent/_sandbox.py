"""Makes the shared sandbox importable: `from _sandbox import world`."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "sandbox"))

import world  # noqa: E402,F401
