"""Boundary for the future real firmware rendering backend."""
from pathlib import Path
from .recipe import Recipe


class ExactEngineUnavailable(RuntimeError):
    pass


def status() -> dict:
    return {
        "engine": "fujifilm-native", "available": False, "phase": "research",
        "firmware_image_pipeline_executed": False,
        "raf_exact_validated": False, "dng_adapter_validated": False,
        "reason": "Firmware image-processing entry point, ABI, calibration state and hardware dependencies have not been reconstructed.",
    }


def render_exact(source: Path, recipe: Recipe, output: Path):
    raise ExactEngineUnavailable(
        "Exact Fuji engine unavailable: the RAW-to-image pipeline cannot yet run "
        "outside the camera. No approximate render or embedded JPEG will be substituted. "
        "Use probe/prepare for inputs and firmware-inspect for research."
    )
