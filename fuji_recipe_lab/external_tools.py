"""Resolve optional tools without relying on an interactive shell's PATH."""
from pathlib import Path
import shutil
import sys


def find_exiftool():
    """Honor PATH first, then standard macOS package-manager installations."""
    executable = shutil.which("exiftool")
    if executable:
        return str(Path(executable).resolve())
    if sys.platform == "darwin":
        for candidate in ("/opt/homebrew/bin/exiftool", "/usr/local/bin/exiftool",
                          "/opt/local/bin/exiftool"):
            executable = shutil.which(candidate)
            if executable:
                return str(Path(executable).resolve())
    return None
