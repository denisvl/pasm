use std::ffi::c_char;

pub const PASM_DBG_RUNNING: u8 = 0;
pub const PASM_DBG_PAUSED: u8 = 1;
pub const PASM_DBG_STEPPING: u8 = 2;
pub const PASM_DBG_EXITED: u8 = 3;
pub const PASM_DBG_ERROR: u8 = 4;

pub const PASM_ARCH_Z80: u8 = 0;
pub const PASM_ARCH_MOS6502: u8 = 1;
pub const PASM_ARCH_MOS6510: u8 = 2;
pub const PASM_ARCH_MOTOROLA68000: u8 = 3;
pub const PASM_ARCH_RICOH2A03: u8 = 4;
pub const PASM_ARCH_MC6809: u8 = 5;

#[repr(C)]
pub struct CPUState {
    _opaque: [u8; 0],
}

#[repr(C)]
#[derive(Clone, Copy, Debug, Default)]
pub struct PASMDebugCounts {
    pub disassembly_rows: u32,
    pub register_rows: u32,
    pub flag_rows: u32,
    pub operand_rows: u32,
    pub stack_rows: u32,
    pub memory_rows: u32,
    pub call_stack_rows: u32,
    pub breakpoint_rows: u32,
    pub watchpoint_rows: u32,
    pub thread_rows: u32,
    pub history_rows: u32,
}

#[repr(C)]
#[derive(Clone, Copy)]
pub struct PASMDebugSnapshotCore {
    pub target_name: [c_char; 64],
    pub status_line: [c_char; 256],
    pub mode: u8,
    pub architecture: u8,
    pub system_clock_hz: u64,
    pub selected_thread_id: u32,
    pub pc: u64,
    pub sp: u64,
    pub total_cycles: u64,
    pub last_step_cycles: u64,
    pub tstate_global: u64,
    pub tstate_frame: u64,
    pub frame_index: u64,
    pub interrupt_mode: u8,
    pub iff1: u8,
    pub iff2: u8,
}

#[repr(C)]
#[derive(Clone, Copy)]
pub struct PASMDebugDisasmRow {
    pub address: u64,
    pub bytes: [c_char; 32],
    pub instruction: [c_char; 96],
    pub symbol: [c_char; 64],
    pub has_symbol: u8,
    pub is_current_ip: u8,
    pub has_breakpoint: u8,
    pub branch_target: u64,
    pub has_branch_target: u8,
    pub changed_since_last_step: u8,
}

#[repr(C)]
#[derive(Clone, Copy)]
pub struct PASMDebugRegisterRow {
    pub name: [c_char; 32],
    pub hex_value: [c_char; 32],
    pub dec_value: [c_char; 32],
    pub has_dec: u8,
    pub changed: u8,
}

#[repr(C)]
#[derive(Clone, Copy)]
pub struct PASMDebugFlagRow {
    pub name: [c_char; 16],
    pub value: u8,
    pub changed: u8,
}

#[repr(C)]
#[derive(Clone, Copy)]
pub struct PASMDebugOperandRow {
    pub expression: [c_char; 96],
    pub resolved: [c_char; 96],
    pub changed: u8,
}

#[repr(C)]
#[derive(Clone, Copy)]
pub struct PASMDebugStackRow {
    pub address: u64,
    pub value: u64,
    pub annotation: [c_char; 64],
    pub has_annotation: u8,
    pub is_sp: u8,
    pub changed: u8,
}

#[repr(C)]
#[derive(Clone, Copy)]
pub struct PASMDebugMemoryRow {
    pub address: u64,
    pub hex_bytes: [c_char; 64],
    pub ascii: [c_char; 17],
    pub changed: u8,
}

#[repr(C)]
#[derive(Clone, Copy)]
pub struct PASMDebugCallFrameRow {
    pub index: u32,
    pub function: [c_char; 64],
    pub address: u64,
    pub source: [c_char; 96],
    pub has_source: u8,
    pub selected: u8,
}

#[repr(C)]
#[derive(Clone, Copy)]
pub struct PASMDebugBreakpointRow {
    pub address: u64,
    pub enabled: u8,
    pub condition: [c_char; 96],
    pub has_condition: u8,
    pub hit_count: u64,
}

#[repr(C)]
#[derive(Clone, Copy)]
pub struct PASMDebugWatchpointRow {
    pub expression: [c_char; 96],
    pub access: [c_char; 16],
    pub enabled: u8,
}

#[repr(C)]
#[derive(Clone, Copy)]
pub struct PASMDebugThreadRow {
    pub thread_id: u32,
    pub state: [c_char; 16],
    pub ip: u64,
    pub selected: u8,
}

#[repr(C)]
#[derive(Clone, Copy)]
pub struct PASMDebugHistoryRow {
    pub address: u64,
    pub instruction: [c_char; 96],
    pub effect: [c_char; 128],
}
