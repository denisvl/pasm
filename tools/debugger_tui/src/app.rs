use crate::actions::Action;
use crate::backend::DebuggerBackend;
use crate::state::{DebuggerMode, DebuggerSnapshot, DisasmRow, MemoryRow};
use crossterm::event::{KeyCode, KeyEvent};
use std::collections::VecDeque;
use std::path::Path;
use std::time::Duration;

const MEMORY_BYTES_PER_ROW: u64 = 16;
const MEMORY_WINDOW_ROWS: usize = 64;
const MAX_HISTORY_ROWS: usize = 100;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Pane {
    Disassembly,
    History,
    Registers,
    Memory,
    Stack,
    Flags,
    Breakpoints,
    Threads,
}

const PANES_WITHOUT_HISTORY: [Pane; 7] = [
    Pane::Disassembly,
    Pane::Memory,
    Pane::Registers,
    Pane::Flags,
    Pane::Breakpoints,
    Pane::Stack,
    Pane::Threads,
];

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum RunSpeedMode {
    Realtime,
    Max,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum JumpTarget {
    Disassembly,
    Memory,
}

#[derive(Clone, Debug)]
pub struct JumpDialog {
    pub active: bool,
    pub target: JumpTarget,
    pub input: String,
}

impl Default for JumpDialog {
    fn default() -> Self {
        Self {
            active: false,
            target: JumpTarget::Disassembly,
            input: String::new(),
        }
    }
}

impl Pane {
    fn all() -> &'static [Pane] {
        &[
            Pane::Disassembly,
            Pane::History,
            Pane::Memory,
            Pane::Registers,
            Pane::Flags,
            Pane::Breakpoints,
            Pane::Stack,
            Pane::Threads,
        ]
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ExecutedHistoryRow {
    pub address: u64,
    pub opcode: String,
    pub mnemonic: String,
}

pub struct App {
    pub backend: Box<dyn DebuggerBackend>,
    pub snapshot: DebuggerSnapshot,
    pub should_quit: bool,
    pub focused_pane: Pane,
    pub scroll: u16,
    pub run_steps_per_tick: usize,
    pub disasm_rows: Vec<DisasmRow>,
    pub disasm_selected_index: usize,
    pub memory_cursor_address: u64,
    pub memory_window_base_address: u64,
    pub memory_rows: Vec<MemoryRow>,
    pub show_instruction_info: bool,
    pub show_history: bool,
    pub execution_history: VecDeque<ExecutedHistoryRow>,
    pub history_scroll: usize,
    pub last_message: Option<String>,
    pub follow_pc: bool,
    pub run_speed_mode: RunSpeedMode,
    pub realtime_cycle_carry_nanos: u128,
    pub jump_dialog: JumpDialog,
    pub run_to_target_address: Option<u64>,
    pub run_to_temp_breakpoint: bool,
}

impl App {
    pub fn new(mut backend: Box<dyn DebuggerBackend>) -> Result<Self, String> {
        backend.set_overlay_enabled(false)?;
        let snapshot = backend.snapshot()?;
        let memory_cursor_address = snapshot
            .memory
            .first()
            .map(|r| r.address)
            .unwrap_or(snapshot.core.pc);
        let memory_window_base_address = Self::align_memory_address(memory_cursor_address);
        let mut app = Self {
            backend,
            snapshot,
            should_quit: false,
            focused_pane: Pane::Disassembly,
            scroll: 0,
            run_steps_per_tick: 50000,
            disasm_rows: Vec::new(),
            disasm_selected_index: 0,
            memory_cursor_address,
            memory_window_base_address,
            memory_rows: Vec::new(),
            show_instruction_info: false,
            show_history: false,
            execution_history: VecDeque::with_capacity(MAX_HISTORY_ROWS),
            history_scroll: 0,
            last_message: None,
            follow_pc: true,
            run_speed_mode: RunSpeedMode::Realtime,
            realtime_cycle_carry_nanos: 0,
            jump_dialog: JumpDialog::default(),
            run_to_target_address: None,
            run_to_temp_breakpoint: false,
        };
        app.disasm_rows = app.snapshot.disassembly.clone();
        if let Some(ip_idx) = app.disasm_rows.iter().position(|r| r.is_current_ip) {
            app.disasm_selected_index = ip_idx;
        }
        app.refresh_memory_window()?;
        Ok(app)
    }

    pub fn handle_key_event(&mut self, key: KeyEvent) -> Result<bool, String> {
        if self.jump_dialog.active {
            match key.code {
                KeyCode::Esc => {
                    self.jump_dialog.active = false;
                    self.last_message = Some("Jump cancelled".to_string());
                }
                KeyCode::Enter => {
                    self.apply_jump_dialog();
                }
                KeyCode::Backspace => {
                    self.jump_dialog.input.pop();
                }
                KeyCode::Char(ch)
                    if ch.is_ascii_hexdigit()
                        || ch == 'x'
                        || ch == 'X'
                        || ch == 'h'
                        || ch == 'H'
                        || ch == '_' =>
                {
                    self.jump_dialog.input.push(ch);
                }
                _ => {}
            }
            return Ok(true);
        }
        Ok(false)
    }

    pub fn refresh(&mut self) -> Result<(), String> {
        let next = self.backend.snapshot()?;
        self.apply_snapshot(next);
        self.sync_disassembly_window()?;
        self.refresh_memory_window()?;
        self.sync_history_from_snapshot();
        Ok(())
    }

    #[allow(dead_code)]
    pub fn on_tick(&mut self) -> Result<(), String> {
        self.on_tick_with_elapsed(Duration::from_millis(100))
    }

    pub fn on_tick_with_elapsed(&mut self, elapsed: Duration) -> Result<(), String> {
        if self.snapshot.core.mode == DebuggerMode::Running {
            let mode = match self.run_speed_mode {
                RunSpeedMode::Max => {
                    let max_steps =
                        u32::try_from(self.run_steps_per_tick.max(1)).unwrap_or(u32::MAX);
                    match self.backend.run_slice(max_steps) {
                        Ok(mode) => mode,
                        Err(err) => {
                            let _ = self.backend.pause();
                            self.last_message = Some(format!("Execution paused: {err}"));
                            self.refresh()?;
                            return Ok(());
                        }
                    }
                }
                RunSpeedMode::Realtime => {
                    let cycles_to_run = self.realtime_cycle_budget(elapsed);
                    match self.backend.run_for_cycles(cycles_to_run) {
                        Ok(mode) => mode,
                        Err(err) => {
                            let _ = self.backend.pause();
                            self.last_message = Some(format!("Execution paused: {err}"));
                            self.refresh()?;
                            return Ok(());
                        }
                    }
                }
            };
            if mode != DebuggerMode::Running {
                self.refresh()?;
                let run_to_msg = self.finish_run_to_if_needed();
                if self.snapshot.core.mode == DebuggerMode::Paused {
                    self.last_message = Some(run_to_msg.unwrap_or_else(|| {
                        format!(
                            "Execution stopped at 0x{:04X}",
                            self.snapshot.core.pc as u16
                        )
                    }));
                }
            }
            return Ok(());
        }
        self.refresh()?;
        Ok(())
    }

    fn realtime_cycle_budget(&mut self, elapsed: Duration) -> u64 {
        let clock_hz = self.snapshot.core.clock_hz.max(1);
        let scaled = elapsed.as_nanos().saturating_mul(u128::from(clock_hz))
            + self.realtime_cycle_carry_nanos;
        let mut cycles_to_run = (scaled / 1_000_000_000u128) as u64;
        self.realtime_cycle_carry_nanos = scaled % 1_000_000_000u128;
        if cycles_to_run == 0 {
            cycles_to_run = 1;
        }
        // Keep UI/input responsive even on slower generated backends.
        let max_chunk = (clock_hz / 60).max(1);
        if cycles_to_run > max_chunk {
            cycles_to_run = max_chunk;
        }
        cycles_to_run
    }

    pub fn handle_action(&mut self, action: Action) -> Result<(), String> {
        match action {
            Action::Quit => {
                self.should_quit = true;
            }
            Action::Refresh => {
                self.refresh()?;
            }
            Action::Reset => {
                self.clear_run_to_state()?;
                self.follow_pc = true;
                self.realtime_cycle_carry_nanos = 0;
                self.backend.reset()?;
                self.last_message = Some("CPU reset (paused at start PC)".to_string());
                self.refresh()?;
            }
            Action::RunPause => {
                if self.snapshot.core.mode == DebuggerMode::Running {
                    self.backend.pause()?;
                    if self.run_to_target_address.is_some() {
                        self.clear_run_to_state()?;
                    }
                    self.last_message = Some("Paused".to_string());
                    self.refresh()?;
                } else {
                    self.backend.run()?;
                    self.follow_pc = true;
                    self.realtime_cycle_carry_nanos = 0;
                    self.last_message = Some("Running".to_string());
                    self.snapshot.core.mode = DebuggerMode::Running;
                    if let Some((_, rom_tail)) =
                        self.snapshot.core.status_line.split_once(" | ROM ")
                    {
                        self.snapshot.core.status_line = format!("Running | ROM {}", rom_tail);
                    } else {
                        self.snapshot.core.status_line = "Running".to_string();
                    }
                }
            }
            Action::StepInto => {
                self.follow_pc = true;
                if self.snapshot.core.mode == DebuggerMode::Running {
                    self.backend.pause()?;
                }
                let pc_before = self.snapshot.core.pc;
                let cycles_before = self.snapshot.core.total_cycles;
                self.backend.step_into()?;
                self.refresh()?;
                let pc_after = self.snapshot.core.pc;
                let cycles_after = self.snapshot.core.total_cycles;
                self.last_message = Some(Self::step_message(
                    "Step into",
                    pc_before,
                    pc_after,
                    cycles_before,
                    cycles_after,
                ));
            }
            Action::StepOver => {
                self.follow_pc = true;
                if self.snapshot.core.mode == DebuggerMode::Running {
                    self.backend.pause()?;
                }
                let pc_before = self.snapshot.core.pc;
                let cycles_before = self.snapshot.core.total_cycles;
                self.backend.step_over()?;
                self.refresh()?;
                let pc_after = self.snapshot.core.pc;
                let cycles_after = self.snapshot.core.total_cycles;
                self.last_message = Some(Self::step_message(
                    "Step over",
                    pc_before,
                    pc_after,
                    cycles_before,
                    cycles_after,
                ));
            }
            Action::StepOut => {
                self.follow_pc = true;
                if self.snapshot.core.mode == DebuggerMode::Running {
                    self.backend.pause()?;
                }
                let pc_before = self.snapshot.core.pc;
                let cycles_before = self.snapshot.core.total_cycles;
                self.backend.step_out()?;
                self.refresh()?;
                let pc_after = self.snapshot.core.pc;
                let cycles_after = self.snapshot.core.total_cycles;
                self.last_message = Some(Self::step_message(
                    "Step out",
                    pc_before,
                    pc_after,
                    cycles_before,
                    cycles_after,
                ));
            }
            Action::ToggleInstructionInfo => {
                self.show_instruction_info = !self.show_instruction_info;
                self.last_message = Some(if self.show_instruction_info {
                    "Disassembly instruction info: ON".to_string()
                } else {
                    "Disassembly instruction info: OFF".to_string()
                });
            }
            Action::ToggleHistory => {
                self.show_history = !self.show_history;
                if self.show_history {
                    self.backend.clear_history()?;
                    self.clear_history_state();
                    self.history_scroll = 0;
                    self.last_message = Some("Execution history: ON".to_string());
                } else {
                    self.backend.clear_history()?;
                    self.clear_history_state();
                    if self.focused_pane == Pane::History {
                        self.focused_pane = Pane::Disassembly;
                    }
                    self.last_message = Some("Execution history: OFF (cleared)".to_string());
                }
            }
            Action::ToggleOverlay => {
                let enabled = !self.backend.overlay_enabled()?;
                self.backend.set_overlay_enabled(enabled)?;
                self.last_message = Some(if enabled {
                    "Overlay: ON".to_string()
                } else {
                    "Overlay: OFF".to_string()
                });
            }
            Action::ToggleBreakpoint => {
                let addr = self
                    .selected_disasm_address()
                    .unwrap_or(self.snapshot.core.pc);
                self.backend.toggle_breakpoint(addr)?;
                self.last_message = Some(format!("Toggled breakpoint at 0x{addr:04X}"));
                self.refresh()?;
            }
            Action::SelectNextPane => {
                self.focused_pane = self.next_visible_pane();
            }
            Action::SelectPrevPane => {
                self.focused_pane = self.prev_visible_pane();
            }
            Action::ScrollDown => {
                if self.focused_pane == Pane::Disassembly {
                    self.follow_pc = false;
                    self.disasm_selected_index = self
                        .disasm_selected_index
                        .saturating_add(1)
                        .min(self.disasm_rows.len().saturating_sub(1));
                } else if self.focused_pane == Pane::History {
                    self.history_scroll = self
                        .history_scroll
                        .saturating_add(1)
                        .min(self.execution_history.len().saturating_sub(1));
                } else if self.focused_pane == Pane::Memory {
                    self.move_memory_cursor(1)?;
                } else {
                    self.scroll = self.scroll.saturating_add(1);
                }
            }
            Action::ScrollUp => {
                if self.focused_pane == Pane::Disassembly {
                    self.follow_pc = false;
                    self.disasm_selected_index = self.disasm_selected_index.saturating_sub(1);
                } else if self.focused_pane == Pane::History {
                    self.history_scroll = self.history_scroll.saturating_sub(1);
                } else if self.focused_pane == Pane::Memory {
                    self.move_memory_cursor(-1)?;
                } else {
                    self.scroll = self.scroll.saturating_sub(1);
                }
            }
            Action::PageDown => {
                const PAGE: usize = 16;
                if self.focused_pane == Pane::Disassembly {
                    self.follow_pc = false;
                    self.disasm_selected_index = self
                        .disasm_selected_index
                        .saturating_add(PAGE)
                        .min(self.disasm_rows.len().saturating_sub(1));
                } else if self.focused_pane == Pane::History {
                    self.history_scroll = self
                        .history_scroll
                        .saturating_add(PAGE)
                        .min(self.execution_history.len().saturating_sub(1));
                } else if self.focused_pane == Pane::Memory {
                    self.move_memory_cursor(PAGE as i64)?;
                } else {
                    self.scroll = self.scroll.saturating_add(PAGE as u16);
                }
            }
            Action::PageUp => {
                const PAGE: usize = 16;
                if self.focused_pane == Pane::Disassembly {
                    self.follow_pc = false;
                    self.disasm_selected_index = self.disasm_selected_index.saturating_sub(PAGE);
                } else if self.focused_pane == Pane::History {
                    self.history_scroll = self.history_scroll.saturating_sub(PAGE);
                } else if self.focused_pane == Pane::Memory {
                    self.move_memory_cursor(-(PAGE as i64))?;
                } else {
                    self.scroll = self.scroll.saturating_sub(PAGE as u16);
                }
            }
            Action::JumpToAddress => {
                self.open_jump_dialog();
            }
            Action::RunToCursor => {
                self.run_to_selected_address()?;
            }
            Action::Noop => {}
        }
        Ok(())
    }

    pub fn selected_disasm_address(&self) -> Option<u64> {
        self.disasm_rows
            .get(self.disasm_selected_index)
            .map(|r| r.address)
    }

    pub fn memory_selected_index(&self) -> usize {
        let offset = self
            .memory_cursor_address
            .saturating_sub(self.memory_window_base_address);
        usize::try_from(offset / MEMORY_BYTES_PER_ROW).unwrap_or(0)
    }

    fn visible_panes(&self) -> &'static [Pane] {
        if self.show_history {
            Pane::all()
        } else {
            &PANES_WITHOUT_HISTORY
        }
    }

    fn next_visible_pane(&self) -> Pane {
        let panes = self.visible_panes();
        let idx = panes
            .iter()
            .position(|pane| *pane == self.focused_pane)
            .unwrap_or(0);
        panes[(idx + 1) % panes.len()]
    }

    fn prev_visible_pane(&self) -> Pane {
        let panes = self.visible_panes();
        let idx = panes
            .iter()
            .position(|pane| *pane == self.focused_pane)
            .unwrap_or(0);
        panes[(idx + panes.len() - 1) % panes.len()]
    }

    fn instruction_mnemonic_only(instruction: &str) -> String {
        if let Some((head, _)) = instruction.split_once(" OP=") {
            return head.trim_end().to_string();
        }
        instruction.to_string()
    }

    fn history_row_from_backend_history(
        row: &crate::state::HistoryRow,
    ) -> Option<ExecutedHistoryRow> {
        let mnemonic = Self::instruction_mnemonic_only(&row.instruction);
        if mnemonic.is_empty() {
            return None;
        }
        Some(ExecutedHistoryRow {
            address: row.address,
            opcode: row.effect.trim().to_string(),
            mnemonic,
        })
    }

    fn sync_history_from_snapshot(&mut self) {
        if !self.show_history || self.snapshot.core.mode == DebuggerMode::Running {
            return;
        }
        let old_scroll = self.history_scroll;
        let rows: Vec<_> = self
            .snapshot
            .history
            .iter()
            .filter_map(Self::history_row_from_backend_history)
            .collect();
        self.execution_history.clear();
        for row in rows {
            self.record_history(Some(row));
        }
        self.history_scroll = old_scroll.min(self.execution_history.len().saturating_sub(1));
        if self.execution_history.is_empty() {
            self.history_scroll = 0;
        }
    }

    fn record_history(&mut self, row: Option<ExecutedHistoryRow>) {
        if !self.show_history {
            return;
        }
        let Some(row) = row else {
            return;
        };
        self.execution_history.push_back(row);
        while self.execution_history.len() > MAX_HISTORY_ROWS {
            let _ = self.execution_history.pop_front();
        }
        if self.history_scroll > self.execution_history.len().saturating_sub(1) {
            self.history_scroll = self.execution_history.len().saturating_sub(1);
        }
    }

    fn clear_history_state(&mut self) {
        self.execution_history.clear();
        self.history_scroll = 0;
    }

    fn step_message(
        label: &str,
        pc_before: u64,
        pc_after: u64,
        cycles_before: u64,
        cycles_after: u64,
    ) -> String {
        let delta = cycles_after.saturating_sub(cycles_before);
        if pc_before == pc_after && delta == 0 {
            return format!("{label}: no advance (CPU halted or waiting for interrupt)");
        }
        format!("{label}: PC 0x{pc_before:04X} -> 0x{pc_after:04X}, +{delta} cycles")
    }

    fn run_to_selected_address(&mut self) -> Result<(), String> {
        let target = self
            .selected_disasm_address()
            .unwrap_or(self.snapshot.core.pc);
        if target == self.snapshot.core.pc && self.snapshot.core.mode != DebuggerMode::Running {
            self.last_message = Some(format!("Run-to already at 0x{target:04X}"));
            return Ok(());
        }

        if self.snapshot.core.mode == DebuggerMode::Running {
            self.backend.pause()?;
            self.refresh()?;
        }

        self.clear_run_to_state()?;
        let has_bp = self
            .snapshot
            .breakpoints
            .iter()
            .any(|bp| bp.enabled && bp.address == target);
        if !has_bp {
            self.backend.toggle_breakpoint(target)?;
            self.run_to_temp_breakpoint = true;
        }
        self.run_to_target_address = Some(target);
        if let Err(err) = self.backend.run() {
            let _ = self.clear_run_to_state();
            return Err(err);
        }
        self.follow_pc = true;
        self.realtime_cycle_carry_nanos = 0;
        self.snapshot.core.mode = DebuggerMode::Running;
        self.last_message = Some(format!("Run-to 0x{target:04X}: running"));
        Ok(())
    }

    fn clear_run_to_state(&mut self) -> Result<(), String> {
        let target = self.run_to_target_address.take();
        let had_temp = self.run_to_temp_breakpoint;
        self.run_to_temp_breakpoint = false;
        if had_temp {
            if let Some(address) = target {
                self.backend.toggle_breakpoint(address)?;
            }
        }
        Ok(())
    }

    fn finish_run_to_if_needed(&mut self) -> Option<String> {
        let target = self.run_to_target_address?;
        let had_temp = self.run_to_temp_breakpoint;
        self.run_to_target_address = None;
        self.run_to_temp_breakpoint = false;

        if had_temp {
            if let Err(err) = self.backend.toggle_breakpoint(target) {
                return Some(format!("Run-to cleanup failed at 0x{target:04X}: {err}"));
            }
        }

        let stopped_pc = self.snapshot.core.pc;
        if stopped_pc == target {
            Some(format!("Run-to reached 0x{target:04X}"))
        } else {
            Some(format!(
                "Run-to interrupted at 0x{stopped_pc:04X} before 0x{target:04X}"
            ))
        }
    }

    fn apply_snapshot(&mut self, mut next: DebuggerSnapshot) {
        Self::apply_diff_markers(&self.snapshot, &mut next);
        next.core.status_line = Self::normalize_rom_status_line(&next.core.status_line);
        self.snapshot = next;
    }

    fn normalize_rom_status_line(status_line: &str) -> String {
        let Some((head, rom_tail)) = status_line.split_once(" | ROM ") else {
            return status_line.to_string();
        };
        let rom_name = Self::rom_name_from_status(rom_tail);
        format!("{head} | ROM {rom_name}")
    }

    fn rom_name_from_status(rom_tail: &str) -> String {
        let tail = rom_tail.trim();
        let candidate = if let Some((_, path_tail)) = tail.split_once("path=") {
            path_tail.trim()
        } else {
            tail
        };
        let candidate = candidate.trim_matches('"').trim_matches('\'').trim();
        if candidate.is_empty() {
            return "-".to_string();
        }
        if let Some(name) = Path::new(candidate).file_name().and_then(|v| v.to_str()) {
            return name.to_string();
        }
        candidate
            .rsplit(['\\', '/'])
            .next()
            .unwrap_or(candidate)
            .to_string()
    }

    fn sync_disassembly_window(&mut self) -> Result<(), String> {
        if self.snapshot.core.mode == DebuggerMode::Running {
            return Ok(());
        }

        if self.follow_pc {
            self.disasm_rows = self.snapshot.disassembly.clone();
            if let Some(ip_idx) = self.disasm_rows.iter().position(|r| r.is_current_ip) {
                self.disasm_selected_index = ip_idx;
            }
        } else {
            let selected_addr = self
                .selected_disasm_address()
                .unwrap_or(self.snapshot.core.pc);
            let rows = self.backend.disassembly_window(selected_addr)?;
            if !rows.is_empty() {
                self.disasm_rows = rows;
                if let Some((idx, _)) = self.closest_disasm_row(selected_addr) {
                    self.disasm_selected_index = idx;
                }
            }
        }

        if self.disasm_selected_index >= self.disasm_rows.len() {
            self.disasm_selected_index = self.disasm_rows.len().saturating_sub(1);
        }
        Ok(())
    }

    fn open_jump_dialog(&mut self) {
        let (target, value) = match self.focused_pane {
            Pane::Disassembly => (
                JumpTarget::Disassembly,
                self.selected_disasm_address()
                    .unwrap_or(self.snapshot.core.pc),
            ),
            Pane::Memory => (JumpTarget::Memory, self.memory_cursor_address),
            _ => {
                self.last_message =
                    Some("Jump is available in Disassembly and Memory panes only".to_string());
                return;
            }
        };
        self.jump_dialog.active = true;
        self.jump_dialog.target = target;
        self.jump_dialog.input = format!("{value:04X}");
    }

    fn parse_jump_input(input: &str) -> Option<u64> {
        let compact = input.trim().replace('_', "");
        if compact.is_empty() {
            return None;
        }
        if let Some(hex) = compact
            .strip_prefix("0x")
            .or_else(|| compact.strip_prefix("0X"))
        {
            return u64::from_str_radix(hex, 16).ok();
        }
        if let Some(hex) = compact
            .strip_suffix('h')
            .or_else(|| compact.strip_suffix('H'))
        {
            return u64::from_str_radix(hex, 16).ok();
        }
        if let Ok(value) = u64::from_str_radix(&compact, 16) {
            return Some(value);
        }
        compact.parse::<u64>().ok()
    }

    fn apply_jump_dialog(&mut self) {
        let raw = self.jump_dialog.input.clone();
        let Some(address) = Self::parse_jump_input(&raw) else {
            self.last_message = Some(format!("Invalid jump address: '{raw}'"));
            return;
        };
        if let Err(err) = self.backend.read_memory(address, 1) {
            self.last_message = Some(format!("Invalid jump address '{raw}': {err}"));
            return;
        }

        match self.jump_dialog.target {
            JumpTarget::Disassembly => {
                if self.snapshot.core.mode == DebuggerMode::Running {
                    if let Err(err) = self.backend.pause() {
                        self.last_message =
                            Some(format!("Disassembly jump failed: could not pause: {err}"));
                        return;
                    }
                    if let Err(err) = self.refresh() {
                        self.last_message = Some(format!(
                            "Disassembly jump failed: paused but refresh failed: {err}"
                        ));
                        return;
                    }
                }
                let prev_rows = self.disasm_rows.clone();
                let prev_index = self.disasm_selected_index;
                let rows = match self.backend.disassembly_window(address) {
                    Ok(rows) => rows,
                    Err(err) => {
                        self.last_message = Some(format!("Disassembly jump failed: {err}"));
                        return;
                    }
                };
                if rows.is_empty() {
                    self.last_message = Some("Disassembly is empty; cannot jump".to_string());
                    return;
                }
                self.disasm_rows = rows;
                if let Some((idx, row_addr)) = self.closest_disasm_row(address) {
                    self.follow_pc = false;
                    self.disasm_selected_index = idx;
                    self.last_message = Some(format!(
                        "Jumped disassembly: requested 0x{address:04X}, selected 0x{row_addr:04X}"
                    ));
                    self.jump_dialog.active = false;
                } else {
                    self.disasm_rows = prev_rows;
                    self.disasm_selected_index = prev_index;
                    self.last_message =
                        Some("Disassembly jump failed: no matching instruction rows".to_string());
                }
            }
            JumpTarget::Memory => {
                let prev_cursor = self.memory_cursor_address;
                let prev_base = self.memory_window_base_address;
                let prev_rows = self.memory_rows.clone();
                self.memory_cursor_address = Self::align_memory_address(address);
                self.ensure_memory_cursor_visible();
                if let Err(err) = self.refresh_memory_window() {
                    self.memory_cursor_address = prev_cursor;
                    self.memory_window_base_address = prev_base;
                    self.memory_rows = prev_rows;
                    self.last_message = Some(format!("Memory jump failed: {err}"));
                } else {
                    self.last_message = Some(format!("Jumped memory to 0x{address:04X}"));
                    self.jump_dialog.active = false;
                }
            }
        }
    }

    fn closest_disasm_row(&self, address: u64) -> Option<(usize, u64)> {
        self.disasm_rows
            .iter()
            .enumerate()
            .min_by_key(|(_, row)| row.address.abs_diff(address))
            .map(|(idx, row)| (idx, row.address))
    }

    fn align_memory_address(address: u64) -> u64 {
        let mask = !(MEMORY_BYTES_PER_ROW - 1);
        address & mask
    }

    fn memory_window_size_bytes() -> u64 {
        MEMORY_BYTES_PER_ROW * MEMORY_WINDOW_ROWS as u64
    }

    fn move_memory_cursor(&mut self, delta_rows: i64) -> Result<(), String> {
        let prev_cursor = self.memory_cursor_address;
        let prev_base = self.memory_window_base_address;
        let prev_rows = self.memory_rows.clone();
        let delta_bytes = delta_rows.saturating_mul(MEMORY_BYTES_PER_ROW as i64);
        self.memory_cursor_address = if delta_bytes >= 0 {
            self.memory_cursor_address
                .saturating_add(delta_bytes as u64)
        } else {
            self.memory_cursor_address
                .saturating_sub(delta_bytes.unsigned_abs())
        };
        self.memory_cursor_address = Self::align_memory_address(self.memory_cursor_address);
        self.ensure_memory_cursor_visible();
        if let Err(err) = self.refresh_memory_window() {
            self.memory_cursor_address = prev_cursor;
            self.memory_window_base_address = prev_base;
            self.memory_rows = prev_rows;
            self.last_message = Some(format!("Memory navigation blocked: {err}"));
        }
        Ok(())
    }

    fn ensure_memory_cursor_visible(&mut self) {
        let window_start = self.memory_window_base_address;
        let window_end = window_start.saturating_add(Self::memory_window_size_bytes());
        if self.memory_cursor_address < window_start || self.memory_cursor_address >= window_end {
            let half_window = Self::memory_window_size_bytes() / 2;
            let centered = self.memory_cursor_address.saturating_sub(half_window);
            self.memory_window_base_address = Self::align_memory_address(centered);
        }
    }

    fn refresh_memory_window(&mut self) -> Result<(), String> {
        let byte_count_u64 = Self::memory_window_size_bytes();
        let byte_count = usize::try_from(byte_count_u64).map_err(|_| "memory window too large")?;
        let bytes = self
            .backend
            .read_memory(self.memory_window_base_address, byte_count)?;
        if bytes.len() != byte_count {
            return Err(format!(
                "backend returned {} bytes, expected {}",
                bytes.len(),
                byte_count
            ));
        }

        let previous = self.memory_rows.clone();
        let mut rows = Vec::with_capacity(MEMORY_WINDOW_ROWS);
        for row_idx in 0..MEMORY_WINDOW_ROWS {
            let start = row_idx * MEMORY_BYTES_PER_ROW as usize;
            let end = start + MEMORY_BYTES_PER_ROW as usize;
            let chunk = &bytes[start..end];
            let address = self
                .memory_window_base_address
                .saturating_add((row_idx as u64) * MEMORY_BYTES_PER_ROW);
            let hex_bytes = chunk
                .iter()
                .map(|b| format!("{:02X}", b))
                .collect::<Vec<_>>()
                .join(" ");
            let ascii = chunk
                .iter()
                .map(|b| {
                    if (0x20..=0x7E).contains(b) {
                        *b as char
                    } else {
                        '.'
                    }
                })
                .collect::<String>();
            let mut row = MemoryRow {
                address,
                hex_bytes,
                ascii,
                changed: false,
            };
            if let Some(old) = previous.iter().find(|r| r.address == row.address) {
                row.changed = row.hex_bytes != old.hex_bytes || row.ascii != old.ascii;
            } else {
                row.changed = true;
            }
            rows.push(row);
        }
        self.memory_rows = rows;
        Ok(())
    }

    fn apply_diff_markers(prev: &DebuggerSnapshot, next: &mut DebuggerSnapshot) {
        for row in &mut next.registers {
            if let Some(old) = prev.registers.iter().find(|r| r.name == row.name) {
                row.changed =
                    row.changed || row.hex_value != old.hex_value || row.dec_value != old.dec_value;
            } else {
                row.changed = true;
            }
        }

        for row in &mut next.flags {
            if let Some(old) = prev.flags.iter().find(|r| r.name == row.name) {
                row.changed = row.changed || row.value != old.value;
            } else {
                row.changed = true;
            }
        }

        for row in &mut next.disassembly {
            if let Some(old) = prev.disassembly.iter().find(|r| r.address == row.address) {
                row.changed = row.changed
                    || row.bytes != old.bytes
                    || row.instruction != old.instruction
                    || row.is_current_ip != old.is_current_ip
                    || row.has_breakpoint != old.has_breakpoint;
            } else {
                row.changed = true;
            }
        }

        for row in &mut next.stack {
            if let Some(old) = prev.stack.iter().find(|r| r.address == row.address) {
                row.changed = row.changed || row.value != old.value || row.is_sp != old.is_sp;
            } else {
                row.changed = true;
            }
        }

        for row in &mut next.memory {
            if let Some(old) = prev.memory.iter().find(|r| r.address == row.address) {
                row.changed =
                    row.changed || row.hex_bytes != old.hex_bytes || row.ascii != old.ascii;
            } else {
                row.changed = true;
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::actions::Action;
    use crate::backend::mock::MockDebuggerBackend;
    use crossterm::event::{KeyCode, KeyEvent, KeyModifiers};

    #[test]
    fn cycles_focus_between_panes() {
        let backend = Box::new(MockDebuggerBackend::new());
        let mut app = App::new(backend).expect("app");
        let initial = app.focused_pane;
        app.handle_action(Action::SelectNextPane).expect("next");
        assert_ne!(app.focused_pane, initial);
        app.handle_action(Action::SelectPrevPane).expect("prev");
        assert_eq!(app.focused_pane, initial);
    }

    #[test]
    fn marks_register_diffs_for_one_refresh() {
        let backend = Box::new(MockDebuggerBackend::new());
        let mut app = App::new(backend).expect("app");
        app.handle_action(Action::StepInto).expect("step");

        let pc = app
            .snapshot
            .registers
            .iter()
            .find(|r| r.name == "PC")
            .expect("pc row");
        assert!(pc.changed);

        app.refresh().expect("refresh");
        let pc2 = app
            .snapshot
            .registers
            .iter()
            .find(|r| r.name == "PC")
            .expect("pc row");
        assert!(!pc2.changed);
    }

    #[test]
    fn running_mode_steps_on_tick() {
        let backend = Box::new(MockDebuggerBackend::new());
        let mut app = App::new(backend).expect("app");
        app.handle_action(Action::RunPause).expect("run");
        let pc0 = app.snapshot.core.pc;
        app.on_tick().expect("tick");
        assert_eq!(app.snapshot.core.pc, pc0);
        app.handle_action(Action::RunPause).expect("pause");
        assert!(app.snapshot.core.pc > pc0);
    }

    #[test]
    fn toggles_breakpoint_on_selected_disassembly_row() {
        let backend = Box::new(MockDebuggerBackend::new());
        let mut app = App::new(backend).expect("app");
        app.disasm_selected_index = 5;
        let addr = app.selected_disasm_address().expect("selected addr");
        app.handle_action(Action::ToggleBreakpoint).expect("toggle");
        assert!(app
            .snapshot
            .breakpoints
            .iter()
            .any(|bp| bp.enabled && bp.address == addr));
    }

    #[test]
    fn running_mode_pauses_on_breakpoint() {
        let backend = Box::new(MockDebuggerBackend::new());
        let mut app = App::new(backend).expect("app");
        app.disasm_selected_index = app
            .snapshot
            .disassembly
            .iter()
            .position(|r| r.address == app.snapshot.core.pc + 1)
            .expect("row at pc+1");
        app.handle_action(Action::ToggleBreakpoint)
            .expect("set bp at next pc");
        app.handle_action(Action::RunPause).expect("run");
        app.on_tick().expect("tick");
        app.on_tick().expect("tick 2");
        assert_eq!(app.snapshot.core.mode, DebuggerMode::Paused);
    }

    #[test]
    fn run_to_cursor_stops_at_selected_line_and_cleans_temp_breakpoint() {
        let backend = Box::new(MockDebuggerBackend::new());
        let mut app = App::new(backend).expect("app");
        let target = app.snapshot.core.pc + 6;
        app.disasm_selected_index = app
            .snapshot
            .disassembly
            .iter()
            .position(|r| r.address == target)
            .expect("target disasm row");

        app.handle_action(Action::RunToCursor).expect("run-to");
        assert_eq!(app.snapshot.core.mode, DebuggerMode::Running);

        for _ in 0..8 {
            app.on_tick().expect("tick");
            if app.snapshot.core.mode == DebuggerMode::Paused {
                break;
            }
        }

        assert_eq!(app.snapshot.core.mode, DebuggerMode::Paused);
        assert_eq!(app.snapshot.core.pc, target);
        assert!(app
            .last_message
            .as_deref()
            .unwrap_or("")
            .contains("Run-to reached"));
        assert!(app.run_to_target_address.is_none());
        assert!(!app.run_to_temp_breakpoint);
        app.refresh().expect("refresh");
        assert!(!app
            .snapshot
            .breakpoints
            .iter()
            .any(|bp| bp.enabled && bp.address == target));
    }

    #[test]
    fn reset_restores_initial_pc() {
        let backend = Box::new(MockDebuggerBackend::new());
        let mut app = App::new(backend).expect("app");
        app.handle_action(Action::StepInto).expect("step");
        assert!(app.snapshot.core.pc > 0);
        app.handle_action(Action::Reset).expect("reset");
        assert_eq!(app.snapshot.core.pc, 0);
        assert_eq!(app.snapshot.core.mode, DebuggerMode::Paused);
    }

    #[test]
    fn disasm_scroll_disables_auto_follow() {
        let backend = Box::new(MockDebuggerBackend::new());
        let mut app = App::new(backend).expect("app");
        assert_eq!(app.disasm_selected_index, 0);
        app.handle_action(Action::ScrollDown).expect("scroll");
        assert_eq!(app.disasm_selected_index, 1);
        app.refresh().expect("refresh");
        assert_eq!(app.disasm_selected_index, 1);
    }

    #[test]
    fn step_re_enables_auto_follow() {
        let backend = Box::new(MockDebuggerBackend::new());
        let mut app = App::new(backend).expect("app");
        app.handle_action(Action::ScrollDown).expect("scroll");
        assert!(!app.follow_pc);
        app.handle_action(Action::StepInto).expect("step");
        assert!(app.follow_pc);
        let ip_index = app
            .snapshot
            .disassembly
            .iter()
            .position(|r| r.is_current_ip)
            .expect("ip row");
        assert_eq!(app.disasm_selected_index, ip_index);
    }

    #[test]
    fn page_down_moves_disassembly_selection() {
        let backend = Box::new(MockDebuggerBackend::new());
        let mut app = App::new(backend).expect("app");
        app.handle_action(Action::PageDown).expect("page down");
        assert!(app.disasm_selected_index > 0);
        app.handle_action(Action::PageUp).expect("page up");
        assert_eq!(app.disasm_selected_index, 0);
    }

    #[test]
    fn memory_pane_uses_own_selection() {
        let backend = Box::new(MockDebuggerBackend::new());
        let mut app = App::new(backend).expect("app");
        app.focused_pane = Pane::Memory;
        let start_addr = app.memory_cursor_address;
        app.handle_action(Action::ScrollDown)
            .expect("scroll memory");
        assert_eq!(app.memory_cursor_address, start_addr + MEMORY_BYTES_PER_ROW);
        app.handle_action(Action::PageDown).expect("page memory");
        assert_eq!(
            app.memory_cursor_address,
            start_addr + MEMORY_BYTES_PER_ROW + (16 * MEMORY_BYTES_PER_ROW)
        );
    }

    #[test]
    fn instruction_info_toggle_defaults_off_and_flips() {
        let backend = Box::new(MockDebuggerBackend::new());
        let mut app = App::new(backend).expect("app");
        assert!(!app.show_instruction_info);
        app.handle_action(Action::ToggleInstructionInfo)
            .expect("toggle on");
        assert!(app.show_instruction_info);
        app.handle_action(Action::ToggleInstructionInfo)
            .expect("toggle off");
        assert!(!app.show_instruction_info);
    }

    #[test]
    fn history_toggle_defaults_off_and_clears_when_disabled() {
        let backend = Box::new(MockDebuggerBackend::new());
        let mut app = App::new(backend).expect("app");
        assert!(!app.show_history);
        assert!(app.execution_history.is_empty());

        app.handle_action(Action::ToggleHistory).expect("toggle on");
        assert!(app.show_history);
        app.record_history(Some(ExecutedHistoryRow {
            address: 0x0010,
            opcode: "00".to_string(),
            mnemonic: "NOP".to_string(),
        }));
        assert_eq!(app.execution_history.len(), 1);
        app.focused_pane = Pane::History;

        app.handle_action(Action::ToggleHistory)
            .expect("toggle off");
        assert!(!app.show_history);
        assert!(app.execution_history.is_empty());
        assert_eq!(app.history_scroll, 0);
        assert_eq!(app.focused_pane, Pane::Disassembly);
    }

    #[test]
    fn step_adds_history_when_enabled() {
        let backend = Box::new(MockDebuggerBackend::new());
        let mut app = App::new(backend).expect("app");
        app.handle_action(Action::ToggleHistory).expect("toggle on");
        assert_eq!(app.execution_history.len(), 0);

        app.handle_action(Action::StepInto).expect("step");
        assert_eq!(app.execution_history.len(), 1);
        let row = app.execution_history.back().expect("history row");
        assert_eq!(row.address, 0);
        assert!(!row.opcode.is_empty());
        assert!(!row.mnemonic.is_empty());
    }

    #[test]
    fn run_collects_history_when_enabled() {
        let backend = Box::new(MockDebuggerBackend::new());
        let mut app = App::new(backend).expect("app");
        app.handle_action(Action::ToggleHistory).expect("toggle on");
        app.handle_action(Action::RunPause).expect("run");
        app.on_tick().expect("tick");
        app.handle_action(Action::RunPause).expect("pause");
        assert!(!app.execution_history.is_empty());
        assert!(app.execution_history.len() <= 100);
    }

    #[test]
    fn history_ring_caps_to_100() {
        let backend = Box::new(MockDebuggerBackend::new());
        let mut app = App::new(backend).expect("app");
        app.handle_action(Action::ToggleHistory).expect("toggle on");
        for i in 0..150u64 {
            app.record_history(Some(ExecutedHistoryRow {
                address: i,
                opcode: format!("{:02X}", i as u8),
                mnemonic: "NOP".to_string(),
            }));
        }
        assert_eq!(app.execution_history.len(), 100);
        let first = app.execution_history.front().expect("first");
        let last = app.execution_history.back().expect("last");
        assert_eq!(first.address, 50);
        assert_eq!(last.address, 149);
    }

    #[test]
    fn pane_cycle_skips_history_when_hidden() {
        let backend = Box::new(MockDebuggerBackend::new());
        let mut app = App::new(backend).expect("app");
        assert!(!app.show_history);
        assert_eq!(app.focused_pane, Pane::Disassembly);
        app.handle_action(Action::SelectNextPane)
            .expect("next pane");
        assert_eq!(app.focused_pane, Pane::Memory);
    }

    #[test]
    fn pane_cycle_includes_history_when_visible() {
        let backend = Box::new(MockDebuggerBackend::new());
        let mut app = App::new(backend).expect("app");
        app.handle_action(Action::ToggleHistory).expect("toggle on");
        assert_eq!(app.focused_pane, Pane::Disassembly);
        app.handle_action(Action::SelectNextPane)
            .expect("next pane");
        assert_eq!(app.focused_pane, Pane::History);
    }

    #[test]
    fn overlay_toggle_flips_backend_flag() {
        let backend = Box::new(MockDebuggerBackend::new());
        let mut app = App::new(backend).expect("app");
        assert!(!app.backend.overlay_enabled().expect("overlay state"));
        app.handle_action(Action::ToggleOverlay).expect("toggle on");
        assert!(app.backend.overlay_enabled().expect("overlay state"));
        app.handle_action(Action::ToggleOverlay)
            .expect("toggle off");
        assert!(!app.backend.overlay_enabled().expect("overlay state"));
    }

    #[test]
    fn jump_dialog_moves_disassembly_selection() {
        let backend = Box::new(MockDebuggerBackend::new());
        let mut app = App::new(backend).expect("app");
        app.focused_pane = Pane::Disassembly;
        app.handle_action(Action::JumpToAddress).expect("open jump");
        assert!(app.jump_dialog.active);
        app.jump_dialog.input = "000A".to_string();
        app.handle_key_event(KeyEvent::new(KeyCode::Enter, KeyModifiers::NONE))
            .expect("submit jump");
        assert!(!app.jump_dialog.active);
        assert_eq!(app.selected_disasm_address(), Some(0x000A));
        assert!(!app.follow_pc);
    }

    #[test]
    fn jump_dialog_moves_memory_cursor() {
        let backend = Box::new(MockDebuggerBackend::new());
        let mut app = App::new(backend).expect("app");
        app.focused_pane = Pane::Memory;
        app.handle_action(Action::JumpToAddress).expect("open jump");
        assert!(app.jump_dialog.active);
        app.jump_dialog.input = "0031".to_string();
        app.handle_key_event(KeyEvent::new(KeyCode::Enter, KeyModifiers::NONE))
            .expect("submit jump");
        assert!(!app.jump_dialog.active);
        assert_eq!(app.memory_cursor_address, 0x0030);
    }

    #[test]
    fn jump_dialog_invalid_input_stays_open() {
        let backend = Box::new(MockDebuggerBackend::new());
        let mut app = App::new(backend).expect("app");
        app.focused_pane = Pane::Disassembly;
        app.handle_action(Action::JumpToAddress).expect("open jump");
        app.jump_dialog.input = "ZZ__".to_string();
        app.handle_key_event(KeyEvent::new(KeyCode::Enter, KeyModifiers::NONE))
            .expect("submit jump");
        assert!(app.jump_dialog.active);
        assert!(app
            .last_message
            .as_deref()
            .unwrap_or("")
            .contains("Invalid jump address"));
    }

    #[test]
    fn jump_dialog_trims_address_input_before_parsing() {
        let backend = Box::new(MockDebuggerBackend::new());
        let mut app = App::new(backend).expect("app");
        app.focused_pane = Pane::Disassembly;
        app.handle_action(Action::JumpToAddress).expect("open jump");
        app.jump_dialog.input = "   0x000A   ".to_string();
        app.handle_key_event(KeyEvent::new(KeyCode::Enter, KeyModifiers::NONE))
            .expect("submit jump");
        assert!(!app.jump_dialog.active);
        assert_eq!(app.selected_disasm_address(), Some(0x000A));
    }

    #[test]
    fn jump_dialog_disassembly_error_is_non_fatal() {
        let backend = Box::new(MockDebuggerBackend::failing_disassembly_window());
        let mut app = App::new(backend).expect("app");
        app.focused_pane = Pane::Disassembly;
        app.handle_action(Action::JumpToAddress).expect("open jump");
        app.jump_dialog.input = "A027".to_string();
        let consumed = app
            .handle_key_event(KeyEvent::new(KeyCode::Enter, KeyModifiers::NONE))
            .expect("submit jump");
        assert!(consumed);
        assert!(app.jump_dialog.active);
        assert!(app
            .last_message
            .as_deref()
            .unwrap_or("")
            .contains("Disassembly jump failed"));
    }

    #[test]
    fn jump_dialog_disassembly_auto_pauses_when_running() {
        let backend = Box::new(MockDebuggerBackend::new());
        let mut app = App::new(backend).expect("app");
        app.focused_pane = Pane::Disassembly;
        app.handle_action(Action::RunPause).expect("run");
        assert_eq!(app.snapshot.core.mode, DebuggerMode::Running);
        app.handle_action(Action::JumpToAddress).expect("open jump");
        app.jump_dialog.input = "000A".to_string();
        app.handle_key_event(KeyEvent::new(KeyCode::Enter, KeyModifiers::NONE))
            .expect("submit jump");
        assert_eq!(app.snapshot.core.mode, DebuggerMode::Paused);
        assert!(!app.jump_dialog.active);
        assert_eq!(app.selected_disasm_address(), Some(0x000A));
    }
}
