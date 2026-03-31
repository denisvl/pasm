use std::ffi::{c_char, c_int, c_uchar, c_uint, c_ulonglong, CString};

use crate::backend::ffi_types::*;
use crate::backend::DebuggerBackend;
use crate::state::{
    Architecture, BreakpointRow, CoreSnapshot, DebugCounts, DebuggerMode, DebuggerSnapshot,
    DisasmRow, FlagRow, HistoryRow, MemoryRow, OperandRow, RegisterRow, StackRow, ThreadRow,
};

#[allow(dead_code)]
unsafe extern "C" {
    fn pasm_dbg_create(memory_size: usize) -> *mut CPUState;
    fn pasm_dbg_destroy(cpu: *mut CPUState);
    fn pasm_dbg_reset(cpu: *mut CPUState);
    fn pasm_dbg_clear_memory(cpu: *mut CPUState) -> c_int;
    fn pasm_dbg_load_system_roms(cpu: *mut CPUState, system_base_dir: *const c_char) -> c_int;
    fn pasm_dbg_load_cartridge_rom(cpu: *mut CPUState, path: *const c_char) -> c_int;
    fn pasm_dbg_load_keyboard_map(cpu: *mut CPUState, path: *const c_char) -> c_int;
    fn pasm_dbg_requires_keyboard_map() -> c_uchar;
    fn pasm_dbg_snapshot_counts(cpu: *mut CPUState, out_counts: *mut PASMDebugCounts) -> c_int;
    fn pasm_dbg_snapshot_fill(
        cpu: *mut CPUState,
        out_core: *mut PASMDebugSnapshotCore,
        disasm_rows: *mut PASMDebugDisasmRow,
        disasm_cap: usize,
        reg_rows: *mut PASMDebugRegisterRow,
        reg_cap: usize,
        flag_rows: *mut PASMDebugFlagRow,
        flag_cap: usize,
        operand_rows: *mut PASMDebugOperandRow,
        operand_cap: usize,
        stack_rows: *mut PASMDebugStackRow,
        stack_cap: usize,
        mem_rows: *mut PASMDebugMemoryRow,
        mem_cap: usize,
        call_rows: *mut PASMDebugCallFrameRow,
        call_cap: usize,
        bp_rows: *mut PASMDebugBreakpointRow,
        bp_cap: usize,
        wp_rows: *mut PASMDebugWatchpointRow,
        wp_cap: usize,
        thread_rows: *mut PASMDebugThreadRow,
        thread_cap: usize,
        hist_rows: *mut PASMDebugHistoryRow,
        hist_cap: usize,
    ) -> c_int;
    fn pasm_dbg_run(cpu: *mut CPUState) -> c_int;
    fn pasm_dbg_run_slice(cpu: *mut CPUState, max_steps: c_uint, out_mode: *mut c_uchar) -> c_int;
    fn pasm_dbg_run_for_cycles(
        cpu: *mut CPUState,
        max_cycles: c_ulonglong,
        out_mode: *mut c_uchar,
    ) -> c_int;
    fn pasm_dbg_pause(cpu: *mut CPUState) -> c_int;
    fn pasm_dbg_step_into(cpu: *mut CPUState) -> c_int;
    fn pasm_dbg_step_over(cpu: *mut CPUState) -> c_int;
    fn pasm_dbg_step_out(cpu: *mut CPUState) -> c_int;
    fn pasm_dbg_toggle_breakpoint(cpu: *mut CPUState, address: c_ulonglong) -> c_int;
    fn pasm_dbg_select_thread(cpu: *mut CPUState, thread_id: c_uint) -> c_int;
    fn pasm_dbg_jump_frame(cpu: *mut CPUState, frame_index: usize) -> c_int;
    fn pasm_dbg_read_memory(
        cpu: *mut CPUState,
        address: c_ulonglong,
        out: *mut c_uchar,
        size: usize,
    ) -> c_int;
    fn pasm_dbg_clear_history(cpu: *mut CPUState) -> c_int;
    fn pasm_dbg_set_pc(cpu: *mut CPUState, address: c_ulonglong) -> c_int;
    fn pasm_dbg_set_overlay_enabled(cpu: *mut CPUState, enabled: c_uchar) -> c_int;
    fn pasm_dbg_get_overlay_enabled(cpu: *mut CPUState, out_enabled: *mut c_uchar) -> c_int;
    fn pasm_dbg_focus_host_window(cpu: *mut CPUState) -> c_int;
}

