pub mod mock;

#[cfg(feature = "linked-emulator")]
pub mod ffi_types;
#[cfg(feature = "linked-emulator")]
pub mod linked_emulator;

use crate::state::{DebugCounts, DebuggerMode, DebuggerSnapshot, DisasmRow};

#[allow(dead_code)]
pub trait DebuggerBackend {
    fn counts(&mut self) -> Result<DebugCounts, String>;
    fn snapshot(&mut self) -> Result<DebuggerSnapshot, String>;
    fn reset(&mut self) -> Result<(), String>;
    fn run(&mut self) -> Result<(), String>;
    fn run_slice(&mut self, max_steps: u32) -> Result<DebuggerMode, String>;
    fn run_for_cycles(&mut self, max_cycles: u64) -> Result<DebuggerMode, String>;
    fn pause(&mut self) -> Result<(), String>;
    fn step_into(&mut self) -> Result<(), String>;
    fn step_over(&mut self) -> Result<(), String>;
    fn step_out(&mut self) -> Result<(), String>;
    fn toggle_breakpoint(&mut self, address: u64) -> Result<(), String>;
    fn select_thread(&mut self, thread_id: u32) -> Result<(), String>;
    fn jump_frame(&mut self, frame_index: usize) -> Result<(), String>;
    fn read_memory(&mut self, address: u64, size: usize) -> Result<Vec<u8>, String>;
    fn disassembly_window(&mut self, anchor_address: u64) -> Result<Vec<DisasmRow>, String>;
    fn clear_history(&mut self) -> Result<(), String>;
    fn set_overlay_enabled(&mut self, enabled: bool) -> Result<(), String>;
    fn overlay_enabled(&mut self) -> Result<bool, String>;
    fn focus_emulator_window(&mut self) -> Result<(), String>;
}
