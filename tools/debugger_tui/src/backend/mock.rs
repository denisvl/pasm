use crate::backend::DebuggerBackend;
use crate::state::{
    Architecture, BreakpointRow, CoreSnapshot, DebugCounts, DebuggerMode, DebuggerSnapshot,
    DisasmRow, FlagRow, HistoryRow, MemoryRow, RegisterRow, StackRow, ThreadRow,
};
use std::collections::VecDeque;

const MAX_HISTORY_ROWS: usize = 100;

pub struct MockDebuggerBackend {
    pc: u16,
    total_cycles: u64,
    running: bool,
    overlay_enabled: bool,
    breakpoints: Vec<u16>,
    fail_disassembly_window: bool,
    history: VecDeque<HistoryRow>,
}

impl MockDebuggerBackend {
    pub fn new() -> Self {
        Self {
            pc: 0,
            total_cycles: 0,
            running: false,
            overlay_enabled: true,
            breakpoints: Vec::new(),
            fail_disassembly_window: false,
            history: VecDeque::with_capacity(MAX_HISTORY_ROWS),
        }
    }

    #[cfg(test)]
    pub fn failing_disassembly_window() -> Self {
        Self {
            fail_disassembly_window: true,
            ..Self::new()
        }
    }
}

impl Default for MockDebuggerBackend {
    fn default() -> Self {
        Self::new()
    }
}

impl DebuggerBackend for MockDebuggerBackend {
    fn counts(&mut self) -> Result<DebugCounts, String> {
        Ok(DebugCounts {
            disassembly_rows: 48,
            register_rows: 8,
            flag_rows: 8,
            operand_rows: 0,
            stack_rows: 8,
            memory_rows: 8,
            call_stack_rows: 0,
            breakpoint_rows: self.breakpoints.len() as u32,
            watchpoint_rows: 0,
            thread_rows: 1,
            history_rows: self.history.len() as u32,
        })
    }

    fn snapshot(&mut self) -> Result<DebuggerSnapshot, String> {
        let mode = if self.running {
            DebuggerMode::Running
        } else {
            DebuggerMode::Paused
        };

        let mut disasm = Vec::new();
        let start = self.pc.saturating_sub(24);
        for i in 0..48u16 {
            let addr = start.wrapping_add(i);
            disasm.push(DisasmRow {
                address: u64::from(addr),
                bytes: format!("{:02X}", addr as u8),
                instruction: if addr == self.pc {
                    "NOP".to_string()
                } else {
                    "LD A,n".to_string()
                },
                is_current_ip: addr == self.pc,
                has_breakpoint: self.breakpoints.contains(&addr),
                changed: false,
            });
        }

        let regs = vec![
            RegisterRow {
                name: "AF".into(),
                hex_value: "0x0040".into(),
                dec_value: "64".into(),
                changed: false,
            },
            RegisterRow {
                name: "BC".into(),
                hex_value: "0x1000".into(),
                dec_value: "4096".into(),
                changed: false,
            },
            RegisterRow {
                name: "DE".into(),
                hex_value: "0x2000".into(),
                dec_value: "8192".into(),
                changed: false,
            },
            RegisterRow {
                name: "HL".into(),
                hex_value: "0x4000".into(),
                dec_value: "16384".into(),
                changed: false,
            },
            RegisterRow {
                name: "IX".into(),
                hex_value: "0x0000".into(),
                dec_value: "0".into(),
                changed: false,
            },
            RegisterRow {
                name: "IY".into(),
                hex_value: "0x0000".into(),
                dec_value: "0".into(),
                changed: false,
            },
            RegisterRow {
                name: "SP".into(),
                hex_value: "0xFFFE".into(),
                dec_value: "65534".into(),
                changed: false,
            },
            RegisterRow {
                name: "PC".into(),
                hex_value: format!("0x{:04X}", self.pc),
                dec_value: self.pc.to_string(),
                changed: false,
            },
        ];

        let flags = vec![
            FlagRow {
                name: "S".into(),
                value: false,
                changed: false,
            },
            FlagRow {
                name: "Z".into(),
                value: false,
                changed: false,
            },
            FlagRow {
                name: "H".into(),
                value: false,
                changed: false,
            },
            FlagRow {
                name: "P/V".into(),
                value: false,
                changed: false,
            },
            FlagRow {
                name: "N".into(),
                value: false,
                changed: false,
            },
            FlagRow {
                name: "C".into(),
                value: false,
                changed: false,
            },
        ];

        let stack = vec![
            StackRow {
                address: 0xFFFE,
                value: 0x0000,
                is_sp: true,
                changed: false,
            },
            StackRow {
                address: 0x0000,
                value: 0x0000,
                is_sp: false,
                changed: false,
            },
        ];

        let memory = vec![MemoryRow {
            address: u64::from(self.pc),
            hex_bytes: "00 3E 41 D3 FE".into(),
            ascii: "..A..".into(),
            changed: false,
        }];

        let breakpoints = self
            .breakpoints
            .iter()
            .map(|bp| BreakpointRow {
                address: u64::from(*bp),
                enabled: true,
            })
            .collect();

        let threads = vec![ThreadRow {
            thread_id: 0,
            state: if self.running { "running" } else { "paused" }.into(),
            ip: u64::from(self.pc),
            selected: true,
        }];

        Ok(DebuggerSnapshot {
            counts: self.counts()?,
            core: CoreSnapshot {
                target_name: "Z80-MOCK".into(),
                status_line: if self.running {
                    "Running".into()
                } else {
                    "Paused".into()
                },
                mode,
                architecture: Architecture::Z80,
                clock_hz: 3_500_000,
                selected_thread_id: 0,
                pc: u64::from(self.pc),
                sp: 0xFFFE,
                total_cycles: self.total_cycles,
                last_step_cycles: 4,
                tstate_global: self.total_cycles,
                tstate_frame: self.total_cycles % 69888,
                frame_index: self.total_cycles / 69888,
                interrupt_mode: 1,
                iff1: true,
                iff2: true,
            },
            disassembly: disasm,
            registers: regs,
            flags,
            operands: Vec::new(),
            stack,
            memory,
            breakpoints,
            threads,
            history: self.history.iter().cloned().collect(),
        })
    }

