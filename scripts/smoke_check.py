"""Offline installation smoke check, with no provider credentials or network."""

from pathlib import Path
import subprocess
import sys
import json

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    health = subprocess.run(
        [sys.executable, str(ROOT / "health.py")], capture_output=True, text=True, check=False
    )
    assert health.returncode == 0
    assert json.loads(health.stdout)["ok"] is True
    invalid = subprocess.run(
        [sys.executable, str(ROOT / "main.py")],
        input="{}",
        capture_output=True,
        text=True,
        check=False,
    )
    assert invalid.returncode == 2
    assert json.loads(invalid.stdout)["definitely_no_external_effect"] is True
    print("Offline QuickBooks bundle smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
