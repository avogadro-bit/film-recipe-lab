"""Reproducible RAW-orchestrator frontier; synthetic input, no image result."""
import hashlib
from pathlib import Path
import struct

from .emulation import run_function
from .pipeline import modules, CONSUMER_ENTRY, compact_execution
from .runtime import calendar_regions, sparse_page, DEFAULT_CALENDAR
from .synchronization import create_object, objects_regions, system_runtime_regions, STACK, STOP
from .xt4 import DEVELOP_ENTRY

ORCHESTRATOR_ENTRY = 0x22152a8


def baseline_compact(directory: Path):
    """Generate a baseline with both native transforms, without cached reports."""
    code = modules(directory)
    stack = {"address": 0x7000000, "size": 65536, "permissions": "rw"}
    source = bytearray(0x4000)
    source[0xb14] = 1
    source[0x611] = source[0x612] = 8
    source[0x5c2] = source[0x5c3] = source[0x5cc] = 4
    builder = run_function({
        "architecture": "arm", "entry": DEVELOP_ENTRY, "stop": STOP,
        "regions": [*code, stack,
                    {"address": 0x6000000, "size": 0x4000, "permissions": "r", "hex": source.hex()},
                    {"address": 0x6100000, "size": 0x2000, "permissions": "r"},
                    {"address": 0x6200000, "size": 4096, "permissions": "rw", "hex": "a5"*4096}],
        "registers": {"R0": 0x6000000, "R1": 0x6100000, "R2": 0x6200000, "SP": STACK, "LR": STOP},
        "outputs": [{"address": 0x6200000, "size": 0x270}], "instruction_limit": 10000,
        "provenance": {"scope": "Native baseline constructor on synthetic settings; no pixels"}})
    if not builder["reached_stop"] or builder["registers"]["SP"] != hex(STACK):
        raise ValueError("Native baseline constructor did not return")
    consumer = run_function({
        "architecture": "arm", "entry": CONSUMER_ENTRY, "stop": STOP,
        "regions": [*code, stack,
                    {"address": 0x6000000, "size": 4096, "permissions": "r",
                     "hex": builder["outputs"][0]["hex"], "initialized_only": True},
                    {"address": 0x6200000, "size": 4096, "permissions": "rw", "hex": "a5"*4096}],
        "registers": {"R0": 0x6000000, "R1": 0, "R2": 0x6200000, "SP": STACK, "LR": STOP},
        "outputs": [{"address": 0x6200000, "size": 28}], "instruction_limit": 10000,
        "provenance": {"scope": "Native baseline compact conversion", "builder_output_sha256": builder["outputs"][0]["sha256"]}})
    if not consumer["reached_stop"] or consumer["registers"]["SP"] != hex(STACK):
        raise ValueError("Native baseline compact conversion did not return")
    return bytes.fromhex(consumer["outputs"][0]["hex"]), {"builder": builder, "consumer": consumer}


