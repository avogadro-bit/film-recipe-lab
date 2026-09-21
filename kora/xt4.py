"""Version-pinned native probes; diagnostic functions are NOT pixel processing."""
import hashlib
from pathlib import Path
import struct

from .emulation import run_function
from .extract import XT4_SHA256

MODULE_SHA256 = "0b5b0fb0ee5fe6b109dae9964b5cddfe18edab46b4a0c195f9da194448906eeb"
MODULE_BASE = 0x01021000
FILM_NAME_ENTRY = 0x0102df5c
DEVELOP_MODULE_SHA256 = "e1ef8b30903d3078fde103cdd134fca7bfc4337d67bcaf55c3080ffd5fd93b13"
DEVELOP_MODULE_BASE = 0x01e0f000
DEVELOP_ENTRY = 0x02237770
# Enum identifiers confirmed independently against fffw's versioned mode_fsim.h.
FILM_NAMES = ["STD", "F1b", "F1c", "F2", "B_AND_W", "SEPIA", "CHROME",
              "MONO_N_FILTER", "MONO_R_FILTER", "MONO_Y_FILTER", "MONO_G_FILTER",
              "NEGA_COL_1", "NEGA_COL_2", "CLASSIC_CHROME", "ACROS_N_FILTER",
              "ACROS_R_FILTER", "ACROS_Y_FILTER", "ACROS_G_FILTER", "ETERNA",
              "SUPERIA", "BLEACH_BYPASS", "NUM"]


def film_probe(module: Path) -> dict:
    module = module.resolve()
    data = module.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != MODULE_SHA256:
        raise ValueError("Native probe requires the pinned decoded X-T4 2.12 module")
    if struct.unpack_from("<I", data, 4)[0] != MODULE_BASE:
        raise ValueError("Module header does not match the documented mapping")
    cases = []
    for value in [*range(23), 255, 0x80000000, 0xffffffff]:
        config = {
            "architecture": "arm", "entry": FILM_NAME_ENTRY, "stop": 0x08000000,
            "regions": [
                {"address": MODULE_BASE, "size": (len(data)+4095)//4096*4096,
                 "permissions": "rx", "file": str(module), "expected_sha256": MODULE_SHA256, "initialized_only": True},
                {"address": 0x07000000, "size": 65536, "permissions": "rw"},
                {"address": 0x08000000, "size": 4096, "permissions": "rx"}],
            "registers": {"R0": value, "SP": 0x0700fff0, "LR": 0x08000000},
            "instruction_limit": 128, "timeout_us": 1000000,
            "provenance": {"dat_sha256": XT4_SHA256, "packed_main_offset": "0x260000",
                           "module_sha256": digest, "function_offset": hex(FILM_NAME_ENTRY-MODULE_BASE),
                           "mapping": "Header word +4; corroborated by MOVW/MOVT string references",
                           "scope": "Native enum-to-debug-name function only; no image processing"}}
        result = run_function(config)
        pointer = int(result["registers"]["R0"], 16)
        text = None
        if MODULE_BASE <= pointer < MODULE_BASE+len(data):
            text = data[pointer-MODULE_BASE:pointer-MODULE_BASE+128].split(b"\0", 1)[0].decode("ascii", errors="replace")
        expected = "MODE_FSIM_"+FILM_NAMES[value] if value < len(FILM_NAMES) else None
        case_passed = (result["reached_stop"] and not result["faults"] and
                       text == expected and (expected is not None or pointer == 0) and
                       result["registers"]["SP"] == "0x700fff0")
        cases.append({"input": value, "returned_name": text, "expected": expected,
                      "passed": case_passed, "execution": result})
    return {"target": "X-T4 2.12", "function": hex(FILM_NAME_ENTRY),
            "passed": all(c["passed"] for c in cases), "case_count": len(cases),
            "firmware_executed": True, "image_pipeline_executed": False,
            "scope": "Film enum diagnostic names, including invalid inputs; not rendering or parameter construction",
            "cases": cases}


