import shutil
import subprocess
from pathlib import Path

import pytest

SHARED_TS = Path(__file__).resolve().parents[2] / "shared" / "ts" / "index.ts"


@pytest.mark.skipif(shutil.which("npx") is None, reason="npx not installed")
def test_shared_ts_strict():
    assert SHARED_TS.is_file()
    r = subprocess.run(
        ["npx", "-p", "typescript@5", "tsc", "--noEmit", "--strict", str(SHARED_TS)],
        capture_output=True, text=True, check=False,
    )
    assert r.returncode == 0, r.stdout + r.stderr
