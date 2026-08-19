from __future__ import annotations

import sys
from collections.abc import Sequence


def mitmgui(args: Sequence[str] | None = None) -> int | None:  # pragma: no cover
    from mitmproxy.tools.mitmgui import main_window as mw

    return mw.launch(args)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m mitmproxy.tools.main mitmgui [...]", file=sys.stderr)
        sys.exit(1)
    cmd = sys.argv[1]
    rest = sys.argv[2:]
    if cmd == "mitmgui":
        mitmgui(rest)
    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        sys.exit(1)
