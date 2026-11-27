"""Backend CLI.

    python -m app.cli sync-strategies
"""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in {"-h", "--help"}:
        print(__doc__.strip())
        return 0
    cmd = args[0]
    if cmd == "sync-strategies":
        from app.api.deps import get_repo
        from app.services.strategy_sync import sync_strategies

        n = sync_strategies(get_repo())
        print(f"synced {n} strateg{'y' if n == 1 else 'ies'}")
        return 0
    print(f"unknown command: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