pub struct LinkedEmulatorBackend {
    cpu: *mut CPUState,
    start_pc: Option<u64>,
    system_dir: Option<String>,
    cart_rom: Option<String>,
    keyboard_map: Option<String>,
}

impl LinkedEmulatorBackend {
    pub fn new(
        memory_size: usize,
        system_dir: Option<&str>,
        cart_rom: Option<&str>,
        keyboard_map: Option<&str>,
        start_pc: Option<u64>,
    ) -> Result<Self, String> {
        // SAFETY: FFI constructor from generated emulator.
        let cpu = unsafe { pasm_dbg_create(memory_size) };
        if cpu.is_null() {
            return Err("pasm_dbg_create returned null".into());
        }
        let backend = Self {
            cpu,
            start_pc,
            system_dir: system_dir.map(ToOwned::to_owned),
            cart_rom: cart_rom.map(ToOwned::to_owned),
            keyboard_map: keyboard_map.map(ToOwned::to_owned),
        };
        if let Some(dir) = system_dir {
            let c_dir = CString::new(dir).map_err(|_| "invalid system path")?;
            let rc = unsafe { pasm_dbg_load_system_roms(backend.cpu, c_dir.as_ptr()) };
            if rc != 0 {
                return Err(format!(
                    "failed to load system ROMs from '{dir}' (code {rc}). \
ROM paths are resolved relative to --system-dir. \
Use the directory that contains your system YAML (for example: examples/systems)."
                ));
            }
        }
        if let Some(path) = cart_rom {
            let c_path = CString::new(path).map_err(|_| "invalid cartridge ROM path")?;
            let rc = unsafe { pasm_dbg_load_cartridge_rom(backend.cpu, c_path.as_ptr()) };
            if rc != 0 {
                return Err(format!(
                    "failed to load cartridge ROM from '{path}' (code {rc})"
                ));
            }
        }
        let keyboard_required = unsafe { pasm_dbg_requires_keyboard_map() } != 0;
        if keyboard_required && keyboard_map.is_none() {
            return Err("missing required --keyboard-map <file>".to_string());
        }
        if let Some(path) = keyboard_map {
            let c_path = CString::new(path).map_err(|_| "invalid keyboard map path")?;
            let rc = unsafe { pasm_dbg_load_keyboard_map(backend.cpu, c_path.as_ptr()) };
            if rc != 0 {
                return Err(format!(
                    "failed to load keyboard map from '{path}' (code {rc})"
                ));
            }
        }
        if system_dir.is_some() || cart_rom.is_some() || keyboard_map.is_some() {
            unsafe { pasm_dbg_reset(backend.cpu) };
        }
        if let Some(pc) = start_pc {
            let rc = unsafe { pasm_dbg_set_pc(backend.cpu, pc) };
            if rc != 0 {
                return Err(format!("failed to set start PC to 0x{pc:04X} (code {rc})"));
            }
        }
        let rc = unsafe { pasm_dbg_pause(backend.cpu) };
        if rc != 0 {
            return Err(format!("failed to enter initial paused state (code {rc})"));
        }
        Ok(backend)
    }

    fn check(&self, code: c_int) -> Result<(), String> {
        if code == 0 {
            Ok(())
        } else {
            Err(format!("debug ABI returned error code {code}"))
        }
    }

    fn c_text(buf: &[c_char]) -> String {
        let mut out = Vec::new();
        for &ch in buf {
            if ch == 0 {
                break;
            }
            out.push(ch as u8);
        }
        String::from_utf8_lossy(&out).to_string()
    }

    fn map_mode(mode: u8) -> DebuggerMode {
        match mode {
            PASM_DBG_RUNNING => DebuggerMode::Running,
            PASM_DBG_PAUSED => DebuggerMode::Paused,
            PASM_DBG_STEPPING => DebuggerMode::Stepping,
            PASM_DBG_EXITED => DebuggerMode::Exited,
            PASM_DBG_ERROR => DebuggerMode::Error,
            _ => DebuggerMode::Error,
        }
    }

    fn map_arch(arch: u8) -> Architecture {
        match arch {
            PASM_ARCH_Z80 => Architecture::Z80,
            PASM_ARCH_MC6809 => Architecture::Mc6809,
            PASM_ARCH_MOS6502 => Architecture::Mos6502,
            PASM_ARCH_MOS6510 => Architecture::Mos6510,
            PASM_ARCH_MOTOROLA68000 => Architecture::Motorola68000,
            PASM_ARCH_RICOH2A03 => Architecture::Ricoh2A03,
            _ => Architecture::Unknown,
        }
    }
}