def orchestrator_probe(directory: Path, with_requests=False, resource_source: Path | None = None, with_transport=False, with_receiver=False, cfg_feb0=None, with_firmware_config=False, with_boot_wb=False, with_extended_config=False, with_raw_resource_plan=False, request_mode=2):
    if type(request_mode) is not int or request_mode not in (2, 6, 7):
        raise ValueError('Request mode must be 2, 6 or 7 in this bounded probe')
    if request_mode != 2 and not with_requests:
        raise ValueError('Nondefault request mode requires request initialization')
    if with_raw_resource_plan and not with_extended_config:
        raise ValueError('RAW resource plan requires extended configuration')
    if with_extended_config and not with_boot_wb:
        raise ValueError('with_extended_config requires native WB boot preparation')
    if with_boot_wb and not with_firmware_config:
        raise ValueError('with_boot_wb requires verified firmware configuration')
    if with_firmware_config and (not with_receiver or cfg_feb0 is not None):
        raise ValueError('with_firmware_config requires receiver and excludes cfg_feb0 hypotheses')
    if cfg_feb0 is not None and (not with_receiver or type(cfg_feb0) is not int or not 0 <= cfg_feb0 <= 255):
        raise ValueError('cfg_feb0 requires receiver exploration and an integer in 0..255')
    if with_receiver and not with_transport:
        raise ValueError('Receiver requires completed native transport')
    if with_transport and resource_source is None:
        raise ValueError('Native transport requires a validated RAF metadata source')
    if resource_source is not None and not with_requests:
        raise ValueError("Resource preparation requires native request initialization")
    firmware_config = None
    if with_firmware_config:
        from .configuration import firmware_configuration
        firmware_config = firmware_configuration(directory)
    boot_wb = None
    if with_boot_wb:
        from .bootstrap import wb_boot_padding
        boot_wb = wb_boot_padding(directory)
    extended_config = None
    if with_extended_config:
        from .extended_configuration import extended_configuration_runtime
        extended_config = extended_configuration_runtime(directory)
    compact, preparation = baseline_compact(directory)
    created = create_object(directory)
    constructors = [created]
    request_regions = []
    request_preparation = None
    if with_requests:
        from .requests_runtime import request_runtime
        request_regions, request_preparation = request_runtime(directory, request_mode)
        constructors.append(create_object(directory, 0x76))
        request_regions.extend([
            sparse_page(0x17b2000, [(0x764, struct.pack("<I", 0x6800000))], "r"),
            sparse_page(0x6805000, [(0xe8c, b"\0")], "r"),
            sparse_page(0x2895000, [], write_initializes=True)])
    descriptor = bytearray(64)
    struct.pack_into("<I", descriptor, 0x30, 0x6400000)
    descriptor[0x39] = 0x41
    if with_requests:
        # Explicit unavailable input, deliberately not mapped or zero-filled.
        struct.pack_into("<I", descriptor, 0, 0x6900000)
    code = modules(directory)
    clock = calendar_regions(directory)[1:]
    sync = objects_regions(constructors)
    context_input = bytearray(0x6000)
    resource_regions, resource_outputs, resource_trace = [], [], []
    metadata = None
    message_preparation, message_outputs, message_ram = None, [], []
    wrapper_preparation = None
    wrapper_region = sparse_page(0x6500000, [(0, struct.pack("<I", 0x6000000))], write_initializes=True)
    if with_receiver:
        from .messaging import wrapper_runtime
        wrapper_region, wrapper_preparation = wrapper_runtime(directory)
    system = system_runtime_regions(directory)
    if resource_source is not None:
        from .resources import resource_inputs
        sync, resource_regions, context_input, metadata = resource_inputs(directory, resource_source, sync)
        resource_outputs = [{"address": 0x700ff9c, "size": 12}, {"address": 0x700ff58, "size": 68},
                            {"address": 0x2895ba0, "size": 20}]
        resource_trace = [{"address": 0x6000048, "size": 28}, {"address": 0x66000cc, "size": 4},
                          {"address": 0x7a55c, "size": 4}, {"address": 0x700ff58, "size": 80}]
    if with_transport:
        from .messaging import message_runtime, message_code, merge_sparse_regions, RAM_PAGES, POOL_BUFFER
        message_ram, message_preparation = message_runtime(directory)
        if message_ram is None:
            raise ValueError('Native message constructors failed')
        code = message_code(directory)
        system = [r for r in system if r['address'] != 0x5b000]
        # The semaphore/thread table and the queue object share a page.
        sync = merge_sparse_regions([*sync, *message_ram])
        resource_outputs[:2] = [{'address': POOL_BUFFER+4, 'size': 8}, {'address': POOL_BUFFER+12, 'size': 68}]
        message_outputs = [{'address': a, 'size': 4096} for a in RAM_PAGES]
        resource_trace.extend({'address': a, 'size': 4096} for a in RAM_PAGES)
    plan_preparation = None
    if with_raw_resource_plan:
        from .resource_plan import raw_resource_plan
        plan, plan_preparation = raw_resource_plan(directory)
        context_input[0x3b:0x3c] = plan
    config = {
        "architecture": "arm", "entry": ORCHESTRATOR_ENTRY, "stop": STOP,
        "regions": [*code, *system, *clock, *sync, *request_regions, *resource_regions,
                    {"address": 0x6000000, "size": 0x6000, "permissions": "rw", "hex": context_input.hex()},
                    {"address": 0x6200000, "size": 4096, "permissions": "r", "hex": compact.hex(), "initialized_only": True},
                    {"address": 0x6300000, "size": 4096, "permissions": "r", "hex": descriptor.hex(), "initialized_only": True},
                    {"address": 0x6400000, "size": 0x4000, "permissions": "r"},
                    wrapper_region,
                    sparse_page(0x2d48000, [], write_initializes=True),
                    {"address": 0x7000000, "size": 65536, "permissions": "rw"}],
        "registers": {"R0": 0x6500000, "R1": 0x6200000, "R2": 0x6300000, "R3": 0x21d28e4,
                      "SP": STACK, "LR": STOP, "CPSR": 0x13},
        "outputs": [{"address": 0x6000000, "size": 0x6000}, {"address": 0x63a78, "size": 20*len(constructors)},
                    {"address": 0x5b580, "size": 16}, {"address": 0x1791688, "size": 4}, *resource_outputs, *message_outputs],
        "memory_trace": [{"address": 0x5b000, "size": 4096}, {"address": 0x63a78, "size": 20*len(constructors)},
                         {"address": 0x1791000, "size": 4096}, {"address": 0x2d48000, "size": 4096},
                         {"address": 0x6500000, "size": 4096},
                         *([{"address": 0x372d000, "size": 0x9000}, {"address": 0x2895000, "size": 4096},
                            {"address": 0x17b2764, "size": 4}, {"address": 0x6805e8c, "size": 1}] if with_requests else []), *resource_trace],
        "instruction_limit": 20000,
        "provenance": {"scope": "Native RAW orchestration to its input-header reader" if with_requests else "Native RAW orchestration to an explicit missing request-table selector",
                       "compact_sha256": hashlib.sha256(compact).hexdigest(),
                       "input_scope": "Synthetic context and auxiliary header; no valid RAW payload or calibration",
                       "synchronization_object": "Exact native constructor output, initial=maximum=1",
                       "request_mode": request_mode if with_requests else None,
                       "logging_configuration": "Native category 12 mask byte=0 in explicit synthetic parameter table" if with_requests else None,
                       "current_thread": "Unmapped opaque fixture pointer 0x6600000; no TCB or scheduler",
                       "resource_fixture": {"owner_id": 1, "cmos_mode": 1, "thread_id": 1,
                                            "thread_scope": "Only ID field and matching table slot; no complete TCB",
                                            "source": metadata["source"]} if metadata else None,
                       "stubs": [], "patched_instructions": False}}
    if with_receiver:
        for region in config['regions']:
            if 'w' in region['permissions'] and region['address'] != 0x7000000:
                config['outputs'].append({'address': region['address'], 'size': region['size']})
    execution = run_function(config)
    context = bytes.fromhex(execution["outputs"][0]["hex"])
    lock = bytes.fromhex(execution["outputs"][2]["hex"])
    count_writes = [x["write_value"] for x in execution["memory_trace"]
                    if x["access"] == "write" and x["address"] == "0x63a84"]
    fields = {0x5c4: 0, 0xb14: 1, 0x611: 8, 0x612: 8, 0x5c0: 0, 0x5c1: 0}
    checks = {
        "expected_dependency_boundary": (not execution["reached_stop"] and len(execution["faults"]) == 1 and
                                         execution["faults"][0]["address"] == ("0x6900000" if with_requests else "0x372d4e0") and
                                         execution["faults"][0]["pc"] == ("0x11713a8" if with_requests else "0x2199678")),
        "settings_installed": all(context[k] == v for k, v in fields.items()),
        "timestamp_installed": context[0x3120:0x3134] == DEFAULT_CALENDAR.strftime("%Y:%m:%d %H:%M:%S").encode()+b"\0",
        "utc_offset_installed": context[0x5424:0x542b] == b"+00:00\0",
        "counter_taken_and_released": count_writes == ["0x0", "0x1"]*(2 if with_requests else 1),
        "synchronization_object_restored": execution["outputs"][1]["hex"] == "".join(x["outputs"][0]["hex"] for x in constructors),
        "kernel_lock_released": lock[:4] == bytes(4) and lock[8:] == struct.pack("<II", 0xffffffff, 0),
        "calendar_lock_released": execution["outputs"][3]["hex"] == "00000000",
        "irq_state_restored": int(execution["registers"]["CPSR"], 16) & 255 == 0x13,
        "trace_complete": not execution["memory_trace_truncated"]}
    if with_requests:
        second_writes = [x["write_value"] for x in execution["memory_trace"]
                         if x["access"] == "write" and x["address"] == "0x63a98"]
        checks["request_counter_taken_and_released"] = second_writes == ["0x0", "0x1"]*3
    resource_result = None
    if metadata:
        from .resources import resource_checks
        extra_checks, resource_result = resource_checks(execution, metadata, with_transport)
        checks.update(extra_checks)
        checks["expected_dependency_boundary"] = (not execution["reached_stop"] and len(execution["faults"]) == 1 and
                                                   execution["faults"][0]["address"] == "0x18ead24" and
                                                   execution["faults"][0]["pc"] == "0x127e7a0")
        execution["provenance"]["scope"] = "Native resource preparation and message construction to missing queue state"
        execution["provenance"]["current_thread"] = "Explicit ID=1 field at 0x66000cc and pointer table slot; no complete TCB or scheduler"
    transport_result = None
    if with_transport:
        from .messaging import output_bytes, QUEUE_OBJECT, QUEUE_BUFFER, POOL_OBJECT, POOL_BUFFER, CAPACITY
        checks['expected_dependency_boundary'] = execution['reached_stop'] and not execution['faults']
        checks['stack_restored'] = execution['registers']['SP'] == hex(STACK)
        checks['resource_lookup_returned'] = execution['registers']['R0'] == '0x1'
        checks['message_in_queue'] = (struct.unpack('<I', output_bytes(execution, QUEUE_OBJECT+24, 4))[0] == 1
                                      and output_bytes(execution, QUEUE_BUFFER, 4) == struct.pack('<I', POOL_BUFFER+4))
        checks['one_message_block_allocated'] = struct.unpack('<I', output_bytes(execution, POOL_OBJECT+8, 4))[0] == CAPACITY-1
        execution['provenance']['scope'] = 'Native RAW resource orchestration and completed message enqueue'
        transport_result = {'message_header_hex': execution['outputs'][4]['hex'],
                            'message_payload_hex': execution['outputs'][5]['hex'],
                            'scope': 'Enqueued native RAW request; no receiver task or pixel processing executed'}
    receiver = None
    if with_receiver and all(checks.values()):
        from .messaging import receiver_frontier
        receiver = receiver_frontier(config, execution, cfg_feb0, firmware_config, boot_wb, extended_config, plan_preparation)
    compact_execution(execution, 0)
    report = {"target": "X-T4 2.12", "request_mode": request_mode if with_requests else None,
            "passed": all(checks.values()), "checks": checks,
            "firmware_executed": True, "orchestrator_completed": False, "image_pipeline_executed": False,
            "scope": "Native request handling reaches unavailable RAW input header" if with_requests else "Expected dependency frontier after native metadata and uncontended synchronization",
            "next_dependency": {"address": "0x6900000", "role": "First byte of unavailable RAW input header, descriptor word 0"} if with_requests else
                               {"address": "0x372d4e0", "role": "Byte selecting a native request descriptor table"},
            "preparation": preparation, "request_preparation": request_preparation,
            "synchronization_constructors": constructors, "execution": execution}
    if metadata:
        report.update(scope="Native resource preparation from real RAF metadata; message send blocked by missing queue state",
                      next_dependency={"address": "0x18ead24", "role": "Queue 9 message-size limit"},
                      resource=resource_result, metadata_preparation=metadata, queue_send_completed=False,
                      source_pixel_compatibility_validated=False)
    if with_transport:
        report.update(scope='Native RAW orchestration returns after enqueue; consumer not executed',
                      next_dependency={'role': 'Destination-9 task handler and real RAW pixel buffers'},
                      orchestrator_completed=execution['reached_stop'], queue_send_completed=checks['message_in_queue'],
                      message_preparation=message_preparation, transport=transport_result)
    if with_receiver:
        report['receiver'] = receiver
        report['wrapper_preparation'] = wrapper_preparation
        report['passed'] = report['passed'] and receiver is not None and receiver.get('passed', False)
        report['next_dependency'] = {'address': '0x680feb0', 'role': 'Unrecovered native configuration byte 0xfeb0; no image output'}
        if with_firmware_config:
            report['scope'] = 'Native RAW receiver with DAT configuration page; WB structure initialization frontier, no pixels'
            report['firmware_configuration'] = firmware_config[1]
            report['next_dependency'] = {'address': '0x288d207', 'role': 'Unknown trailing byte of WB structure copied by native LDM; boot state not reconstructed'}
        if with_boot_wb:
            report['scope'] = 'Native RAW receiver with DAT configuration and derived BSS padding; no pixels'
            report['wb_boot_padding'] = boot_wb[1]
            report['next_dependency'] = receiver['faults'][0] if receiver and receiver.get('faults') else None
        if with_extended_config:
            report['scope'] = 'Native RAW receiver with verified DAT DEFAULT block and explicit native access mode 0; no pixels'
            report['extended_configuration'] = extended_config[1]
            report['next_dependency'] = {'role': 'Intermediate RAW resource 0x2f, index 0, missing for owner 1',
                                         'fault_address': '0x0', 'pc': '0x2218b04',
                                         'pixel_buffer_initialized': False}
        if cfg_feb0 is not None:
            report['scope'] = 'Exploratory configuration variant; not a recovered camera state and not an exact image renderer'
            report['next_dependency'] = receiver['faults'][0] if receiver and receiver.get('faults') else None
        if with_raw_resource_plan:
            from .resource_plan import dma_initialization_frontier
            report['raw_resource_plan'] = plan_preparation
            report['dma_initialization'] = dma_initialization_frontier(directory)
            report['passed'] = report['passed'] and report['dma_initialization']['passed']
            report['scope'] = 'Native receiver with explicit partial RAW coordinator preparation; no image output'
            report['next_dependency'] = {
                'role': 'DMA initialization needs hardware register semantics; input geometry and buffers remain unvalidated',
                'receiver_fault': receiver['faults'][0] if receiver and receiver.get('faults') else None,
                'dma_initializer_fault': report['dma_initialization']['faults'][0]
                    if report['dma_initialization']['faults'] else None,
                'pixel_buffer_initialized': False}
    if with_receiver and receiver is None:
        report['scope'] = 'Orchestration prerequisites failed; receiver not executed'
        report['next_dependency'] = execution['faults'][0] if execution.get('faults') else {
            'role': 'Orchestrator checks failed before receiver entry'}
    return report
