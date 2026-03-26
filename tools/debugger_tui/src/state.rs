#![allow(dead_code)]

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Architecture {
    Z80,
    Mc6809,
    Mos6502,
    Mos6510,
    Motorola68000,
    Ricoh2A03,
    Unknown,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum DebuggerMode {
    Running,
    Paused,
    Stepping,
    Exited,
    Error,
}

#[derive(Clone, Debug, Default)]
pub struct DebugCounts {
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

#[derive(Clone, Debug, Default)]
pub struct CoreSnapshot {
    pub target_name: String,
    pub status_line: String,
    pub mode: DebuggerMode,
    pub architecture: Architecture,
    pub clock_hz: u64,
    pub selected_thread_id: u32,
    pub pc: u64,
    pub sp: u64,
    pub total_cycles: u64,
    pub last_step_cycles: u64,
    pub tstate_global: u64,
    pub tstate_frame: u64,
    pub frame_index: u64,
    pub interrupt_mode: u8,
    pub iff1: bool,
    pub iff2: bool,
}

#[derive(Clone, Debug, Default)]
pub struct DisasmRow {
    pub address: u64,
    pub bytes: String,
    pub instruction: String,
    pub is_current_ip: bool,
    pub has_breakpoint: bool,
    pub changed: bool,
}

#[derive(Clone, Debug, Default)]
pub struct RegisterRow {
    pub name: String,
    pub hex_value: String,
    pub dec_value: String,
    pub changed: bool,
}

#[derive(Clone, Debug, Default)]
pub struct FlagRow {
    pub name: String,
    pub value: bool,
    pub changed: bool,
}

#[derive(Clone, Debug, Default)]
pub struct OperandRow {
    pub expression: String,
    pub resolved: String,
    pub changed: bool,
}

#[derive(Clone, Debug, Default)]
pub struct StackRow {
    pub address: u64,
    pub value: u64,
    pub is_sp: bool,
    pub changed: bool,
}

#[derive(Clone, Debug, Default)]
pub struct MemoryRow {
    pub address: u64,
    pub hex_bytes: String,
    pub ascii: String,
    pub changed: bool,
}

#[derive(Clone, Debug, Default)]
pub struct BreakpointRow {
    pub address: u64,
    pub enabled: bool,
}

#[derive(Clone, Debug, Default)]
pub struct ThreadRow {
    pub thread_id: u32,
    pub state: String,
    pub ip: u64,
    pub selected: bool,
}

#[derive(Clone, Debug, Default)]
pub struct HistoryRow {
    pub address: u64,
    pub instruction: String,
    pub effect: String,
}

#[derive(Clone, Debug, Default)]
pub struct DebuggerSnapshot {
    pub counts: DebugCounts,
    pub core: CoreSnapshot,
    pub disassembly: Vec<DisasmRow>,
    pub registers: Vec<RegisterRow>,
    pub flags: Vec<FlagRow>,
    pub operands: Vec<OperandRow>,
    pub stack: Vec<StackRow>,
    pub memory: Vec<MemoryRow>,
    pub breakpoints: Vec<BreakpointRow>,
    pub threads: Vec<ThreadRow>,
    pub history: Vec<HistoryRow>,
}

impl Default for DebuggerMode {
    fn default() -> Self {
        Self::Paused
    }
}

impl Default for Architecture {
    fn default() -> Self {
        Self::Unknown
    }
}
