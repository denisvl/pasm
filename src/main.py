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


def main():
    """Main CLI entry point."""

    parser = argparse.ArgumentParser(
        prog="pasm",
        description="PASM - Processor Architecture Specification for Emulation\n"
        "Generate C emulators from ISA definitions",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Generate command
    gen_parser = subparsers.add_parser(
        "generate",
        help="Generate emulator from ISA file",
        aliases=["gen"],
    )
    gen_parser.add_argument(
        "--isa",
        "-i",
        required=True,
        help="Input YAML ISA file",
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
        help="Validate ISA and exit without generating",
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
        help="Validate ISA file without generating",
    )
    val_parser.add_argument(
        "--isa",
        "-i",
        required=True,
        help="Input YAML ISA file",
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
        help="Show ISA summary",
    )
    info_parser.add_argument(
        "--isa",
        "-i",
        required=True,
        help="Input YAML ISA file",
    )

    args = parser.parse_args()

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
        print(f"Error: {e}", file=sys.stderr)
        if args.verbose:
            import traceback

            traceback.print_exc()
        return 1

    return 0


def generate_command(args):
    """Handle generate command."""

    isa_path = args.isa

    # Validate ISA file exists
    if not os.path.exists(isa_path):
        print(f"Error: ISA file not found: {isa_path}", file=sys.stderr)
        return 1

    # Load ISA
    if args.verbose:
        print(f"Loading ISA from {isa_path}...")

    loader = src.parser.yaml_loader.ISALoader()
    try:
        isa_data = loader.load(isa_path)
    except Exception as e:
        print(f"Error loading ISA: {e}", file=sys.stderr)
        return 1

    # If requested, only validate and exit
    if getattr(args, "validate_only", False):
        if args.verbose:
            print(f"ISA file is valid: {isa_path}")
        return 0

    # Determine output directory
    cpu_name = isa_data.get("metadata", {}).get("name", "cpu")

    if args.output:
        output_dir = args.output
    else:
        output_dir = f"./generated/{cpu_name.lower()}"

    # Generate
    generator = src.generator.EmulatorGenerator(isa_path)
    generator.generate(output_dir, dispatch_mode=args.dispatch)

    return 0


def validate_command(args):
    """Handle validate command."""

    isa_path = args.isa

    if not os.path.exists(isa_path):
        print(f"Error: ISA file not found: {isa_path}", file=sys.stderr)
        return 1

    try:
        loader = src.parser.yaml_loader.ISALoader()
        isa_data = loader.load(isa_path)

        if args.verbose:
            print(f"ISA file is valid: {isa_path}")

        return 0
    except Exception as e:
        print(f"Validation failed: {e}", file=sys.stderr)
        return 1


def info_command(args):
    """Handle info command."""

    isa_path = args.isa

    if not os.path.exists(isa_path):
        print(f"Error: ISA file not found: {isa_path}", file=sys.stderr)
        return 1

    try:
        loader = src.parser.yaml_loader.ISALoader()
        isa_data = loader.load(isa_path)
        summary = loader.get_summary(isa_data)

        print(f"=== {summary['name']} ISA Summary ===")
        print(f"Version: {summary['version']}")
        print(f"Bits: {summary['bits']}")
        print(f"Address bits: {summary['address_bits']}")
        print(f"Endian: {summary['endian']}")
        print(f"Registers: {summary['num_registers']}")
        print(f"Flags: {summary['num_flags']}")
        print(f"Instructions: {summary['num_instructions']}")
        print(f"Undefined opcode policy: {summary.get('undefined_opcode_policy', 'trap')}")
        print(f"Interrupts: {'Yes' if summary['has_interrupts'] else 'No'}")
        interrupt_model = summary.get("interrupt_model")
        if summary["has_interrupts"] and interrupt_model:
            print(f"Interrupt model: {interrupt_model}")
        print(f"Ports: {'Yes' if summary['has_ports'] else 'No'}")

        hooks = summary.get("hooks", {})
        if hooks:
            print("Hooks enabled:")
            for hook_name, hook_data in hooks.items():
                if hook_data.get("enabled"):
                    desc = hook_data.get("description", "")
                    print(f"  - {hook_name}: {desc}")

        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
