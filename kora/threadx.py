"""Version-pinned ThreadX helpers with explicit synthetic core-0 state.

Not a scheduler, camera boot, or hardware model. The two helper instruction
bodies match Eclipse ThreadX Cortex-A7 SMP sources; array literals are Fuji's.
"""
from pathlib import Path
import struct

from .emulation import run_function
from .pipeline import system_module, SYSTEM_SHA256

THREAD_ARRAY = 0x5b570
STATE_ARRAY = 0x5b4f8
THREAD_GET = 0x48e14
STATE_GET = 0x48de8
SOURCE_COMMIT = "44d7c95c582d415c4ad84527180b29c93c3bf664"


def threadx_probe(directory: Path):
    system = system_module(directory)
    # Same ten instructions, different final address literal. Check structural
    # evidence again before using the inferred state-array addresses.
    first, second = STATE_GET-0x40000, THREAD_GET-0x40000
    if system[first:first+40] != system[second:second+40]:
        raise ValueError("ThreadX helper bodies no longer match")
    if (struct.unpack_from("<I", system, first+40)[0] != STATE_ARRAY or
            struct.unpack_from("<I", system, second+40)[0] != THREAD_ARRAY):
        raise ValueError("ThreadX helper array literals changed")
    specs = []
    for irq in [0, 0x80]:
        for pointer, state in [(0, 0), (0x11110000, 0), (0x22220000, 1), (0x33330000, 0x1234)]:
            for name, entry, expected in [("current_thread", THREAD_GET, pointer), ("system_state", STATE_GET, state)]:
                specs.append((name, entry, pointer, state, irq, expected))
        # The actual Fuji wrapper detects an interrupt/system context or its
        # sentinel thread and returns zero without a thread object lookup.
        specs.extend([("wrapper_sentinel", 0x57b74, 0x5b680, 0, irq, 0),
                      ("wrapper_system_context", 0x57b74, 0, 1, irq, 0)])
    cases = []
    for name, entry, pointer, state, irq, expected in specs:
        data = bytearray(b"\xcc"*0x1c000)
        data[:len(system)] = system
        struct.pack_into("<4I", data, THREAD_ARRAY-0x40000, pointer, 0x44440001, 0x44440002, 0x44440003)
        struct.pack_into("<4I", data, STATE_ARRAY-0x40000, state, 0x55550001, 0x55550002, 0x55550003)
        cpsr = 0xa0000013 | irq
        result = run_function({
            "architecture": "arm", "entry": entry, "stop": 0x08000000,
            "regions": [{"address": 0x40000, "size": len(data), "permissions": "rx", "hex": data.hex(),
                         "valid_ranges": [{"offset": 0, "size": len(system)},
                                          {"offset": THREAD_ARRAY-0x40000, "size": 16},
                                          {"offset": STATE_ARRAY-0x40000, "size": 16}]},
                        {"address": 0x07000000, "size": 65536, "permissions": "rw"},
                        {"address": 0x08000000, "size": 4096, "permissions": "rx"}],
            "registers": {"LR": 0x08000000, "SP": 0x0700fff0, "CPSR": cpsr},
            "arm_cp_registers": [{"coproc": 15, "opc1": 0, "crn": 0, "crm": 0, "opc2": 5, "el": 0, "value": 0x80000000}],
            "memory_trace": [{"address": 0x5b0c0, "size": 0xf40}], "instruction_limit": 256,
            "provenance": {"system_sha256": SYSTEM_SHA256, "threadx_source_commit": SOURCE_COMMIT,
                           "scope": "Core-0 helpers and two wrapper branches; synthetic arrays, no real thread objects",
                           "unknown_bytes": "0xCC and forbidden by sparse valid_ranges", "patched_instructions": False}})
        addresses = {int(a["address"], 16) for a in result["memory_trace"]}
        # Getter restores the complete CPSR. Wrapper compares its result and
        # may change condition flags, but must preserve interrupt control/mode.
        status_mask = 0xffffffff if name in {"current_thread", "system_state"} else 0xff
        passed = (result["reached_stop"] and int(result["registers"]["R0"], 16) == expected and
                  int(result["registers"]["CPSR"], 16) & status_mask == cpsr & status_mask and
                  result["registers"]["SP"] == "0x700fff0" and
                  addresses <= {THREAD_ARRAY, STATE_ARRAY} and not result["memory_trace_truncated"])
        cases.append({"name": name, "pointer": hex(pointer), "state": hex(state), "irq_disabled": bool(irq),
                      "expected": hex(expected), "passed": passed, "execution": result})
    return {"target": "X-T4 2.12", "passed": all(c["passed"] for c in cases), "case_count": len(cases),
            "core_ids_tested": [0], "scheduler_emulated": False, "camera_booted": False,
            "image_pipeline_executed": False, "cases": cases,
            "limitation": "MPIDR writes requesting core 1 read back 0x80000000 in Unicorn 2.1.4; only core 0 tested"}
