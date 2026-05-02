#!/usr/bin/env python3
import sys
import re

# Mesen: FF5F  BEQ $FF5A                        A:00 X:FF Y:1A S:FF P:nv--dIZc V:0   H:87
MESEN_RE = re.compile(r'^([0-9A-F]+)\s+(\w+)\s+.*P:([a-zA-Z-]+)')

def analyze_mesen_cycles(filename):
    print(f"Analyzing potential cycle drift in {filename}...")
    total_missing_cycles = 0
    instruction_count = 0
    branches_taken = 0
    
    with open(filename, 'r') as f:
        last_pc = None
        for line in f:
            m = MESEN_RE.match(line)
            if not m: continue
            
            pc = int(m.group(1), 16)
            mnemonic = m.group(2)
            
            if last_pc is not None:
                # Check if it was a branch
                # This is simplified: we check if the instruction at last_pc was a branch
                pass
            
            # Better: just look for branch mnemonics and check if PC jumped
            # But we need the instruction AT that line.
            
            instruction_count += 1
            if mnemonic in ['BPL', 'BMI', 'BVC', 'BVS', 'BCC', 'BCS', 'BNE', 'BEQ']:
                # We'll need the next line's PC to see if it was taken
                # Or just use the fact that branches are 2 bytes long
                pass
                
            last_pc = pc

    print("Analysis complete.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 analyze_cycles.py <mesen_log>")
        sys.exit(1)
    analyze_mesen_cycles(sys.argv[1])
