"""One bounded host-v2 request and one canonical subprocess response."""

from __future__ import annotations

import json
import sys
from typing import Any

from qbo.runtime import handle
from qbo.validation import INPUT_LIMIT


def main() -> int:
    try:
        raw = sys.stdin.buffer.read(INPUT_LIMIT + 1)
        if len(raw) > INPUT_LIMIT:
            raise ValueError("Input exceeds byte budget")
        value: Any = json.loads(raw)
        response = handle(value) if isinstance(value, dict) else handle({})
    except (ValueError, UnicodeError, RecursionError):
        response = handle({})
    sys.stdout.write(json.dumps(response, ensure_ascii=False, allow_nan=False) + "\n")
    return 0 if response["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