impl Drop for LinkedEmulatorBackend {
    fn drop(&mut self) {
        if !self.cpu.is_null() {
            // SAFETY: CPU pointer was created by pasm_dbg_create and is owned by this type.
            unsafe { pasm_dbg_destroy(self.cpu) };
            self.cpu = std::ptr::null_mut();
        }
    }
}

impl DebuggerBackend for LinkedEmulatorBackend {
    fn counts(&mut self) -> Result<DebugCounts, String> {
        let mut raw = PASMDebugCounts::default();
        self.check(unsafe { pasm_dbg_snapshot_counts(self.cpu, &mut raw) })?;
        Ok(DebugCounts {
            disassembly_rows: raw.disassembly_rows,
            register_rows: raw.register_rows,
            flag_rows: raw.flag_rows,
            operand_rows: raw.operand_rows,
            stack_rows: raw.stack_rows,
            memory_rows: raw.memory_rows,
            call_stack_rows: raw.call_stack_rows,
            breakpoint_rows: raw.breakpoint_rows,
            watchpoint_rows: raw.watchpoint_rows,
            thread_rows: raw.thread_rows,
            history_rows: raw.history_rows,
        })
    }

    fn snapshot(&mut self) -> Result<DebuggerSnapshot, String> {
        let counts = self.counts()?;
        let mut core: PASMDebugSnapshotCore = unsafe { std::mem::zeroed() };

        let mut disasm: Vec<PASMDebugDisasmRow> = (0..counts.disassembly_rows)
            .map(|_| unsafe { std::mem::zeroed() })
            .collect();
        let mut regs: Vec<PASMDebugRegisterRow> = (0..counts.register_rows)
            .map(|_| unsafe { std::mem::zeroed() })
            .collect();
        let mut flags: Vec<PASMDebugFlagRow> = (0..counts.flag_rows)
            .map(|_| unsafe { std::mem::zeroed() })
            .collect();
        let mut operands: Vec<PASMDebugOperandRow> = (0..counts.operand_rows)
            .map(|_| unsafe { std::mem::zeroed() })
            .collect();
        let mut stack: Vec<PASMDebugStackRow> = (0..counts.stack_rows)
            .map(|_| unsafe { std::mem::zeroed() })
            .collect();
        let mut mem: Vec<PASMDebugMemoryRow> = (0..counts.memory_rows)
            .map(|_| unsafe { std::mem::zeroed() })
            .collect();
        let mut calls: Vec<PASMDebugCallFrameRow> = (0..counts.call_stack_rows)
            .map(|_| unsafe { std::mem::zeroed() })
            .collect();
        let mut bps: Vec<PASMDebugBreakpointRow> = (0..counts.breakpoint_rows)
            .map(|_| unsafe { std::mem::zeroed() })
            .collect();
        let mut wps: Vec<PASMDebugWatchpointRow> = (0..counts.watchpoint_rows)
            .map(|_| unsafe { std::mem::zeroed() })
            .collect();
        let mut threads: Vec<PASMDebugThreadRow> = (0..counts.thread_rows)
            .map(|_| unsafe { std::mem::zeroed() })
            .collect();
        let mut history: Vec<PASMDebugHistoryRow> = (0..counts.history_rows)
            .map(|_| unsafe { std::mem::zeroed() })
            .collect();

        self.check(unsafe {
            pasm_dbg_snapshot_fill(
                self.cpu,
                &mut core,
                disasm.as_mut_ptr(),
                disasm.len(),
                regs.as_mut_ptr(),
                regs.len(),
                flags.as_mut_ptr(),
                flags.len(),
                operands.as_mut_ptr(),
                operands.len(),
                stack.as_mut_ptr(),
                stack.len(),
                mem.as_mut_ptr(),
                mem.len(),
                calls.as_mut_ptr(),
                calls.len(),
                bps.as_mut_ptr(),
                bps.len(),
                wps.as_mut_ptr(),
                wps.len(),
                threads.as_mut_ptr(),
                threads.len(),
                history.as_mut_ptr(),
                history.len(),
            )
        })?;

        Ok(DebuggerSnapshot {
            counts,
            core: CoreSnapshot {
                target_name: Self::c_text(&core.target_name),
                status_line: Self::c_text(&core.status_line),
                mode: Self::map_mode(core.mode),
                architecture: Self::map_arch(core.architecture),
                clock_hz: core.system_clock_hz,
                selected_thread_id: core.selected_thread_id,
                pc: core.pc,
                sp: core.sp,
                total_cycles: core.total_cycles,
                last_step_cycles: core.last_step_cycles,
                tstate_global: core.tstate_global,
                tstate_frame: core.tstate_frame,
                frame_index: core.frame_index,
                interrupt_mode: core.interrupt_mode,
                iff1: core.iff1 != 0,
                iff2: core.iff2 != 0,
            },
            disassembly: disasm
                .iter()
                .map(|r| DisasmRow {
                    address: r.address,
                    bytes: Self::c_text(&r.bytes),
                    instruction: Self::c_text(&r.instruction),
                    is_current_ip: r.is_current_ip != 0,
                    has_breakpoint: r.has_breakpoint != 0,
                    changed: r.changed_since_last_step != 0,
                })
                .collect(),
            registers: regs
                .iter()
                .map(|r| RegisterRow {
                    name: Self::c_text(&r.name),
                    hex_value: Self::c_text(&r.hex_value),
                    dec_value: Self::c_text(&r.dec_value),
                    changed: r.changed != 0,
                })
                .collect(),
            flags: flags
                .iter()
                .map(|r| FlagRow {
                    name: Self::c_text(&r.name),
                    value: r.value != 0,
                    changed: r.changed != 0,
                })
                .collect(),
            operands: operands
                .iter()
                .map(|r| OperandRow {
                    expression: Self::c_text(&r.expression),
                    resolved: Self::c_text(&r.resolved),
                    changed: r.changed != 0,
                })
                .collect(),
            stack: stack
                .iter()
                .map(|r| StackRow {
                    address: r.address,
                    value: r.value,
                    is_sp: r.is_sp != 0,
                    changed: r.changed != 0,
                })
                .collect(),
            memory: mem
                .iter()
                .map(|r| MemoryRow {
                    address: r.address,
                    hex_bytes: Self::c_text(&r.hex_bytes),
                    ascii: Self::c_text(&r.ascii),
                    changed: r.changed != 0,
                })
                .collect(),
            breakpoints: bps
                .iter()
                .map(|r| BreakpointRow {
                    address: r.address,
                    enabled: r.enabled != 0,
                })
                .collect(),
            threads: threads
                .iter()
                .map(|r| ThreadRow {
                    thread_id: r.thread_id,
                    state: Self::c_text(&r.state),
                    ip: r.ip,
                    selected: r.selected != 0,
                })
                .collect(),
            history: history
                .iter()
                .map(|r| HistoryRow {
                    address: r.address,
                    instruction: Self::c_text(&r.instruction),
                    effect: Self::c_text(&r.effect),
                })
                .collect(),
        })
    }