def parameter_probe(directory: Path) -> dict:
    """Run complete native parameter constructor, with native utility callees.

    Inputs are deliberately synthetic structures, not camera RAM/calibration.
    Expected fields come from static control-flow analysis, not a camera oracle.
    Invalid settings enter logging and must expose its unmapped dependency.
    """
    directory = directory.resolve()
    modules = []
    for name, base, digest in [
        ("unpacked_00260000.bin", MODULE_BASE, MODULE_SHA256),
        ("unpacked_005c0000.bin", DEVELOP_MODULE_BASE, DEVELOP_MODULE_SHA256)]:
        path = directory / name
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != digest or struct.unpack_from("<I", data, 4)[0] != base:
            raise ValueError(f"Pinned module hash/header mismatch: {name}")
        modules.append({"address": base, "size": (len(data)+4095)//4096*4096,
                        "permissions": "rx", "file": str(path), "expected_sha256": digest, "initialized_only": True})

    # Zero is not a neutral setting for every field. These values are chosen
    # from the actual switch branches, not from public recipe enum assumptions.
    baseline_input = bytearray(0x4000)
    baseline_input[0xb14] = 1
    baseline_input[0x611] = baseline_input[0x612] = 8
    baseline_input[0x5c2] = baseline_input[0x5c3] = baseline_input[0x5cc] = 4
    film_codes = {0: 1, 1: 3, 3: 2, 5: 10, 7: 6, 8: 8, 9: 7, 10: 9,
                  11: 5, 12: 4, 13: 11, 14: 12, 15: 14, 16: 13, 17: 15,
                  18: 16, 19: 17, 20: 18}
    specs = []
    for film, output in film_codes.items():
        for dr in range(1, 5):
            specs.append((f"film_{film}_dr_{dr}", {0x5c4: film, 0xb14: dr},
                          {0x21d: output, 0x215: 100 << (dr-1)}, True))
    for source, target, name in [(0x611, 0x23d, "highlight"), (0x612, 0x241, "shadow")]:
        for value in range(4, 17):
            specs.append((f"{name}_{value}", {source: value}, {target: (value-8)*5}, True))
    for source, target, name in [(0x5c0, 0x231, "wb_red"), (0x5c1, 0x235, "wb_blue")]:
        for value in range(-9, 10):
            specs.append((f"{name}_{value}", {source: value & 255}, {target: value}, True))
    for name, source, values in [("film", 0x5c4, [2, 4, 6, 255]), ("dr", 0xb14, [0, 5]),
                                  ("highlight", 0x611, [3, 17]), ("wb_red", 0x5c0, [-10, 10])]:
        for value in values:
            specs.append((f"invalid_{name}_{value}", {source: value & 255}, {}, False))
    cases = []
    baseline_output = None
    for name, changes, fields, valid in specs:
        source = bytearray(baseline_input)
        for offset, value in changes.items():
            source[offset] = value
        config = {
            "architecture": "arm", "entry": DEVELOP_ENTRY, "stop": 0x08000000,
            "regions": [*modules,
                        {"address": 0x06000000, "size": 0x4000, "permissions": "r", "hex": source.hex()},
                        {"address": 0x06100000, "size": 0x2000, "permissions": "r"},
                        {"address": 0x06200000, "size": 4096, "permissions": "rw", "hex": "a5"*4096},
                        {"address": 0x07000000, "size": 65536, "permissions": "rw"},
                        {"address": 0x08000000, "size": 4096, "permissions": "rx"}],
            "registers": {"R0": 0x06000000, "R1": 0x06100000, "R2": 0x06200000,
                          "SP": 0x0700fff0, "LR": 0x08000000},
            "outputs": [{"address": 0x06200000, "size": 4096}],
            "instruction_limit": 10000, "timeout_us": 1000000,
            "provenance": {"dat_sha256": XT4_SHA256, "function": hex(DEVELOP_ENTRY),
                           "module_bases": "Header word +4, corroborated by code/string references",
                           "inputs": "Synthetic structures, no camera RAM or image pixels",
                           "stubs": [], "patched_instructions": False}}
        result = run_function(config)
        output = bytes.fromhex(result["outputs"][0]["hex"])
        if name == "film_0_dr_1" and result["reached_stop"]:
            baseline_output = output
        guard_intact = output[0x270:] == b"\xa5"*(4096-0x270)
        observed = {hex(offset): struct.unpack_from("<i", output, offset)[0] for offset in fields}
        expected = None
        if baseline_output is not None:
            expected = bytearray(baseline_output)
            for offset, value in fields.items():
                struct.pack_into("<i", expected, offset, value)
        if valid:
            passed = (result["reached_stop"] and not result["faults"] and guard_intact and
                      result["registers"]["SP"] == "0x700fff0" and output == expected)
        else:
            passed = not result["reached_stop"] and bool(result["faults"]) and guard_intact
        passed = passed and [r["sha256"] for r in result["regions"][:2]] == [MODULE_SHA256, DEVELOP_MODULE_SHA256]
        # Keep the full destination hash and prefix; the unchanged canary tail
        # adds no evidence to the report. The comparison above uses all bytes.
        result["outputs"][0]["parameter_prefix_hex"] = output[:0x270].hex()
        del result["outputs"][0]["hex"]
        cases.append({"name": name, "valid_input": valid, "input_bytes": {hex(k): v for k, v in changes.items()},
                      "expected_fields": {hex(k): v for k, v in fields.items()}, "observed_fields": observed,
                      "guard_intact": guard_intact, "passed": passed, "execution": result})
    return {"target": "X-T4 2.12", "function": hex(DEVELOP_ENTRY), "passed": all(c["passed"] for c in cases),
            "case_count": len(cases), "valid_input_cases": sum(c["valid_input"] for c in cases),
            "firmware_executed": True, "native_utilities_executed": True, "image_pipeline_executed": False,
            "validation": "Native execution agrees with static field mapping and unchanged-byte invariants; no camera oracle",
            "invalid_input_scope": "Unmapped dependency exposed; complete error handling not implemented",
            "cases": cases}
