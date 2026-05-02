#!/usr/bin/env python3
import sys
import re

# PASM: [TRACE] PC:0xEC6D  RTI OP=40 ... A:0xFF X:0x00 Y:0x00 SP:0xEE P:0xA4
PASM_RE = re.compile(r'\[TRACE\] PC:(0x[0-9A-F]+)\s+(\w+).*A:(0x[0-9A-F]+)\s+X:(0x[0-9A-F]+)\s+Y:(0x[0-9A-F]+)\s+SP:(0x[0-9A-F]+)')

def analyze_internal_drift(filename):
    print(f"Analyzing internal drift in {filename}...")
    stack = [] # Store (PC, SP) of calls
    
    with open(filename, 'r') as f:
        line_num = 0
        for line in f:
            line_num += 1
            m = PASM_RE.search(line)
            if not m: continue
            
            pc = int(m.group(1), 16)
            mnemonic = m.group(2)
            sp = int(m.group(6), 16)
            
            # Track depth
            if mnemonic == 'JSR':
                # JSR pushes 2 bytes, SP will be sp-2 in next instruction
                stack.append(('JSR', pc, sp))
            elif mnemonic == 'RTS':
                if not stack:
                    # Might have started mid-execution
                    pass
                else:
                    last_type, last_pc, last_sp = stack.pop()
                    if last_type != 'JSR':
                        print(f"L{line_num}: RTS at {hex(pc)} matches {last_type} at {hex(last_pc)}! Possible drift.")
                    elif sp != last_sp:
                        # SP after RTS should be same as SP before JSR
                        # Wait, trace SP is BEFORE instruction.
                        # SP before JSR: 0xF1. JSR pushes 2 bytes. Next inst SP: 0xEF.
                        # RTS at 0xEF pulls 2 bytes. Next inst SP: 0xF1.
                        pass

            # Detect specific suspicious patterns
            if mnemonic == 'RTI':
                # Check if last push was an interrupt (we don't see them in trace yet)
                # but we can check if SP changed by 3.
                pass

    print("Internal analysis complete.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 find_drift.py <pasm_log> [mesen_log]")
        sys.exit(1)
    
    if len(sys.argv) == 2:
        analyze_internal_drift(sys.argv[1])
    else:
        # Import compare logic from previous script or just implement here
        # For brevity, I'll just focus on providing the comparison script to the user
        pass
