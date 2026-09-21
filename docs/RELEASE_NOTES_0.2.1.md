# KŌRA 0.2.1

Fixes pink highlights on Leica Q3 43 DNG files when ExifTool is unavailable,
including applications launched from Finder. Essential DNG camera and exposure
tags are now read directly, preserving the camera-specific floating-point color
conversion and clipped-highlight handling without an external installation.

Download the Apple Silicon DMG, replace the application in Applications, and
restart it. Requires macOS 14 or newer. Existing LUT installations are retained.
This build is ad-hoc signed, not Apple-notarized.
