import argparse
import json
from pathlib import Path
import sys


def save_or_print(value, path):
    data = json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)
    if path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Reports are immutable: reruns must choose a fresh filename.
        with path.open("x", encoding="utf-8") as f:
            f.write(data + "\n")
        print(str(path.resolve()))
    else:
        print(data)


def main():
    parser = argparse.ArgumentParser(description="Film Recipe Lab · local RAW and film-recipe studio")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("gui", help="Open the local RAF/DNG studio with previews and recipe editing")
    p.add_argument("--root", type=Path, action="append", default=[])
    p.add_argument("--port", type=int, default=8765)
    p = sub.add_parser("status", help="Report the engine status accurately")
    p.add_argument("--output")
    p = sub.add_parser("inventory", help="Inventory RAW files without reading iCloud placeholders")
    p.add_argument("roots", type=Path, nargs="+")
    p.add_argument("--output")
    p = sub.add_parser("probe", help="Read RAW structure, CFA, matrices, and metadata")
    p.add_argument("source", type=Path)
    p.add_argument("--output")
    p = sub.add_parser("prepare", help="Prepare neutral LibRaw test inputs, not a Fuji render")
    p.add_argument("source", type=Path)
    p.add_argument("directory", type=Path)
    p.add_argument("--max-edge", type=int, default=1500)
    p = sub.add_parser("firmware-inspect", help="Inspect the DAT statically without modifying it")
    p.add_argument("source", type=Path)
    p.add_argument("--output")
    p = sub.add_parser("firmware-extract", help="Extract and decompress the verified X-T4 2.12 DAT")
    p.add_argument("source", type=Path)
    p.add_argument("directory", type=Path)
    p.add_argument("--output")
    p = sub.add_parser("xt4-film-probe", help="Run the native film-name function; no rendering")
    p.add_argument("module", type=Path)
    p.add_argument("--output")
    p = sub.add_parser("xt4-parameter-probe", help="Test the native RAW parameter constructor; no rendering")
    p.add_argument("directory", type=Path)
    p.add_argument("--output")
    p = sub.add_parser("xt4-map", help="Check static references in the two identified ARM modules")
    p.add_argument("directory", type=Path)
    p.add_argument("--output")
    p = sub.add_parser("xt4-chain-probe", help="Trace native parameters to the first missing dependency")
    p.add_argument("directory", type=Path)
    p.add_argument("--output")
    p = sub.add_parser("xt4-threadx-probe", help="Test identified system functions with explicit core-0 state")
    p.add_argument("directory", type=Path)
    p.add_argument("--output")
    p = sub.add_parser("xt4-cfg-probe", help="Check configuration and WB coefficients in the Fuji DAT; no rendering")
    p.add_argument("directory", type=Path)
    p.add_argument("--output", type=Path)
    p = sub.add_parser("xt4-wb-probe", help="Check native white-balance calculation with explicit synthetic calibration; no rendering")
    p.add_argument("directory", type=Path)
    p.add_argument("--output", type=Path)
    p = sub.add_parser("xt4-message-probe", help="Test native message constructors and transport without pixels")
    p.add_argument("directory", type=Path)
    p.add_argument("--output", type=Path)
    p = sub.add_parser("xt4-dma-probe", help="Check native DMA lists and capture register writes; no pixel transfer")
    p.add_argument("directory", type=Path)
    p.add_argument("--control", action="store_true", help="Test status decoding and launch separately with static synthetic registers")
    p.add_argument("--output", type=Path)
    p = sub.add_parser("xt4-resource-probe", help="Prepare the native RAW resource and reach its message send")
    p.add_argument("directory", type=Path)
    p.add_argument("source", type=Path)
    p.add_argument("--with-transport", action="store_true", help="Build messaging objects and complete the native send")
    p.add_argument("--with-receiver", action="store_true", help="Trace the receiving task after send (implies --with-transport)")
    p.add_argument("--cfg-feb0", type=int, help="Research only: hypothetical configuration byte 0..255, not a validated camera value")
    p.add_argument("--firmware-config", action="store_true", help="Load the verified DAT configuration page; requires --with-receiver")
    p.add_argument("--boot-wb", action="store_true", help="Initialize WB fill from the native BSS path; requires --firmware-config")
    p.add_argument("--extended-config", action="store_true", help="Load the verified DEFAULT block from the DAT; requires --boot-wb")
    p.add_argument("--raw-resource-plan", action="store_true", help="Run native RAW plan 6 assignment; partial preparation, requires --extended-config")
    p.add_argument("--request-mode", type=int, choices=(2, 6, 7), default=2, help="Buffer mode to study: historical mode 2 or alternative native tables 6/7")
    p.add_argument("--output", type=Path)
    p = sub.add_parser("xt4-raf-metadata-probe", help="Read RAF geometry with the native Fuji reader; no pixels")
    p.add_argument("directory", type=Path)
    p.add_argument("source", type=Path)
    p.add_argument("--output", type=Path)
    p = sub.add_parser("xt4-raw-frontier-probe", help="Run initializations and reach the native RAW header reader")
    p.add_argument("directory", type=Path)
    p.add_argument("--output", type=Path)
    p = sub.add_parser("xt4-orchestrator-probe", help="Reach the missing dependency after native setup and synchronization")
    p.add_argument("directory", type=Path)
    p.add_argument("--output", type=Path)
    p = sub.add_parser("xt4-sync-probe", help="Test the native constructor and synchronization on core 0")
    p.add_argument("directory", type=Path)
    p.add_argument("--output", type=Path)
    p = sub.add_parser("xt4-runtime-probe", help="Run the three native setting stages with an explicit schedule")
    p.add_argument("directory", type=Path)
    p.add_argument("--output")
    p = sub.add_parser("compare", help="Compare pixels without alignment or resizing")
    p.add_argument("reference", type=Path)
    p.add_argument("candidate", type=Path)
    p.add_argument("--output")
    p = sub.add_parser("emulator-selftest", help="Test ARM/Thumb/ARM64 with synthetic code")
    p.add_argument("--output")
    p = sub.add_parser("emulate", help="Run a function with an explicit memory map")
    p.add_argument("config", type=Path)
    p.add_argument("--output")
    p = sub.add_parser("recipe", help="Create an example or validate a JSON recipe")
    p.add_argument("source", type=Path, nargs="?")
    p.add_argument("--output")
    p = sub.add_parser("render", help="Reserved for the exact engine; unavailable until reconstructed")
    p.add_argument("source", type=Path)
    p.add_argument("recipe", type=Path)
    p.add_argument("destination", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "gui":
            from .gui import serve
            serve(args.root, args.port)
            return 0
        if args.command == "status":
            from .engine import status
            result = status()
        elif args.command == "inventory":
            from .raw import inventory
            result = inventory(args.roots)
        elif args.command == "probe":
            from .raw import probe
            result = probe(args.source)
        elif args.command == "prepare":
            from .raw import prepare
            result = prepare(args.source, args.directory, args.max_edge)
        elif args.command == "firmware-inspect":
            from .firmware import inspect_firmware
            result = inspect_firmware(args.source)
        elif args.command == "firmware-extract":
            from .extract import extract
            result = extract(args.source, args.directory)
        elif args.command == "xt4-film-probe":
            from .xt4 import film_probe
            result = film_probe(args.module)
        elif args.command == "xt4-parameter-probe":
            from .xt4 import parameter_probe
            result = parameter_probe(args.directory)
        elif args.command == "xt4-map":
            from .mapping import analyze_xt4
            result = analyze_xt4(args.directory)
        elif args.command == "xt4-chain-probe":
            from .pipeline import chain_probe
            result = chain_probe(args.directory)
        elif args.command == "xt4-threadx-probe":
            from .threadx import threadx_probe
            result = threadx_probe(args.directory)
        elif args.command == "xt4-runtime-probe":
            from .pipeline import chain_probe
            result = chain_probe(args.directory, with_calendar=True)
        elif args.command == "xt4-sync-probe":
            from .synchronization import synchronization_probe
            result = synchronization_probe(args.directory)
        elif args.command == "xt4-orchestrator-probe":
            from .orchestration import orchestrator_probe
            result = orchestrator_probe(args.directory)
        elif args.command == "xt4-raw-frontier-probe":
            from .orchestration import orchestrator_probe
            result = orchestrator_probe(args.directory, with_requests=True)
        elif args.command == "xt4-raf-metadata-probe":
            from .raf_metadata import metadata_probe
            result = metadata_probe(args.directory, args.source)
        elif args.command == "xt4-cfg-probe":
            from .configuration import configuration_probe
            result = configuration_probe(args.directory)
        elif args.command == "xt4-wb-probe":
            from .white_balance import white_balance_probe
            result = white_balance_probe(args.directory)
        elif args.command == "xt4-message-probe":
            from .messaging import message_probe
            result = message_probe(args.directory)
        elif args.command == "xt4-dma-probe":
            from .dma import descriptor_probe, control_probe
            result = control_probe(args.directory) if args.control else descriptor_probe(args.directory)
        elif args.command == "xt4-resource-probe":
            from .orchestration import orchestrator_probe
            result = orchestrator_probe(args.directory, with_requests=True, resource_source=args.source,
                                        with_transport=args.with_transport or args.with_receiver, with_receiver=args.with_receiver,
                                        cfg_feb0=args.cfg_feb0, with_firmware_config=args.firmware_config, with_boot_wb=args.boot_wb,
                                        with_extended_config=args.extended_config,
                                        with_raw_resource_plan=args.raw_resource_plan,
                                        request_mode=args.request_mode)
        elif args.command == "compare":
            from .compare import compare
            result = compare(args.reference, args.candidate)
        elif args.command == "emulator-selftest":
            from .emulation import self_test
            result = self_test()
        elif args.command == "emulate":
            from .emulation import run_function
            result = run_function(json.loads(args.config.read_text()), args.config.parent)
        elif args.command == "recipe":
            from .recipe import Recipe
            recipe = Recipe.model_validate_json(args.source.read_text()) if args.source else Recipe()
            if recipe.unsupported():
                raise ValueError(" ".join(recipe.unsupported()))
            result = recipe.model_dump()
        elif args.command == "render":
            from .engine import render_exact
            from .recipe import Recipe
            result = render_exact(args.source, Recipe.model_validate_json(args.recipe.read_text()), args.destination)
        save_or_print(result, getattr(args, "output", None))
        if args.command in {"emulator-selftest", "xt4-wb-probe", "xt4-cfg-probe"} and not result["passed"]:
            return 1
        if args.command == "emulate" and not result["reached_stop"]:
            return 1
        if args.command in {"xt4-film-probe", "xt4-parameter-probe", "xt4-chain-probe", "xt4-threadx-probe", "xt4-runtime-probe", "xt4-sync-probe", "xt4-orchestrator-probe", "xt4-raw-frontier-probe", "xt4-raf-metadata-probe", "xt4-resource-probe", "xt4-message-probe", "xt4-dma-probe"} and not result["passed"]:
            return 1
        if args.command == "firmware-extract" and not all(p["decoded"] for p in result["packed_objects"]):
            return 1
        return 0
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
