"""Bounded ARM/Thumb/AArch64 function harness. No fake hardware responses.

Each run requires explicit memory regions, register state and an exit address.
Missing memory is reported and stops execution. This is NOT a virtual camera.
"""
from collections import deque
import hashlib
from pathlib import Path


def number(x):
    return int(x, 0) if isinstance(x, str) else int(x)


def run_function(config: dict, root: Path = Path(".")) -> dict:
    import unicorn as u
    from unicorn import arm_const, arm64_const
    arch = config["architecture"]
    if arch not in {"arm", "thumb", "arm64"}:
        raise ValueError("architecture must be arm, thumb, or arm64")
    limit = number(config.get("instruction_limit", 100000))
    timeout = number(config.get("timeout_us", 1000000))
    if not 1 <= limit <= 10000000 or not 1 <= timeout <= 10000000:
        raise ValueError("A bounded instruction limit and timeout (≤10 seconds) are mandatory")
    cpu = u.Uc(u.UC_ARCH_ARM64 if arch == "arm64" else u.UC_ARCH_ARM,
               u.UC_MODE_ARM if arch in {"arm", "arm64"} else u.UC_MODE_THUMB)
    constants = arm64_const if arch == "arm64" else arm_const
    prefix = "UC_ARM64_REG_" if arch == "arm64" else "UC_ARM_REG_"
    mapped = []
    initialized_guards = []
    total_size = 0
    for region in config["regions"]:
        address, size = number(region["address"]), number(region["size"])
        total_size += size
        if address < 0 or address % 4096 or size < 4096 or size % 4096 or total_size > 512 * 1024 * 1024:
            raise ValueError("Regions must be 4 KiB aligned; total memory limited to 512 MiB")
        permissions = region.get("permissions", "rw")
        if not permissions or set(permissions) - set("rwx"):
            raise ValueError("Invalid permissions")
        mask = sum({"r": u.UC_PROT_READ, "w": u.UC_PROT_WRITE, "x": u.UC_PROT_EXEC}[p] for p in set(permissions))
        cpu.mem_map(address, size, mask)
        if "file" in region and "hex" in region:
            raise ValueError("Specify file OR hex")
        data = (root / region["file"]).read_bytes() if "file" in region else bytes.fromhex(region.get("hex", ""))
        if "expected_sha256" in region and hashlib.sha256(data).hexdigest() != region["expected_sha256"]:
            raise ValueError("Region SHA-256 mismatch before execution")
        if len(data) > size:
            raise ValueError("Region data exceeds mapping")
        if data:
            cpu.mem_write(address, data)
        if "valid_ranges" in region and region.get("initialized_only", False):
            raise ValueError("Use initialized_only OR valid_ranges")
        ranges = None
        if region.get("initialized_only", False):
            ranges = [(address, address+len(data))]
        elif "valid_ranges" in region:
            ranges = []
            for valid in region["valid_ranges"]:
                offset, length = number(valid["offset"]), number(valid["size"])
                if offset < 0 or length <= 0 or offset+length > len(data):
                    raise ValueError("valid_ranges must describe initialized data")
                ranges.append((address+offset, address+offset+length))
            ranges.sort()
            merged = []
            for start, end in ranges:
                if merged and start <= merged[-1][1]:
                    merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
                else:
                    merged.append((start, end))
            ranges = merged
        write_initializes = bool(region.get("write_initializes", False))
        if write_initializes and (ranges is None or "w" not in permissions):
            raise ValueError("write_initializes requires guarded writable memory")
        if ranges is not None:
            initialized_guards.append((address, address+size, ranges, write_initializes, len(mapped)))
        mapped.append({"address": hex(address), "size": size, "permissions": permissions, "sha256": hashlib.sha256(data).hexdigest(), "initialized_bytes": len(data), "zero_filled_bytes": size - len(data)})
        mapped[-1]["initialized_only"] = bool(region.get("initialized_only", False))
        if ranges is not None:
            mapped[-1]["valid_ranges"] = [{"address": hex(a), "size": b-a} for a, b in ranges]
        mapped[-1]["write_initializes"] = write_initializes
    for name, value in config.get("registers", {}).items():
        key = prefix + name.upper()
        if not hasattr(constants, key):
            raise ValueError(f"Unknown register: {name}")
        cpu.reg_write(getattr(constants, key), number(value))
    cp_initial = []
    for cp in config.get("arm_cp_registers", []):
        if arch == "arm64":
            raise ValueError("arm_cp_registers requires ARM/Thumb")
        fields = {k: number(cp[k]) for k in ["coproc", "opc1", "crn", "crm", "opc2", "el"]}
        fields["is_64"] = bool(cp.get("is_64", False))
        cpu.cpr_write(**fields, value=number(cp["value"]))
        actual = cpu.cpr_read(**fields)
        if actual != number(cp["value"]):
            raise ValueError(f"Coprocessor initial value readback mismatch: requested {number(cp['value']):#x}, read {actual:#x}")
        cp_initial.append({**fields, "value": hex(actual)})
    tail = deque(maxlen=64)
    faults = []
    observations = []
    observed_count = 0
    register_points = {number(a) for a in config.get('register_trace', [])}
    register_limit = number(config.get('register_trace_limit', 128))
    if len(register_points) > 64 or any(a < 0 for a in register_points) or not 1 <= register_limit <= 1024:
        raise ValueError('register_trace needs at most 64 nonnegative addresses and limit 1..1024')
    register_samples = []
    register_sample_count = 0
    sampled_names = ([f'X{i}' for i in range(13)] if arch == 'arm64' else [f'R{i}' for i in range(13)]) + ['SP', 'LR', 'PC']
    observation_limit = number(config.get("memory_trace_limit", 2048))
    if not 1 <= observation_limit <= 10000:
        raise ValueError("memory_trace_limit must be 1..10000")
    watches = []
    for watch in config.get("memory_trace", []):
        address, size = number(watch["address"]), number(watch["size"])
        access = watch.get("access", "rw")
        if address < 0 or size <= 0 or not access or set(access)-set("rw"):
            raise ValueError("Invalid memory trace range/access")
        watches.append((address, address+size, access))
    instruction_count = 0
    def check_initialized(_cpu, kind, address, size):
        for start, mapped_end, ranges, write_initializes, _index in initialized_guards:
            left, right = max(address, start), min(address+size, mapped_end)
            if left < right and kind == "write" and write_initializes:
                merged = []
                for a, b in sorted([*ranges, (left, right)]):
                    if merged and a <= merged[-1][1]:
                        merged[-1] = (merged[-1][0], max(b, merged[-1][1]))
                    else:
                        merged.append((a, b))
                ranges[:] = merged
            if left < right and not any(a <= left and right <= b for a, b in ranges):
                faults.append({"access": kind, "address": hex(address), "size": size,
                               "pc": hex(_cpu.reg_read(getattr(constants, prefix+"PC"))),
                               "reason": "Access outside initialized bytes of a guarded region"})
                _cpu.emu_stop()
                return False
        return True
    def trace(_cpu, address, size, _user):
        nonlocal instruction_count, register_sample_count
        instruction_count += 1
        tail.append(hex(address))
        check_initialized(_cpu, "fetch", address, size)
        if address in register_points:
            register_sample_count += 1
            if len(register_samples) < register_limit:
                register_samples.append({'pc': hex(address), 'instruction': instruction_count,
                                         'registers': {name: hex(_cpu.reg_read(getattr(constants, prefix+name)))
                                                       for name in sampled_names}})
    def fault(_cpu, access, address, size, value, _user):
        faults.append({"access": access, "address": hex(address), "size": size, "value": value,
                       "pc": hex(_cpu.reg_read(getattr(constants, prefix+"PC")))})
        return False
    def observe(_cpu, access, address, size, value, _user):
        nonlocal observed_count
        kind = "w" if access == u.UC_MEM_WRITE else "r"
        check_initialized(_cpu, "write" if kind == "w" else "read", address, size)
        if not any(address < end and address+size > start and kind in modes for start, end, modes in watches):
            return
        observed_count += 1
        if len(observations) < observation_limit:
            # A hook describes an attempted access; faults still stop the CPU.
            observations.append({"access": "write" if kind == "w" else "read", "address": hex(address),
                                 "size": size, "pc": hex(_cpu.reg_read(getattr(constants, prefix+"PC"))),
                                 "write_value": hex(value & ((1 << (size*8))-1)) if kind == "w" and size <= 8 else None})
    cpu.hook_add(u.UC_HOOK_CODE, trace)
    cpu.hook_add(u.UC_HOOK_MEM_INVALID, fault)
    if watches or initialized_guards:
        cpu.hook_add(u.UC_HOOK_MEM_READ | u.UC_HOOK_MEM_WRITE, observe)
    entry, stop = number(config["entry"]), number(config["stop"])
    if arch == "thumb":
        entry |= 1
    error = None
    try:
        cpu.emu_start(entry, stop, timeout=timeout, count=limit)
    except u.UcError as exc:
        error = str(exc)
    pc = cpu.reg_read(getattr(constants, prefix + "PC"))
    names = ["X0", "X1", "X2", "X3", "SP", "PC", "LR"] if arch == "arm64" else ["R0", "R1", "R2", "R3", "SP", "PC", "LR", "CPSR"]
    outputs = []
    for _start, _end, ranges, write_initializes, index in initialized_guards:
        if write_initializes:
            mapped[index]["final_valid_ranges"] = [{"address": hex(a), "size": b-a} for a, b in ranges]
    for region in config.get("outputs", []):
        address, size = number(region["address"]), number(region["size"])
        if not 0 < size <= 1048576:
            raise ValueError("Output regions must be 1 byte to 1 MiB")
        try:
            data = bytes(cpu.mem_read(address, size))
            outputs.append({"address": hex(address), "size": size, "sha256": hashlib.sha256(data).hexdigest(), "hex": data.hex()})
        except u.UcError as exc:
            outputs.append({"address": hex(address), "error": str(exc)})
    return {"architecture": arch, "unicorn_version": u.__version__, "reached_stop": pc == stop and error is None and not faults,
            "instructions": instruction_count, "error": error, "faults": faults,
            "registers": {name: hex(cpu.reg_read(getattr(constants, prefix + name))) for name in names},
            "trace_tail": list(tail), "regions": mapped, "outputs": outputs,
            "memory_trace": observations, "memory_trace_total": observed_count,
            "memory_trace_truncated": observed_count > len(observations),
            'register_trace': register_samples, 'register_trace_total': register_sample_count,
            'register_trace_truncated': register_sample_count > len(register_samples),
            "arm_cp_initial": cp_initial,
            "camera_emulated": False, "image_pipeline_validated": False,
            "provenance": config.get("provenance", "unspecified; cannot claim firmware execution")}


def self_test() -> dict:
    results = []
    for arch, code, reg in [("arm", "010080e21eff2fe1", "R0"), ("thumb", "01307047", "R0"), ("arm64", "00040091c0035fd6", "X0")]:
        config = {"architecture": arch, "entry": "0x10000", "stop": "0x20000",
                  "regions": [{"address": "0x10000", "size": 4096, "permissions": "rx", "hex": code}, {"address": "0x20000", "size": 4096, "permissions": "rx"}],
                  "registers": {reg: 41, "LR": "0x20000"}, "instruction_limit": 10,
                  "provenance": "Synthetic ADD + RETURN instructions authored for infrastructure testing; NOT Fujifilm code."}
        result = run_function(config)
        result["test_passed"] = result["reached_stop"] and result["registers"][reg] == "0x2a"
        results.append(result)
    return {"passed": all(r["test_passed"] for r in results), "cases": results, "firmware_executed": False}
