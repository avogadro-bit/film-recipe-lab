"""Native initialization of the request allocator's RAM and mode selection.

Modes 2, 6 and 7 are explicit test inputs, not a recovered live-camera state.
Mode 6 lacks the RAW request/response entries used by the current orchestrator.
"""
from pathlib import Path

from .emulation import run_function
from .pipeline import modules, compact_execution
from .runtime import sparse_page
from .synchronization import STACK, STOP

REQUEST_PAGES = [*range(0x372d000, 0x3736000, 4096), 0x2f00000]
INIT_ENTRY = 0x219b658
SELECT_ENTRY = 0x2198fc0


def snapshot_native_ram(execution, addresses, write_initializes=False):
    """Transfer only guarded, known bytes from a successfully completed call."""
    if not execution["reached_stop"]:
        raise ValueError("Cannot transfer RAM from an incomplete native initialization")
    result = []
    for address in addresses:
        mapped = next(x for x in execution["regions"] if int(x["address"], 16) == address)
        ranges = mapped.get("final_valid_ranges", mapped.get("valid_ranges"))
        if ranges is None or mapped["size"] != 4096:
            raise ValueError("Only guarded 4 KiB RAM snapshots may be transferred")
        output = next(x for x in execution["outputs"] if int(x["address"], 16) == address)
        data = bytes.fromhex(output["hex"])
        if len(data) != 4096:
            raise ValueError("Snapshot must contain exactly one page")
        fields = [(int(x["address"], 16)-address, data[int(x["address"], 16)-address:int(x["address"], 16)-address+x["size"]]) for x in ranges]
        result.append(sparse_page(address, fields, write_initializes=write_initializes))
    return result


def request_runtime(directory: Path, mode=2):
    if type(mode) is not int or mode not in (2, 6, 7):
        raise ValueError('Request mode must be 2, 6 or 7 in this bounded probe')
    code = modules(directory)
    ram = [sparse_page(a, [], write_initializes=True) for a in REQUEST_PAGES]
    results = []
    for entry, argument, expected_mode in [(INIT_ENTRY, 0, 8), (SELECT_ENTRY, mode, mode)]:
        execution = run_function({
            "architecture": "arm", "entry": entry, "stop": STOP,
            "regions": [*code, *ram, {"address": 0x7000000, "size": 65536, "permissions": "rw"}],
            "registers": {"R0": argument, "SP": STACK, "LR": STOP, "CPSR": 0x13},
            "outputs": [{"address": a, "size": 4096} for a in REQUEST_PAGES],
            "memory_trace": [{"address": a, "size": 4096} for a in REQUEST_PAGES],
            "memory_trace_limit": 10000, "instruction_limit": 100000, "timeout_us": 3000000,
            "provenance": {"scope": "Native request RAM initialization" if entry == INIT_ENTRY else f"Native mode-{mode} selection after native initialization",
                           "mode_6_callsite": "0x2214a64..0x2214a70" if mode == 6 else None,
                           "mode_7_selector": "0x21ee5ec..0x21ee5fc, selected when input byte +8 is 1" if mode == 7 else None,
                           "initial_unknown_bytes": "Unreadable until written by native instructions",
                           "stubs": [], "patched_instructions": False}})
        passed = (execution["reached_stop"] and execution["registers"]["SP"] == hex(STACK) and
                  int(execution["registers"]["CPSR"], 16) & 255 == 0x13 and not execution["memory_trace_truncated"] and
                  bytes.fromhex(execution["outputs"][0]["hex"])[0x4e0] == expected_mode)
        if not passed:
            raise ValueError(f"Native request initialization failed at {entry:#x}")
        ram = snapshot_native_ram(execution, REQUEST_PAGES, write_initializes=entry == INIT_ENTRY)
        execution["passed"] = passed
        compact_execution(execution, 0)
        results.append(execution)
    return ram, {"passed": True, "initialization": results[0], "mode_selection": results[1],
                 "mode": mode,
                 "scope": f"Native RAM initialization and mode-{mode} selection; no image processing or live-camera oracle"}
