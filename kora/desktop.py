"""Desktop entry point used by the packaged macOS and Windows applications."""
import argparse
import os
from pathlib import Path
import sys
from kora import diagnostics

from kora.gui import serve
from kora.compatibility import browser_disabled


def log_path():
    return diagnostics.log_path()


def record_crash(exc):
    """Keep frozen-app startup failures diagnosable when no terminal is visible."""
    diagnostics.record_error('startup', exc, path=log_path())


def main(argv=None):
    diagnostics.install_hooks()
    parser = argparse.ArgumentParser(description="KŌRA desktop application")
    parser.add_argument("--root", type=Path, action="append", default=[])
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--smoke-report", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        open_browser = not args.no_browser and not browser_disabled()
        if sys.platform == "win32" and open_browser:
            from kora.windows_app import run
            if args.smoke_report:
                return run(args.root, args.port, smoke_report=args.smoke_report)
            return run(args.root, args.port)
        if sys.platform == "darwin" and getattr(sys, "frozen", False) and open_browser:
            from kora.macos_app import run
            return run(args.root, args.port)
        serve(
            args.root,
            args.port,
            open_browser=open_browser,
        )
        return 0
    except Exception as exc:
        record_crash(exc)
        if sys.platform == "win32" and not args.no_browser and not args.smoke_report:
            from kora.windows_app import show_startup_error
            show_startup_error()
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
