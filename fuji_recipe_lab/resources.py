"""Native resource preparation and dispatch frontier on real RAF metadata.

Only metadata comes from the photo. Owner 1, CMOS mode 1, and thread identity 1
are explicit fixtures. No frame buffer, queue, scheduler or ISP is supplied.
"""
from pathlib import Path
import struct

from .raf_metadata import metadata_probe, read_metadata
from .runtime import sparse_page


def resource_inputs(directory: Path, source: Path, synchronization_regions):
    metadata = metadata_probe(directory, source)
    if not metadata["passed"]:
        raise ValueError("Native RAF metadata precondition failed")
    block, _, provenance = read_metadata(source)
    if provenance != metadata["source"]:
        raise ValueError("RAF metadata changed between validation and use")
    # Preserve all native semaphore table entries, adding just one thread slot.
    table = next(x for x in synchronization_regions if x["address"] == 0x7a000)
    data = bytes.fromhex(table["hex"])
    fields = [(r["offset"], data[r["offset"]:r["offset"]+r["size"]]) for r in table["valid_ranges"]]
    extended = sparse_page(0x7a000, [*fields, (0x55c, struct.pack("<I", 0x6600000))], "r")
    sync = [extended if x is table else x for x in synchronization_regions]
    context = bytearray(0x6000)
    struct.pack_into("<h", context, 0x3c, 1)  # Zero terminates the owner table.
    struct.pack_into("<I", context, 0xb80, 1)  # First actual CMOS-mode table entry.
    regions = [
        {"address": 0x6900000, "size": (len(block)+4095)//4096*4096, "permissions": "r",
         "hex": block.hex(), "initialized_only": True, "expected_sha256": provenance["metadata_sha256"]},
        sparse_page(0x6600000, [(0xcc, struct.pack("<I", 1))], "r")]
    return sync, regions, context, metadata


def resource_checks(execution, metadata, transported=False):
    context = bytes.fromhex(execution["outputs"][0]["hex"])
    geometry = metadata["observed_words"]
    resource = list(struct.unpack_from("<7I", context, 0x48))
    expected = [0, 0, 0, 2*geometry[1], 2*(geometry[5]+2*geometry[3]), geometry[0], 0x10200000 if transported else 0x200000]
    header = bytes.fromhex(execution["outputs"][4]["hex"])
    payload = bytes.fromhex(execution["outputs"][5]["hex"])
    if transported:
        event, sender, destination, length = struct.unpack("<HBBI", header)
        pointer = int(execution['outputs'][5]['address'], 16)
    else:
        event, sender, destination, length, pointer = struct.unpack("<HBBII", header)
    raw = bytes.fromhex(execution["outputs"][6]["hex"])
    message = {"event": hex(event), "sender": sender, "destination": destination,
               "payload_size": length, "payload_pointer": hex(pointer),
               "wrapper": hex(struct.unpack_from("<I", payload)[0]), "operation": payload[4],
               "callback": hex(struct.unpack_from("<I", payload, 8)[0]), "type": payload[12],
               "scope": "Copied to allocated block and queued; padding not validated" if transported else "Constructed on stack; queue send has not completed; padding not validated"}
    checks = {
        "native_metadata_inside_orchestrator": list(struct.unpack("<10H", raw)) == geometry,
        "resource_fields_match_native_metadata": resource == expected,
        "cmos_table_tail_installed": struct.unpack_from("<2I", context, 0x584) == (2, 4),
        "native_message_header": (event, sender, destination, length) == (0x1219, 1, 9, 68) and (transported or pointer == 0x700ff58),
        "native_message_payload": (message["wrapper"] == "0x6500000" and message["operation"] == 0x23 and
                                   message["callback"] == "0x21d28e4" and message["type"] == 5),
        "queue_argument_points_to_message": transported or (execution["registers"]["R0"] == "0x9" and execution["registers"]["R1"] == "0x700ff9c")}
    return checks, {"observed_resource_words": resource, "expected_resource_words": expected,
                    "row_bytes": resource[3], "active_row_bytes": resource[4], "rows": resource[5],
                    "message": message, "resource_preparer_returned": checks["native_message_header"]}


def resource_probe(directory: Path, source: Path):
    from .orchestration import orchestrator_probe
    return orchestrator_probe(directory, with_requests=True, resource_source=source)
