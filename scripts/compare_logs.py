#!/usr/bin/env python3
import sys
import re

# Mesen: FF5F  BEQ $FF5A                        A:00 X:FF Y:1A S:FF P:nv--dIZc V:0   H:87
MESEN_RE = re.compile(r'^([0-9A-F]{4})\s+(\w+)\s+.*A:([0-9A-F]{2})\s+X:([0-9A-F]{2})\s+Y:([0-9A-F]{2})\s+S:([0-9A-F]{2})\s+P:([a-zA-Z-]+)')

# PASM: [TRACE] PC:0xFF50  SEI OP=78 ... A:0x00 X:0x00 Y:0x00 SP:0xFD P:0x04
PASM_RE = re.compile(r'\[TRACE\] PC:0x([0-9A-F]{4})\s+(\w+)\s+.*A:0x([0-9A-F]{2})\s+X:0x([0-9A-F]{2})\s+Y:0x([0-9A-F]{2})\s+SP:0x([0-9A-F]{2})\s+P:0x([0-9A-F]{2})')

def parse_mesen(line):
    m = MESEN_RE.match(line)
    if not m: return None
    return {
        'pc': int(m.group(1), 16),
        'a': int(m.group(3), 16),
        'x': int(m.group(4), 16),
        'line': line.strip()
    }

def parse_pasm(line):
    m = PASM_RE.search(line)
    if not m: return None
    return {
        'pc': int(m.group(1), 16),
        'a': int(m.group(3), 16),
        'x': int(m.group(4), 16),
        'line': line.strip()
    }

def line_generator(path, parser):
    with open(path, 'r') as f:
        for line in f:
            p = parser(line)
            if p: yield p

def compare(mesen_path, pasm_path, skip=0):
    print(f"Comparing logs streamingly (skipping {skip} Mesen lines)...")
    
    m_gen = line_generator(mesen_path, parse_mesen)
    p_gen = line_generator(pasm_path, parse_pasm)
    
    # Skip initial Mesen lines
    for _ in range(skip):
        next(m_gen, None)
    
    # Auto-align: Find first PC match
    m_first = next(m_gen, None)
    if not m_first: return
    
    print(f"Searching for first PC match (0x{m_first['pc']:04X})...")
    p_curr = None
    while True:
        p_curr = next(p_gen, None)
        if not p_curr:
            print("Could not find sync point.")
            return
        if p_curr['pc'] == m_first['pc']:
            break

    print(f"Synced at PC: 0x{m_first['pc']:04X}")
    
    m_history = [m_first]
    p_history = [p_curr]
    
    idx = 1
    while True:
        m = next(m_gen, None)
        p = next(p_gen, None)
        if not m or not p: break
        
        m_history.append(m)
        p_history.append(p)
        if len(m_history) > 10: m_history.pop(0)
        if len(p_history) > 10: p_history.pop(0)
        
        if m['pc'] != p['pc'] or m['a'] != p['a'] or m['x'] != p['x']:
            print(f"\n!!! DRIFT DETECTED at instruction #{idx} !!!")
            print("Mesen history:")
            for h in m_history: print(f"  {h['line']}")
            print("\nPASM history:")
            for h in p_history: print(f"  {h['line']}")
            
            print("\nDifferences:")
            if m['pc'] != p['pc']: print(f"  - PC: Mesen=0x{m['pc']:04x} PASM=0x{p['pc']:04x}")
            if m['a'] != p['a']: print(f"  - A: Mesen=0x{m['a']:02x} PASM=0x{p['a']:02x}")
            if m['x'] != p['x']: print(f"  - X: Mesen=0x{m['x']:02x} PASM=0x{p['x']:02x}")
            return
        idx += 1

    print("Reached end of logs without finding drifts.")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: compare_logs.py <mesen_log> <pasm_log> [skip]")
        sys.exit(1)
    compare(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 0)
