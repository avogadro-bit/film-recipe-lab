"""Version-pinned native synchronization probes, restricted to core 0.

The native constructor initializes objects in guarded RAM. Subsequent native
take/give calls receive those exact bytes. No scheduler or waiting thread is
implemented; the current-thread value is an opaque, unmapped fixture pointer.
"""
import hashlib
from pathlib import Path
import struct

from .emulation import run_function
from .pipeline import system_module, SYSTEM_SHA256
from .runtime import sparse_page

CREATE_ENTRY = 0x4be9c
TAKE_ENTRY = 0x551c8
GIVE_ENTRY = 0x51920
OBJECT_BASE = 0x63168
TABLE_BASE = 0x7a944
STOP = 0x8000000
STACK = 0x700fff0


def system_runtime_regions(directory: Path):
    system = system_module(directory)
    # The original module ends at 0x5b0c0. Its final page contains data;
    # only the explicit additional RAM fields below can be read or written.
    fields = [(0, system[0x1b000:]), (0x4f8, bytes(4)), (0x56c, bytes(4)),
              (0x570, struct.pack("<I", 0x6600000)), (0x580, bytes(4)),
              (0x588, struct.pack("<II", 0xffffffff, 0))]
    return [{"address": 0x40000, "size": 0x1b000, "permissions": "rx",
             "hex": system[:0x1b000].hex(), "initialized_only": True,
             "expected_sha256": hashlib.sha256(system[:0x1b000]).hexdigest()},
            sparse_page(0x5b000, fields)]


def object_addresses(identifier):
    if type(identifier) is not int or not 1 <= identifier <= 250:
        raise ValueError("Synchronization identifier must be 1..250 for this firmware")
    return OBJECT_BASE+20*(identifier-1), TABLE_BASE+4*(identifier-1)


def _execute(directory, entry, registers, regions, outputs, watches):
    return run_function({
        "architecture": "arm", "entry": entry, "stop": STOP,
        "regions": [*system_runtime_regions(directory), *regions,
                    {"address": 0x7000000, "size": 65536, "permissions": "rw"}],
        "registers": {"SP": STACK, "LR": STOP, "CPSR": 0x13, **registers},
        "outputs": outputs, "memory_trace": watches, "instruction_limit": 3000,
        "provenance": {"system_module_sha256": SYSTEM_SHA256,
                       "scope": "Native synchronization, explicit core-0 state, no waiting threads",
                       "patched_instructions": False, "stubs": []}})


def create_object(directory: Path, identifier=0x75, initial=1, maximum=1):
    address, slot = object_addresses(identifier)
    if not 0 <= initial <= maximum <= 0x7fffffff or maximum == 0:
        raise ValueError("Require 0 <= initial <= maximum <= INT_MAX and maximum > 0")
    regions = [sparse_page(address & ~4095, [], write_initializes=True),
               sparse_page(slot & ~4095, [], write_initializes=True),
               sparse_page(0x6700000, [(0, struct.pack("<III", 0, initial, maximum))], "r")]
    outputs = [{"address": address, "size": 20}, {"address": slot, "size": 4}]
    watches = [{"address": address & ~4095, "size": 4096}, {"address": slot & ~4095, "size": 4096}]
    result = _execute(directory, CREATE_ENTRY, {"R0": identifier, "R1": 0x6700000}, regions, outputs, watches)
    expected = [struct.pack("<5I", 0, initial, maximum, initial, 0).hex(), struct.pack("<I", address).hex()]
    written = {int(a["address"], 16)+i for a in result["memory_trace"] if a["access"] == "write" for i in range(a["size"])}
    result["passed"] = (result["reached_stop"] and result["registers"]["R0"] == "0x0" and
                        result["registers"]["SP"] == hex(STACK) and
                        [o.get("hex") for o in result["outputs"]] == expected and
                        written == set(range(address, address+20)) | set(range(slot, slot+4)) and
                        not result["memory_trace_truncated"])
    if not result["passed"]:
        raise ValueError("Native synchronization constructor validation failed")
    return result


def object_regions(created):
    return objects_regions([created])


def objects_regions(constructors):
    pages = {}
    for created in constructors:
        if not created.get("passed"):
            raise ValueError("Only validated native constructor outputs may be reused")
        for output, permissions in zip(created["outputs"], ["rw", "r"]):
            address = int(output["address"], 16)
            pages.setdefault((address & ~4095, permissions), []).append((address & 4095, bytes.fromhex(output["hex"])))
    return [sparse_page(address, fields, permissions) for (address, permissions), fields in pages.items()]


def synchronization_probe(directory: Path):
    cases = []
    for identifier in [1, 0x75, 0x76, 250]:
        for initial, maximum, entry, expected_return, expected_count in [
            (1, 1, TAKE_ENTRY, 0, 0), (0, 1, TAKE_ENTRY, 0xffffffce, 0),
            (0, 1, GIVE_ENTRY, 0, 1), (1, 1, GIVE_ENTRY, 0xffffffd5, 1),
            (2, 3, TAKE_ENTRY, 0, 1), (2, 3, GIVE_ENTRY, 0, 3)]:
            created = create_object(directory, identifier, initial, maximum)
            address, _ = object_addresses(identifier)
            result = _execute(directory, entry, {"R0": identifier, "R1": 0}, object_regions(created),
                              [{"address": address, "size": 20}, {"address": 0x5b580, "size": 16}],
                              [{"address": address, "size": 20}, {"address": 0x5b580, "size": 16}])
            expected = struct.pack("<5I", 0, initial, maximum, expected_count, 0).hex()
            lock = bytes.fromhex(result["outputs"][1]["hex"])
            passed = (result["reached_stop"] and int(result["registers"]["R0"], 16) == expected_return and
                      result["registers"]["SP"] == hex(STACK) and int(result["registers"]["CPSR"], 16) & 255 == 0x13 and
                      result["outputs"][0]["hex"] == expected and lock[:4] == bytes(4) and
                      lock[8:] == struct.pack("<II", 0xffffffff, 0) and not result["memory_trace_truncated"])
            cases.append({"identifier": identifier, "initial": initial, "maximum": maximum,
                          "operation": "take_nonblocking" if entry == TAKE_ENTRY else "give",
                          "expected_return": hex(expected_return), "expected_count": expected_count,
                          "passed": passed, "constructor": created, "execution": result})
    return {"target": "X-T4 2.12", "passed": all(c["passed"] for c in cases), "case_count": len(cases),
            "scope": "Native constructor and uncontended/nonblocking synchronization, core 0 only",
            "firmware_executed": True, "scheduler_emulated": False, "image_pipeline_executed": False, "cases": cases}
