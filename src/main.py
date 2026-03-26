"""CLI entry point for PASM."""

import argparse
import sys
import os

# Ensure the package directory is in path
_pkg_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _pkg_dir not in sys.path:
    sys.path.insert(0, _pkg_dir)

# Now import the modules using absolute imports
import src.parser.yaml_loader
import src.generator
from src.logging_utils import configure_logging, logger


def main():
    """Main CLI entry point."""
    configure_logging(verbose=False)

    parser = argparse.ArgumentParser(
        prog="pasm",
        description="PASM - Processor Architecture Specification for Emulation\n"
        "Generate C emulators from ISA definitions",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    if "--isa" in sys.argv:
        logger.error(
            "Error: single-file ISA input was removed. Use --processor and --system.",
        )
        return 1

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Generate command
    gen_parser = subparsers.add_parser(
        "generate",
        help="Generate emulator from processor/system files",
        aliases=["gen"],
    )
    gen_parser.add_argument(
        "--processor",
        required=True,
        help="Input YAML processor definition file",
    )
    gen_parser.add_argument(
        "--system",
        required=True,
        help="Input YAML system definition file",
    )
    gen_parser.add_argument(
        "--ic",
        action="append",
        default=[],
        help="Input YAML IC definition file (repeatable, order-preserving)",
    )
    gen_parser.add_argument(
        "--device",
        action="append",
        default=[],
        help="Input YAML device definition file (repeatable, order-preserving)",
    )
    gen_parser.add_argument(
        "--host",
        action="append",
        default=[],
        help="Input YAML host definition file (repeatable, order-preserving)",
    )
    gen_parser.add_argument(
        "--cartridge-map",
        help="Input YAML cartridge mapper definition file (single active cartridge)",
    )
    gen_parser.add_argument(
        "--cartridge-rom",
        help="Cartridge ROM binary path (required when --cartridge-map is used)",
    )
    gen_parser.add_argument(
        "--output",
        "-o",
        help="Output directory (default: ./generated/<cpu_name>)",
    )
    gen_parser.add_argument(
        "--dispatch",
        choices=["switch", "threaded", "both"],
        default="switch",
        help="Dispatch strategy (default: switch)",
    )
    gen_parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate processor/system files and exit without generating",
    )
    gen_parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose output",
    )

    # Validate command
    val_parser = subparsers.add_parser(
        "validate",
        help="Validate processor/system files without generating",
    )
    val_parser.add_argument(
        "--processor",
        required=True,
        help="Input YAML processor definition file",
    )
    val_parser.add_argument(
        "--system",
        required=True,
        help="Input YAML system definition file",
    )
    val_parser.add_argument(
        "--ic",
        action="append",
        default=[],
        help="Input YAML IC definition file (repeatable, order-preserving)",
    )
    val_parser.add_argument(
        "--device",
        action="append",
        default=[],
        help="Input YAML device definition file (repeatable, order-preserving)",
    )
    val_parser.add_argument(
        "--host",
        action="append",
        default=[],
        help="Input YAML host definition file (repeatable, order-preserving)",
    )
    val_parser.add_argument(
        "--cartridge-map",
        help="Input YAML cartridge mapper definition file (single active cartridge)",
    )
    val_parser.add_argument(
        "--cartridge-rom",
        help="Cartridge ROM binary path (required when --cartridge-map is used)",
    )
    val_parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose output",
    )

    # Info command
    info_parser = subparsers.add_parser(
        "info",
        help="Show processor/system summary",
    )
    info_parser.add_argument(
        "--processor",
        required=True,
        help="Input YAML processor definition file",
    )
    info_parser.add_argument(
        "--system",
        required=True,
        help="Input YAML system definition file",
    )
    info_parser.add_argument(
        "--ic",
        action="append",
        default=[],
        help="Input YAML IC definition file (repeatable, order-preserving)",
    )
    info_parser.add_argument(
        "--device",
        action="append",
        default=[],
        help="Input YAML device definition file (repeatable, order-preserving)",
    )
    info_parser.add_argument(
        "--host",
        action="append",
        default=[],
        help="Input YAML host definition file (repeatable, order-preserving)",
    )
    info_parser.add_argument(
        "--cartridge-map",
        help="Input YAML cartridge mapper definition file (single active cartridge)",
    )
    info_parser.add_argument(
        "--cartridge-rom",
        help="Cartridge ROM binary path (required when --cartridge-map is used)",
    )

    args = parser.parse_args()
    configure_logging(verbose=bool(getattr(args, "verbose", False)))

    if not args.command:
        parser.print_help()
        return 1

    try:
        if args.command == "generate" or args.command == "gen":
            return generate_command(args)
        elif args.command == "validate":
            return validate_command(args)
        elif args.command == "info":
            return info_command(args)
    except Exception as e:
        logger.error(f"Error: {e}")
        if args.verbose:
            logger.exception("Unhandled CLI exception")
        return 1

    return 0


