# KŌRA 0.2.0

First packaged desktop release for Apple Silicon Macs running macOS 14 or newer.

## Included

- Self-contained KŌRA application; Python is not required.
- Automatic launch of the authenticated local studio in the default browser.
- Multi-camera RAW development, film recipes, batch selection, and JPEG/TIFF export.
- Source-resolution detail tiles, processing progress, and resizable workspace panels.
- Optional Lensfun-based lens corrections.

## Official Fujifilm LUTs

The proprietary GFX ETERNA 55 LUTs are not redistributed. On first launch, Setup
opens the official Fujifilm download and then lets the user choose the downloaded
v1.10 ZIP. KŌRA verifies all ten LUT hashes before installing them
locally. An already downloaded copy of that ZIP can be selected instead.

## Installation

Open the DMG and drag KŌRA to Applications. This build is ad-hoc signed
but not Apple-notarized. If macOS blocks the first launch, Control-click the app,
choose Open, and confirm.

ExifTool remains optional. Without it, some metadata and camera-specific input
details are unavailable.
