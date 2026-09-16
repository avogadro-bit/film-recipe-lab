"""Build the self-contained macOS application, ZIP, DMG, and checksums."""
import hashlib
import platform
from pathlib import Path
import shutil
import subprocess
import sys

from fuji_recipe_lab import __version__


ROOT = Path(__file__).resolve().parents[1]
VERSION = __version__


def run(*command):
    print("+", " ".join(map(str, command)), flush=True)
    subprocess.run([str(part) for part in command], cwd=ROOT, check=True)


def reset_directory(path):
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            value.update(chunk)
    return value.hexdigest()


def main():
    if sys.platform != "darwin":
        raise SystemExit("The macOS release must be built on macOS.")
    architecture = platform.machine().lower()
    if architecture not in {"arm64", "x86_64"}:
        raise SystemExit(f"Unsupported macOS architecture: {architecture}")

    work = ROOT / "build" / "pyinstaller"
    app_dist = ROOT / "dist" / "macos"
    release = ROOT / "dist" / "release"
    staging = ROOT / "build" / "dmg-root"
    for path in (work, app_dist, release, staging):
        reset_directory(path)

    run(
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--workpath",
        work,
        "--distpath",
        app_dist,
        ROOT / "packaging" / "FilmRecipeLab.spec",
    )

    app = app_dist / "Film Recipe Lab.app"
    if not app.is_dir():
        raise SystemExit(f"Application bundle was not produced: {app}")
    # Ad-hoc signing catches altered nested binaries and avoids an entirely
    # unsigned bundle. Public notarization still requires an Apple Developer ID.
    run("codesign", "--force", "--deep", "--sign", "-", app)
    run("codesign", "--verify", "--deep", "--strict", app)

    base = f"Film-Recipe-Lab-{VERSION}-macOS-{architecture}"
    archive = release / f"{base}.zip"
    image = release / f"{base}.dmg"
    run("ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", app, archive)

    run("ditto", app, staging / app.name)
    (staging / "Applications").symlink_to("/Applications")
    run(
        "hdiutil",
        "create",
        "-volname",
        "Film Recipe Lab",
        "-srcfolder",
        staging,
        "-ov",
        "-format",
        "UDZO",
        image,
    )

    checksums = release / "SHA256SUMS.txt"
    checksums.write_text(
        "".join(f"{digest(path)}  {path.name}\n" for path in (archive, image)),
        encoding="utf-8",
    )
    print(f"Release artifacts: {release}")


if __name__ == "__main__":
    main()
