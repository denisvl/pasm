#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path


OPCODES: dict[tuple[str, str], int] = {
    ("ADC", "imm"): 0x69,
    ("AND", "imm"): 0x29,
    ("ASL", "acc"): 0x0A,
    ("BCC", "rel"): 0x90,
    ("BCS", "rel"): 0xB0,
    ("BEQ", "rel"): 0xF0,
    ("BIT", "zp"): 0x24,
    ("BIT", "abs"): 0x2C,
    ("BMI", "rel"): 0x30,
    ("BNE", "rel"): 0xD0,
    ("BPL", "rel"): 0x10,
    ("BVC", "rel"): 0x50,
    ("CLC", "impl"): 0x18,
    ("CLD", "impl"): 0xD8,
    ("CLI", "impl"): 0x58,
    ("CMP", "imm"): 0xC9,
    ("CMP", "zp"): 0xC5,
    ("CPY", "imm"): 0xC0,
    ("CPY", "zp"): 0xC4,
    ("DEC", "zp"): 0xC6,
    ("DEX", "impl"): 0xCA,
    ("DEY", "impl"): 0x88,
    ("EOR", "imm"): 0x49,
    ("INC", "zp"): 0xE6,
    ("INX", "impl"): 0xE8,
    ("INY", "impl"): 0xC8,
    ("JMP", "abs"): 0x4C,
    ("JMP", "ind"): 0x6C,
    ("JSR", "abs"): 0x20,
    ("LDA", "imm"): 0xA9,
    ("LDA", "zp"): 0xA5,
    ("LDA", "zpx"): 0xB5,
    ("LDA", "abs"): 0xAD,
    ("LDA", "absy"): 0xB9,
    ("LDA", "indx"): 0xA1,
    ("LDX", "imm"): 0xA2,
    ("LDY", "imm"): 0xA0,
    ("LSR", "acc"): 0x4A,
    ("ORA", "imm"): 0x09,
    ("PHA", "impl"): 0x48,
    ("PLA", "impl"): 0x68,
    ("ROL", "acc"): 0x2A,
    ("ROL", "zp"): 0x26,
    ("RTS", "impl"): 0x60,
    ("SBC", "zp"): 0xE5,
    ("STA", "zp"): 0x85,
    ("STA", "zpx"): 0x95,
    ("STA", "abs"): 0x8D,
    ("STA", "absy"): 0x99,
    ("STA", "indx"): 0x81,
    ("STX", "zp"): 0x86,
    ("STY", "zp"): 0x84,
    ("STY", "abs"): 0x8C,
    ("TAX", "impl"): 0xAA,
}