    fn run(&mut self) -> Result<(), String> {
        self.check(unsafe { pasm_dbg_run(self.cpu) })
    }

    fn run_slice(&mut self, max_steps: u32) -> Result<DebuggerMode, String> {
        let mut mode: c_uchar = PASM_DBG_ERROR;
        let steps = if max_steps == 0 { 1 } else { max_steps };
        self.check(unsafe { pasm_dbg_run_slice(self.cpu, steps, &mut mode as *mut c_uchar) })?;
        Ok(Self::map_mode(mode))
    }

    fn run_for_cycles(&mut self, max_cycles: u64) -> Result<DebuggerMode, String> {
        let mut mode: c_uchar = PASM_DBG_ERROR;
        let cycles = if max_cycles == 0 { 1 } else { max_cycles };
        self.check(unsafe {
            pasm_dbg_run_for_cycles(self.cpu, cycles, &mut mode as *mut c_uchar)
        })?;
        Ok(Self::map_mode(mode))
    }

    fn reset(&mut self) -> Result<(), String> {
        unsafe { pasm_dbg_reset(self.cpu) };
        self.check(unsafe { pasm_dbg_clear_memory(self.cpu) })?;
        if let Some(dir) = self.system_dir.as_deref() {
            let c_dir = CString::new(dir).map_err(|_| "invalid system path")?;
            let rc = unsafe { pasm_dbg_load_system_roms(self.cpu, c_dir.as_ptr()) };
            if rc != 0 {
                return Err(format!(
                    "failed to reload system ROMs from '{dir}' during reset (code {rc})"
                ));
            }
        }
        if let Some(path) = self.cart_rom.as_deref() {
            let c_path = CString::new(path).map_err(|_| "invalid cartridge ROM path")?;
            let rc = unsafe { pasm_dbg_load_cartridge_rom(self.cpu, c_path.as_ptr()) };
            if rc != 0 {
                return Err(format!(
                    "failed to reload cartridge ROM from '{path}' during reset (code {rc})"
                ));
            }
        }
        let keyboard_required = unsafe { pasm_dbg_requires_keyboard_map() } != 0;
        if keyboard_required && self.keyboard_map.is_none() {
            return Err("missing required --keyboard-map <file>".to_string());
        }
        if let Some(path) = self.keyboard_map.as_deref() {
            let c_path = CString::new(path).map_err(|_| "invalid keyboard map path")?;
            let rc = unsafe { pasm_dbg_load_keyboard_map(self.cpu, c_path.as_ptr()) };
            if rc != 0 {
                return Err(format!(
                    "failed to reload keyboard map from '{path}' during reset (code {rc})"
                ));
            }
        }
        if self.system_dir.is_some() || self.cart_rom.is_some() || self.keyboard_map.is_some() {
            unsafe { pasm_dbg_reset(self.cpu) };
        }
        if let Some(pc) = self.start_pc {
            self.check(unsafe { pasm_dbg_set_pc(self.cpu, pc) })?;
        }
        self.check(unsafe { pasm_dbg_pause(self.cpu) })
    }