def generate_command(args):
    """Handle generate command."""

    processor_path = args.processor
    system_path = args.system
    ic_paths = list(getattr(args, "ic", []) or [])
    device_paths = list(getattr(args, "device", []) or [])
    host_paths = list(getattr(args, "host", []) or [])
    cartridge_map_path = getattr(args, "cartridge_map", None)
    cartridge_rom_path = getattr(args, "cartridge_rom", None)

    # Validate input files exist
    if not os.path.exists(processor_path):
        logger.error(f"Error: Processor file not found: {processor_path}")
        return 1
    if not os.path.exists(system_path):
        logger.error(f"Error: System file not found: {system_path}")
        return 1
    for ic_path in ic_paths:
        if not os.path.exists(ic_path):
            logger.error(f"Error: IC file not found: {ic_path}")
            return 1
    for device_path in device_paths:
        if not os.path.exists(device_path):
            logger.error(f"Error: Device file not found: {device_path}")
            return 1
    for host_path in host_paths:
        if not os.path.exists(host_path):
            logger.error(f"Error: Host file not found: {host_path}")
            return 1
    if cartridge_map_path and not os.path.exists(cartridge_map_path):
        logger.error(f"Error: Cartridge map file not found: {cartridge_map_path}")
        return 1

    # Load processor+system model
    if args.verbose:
        logger.info(f"Loading processor from {processor_path}...")
        logger.info(f"Loading system from {system_path}...")
        for ic_path in ic_paths:
            logger.info(f"Loading IC from {ic_path}...")
        for device_path in device_paths:
            logger.info(f"Loading device from {device_path}...")
        for host_path in host_paths:
            logger.info(f"Loading host from {host_path}...")
        if cartridge_map_path:
            logger.info(f"Loading cartridge map from {cartridge_map_path}...")
        if cartridge_rom_path:
            logger.info(f"Using cartridge ROM {cartridge_rom_path}...")

    loader = src.parser.yaml_loader.ProcessorSystemLoader()
    try:
        isa_data = loader.load(
            processor_path,
            system_path,
            ic_paths=ic_paths,
            device_paths=device_paths,
            host_paths=host_paths,
            cartridge_path=cartridge_map_path,
            cartridge_rom_path=cartridge_rom_path,
        )
    except Exception as e:
        logger.error(f"Error loading processor/system definition: {e}")
        return 1

    # If requested, only validate and exit
    if getattr(args, "validate_only", False):
        if args.verbose:
            logger.info(
                "Processor/system/component files are valid: "
                f"{processor_path}, {system_path}, {len(ic_paths)} IC(s), "
                f"{len(device_paths)} device(s), {len(host_paths)} host(s), "
                f"{'1' if cartridge_map_path else '0'} cartridge(s)"
            )
        return 0

    # Determine output directory
    cpu_name = isa_data.get("metadata", {}).get("name", "cpu")

    if args.output:
        output_dir = args.output
    else:
        output_dir = f"./generated/{cpu_name.lower()}"

    # Generate
    generator = src.generator.EmulatorGenerator(
        processor_path,
        system_path,
        ic_paths=ic_paths,
        device_paths=device_paths,
        host_paths=host_paths,
        cartridge_map_path=cartridge_map_path,
        cartridge_rom_path=cartridge_rom_path,
    )
    generator.generate(output_dir, dispatch_mode=args.dispatch)

    return 0


def validate_command(args):
    """Handle validate command."""

    processor_path = args.processor
    system_path = args.system
    ic_paths = list(getattr(args, "ic", []) or [])
    device_paths = list(getattr(args, "device", []) or [])
    host_paths = list(getattr(args, "host", []) or [])
    cartridge_map_path = getattr(args, "cartridge_map", None)
    cartridge_rom_path = getattr(args, "cartridge_rom", None)

    if not os.path.exists(processor_path):
        logger.error(f"Error: Processor file not found: {processor_path}")
        return 1
    if not os.path.exists(system_path):
        logger.error(f"Error: System file not found: {system_path}")
        return 1
    for ic_path in ic_paths:
        if not os.path.exists(ic_path):
            logger.error(f"Error: IC file not found: {ic_path}")
            return 1
    for device_path in device_paths:
        if not os.path.exists(device_path):
            logger.error(f"Error: Device file not found: {device_path}")
            return 1
    for host_path in host_paths:
        if not os.path.exists(host_path):
            logger.error(f"Error: Host file not found: {host_path}")
            return 1
    if cartridge_map_path and not os.path.exists(cartridge_map_path):
        logger.error(f"Error: Cartridge map file not found: {cartridge_map_path}")
        return 1

    try:
        loader = src.parser.yaml_loader.ProcessorSystemLoader()
        loader.load(
            processor_path,
            system_path,
            ic_paths=ic_paths,
            device_paths=device_paths,
            host_paths=host_paths,
            cartridge_path=cartridge_map_path,
            cartridge_rom_path=cartridge_rom_path,
        )

        if args.verbose:
            logger.info(
                "Processor/system/component files are valid: "
                f"{processor_path}, {system_path}, {len(ic_paths)} IC(s), "
                f"{len(device_paths)} device(s), {len(host_paths)} host(s), "
                f"{'1' if cartridge_map_path else '0'} cartridge(s)"
            )

        return 0
    except Exception as e:
        logger.error(f"Validation failed: {e}")
        return 1


