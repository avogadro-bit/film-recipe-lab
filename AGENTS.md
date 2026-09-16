# Current direction — authorized by the user

The GUI now uses an independent Fuji-inspired engine with PROVIA as its default, RAF/DNG input, and controls similar to X RAW STUDIO. Approximations are explicitly allowed for this engine; never present them as native or calibrated. This instruction supersedes the ban on approximations for the GUI.

The constraints below still apply to the separate native research workbench.

# Project goal

The user wants an equivalent of FUJIFILM X RAW STUDIO without a connected camera,
using the exact Fuji engine with RAF/DNG input. Reverse engineering is explicitly
accepted. Artistic LUTs and approximations are outside the native workbench scope.

- Never substitute LibRaw, a LUT, an ICC profile, or the embedded JPEG for native Fuji rendering.
- `prepare` produces neutral diagnostic inputs only. Do not present it as the Fuji engine.
- Do not claim the engine is operational before the image pipeline runs and provenance is validated.
- Preserve the documented emulation limits, unknown hardware dependencies, and missing calibration data.
- Never convert file offsets into execution addresses without documented justification.
- Treat photo sources as read-only and avoid reading iCloud placeholders.
- Keep proprietary firmware and binaries local and excluded from the repository. No camera flashing or writing is requested.
- Initial research target: X-T4 2.12 / ARMv7. User RAF target: X100VI / ARM64. Treat them separately.
- DNG: define the engine input space. A DNG adaptation is not physically equivalent to another sensor.
- Local validation: `.venv/bin/python -m unittest discover -s tests -v`.
