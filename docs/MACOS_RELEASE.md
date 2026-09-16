# macOS application release

Film Recipe Lab 0.2.0 can be distributed as a self-contained macOS application.
The application includes Python and the required RAW-processing libraries; users
do not need to install Python or create a virtual environment.

## User installation

1. On an Apple Silicon Mac running macOS 14 or newer, download the ARM64 DMG
   and open it.
2. Drag **Film Recipe Lab** into **Applications**.
3. Open the application. It starts a local service bound only to `127.0.0.1`
   and opens the complete session link in the default browser.
4. On first launch, use **Download from Fujifilm**, then **Choose Downloaded ZIP**.
   The application accepts GFX ETERNA 55 v1.10 only, verifies all ten LUT hashes,
   installs them in the user's data directory, and deletes its temporary copy.

The official LUTs are not redistributed in the application. Existing users can
select a previously downloaded LUT ZIP instead of downloading it again. ExifTool
is optional; without it, some camera metadata and input normalization details are
unavailable.

The initial application is ad-hoc signed, but not Apple-notarized. If Gatekeeper
blocks the first launch, Control-click the application, choose **Open**, then
confirm. A Developer ID certificate and Apple notarization should be added before
wide public distribution.

## Maintainer build

Use a clean build environment so unrelated Python packages are not bundled:

```bash
python3 -m venv .venv-release
.venv-release/bin/python -m pip install -e '.[release,optics]'
.venv-release/bin/python scripts/prepare_release_notices.py
.venv-release/bin/python scripts/build_macos_release.py
```

The script builds and verifies the `.app`, then creates a ZIP, a DMG, dependency
source and notice ZIPs, and `SHA256SUMS.txt` under `dist/release/`. PyInstaller targets the architecture of
the Python interpreter used for the build. Build once on Apple Silicon and once
on Intel to publish both native variants.