def info_command(args):
    """Handle info command."""

    processor_path = args.processor
    system_path = args.system
    ic_paths = list(getattr(args, "ic", []) or [])
    device_paths = list(getattr(args, "device", []) or [])
    host_paths = list(getattr(args, "host", []) or [])
    cartridge_map_path = getattr(args, "cartridge_map", None)
    cartridge_rom_path = getattr(args, "cartridge_rom", None)

    if not os.path.exists(processor_path):
        logger.error(f"Error: Processor file not found: {processor_path}")
        return 1
    if not os.path.exists(system_path):
        logger.error(f"Error: System file not found: {system_path}")
        return 1
    for ic_path in ic_paths:
        if not os.path.exists(ic_path):
            logger.error(f"Error: IC file not found: {ic_path}")
            return 1
    for device_path in device_paths:
        if not os.path.exists(device_path):
            logger.error(f"Error: Device file not found: {device_path}")
            return 1
    for host_path in host_paths:
        if not os.path.exists(host_path):
            logger.error(f"Error: Host file not found: {host_path}")
            return 1
    if cartridge_map_path and not os.path.exists(cartridge_map_path):
        logger.error(f"Error: Cartridge map file not found: {cartridge_map_path}")
        return 1

    try:
        loader = src.parser.yaml_loader.ProcessorSystemLoader()
        isa_data = loader.load(
            processor_path,
            system_path,
            ic_paths=ic_paths,
            device_paths=device_paths,
            host_paths=host_paths,
            cartridge_path=cartridge_map_path,
            cartridge_rom_path=cartridge_rom_path,
        )
        summary = loader.get_summary(isa_data)

        logger.info(f"=== {summary['name']} + {summary['system_name']} Summary ===")
        logger.info(f"Processor Version: {summary['version']}")
        logger.info(f"Bits: {summary['bits']}")
        logger.info(f"Address bits: {summary['address_bits']}")
        logger.info(f"Endian: {summary['endian']}")
        logger.info(f"Clock Hz: {summary['clock_hz']}")
        logger.info(f"Memory default size: {summary['memory_default_size']}")
        logger.info(f"Registers: {summary['num_registers']}")
        logger.info(f"Flags: {summary['num_flags']}")
        logger.info(f"Instructions: {summary['num_instructions']}")
        logger.info(f"Undefined opcode policy: {summary.get('undefined_opcode_policy', 'trap')}")
        logger.info(f"ICs: {summary.get('num_ics', 0)}")
        ic_ids = [ic_id for ic_id in summary.get("ic_ids", []) if ic_id]
        if ic_ids:
            logger.info(f"IC IDs: {', '.join(ic_ids)}")
        logger.info(f"Devices: {summary.get('num_devices', 0)}")
        device_ids = [dev_id for dev_id in summary.get("device_ids", []) if dev_id]
        if device_ids:
            logger.info(f"Device IDs: {', '.join(device_ids)}")
        logger.info(f"Hosts: {summary.get('num_hosts', 0)}")
        host_ids = [host_id for host_id in summary.get("host_ids", []) if host_id]
        if host_ids:
            logger.info(f"Host IDs: {', '.join(host_ids)}")
        logger.info(f"Cartridges: {summary.get('num_cartridges', 0)}")
        cart_id = str(summary.get("cartridge_id", "")).strip()
        if cart_id:
            logger.info(f"Cartridge ID: {cart_id}")
        cart_rom = str(summary.get("cartridge_rom_path", "")).strip()
        if cart_rom:
            logger.info(f"Cartridge ROM: {cart_rom}")
        logger.info(f"System ROM images: {summary.get('num_rom_images', 0)}")
        logger.info(f"Interrupts: {'Yes' if summary['has_interrupts'] else 'No'}")
        interrupt_model = summary.get("interrupt_model")
        if summary["has_interrupts"] and interrupt_model:
            logger.info(f"Interrupt model: {interrupt_model}")
        logger.info(f"Ports: {'Yes' if summary['has_ports'] else 'No'}")

        hooks = summary.get("hooks", {})
        if hooks:
            logger.info("Hooks enabled:")
            for hook_name, hook_data in hooks.items():
                if hook_data.get("enabled"):
                    desc = hook_data.get("description", "")
                    logger.info(f"  - {hook_name}: {desc}")

        return 0
    except Exception as e:
        logger.error(f"Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
