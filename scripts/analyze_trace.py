#!/usr/bin/env python3
import sys
import re

def analyze_trace(filename):
    # Trace format patterns
    trace_re = re.compile(r'\[TRACE\] PC:(0x[0-9A-F]+)\s+(\w+).*SP:(0x[0-9A-F]+)\s+P:(0x[0-9A-F]+)')
    # Mesen-like format: EAC3  LDA $EB = $00                    A:00 X:00 Y:1A S:FB P:nv--dIZc V:83  H:108
    mesen_re = re.compile(r'^([0-9A-F]{4})\s+(\w+).*A:([0-9A-F]{2})\s+X:([0-9A-F]{2})\s+Y:([0-9A-F]{2})\s+S:([0-9A-F]{2})')

    history = []
    rti_count = 0
    
    print(f"Analyzing {filename}...")
    
    with open(filename, 'r') as f:
        for line in f:
            match = trace_re.search(line)
            is_mesen = False
            if not match:
                match = mesen_re.match(line)
                is_mesen = True
            
            if match:
                if not is_mesen:
                    pc_str, mnemonic, sp_str, p_str = match.groups()
                    pc = int(pc_str, 16)
                    sp = int(sp_str, 16)
                else:
                    pc_str, mnemonic, a, x, y, sp_str = match.groups()
                    pc = int(pc_str, 16)
                    sp = int(sp_str, 16)
                
                entry = {
                    'pc': pc,
                    'pc_str': pc_str if pc_str.startswith('0x') else f"0x{pc_str}",
                    'mnemonic': mnemonic,
                    'sp': sp,
                    'line': line.strip()
                }
                
                # Check for JSR that would push 852D (JSR at 852B)
                if mnemonic == 'JSR' and pc == 0x852B:
                    print(f"\n[INFO] JSR at 0x852B found. Pushing return address 0x852D to stack (SP={hex(sp)})")
                
                # Check for RTI
                if mnemonic == 'RTI':
                    rti_count += 1
                    # Look ahead for the return address
                    try:
                        next_line = next(f)
                        # Skip blank or non-trace lines
                        while next_line and not (trace_re.search(next_line) or mesen_re.match(next_line)):
                            next_line = next(f)
                        
                        next_match = trace_re.search(next_line) or mesen_re.match(next_line)
                        if next_match:
                            ret_pc_str = next_match.group(1)
                            ret_pc = int(ret_pc_str, 16)
                            
                            if ret_pc == 0x852D:
                                print(f"\n!!! FOUND RTI AT {hex(pc)} RETURNING TO 0x852D !!!")
                                print("Context (Last 5 instructions):")
                                for h in history[-5:]:
                                    print(f"  {h['line']}")
                                print(f"  {line.strip()}")
                                print(f"  {next_line.strip()}")
                                
                                # Analyze stack shift
                                if any(h['mnemonic'] == 'PLP' for h in history[-3:]):
                                    print("CRITICAL: PLP found immediately before RTI. This shifted the stack!")
                                    print("On MOS6502, RTI pulls P, then PC. If you manually PLP before RTI, RTI pulls the original PCL as its P, and PCH as its PCL.")
                    except StopIteration:
                        break
                
                history.append(entry)
                if len(history) > 100:
                    history.pop(0)

    print(f"\nAnalysis complete. Found {rti_count} RTI instructions.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 analyze_trace.py <trace_file>")
        sys.exit(1)
    analyze_trace(sys.argv[1])