BRANCHES = {"BCC", "BCS", "BEQ", "BMI", "BNE", "BPL", "BVC"}
IMPLIED = {"CLC", "CLD", "CLI", "DEX", "DEY", "INX", "INY", "PHA", "PLA", "RTS", "TAX"}
ACCUMULATOR = {"ASL", "LSR", "ROL"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    return parser.parse_args()


def strip_comment(line: str) -> str:
    return line.split(";", 1)[0].rstrip()


def parse_number(token: str) -> int:
    token = token.strip()
    if not token:
        raise ValueError("empty token")
    if token.startswith("$"):
        return int(token[1:], 16)
    if token.startswith("%"):
        return int(token[1:].replace(".", ""), 2)
    if token.startswith('"') and token.endswith('"') and len(token) >= 2:
        inner = token[1:-1]
        if inner == r"\\":
            return ord("\\")
        if len(inner) != 1:
            raise ValueError(f"unsupported char literal: {token}")
        return ord(inner)
    return int(token, 10)


def first_expr(expr: str) -> str:
    head, _, _ = expr.partition(",")
    return head.strip()


def eval_expr(expr: str, symbols: dict[str, int]) -> int:
    expr = expr.strip()
    if not expr:
        raise ValueError("empty expression")
    parts = re.split(r"([+-])", expr)
    total = None
    op = "+"
    for raw in parts:
        token = raw.strip()
        if not token:
            continue
        if token in {"+", "-"}:
            op = token
            continue
        if token in symbols:
            value = symbols[token]
        else:
            value = parse_number(token)
        if total is None:
            total = value if op == "+" else -value
        elif op == "+":
            total += value
        else:
            total -= value
    if total is None:
        raise ValueError(f"could not evaluate expression: {expr}")
    return total & 0xFFFF


def split_label(line: str) -> tuple[str | None, str]:
    if not line or line[0].isspace():
        return None, line.strip()
    parts = line.split(None, 1)
    if len(parts) == 1:
        return parts[0], ""
    head, tail = parts
    if tail.startswith(".EQ"):
        return head, tail
    if head.startswith("."):
        return None, line.strip()
    if head.upper() in OPCODES or head.upper() in IMPLIED or head.upper() in ACCUMULATOR or head.upper() in BRANCHES:
        return None, line.strip()
    return head, tail.strip()


def canonicalize_body(body: str) -> str:
    body = body.strip()
    if not body:
        return body
    mnemonic, sep, rest = body.partition(" ")
    if not sep:
        return mnemonic
    operand = rest.strip()
    if not operand:
        return mnemonic
    operand = re.split(r"\s{2,}", operand, maxsplit=1)[0].strip()
    return f"{mnemonic} {operand}"


def detect_mode(mnemonic: str, operand: str, symbols: dict[str, int]) -> tuple[str, int | None]:
    operand = operand.strip()
    if mnemonic in IMPLIED:
        return "impl", None
    if mnemonic in BRANCHES:
        return "rel", eval_expr(operand, symbols)
    if operand.startswith("#"):
        return "imm", eval_expr(operand[1:], symbols)
    if operand.startswith("(") and operand.endswith(",X)"):
        return "indx", eval_expr(operand[1:-3], symbols)
    if operand.startswith("(") and operand.endswith(")"):
        return "ind", eval_expr(operand[1:-1], symbols)
    if mnemonic in ACCUMULATOR:
        try:
            value = eval_expr(operand, symbols)
        except Exception:
            return "acc", None
        return ("zp" if value <= 0xFF else "abs"), value
    if operand.endswith(",X"):
        value = eval_expr(operand[:-2], symbols)
        return ("zpx" if value <= 0xFF else "absx"), value
    if operand.endswith(",Y"):
        value = eval_expr(operand[:-2], symbols)
        return ("zpy" if value <= 0xFF else "absy"), value
    value = eval_expr(operand, symbols)
    return ("zp" if value <= 0xFF else "abs"), value


def detect_mode_first_pass(mnemonic: str, operand: str, symbols: dict[str, int]) -> str:
    operand = operand.strip()
    if mnemonic in IMPLIED:
        return "impl"
    if mnemonic in BRANCHES:
        return "rel"
    if operand.startswith("#"):
        return "imm"
    if operand.startswith("(") and operand.endswith(",X)"):
        return "indx"
    if operand.startswith("(") and operand.endswith(")"):
        return "ind"
    if mnemonic in ACCUMULATOR:
        try:
            value = eval_expr(operand, symbols)
        except Exception:
            return "acc"
        return "zp" if value <= 0xFF else "abs"
    if operand.endswith(",X"):
        base = operand[:-2].strip()
        try:
            value = eval_expr(base, symbols)
        except Exception:
            return "absx"
        return "zpx" if value <= 0xFF else "absx"
    if operand.endswith(",Y"):
        base = operand[:-2].strip()
        try:
            value = eval_expr(base, symbols)
        except Exception:
            return "absy"
        return "zpy" if value <= 0xFF else "absy"
    try:
        value = eval_expr(operand, symbols)
    except Exception:
        return "abs"
    return "zp" if value <= 0xFF else "abs"


def instr_size(mode: str) -> int:
    return {
        "impl": 1,
        "acc": 1,
        "imm": 2,
        "rel": 2,
        "zp": 2,
        "zpx": 2,
        "zpy": 2,
        "indx": 2,
        "indy": 2,
        "abs": 3,
        "absx": 3,
        "absy": 3,
        "ind": 3,
    }[mode]


def parse_source(text: str) -> list[tuple[str | None, str]]:
    rows: list[tuple[str | None, str]] = []
    for raw in text.splitlines():
        line = strip_comment(raw)
        if not line.strip():
            continue
        label, body = split_label(line)
        rows.append((label, canonicalize_body(body)))
    return rows


def first_pass(rows: list[tuple[str | None, str]]) -> tuple[dict[str, int], int]:
    symbols: dict[str, int] = {}
    pc = 0
    origin = 0
    for label, body in rows:
        if label and body.startswith(".EQ"):
            symbols[label] = eval_expr(first_expr(body[3:].strip()), symbols)
            continue
        if body.startswith(".OR"):
            pc = eval_expr(body[3:].strip(), symbols)
            origin = pc
        if label and body.startswith(".OR"):
            symbols[label] = pc
            continue
        if label:
            symbols[label] = pc
        if not body:
            continue
        if body.startswith("."):
            directive, _, rest = body.partition(" ")
            if directive == ".DA":
                pc += 2
            continue
        mnemonic, _, operand = body.partition(" ")
        pc += instr_size(detect_mode_first_pass(mnemonic.upper(), operand, symbols))
    return symbols, origin


def second_pass(rows: list[tuple[str | None, str]], symbols: dict[str, int], origin: int) -> bytes:
    pc = origin
    out = bytearray()
    for label, body in rows:
        if label and body.startswith(".EQ"):
            continue
        if body.startswith(".OR"):
            pc = eval_expr(body[3:].strip(), symbols)
            continue
        if not body:
            continue
        if body.startswith("."):
            directive, _, rest = body.partition(" ")
            if directive == ".DA":
                value = eval_expr(rest.strip(), symbols)
                out.extend((value & 0xFF, (value >> 8) & 0xFF))
                pc += 2
            continue
        mnemonic, _, operand = body.partition(" ")
        mnemonic = mnemonic.upper()
        mode, value = detect_mode(mnemonic, operand, symbols)
        opcode = OPCODES[(mnemonic, mode)]
        out.append(opcode)
        size = instr_size(mode)
        if mode == "imm" or mode.startswith("zp") or mode in {"indx", "indy"}:
            assert value is not None
            out.append(value & 0xFF)
        elif mode == "rel":
            assert value is not None
            offset = (value - (pc + 2)) & 0xFF
            out.append(offset)
        elif mode in {"abs", "absx", "absy", "ind"}:
            assert value is not None
            out.extend((value & 0xFF, (value >> 8) & 0xFF))
        pc += size
    return bytes(out)


def main() -> int:
    args = parse_args()
    rows = parse_source(args.source.read_text(encoding="utf-8"))
    symbols, origin = first_pass(rows)
    image = second_pass(rows, symbols, origin)
    args.output.write_bytes(image)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