    fn reset(&mut self) -> Result<(), String> {
        self.pc = 0;
        self.total_cycles = 0;
        self.running = false;
        self.history.clear();
        Ok(())
    }

    fn run(&mut self) -> Result<(), String> {
        self.running = true;
        Ok(())
    }

    fn run_slice(&mut self, max_steps: u32) -> Result<DebuggerMode, String> {
        let steps = max_steps.max(1);
        for _ in 0..steps {
            if !self.running {
                break;
            }
            if self.breakpoints.contains(&self.pc) {
                self.running = false;
                break;
            }
            self.record_history_current_pc();
            self.pc = self.pc.wrapping_add(1);
            self.total_cycles += 4;
        }
        if self.running {
            Ok(DebuggerMode::Running)
        } else {
            Ok(DebuggerMode::Paused)
        }
    }

    fn run_for_cycles(&mut self, max_cycles: u64) -> Result<DebuggerMode, String> {
        let steps = (max_cycles.saturating_add(3) / 4).max(1);
        let capped = u32::try_from(steps).unwrap_or(u32::MAX);
        self.run_slice(capped)
    }

    fn pause(&mut self) -> Result<(), String> {
        self.running = false;
        Ok(())
    }

    fn step_into(&mut self) -> Result<(), String> {
        if self.running && self.breakpoints.contains(&self.pc) {
            self.running = false;
            return Ok(());
        }
        self.record_history_current_pc();
        self.pc = self.pc.wrapping_add(1);
        self.total_cycles += 4;
        Ok(())
    }

    fn step_over(&mut self) -> Result<(), String> {
        self.step_into()
    }

    fn step_out(&mut self) -> Result<(), String> {
        self.step_into()
    }

    fn toggle_breakpoint(&mut self, address: u64) -> Result<(), String> {
        let addr = (address & 0xFFFF) as u16;
        if let Some(idx) = self.breakpoints.iter().position(|v| *v == addr) {
            self.breakpoints.remove(idx);
        } else {
            self.breakpoints.push(addr);
            self.breakpoints.sort_unstable();
        }
        Ok(())
    }

    fn select_thread(&mut self, thread_id: u32) -> Result<(), String> {
        if thread_id == 0 {
            Ok(())
        } else {
            Err("mock backend only supports thread 0".into())
        }
    }

    fn jump_frame(&mut self, _frame_index: usize) -> Result<(), String> {
        Ok(())
    }

    fn read_memory(&mut self, address: u64, size: usize) -> Result<Vec<u8>, String> {
        let mut out = Vec::with_capacity(size);
        for i in 0..size {
            let byte = address.saturating_add(i as u64) as u8;
            out.push(byte);
        }
        Ok(out)
    }

    fn disassembly_window(&mut self, anchor_address: u64) -> Result<Vec<DisasmRow>, String> {
        if self.fail_disassembly_window {
            return Err("Pause execution before jumping disassembly".to_string());
        }
        let anchor = (anchor_address & 0xFFFF) as u16;
        let start = anchor.saturating_sub(24);
        let mut rows = Vec::with_capacity(64);
        for i in 0..64u16 {
            let addr = start.wrapping_add(i);
            rows.push(DisasmRow {
                address: u64::from(addr),
                bytes: format!("{:02X}", addr as u8),
                instruction: if addr == self.pc {
                    "NOP".to_string()
                } else {
                    "LD A,n".to_string()
                },
                is_current_ip: addr == self.pc,
                has_breakpoint: self.breakpoints.contains(&addr),
                changed: false,
            });
        }
        Ok(rows)
    }

    fn clear_history(&mut self) -> Result<(), String> {
        self.history.clear();
        Ok(())
    }

    fn set_overlay_enabled(&mut self, enabled: bool) -> Result<(), String> {
        self.overlay_enabled = enabled;
        Ok(())
    }

    fn overlay_enabled(&mut self) -> Result<bool, String> {
        Ok(self.overlay_enabled)
    }

    fn focus_emulator_window(&mut self) -> Result<(), String> {
        Ok(())
    }
}

impl MockDebuggerBackend {
    fn record_history_current_pc(&mut self) {
        let row = HistoryRow {
            address: u64::from(self.pc),
            instruction: "NOP".to_string(),
            effect: format!("{:02X}", self.pc as u8),
        };
        self.history.push_back(row);
        while self.history.len() > MAX_HISTORY_ROWS {
            let _ = self.history.pop_front();
        }
    }
}
