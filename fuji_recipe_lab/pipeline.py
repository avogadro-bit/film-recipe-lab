"""Native settings data flow; explicitly stops before unavailable runtime state."""
import hashlib
from pathlib import Path
import struct

from .emulation import run_function
from .xt4 import parameter_probe, MODULE_BASE, MODULE_SHA256, DEVELOP_MODULE_BASE, DEVELOP_MODULE_SHA256

CONSUMER_ENTRY = 0x022388b8
INSTALLER_ENTRY = 0x022357ac
MAIN_SHA256 = "ac1c4a4f40d7eac89ca58662dbbabd1256402fb2d89df436872be61c36273442"
SYSTEM_SHA256 = "bae8613409663200796fef039468f00895924921f07179c987e368f4bc0a6111"


def modules(directory):
    result = []
    for name, address, digest in [
        ("unpacked_00260000.bin", MODULE_BASE, MODULE_SHA256),
        ("unpacked_005c0000.bin", DEVELOP_MODULE_BASE, DEVELOP_MODULE_SHA256)]:
        path = (directory/name).resolve()
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError(f"Pinned module hash mismatch: {name}")
        result.append({"address": address, "size": (len(data)+4095)//4096*4096,
                       "file": str(path), "permissions": "rx", "initialized_only": True, "expected_sha256": digest})
    return result


def system_module(directory):
    main = (directory/"main.bin").read_bytes()
    if hashlib.sha256(main).hexdigest() != MAIN_SHA256:
        raise ValueError("Pinned main segment hash mismatch")
    data = main[0x60000:0x7b0c0]
    if (hashlib.sha256(data).hexdigest() != SYSTEM_SHA256 or
            struct.unpack_from("<8I", data) != (0, 0x40000, 0x1b0c0, 0x576ac, 0, 0, 0, 0xaaaaffff)):
        raise ValueError("System module hash/header mismatch")
    return data


def compact_execution(result, prefix_size):
    """Keep provenance, traces and full hashes without megabytes of raw dumps."""
    for out in result["outputs"]:
        if "hex" in out:
            data = out.pop("hex")
            out["prefix_hex"] = data[:prefix_size*2]
    return result


