"""Desktop entry point used by the packaged macOS application."""
import argparse
import os
from pathlib import Path
import sys
import traceback

from fuji_recipe_lab.gui import serve


def log_path():
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Logs" / "Film Recipe Lab" / "app.log"
    return Path.home() / ".local" / "state" / "film-recipe-lab" / "app.log"


def record_crash(exc):
    """Keep frozen-app startup failures diagnosable when no terminal is visible."""
    try:
        target = log_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as stream:
            stream.write(f"{type(exc).__name__}: {exc}\n")
            traceback.print_exc(file=stream)
    except OSError:
        pass


def main(argv=None):
    parser = argparse.ArgumentParser(description="Film Recipe Lab desktop application")
    parser.add_argument("--root", type=Path, action="append", default=[])
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        serve(
            args.root,
            args.port,
            open_browser=not args.no_browser and os.environ.get("FILM_RECIPE_LAB_NO_BROWSER") != "1",
        )
        return 0
    except Exception as exc:
        record_crash(exc)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
