"""Desktop entry point used by the packaged macOS and Windows applications."""
import argparse
import os
from pathlib import Path
import sys
from fuji_recipe_lab import diagnostics

from fuji_recipe_lab.gui import serve


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
    args = parser.parse_args(argv)
    try:
        open_browser = not args.no_browser and os.environ.get("FILM_RECIPE_LAB_NO_BROWSER") != "1"
        if sys.platform == "win32" and open_browser:
            from fuji_recipe_lab.windows_app import run
            return run(args.root, args.port)
        if sys.platform == "darwin" and getattr(sys, "frozen", False) and open_browser:
            from fuji_recipe_lab.macos_app import run
            return run(args.root, args.port)
        serve(
            args.root,
            args.port,
            open_browser=open_browser,
        )
        return 0
    except Exception as exc:
        record_crash(exc)
        if sys.platform == "win32" and not args.no_browser:
            from fuji_recipe_lab.windows_app import show_startup_error
            show_startup_error()
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