def chain_probe(directory: Path, with_calendar: bool = False):
    code = modules(directory)
    builder = parameter_probe(directory)
    if not builder["passed"]:
        raise ValueError("Builder precondition failed; consumer chain not executed")
    base_source = {0x5c4: 0, 0xb14: 1, 0x611: 8, 0x612: 8, 0x5c0: 0, 0x5c1: 0}
    compact_fields = {0x5c4: 5, 0xb14: 4, 0x611: 0x17, 0x612: 0x18, 0x5c0: 0x12, 0x5c1: 0x13}
    common = [{"address": 0x07000000, "size": 65536, "permissions": "rw"},
              {"address": 0x08000000, "size": 4096, "permissions": "rx"}]
    runtime_regions, runtime_trace, runtime_outputs = [], [], []
    if with_calendar:
        from .runtime import calendar_regions, DEFAULT_CALENDAR
        runtime_regions = calendar_regions(directory)
        runtime_trace = [{"address": 0x01791000, "size": 4096}, {"address": 0x01b84000, "size": 4096}]
        runtime_outputs = [{"address": 0x01791688, "size": 4}, {"address": 0x017916b0, "size": 6}]
    cases = []
    for parent in builder["cases"]:
        if not parent["valid_input"]:
            continue
        source = {**base_source, **{int(k, 16): v for k, v in parent["input_bytes"].items()}}
        packet = bytes.fromhex(parent["execution"]["outputs"][0]["parameter_prefix_hex"])
        for mode in [0, 1]:
            consumer = run_function({
                "architecture": "arm", "entry": CONSUMER_ENTRY, "stop": 0x08000000,
                "regions": [*code, *common,
                            {"address": 0x06000000, "size": 4096, "permissions": "r", "hex": packet.hex(), "initialized_only": True},
                            {"address": 0x06200000, "size": 4096, "permissions": "rw", "hex": "a5"*4096}],
                "registers": {"R0": 0x06000000, "R1": mode, "R2": 0x06200000, "SP": 0x0700fff0, "LR": 0x08000000},
                "outputs": [{"address": 0x06200000, "size": 4096}],
                "memory_trace": [{"address": 0x06200000, "size": 4096, "access": "w"}],
                "instruction_limit": 10000, "provenance": {"scope": "Native compact parameter conversion, no pixels", "builder_case": parent["name"], "packet_sha256": hashlib.sha256(packet).hexdigest()}})
            raw = bytes.fromhex(consumer["outputs"][0]["hex"])
            compact = raw[:0x1c]
            writes = {int(a["address"], 16)+i-0x06200000 for a in consumer["memory_trace"] for i in range(a["size"])}
            expected = {target: source[src] for src, target in compact_fields.items()}
            consumer_ok = (consumer["reached_stop"] and consumer["registers"]["SP"] == "0x700fff0" and
                           all(compact[k] == v for k, v in expected.items()) and
                           raw[0x1c:] == b"\xa5"*(4096-0x1c) and
                           not consumer["memory_trace_truncated"] and 0xc not in writes)
            installer = None
            roundtrip = False
            if consumer_ok:
                descriptor = bytearray(64)
                struct.pack_into("<I", descriptor, 0x30, 0x06400000)
                descriptor[0x39] = 0x41  # Literal used by the observed real caller.
                installer = run_function({
                    "architecture": "arm", "entry": INSTALLER_ENTRY, "stop": 0x08000000,
                    "regions": [*code, *common, *runtime_regions,
                                {"address": 0x06000000, "size": 0x6000, "permissions": "rw"},
                                {"address": 0x06200000, "size": 4096, "permissions": "r", "hex": compact.hex(), "initialized_only": True},
                                {"address": 0x06300000, "size": 4096, "permissions": "r", "hex": descriptor.hex(), "initialized_only": True},
                                {"address": 0x06400000, "size": 0x4000, "permissions": "r"}],
                    "registers": {"R0": 0x06000000, "R1": 0x06200000, "R2": 0x06300000, "SP": 0x0700fff0, "LR": 0x08000000, "CPSR": 0x13},
                    "outputs": [{"address": 0x06000000, "size": 0x6000}, *runtime_outputs],
                    "memory_trace": [{"address": 0x06200000, "size": 4096, "access": "r"}, *runtime_trace],
                    "instruction_limit": 10000,
                    "provenance": {"scope": "Native installer with explicit cached-calendar state" if with_calendar else "Native installer, expected incomplete at unmapped global state",
                                   "input_scope": "Synthetic context/header; no valid RAF, no pixels, no stubs", "compact_sha256": hashlib.sha256(compact).hexdigest()}})
                context = bytes.fromhex(installer["outputs"][0]["hex"])
                reads = {int(a["address"], 16)+i-0x06200000 for a in installer["memory_trace"]
                         if 0x06200000 <= int(a["address"], 16) < 0x06201000 for i in range(a["size"])}
                roundtrip = (all(context[k] == source[k] for k in compact_fields) and
                             not installer["memory_trace_truncated"] and reads <= writes)
                if with_calendar:
                    timestamp = context[0x3120:0x3134].split(b"\0")[0].decode("ascii", errors="replace")
                    offset = context[0x5424:0x542b].split(b"\0")[0].decode("ascii", errors="replace")
                    lock_writes = [a["write_value"] for a in installer["memory_trace"] if a["access"] == "write" and a["address"] == "0x1791688"]
                    calendar_bytes = bytes([DEFAULT_CALENDAR.year-2000, DEFAULT_CALENDAR.month, DEFAULT_CALENDAR.day,
                                            DEFAULT_CALENDAR.hour, DEFAULT_CALENDAR.minute, DEFAULT_CALENDAR.second])
                    metadata_ok = (timestamp == DEFAULT_CALENDAR.strftime("%Y:%m:%d %H:%M:%S") and offset == "+00:00" and
                                   installer["outputs"][1]["hex"] == "00000000" and
                                   installer["outputs"][2]["hex"] == calendar_bytes.hex() and lock_writes == ["0x1", "0x0"])
                    roundtrip = (roundtrip and installer["reached_stop"] and metadata_ok and
                                 installer["registers"]["SP"] == "0x700fff0" and int(installer["registers"]["CPSR"], 16) & 255 == 0x13)
                    installer["metadata_validation"] = {"passed": metadata_ok, "timestamp": timestamp, "offset": offset,
                                                        "spinlock_writes": lock_writes, "calendar_source_unchanged": installer["outputs"][2]["hex"] == calendar_bytes.hex()}
                else:
                    roundtrip = (roundtrip and not installer["reached_stop"] and len(installer["faults"]) == 1 and
                                 installer["faults"][0]["address"] == "0x1b8441c" and installer["faults"][0]["pc"] == "0x126a114")
                installer["observed_source_bytes"] = {hex(k): context[k] for k in compact_fields}
                compact_execution(installer, 0)
            cases.append({"builder_case": parent["name"], "mode": mode, "passed": consumer_ok and roundtrip,
                          "compact_fields": {hex(k): compact[k] for k in expected},
                          "compact_unwritten_offsets": sorted(set(range(28))-writes),
                          "consumer": compact_execution(consumer, 28), "installer": installer})
    # Newly identified low module: probe an existing missing call without
    # inventing BSS contents in the alignment padding after its file bytes.
    system = system_module(directory)
    system_result = run_function({
        "architecture": "arm", "entry": 0x57b74, "stop": 0x08000000,
        "regions": [*common, {"address": 0x40000, "size": 0x1c000, "permissions": "rx", "hex": system.hex(), "initialized_only": True}],
        "registers": {"SP": 0x0700fff0, "LR": 0x08000000}, "instruction_limit": 1000,
        "provenance": {"main_offset": "0x60000", "load_base": "0x40000", "sha256": SYSTEM_SHA256,
                       "scope": "System dependency probe, no fabricated BSS or thread state"}})
    return {"target": "X-T4 2.12", "passed": all(c["passed"] for c in cases), "case_count": len(cases),
            "builder_precondition": {"passed": builder["passed"], "valid_cases": builder["valid_input_cases"]},
            "scope": "Roundtrip of six settings through real builder, complete consumer and " + ("complete installer with explicit calendar state" if with_calendar else "partial installer") + "; no image calculation",
            "installer_completed": with_calendar and all(c["passed"] for c in cases), "image_pipeline_executed": False, "camera_oracle_used": False,
            "system_module_probe": system_result, "cases": cases}
