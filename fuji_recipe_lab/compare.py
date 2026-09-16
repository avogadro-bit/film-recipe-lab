"""Strict digital output comparison; never align/rescale to hide differences."""
from pathlib import Path
import hashlib
import numpy as np
from PIL import Image


def compare(reference: Path, candidate: Path) -> dict:
    def read(path):
        if path.suffix.lower() == ".npy":
            a = np.load(path, allow_pickle=False)
            return a, {"format": "npy", "mode": str(a.dtype), "icc_sha256": None, "orientation": None}
        if path.suffix.lower() in {".tif", ".tiff"}:
            import tifffile
            with tifffile.TiffFile(path) as tif:
                a = tif.asarray()
                tags = tif.pages[0].tags
                icc = tags[34675].value if 34675 in tags else b""
                orientation = int(tags[274].value) if 274 in tags else 1
            return a, {"format": "tiff", "mode": str(a.dtype), "icc_sha256": hashlib.sha256(icc).hexdigest(), "orientation": orientation}
        with Image.open(path) as im:
            return np.asarray(im), {"format": im.format, "mode": im.mode, "icc_sha256": hashlib.sha256(im.info.get("icc_profile", b"")).hexdigest(), "orientation": im.getexif().get(274, 1)}
    a, am = read(reference)
    b, bm = read(candidate)
    comparable = a.shape == b.shape and a.dtype == b.dtype and am == bm
    result = {"reference": str(reference), "candidate": str(candidate), "comparable": comparable, "reference_shape": list(a.shape), "candidate_shape": list(b.shape), "reference_metadata": am, "candidate_metadata": bm, "pixel_identical": False, "proves_camera_equivalence": False}
    if not comparable:
        result["reason"] = "Shape, dtype, format, ICC or orientation differs. No automatic normalization."
        return result
    if not np.isfinite(a).all() or not np.isfinite(b).all():
        result["reason"] = "Non-finite pixels."
        result["comparable"] = False
        return result
    diff = a.astype(np.float64) - b.astype(np.float64)
    result.update(pixel_identical=bool(np.array_equal(a, b)), max_abs_error=float(np.max(np.abs(diff))), mean_abs_error=float(np.mean(np.abs(diff))), rmse=float(np.sqrt(np.mean(diff ** 2))), changed_samples=int(np.count_nonzero(diff)))
    result["note"] = "Equality of this pair alone does not establish provenance or general engine equivalence. Pixel errors are in native sample units."
    return result
