"""Offline module and operation catalog health; no OAuth or provider requests."""

from __future__ import annotations

import json

from qbo.catalog import OPERATIONS
from qbo.runtime import handle


def main() -> int:
    valid = len(OPERATIONS) == 145 and handle({})["ok"] is False
    print(
        json.dumps(
            {
                "ok": valid,
                "result": {
                    "status": "ok" if valid else "invalid",
                    "operation_count": len(OPERATIONS),
                },
            }
        )
    )
    return 0 if valid else 2


if __name__ == "__main__":
    raise SystemExit(main())