    fn pause(&mut self) -> Result<(), String> {
        self.check(unsafe { pasm_dbg_pause(self.cpu) })
    }

    fn step_into(&mut self) -> Result<(), String> {
        self.check(unsafe { pasm_dbg_step_into(self.cpu) })
    }

    fn step_over(&mut self) -> Result<(), String> {
        self.check(unsafe { pasm_dbg_step_over(self.cpu) })
    }

    fn step_out(&mut self) -> Result<(), String> {
        self.check(unsafe { pasm_dbg_step_out(self.cpu) })
    }

    fn toggle_breakpoint(&mut self, address: u64) -> Result<(), String> {
        self.check(unsafe { pasm_dbg_toggle_breakpoint(self.cpu, address) })
    }

    fn select_thread(&mut self, thread_id: u32) -> Result<(), String> {
        self.check(unsafe { pasm_dbg_select_thread(self.cpu, thread_id) })
    }

    fn jump_frame(&mut self, frame_index: usize) -> Result<(), String> {
        self.check(unsafe { pasm_dbg_jump_frame(self.cpu, frame_index) })
    }

    fn read_memory(&mut self, address: u64, size: usize) -> Result<Vec<u8>, String> {
        let mut out = vec![0u8; size];
        self.check(unsafe { pasm_dbg_read_memory(self.cpu, address, out.as_mut_ptr(), size) })?;
        Ok(out)
    }

    fn disassembly_window(&mut self, anchor_address: u64) -> Result<Vec<DisasmRow>, String> {
        let current = self.snapshot()?;
        if current.core.mode == DebuggerMode::Running {
            return Err("Pause execution before jumping disassembly".to_string());
        }
        if current.disassembly.is_empty() {
            return Ok(current.disassembly);
        }
        if current
            .disassembly
            .iter()
            .any(|row| row.address == anchor_address)
        {
            return Ok(current.disassembly);
        }

        let saved_pc = current.core.pc;
        self.check(unsafe { pasm_dbg_set_pc(self.cpu, anchor_address) })?;
        let peek = self.snapshot();
        let _ = unsafe { pasm_dbg_set_pc(self.cpu, saved_pc) };
        let mut rows = peek?.disassembly;
        for row in &mut rows {
            row.is_current_ip = row.address == saved_pc;
        }
        Ok(rows)
    }

    fn clear_history(&mut self) -> Result<(), String> {
        self.check(unsafe { pasm_dbg_clear_history(self.cpu) })
    }

    fn set_overlay_enabled(&mut self, enabled: bool) -> Result<(), String> {
        let raw: c_uchar = if enabled { 1 } else { 0 };
        self.check(unsafe { pasm_dbg_set_overlay_enabled(self.cpu, raw) })
    }

    fn overlay_enabled(&mut self) -> Result<bool, String> {
        let mut enabled: c_uchar = 0;
        self.check(unsafe {
            pasm_dbg_get_overlay_enabled(self.cpu, &mut enabled as *mut c_uchar)
        })?;
        Ok(enabled != 0)
    }

    fn focus_emulator_window(&mut self) -> Result<(), String> {
        self.check(unsafe { pasm_dbg_focus_host_window(self.cpu) })
    }
}
