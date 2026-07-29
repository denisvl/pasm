#![allow(non_camel_case_types)]

use core::ffi::{c_char, c_void};

pub const EMU_AUTOMATION_ABI_VERSION: u32 = 2;
pub const EMU_AUTOMATION_STRUCT_VERSION: u32 = 2;

pub const EMU_AUTOMATION_CAP_SCREEN_FRAMEBUFFER: u64 = 1 << 0;
pub const EMU_AUTOMATION_CAP_INPUT_KEYBOARD: u64 = 1 << 1;
pub const EMU_AUTOMATION_CAP_INPUT_CONTROLLER: u64 = 1 << 2;
pub const EMU_AUTOMATION_CAP_EXEC_PAUSE: u64 = 1 << 3;
pub const EMU_AUTOMATION_CAP_EXEC_RESUME: u64 = 1 << 4;
pub const EMU_AUTOMATION_CAP_EXEC_RESET: u64 = 1 << 5;
pub const EMU_AUTOMATION_CAP_EXEC_STEP_FRAME: u64 = 1 << 6;
pub const EMU_AUTOMATION_CAP_EXEC_RUN_FRAMES: u64 = 1 << 7;
pub const EMU_AUTOMATION_CAP_EVENTS_FRAME_COMPLETED: u64 = 1 << 8;
pub const EMU_AUTOMATION_CAP_SCREEN_TEXT_GRID: u64 = 1 << 9;
pub const EMU_AUTOMATION_CAP_INSPECT_MEMORY: u64 = 1 << 10;
pub const EMU_AUTOMATION_CAP_EXEC_PROGRAM_COUNTER: u64 = 1 << 11;
pub const EMU_AUTOMATION_CAP_EXEC_TIMING: u64 = 1 << 12;
pub const EMU_AUTOMATION_CAP_INSPECT_MEMORY_WRITE: u64 = 1 << 13;
pub const EMU_AUTOMATION_CAP_INSPECT_REGISTERS: u64 = 1 << 14;
pub const EMU_AUTOMATION_CAP_EXEC_CURRENT_INSTRUCTION: u64 = 1 << 15;

#[repr(C)]
pub struct emu_automation_machine {
    _private: [u8; 0],
}

pub type emu_automation_machine_t = emu_automation_machine;

#[repr(C)]
pub struct emu_automation_subscription {
    _private: [u8; 0],
}

pub type emu_automation_subscription_t = emu_automation_subscription;

#[repr(C)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum emu_automation_result_t {
    EMU_AUTOMATION_OK = 0,
    EMU_AUTOMATION_UNSUPPORTED = 1,
    EMU_AUTOMATION_INVALID_ARGUMENT = 2,
    EMU_AUTOMATION_INVALID_STATE = 3,
    EMU_AUTOMATION_NOT_RUNNING = 4,
    EMU_AUTOMATION_ALREADY_RUNNING = 5,
    EMU_AUTOMATION_NOT_READY = 6,
    EMU_AUTOMATION_TIMEOUT = 7,
    EMU_AUTOMATION_MAPPING_UNAVAILABLE = 8,
    EMU_AUTOMATION_CHARACTER_UNSUPPORTED = 9,
    EMU_AUTOMATION_DEVICE_UNAVAILABLE = 10,
    EMU_AUTOMATION_RESOURCE_UNAVAILABLE = 11,
    EMU_AUTOMATION_TRANSPORT_ERROR = 12,
    EMU_AUTOMATION_SERIALIZATION_ERROR = 13,
    EMU_AUTOMATION_ADAPTER_ERROR = 14,
    EMU_AUTOMATION_INTERNAL_ERROR = 15,
}

#[repr(C)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum emu_automation_execution_state_t {
    EMU_AUTOMATION_EXECUTION_STOPPED = 0,
    EMU_AUTOMATION_EXECUTION_RUNNING = 1,
    EMU_AUTOMATION_EXECUTION_PAUSED = 2,
    EMU_AUTOMATION_EXECUTION_RESETTING = 3,
    EMU_AUTOMATION_EXECUTION_ERROR = 4,
}

#[repr(C)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum emu_automation_reset_kind_t {
    EMU_AUTOMATION_RESET_COLD = 0,
    EMU_AUTOMATION_RESET_WARM = 1,
}

#[repr(C)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum emu_automation_pixel_format_t {
    EMU_AUTOMATION_PIXEL_FORMAT_UNKNOWN = 0,
    EMU_AUTOMATION_PIXEL_FORMAT_RGBA8888 = 1,
    EMU_AUTOMATION_PIXEL_FORMAT_BGRA8888 = 2,
    EMU_AUTOMATION_PIXEL_FORMAT_RGB565 = 3,
    EMU_AUTOMATION_PIXEL_FORMAT_INDEX8 = 4,
}

#[repr(C)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum emu_automation_input_action_t {
    EMU_AUTOMATION_INPUT_RELEASE = 0,
    EMU_AUTOMATION_INPUT_PRESS = 1,
}

#[repr(C)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum emu_automation_timing_kind_t {
    EMU_AUTOMATION_TIMING_IMMEDIATE = 0,
    EMU_AUTOMATION_TIMING_FRAME = 1,
    EMU_AUTOMATION_TIMING_CYCLE = 2,
    EMU_AUTOMATION_TIMING_DELAY_FRAMES = 3,
    EMU_AUTOMATION_TIMING_DELAY_CYCLES = 4,
}

#[repr(C)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum emu_automation_event_type_t {
    EMU_AUTOMATION_EVENT_NONE = 0,
    EMU_AUTOMATION_EVENT_FRAME_COMPLETED = 1,
    EMU_AUTOMATION_EVENT_MACHINE_RESET = 2,
    EMU_AUTOMATION_EVENT_EXECUTION_STATE_CHANGED = 3,
    EMU_AUTOMATION_EVENT_INPUT_SUBMITTED = 4,
    EMU_AUTOMATION_EVENT_SCREEN_CHANGED = 5,
    EMU_AUTOMATION_EVENT_TEXT_CHANGED = 6,
    EMU_AUTOMATION_EVENT_MEDIA_ACTIVITY = 7,
    EMU_AUTOMATION_EVENT_DEBUG_MESSAGE = 8,
    EMU_AUTOMATION_EVENT_ERROR = 9,
}

pub const EMU_AUTOMATION_KEY_MODIFIER_SHIFT: u32 = 1u32 << 0;
pub const EMU_AUTOMATION_KEY_MODIFIER_CTRL: u32 = 1u32 << 1;
pub const EMU_AUTOMATION_KEY_MODIFIER_ALT: u32 = 1u32 << 2;
pub const EMU_AUTOMATION_KEY_MODIFIER_META: u32 = 1u32 << 3;

#[repr(C)]
#[derive(Clone, Copy)]
pub struct emu_automation_capabilities_t {
    pub struct_size: u32,
    pub struct_version: u32,
    pub feature_bits: u64,
}

#[repr(C)]
#[derive(Clone, Copy)]
pub struct emu_automation_machine_descriptor_t {
    pub struct_size: u32,
    pub struct_version: u32,
    pub machine_id: *const c_char,
    pub system_id: *const c_char,
    pub model_id: *const c_char,
    pub region: *const c_char,
    pub video_standard: *const c_char,
    pub adapter_version: *const c_char,
    pub configured_memory_bytes: u64,
    pub capabilities: emu_automation_capabilities_t,
}

#[repr(C)]
#[derive(Clone, Copy)]
pub struct emu_automation_character_mapping_descriptor_t {
    pub struct_size: u32,
    pub struct_version: u32,
    pub device_id: *const c_char,
    pub unicode_codepoint: u32,
    pub native_code: u32,
    pub key_id: *const c_char,
    pub required_modifier_bits: u32,
    pub shift_key_id: *const c_char,
    pub ctrl_key_id: *const c_char,
    pub alt_key_id: *const c_char,
    pub meta_key_id: *const c_char,
}

#[repr(C)]
#[derive(Clone, Copy)]
pub struct emu_automation_frame_metadata_t {
    pub struct_size: u32,
    pub struct_version: u32,
    pub frame_number: u64,
    pub emulated_cycles: u64,
    pub emulated_time_ns: u64,
    pub execution_state: emu_automation_execution_state_t,
}

#[repr(C)]
#[derive(Clone, Copy)]
pub struct emu_automation_rect_t {
    pub x: i32,
    pub y: i32,
    pub width: u32,
    pub height: u32,
}

#[repr(C)]
#[derive(Clone, Copy)]
pub struct emu_automation_framebuffer_snapshot_t {
    pub struct_size: u32,
    pub struct_version: u32,
    pub frame: emu_automation_frame_metadata_t,
    pub width: u32,
    pub height: u32,
    pub stride_bytes: u32,
    pub pixel_format: emu_automation_pixel_format_t,
    pub visible_area: emu_automation_rect_t,
    pub pixel_aspect_numerator: u32,
    pub pixel_aspect_denominator: u32,
    pub pixels: *const u8,
    pub pixel_size: usize,
    pub adapter_owned: *mut c_void,
}

#[repr(C)]
#[derive(Clone, Copy)]
pub struct emu_automation_text_cell_t {
    pub struct_size: u32,
    pub struct_version: u32,
    pub native_code: u32,
    pub unicode_codepoint: u32,
    pub glyph_id: *const c_char,
    pub foreground_color: i32,
    pub background_color: i32,
    pub attribute_flags: u32,
    pub charset_id: *const c_char,
    pub source_address: u64,
    pub confidence: u8,
}

#[repr(C)]
#[derive(Clone, Copy)]
pub struct emu_automation_text_view_descriptor_t {
    pub struct_size: u32,
    pub struct_version: u32,
    pub region_id: *const c_char,
    pub columns: u32,
    pub rows: u32,
    pub row_stride: u32,
    pub charset_id: *const c_char,
    pub native_encoding: *const c_char,
    pub unicode_map: *const c_char,
}

#[repr(C)]
#[derive(Clone, Copy)]
pub struct emu_automation_text_grid_snapshot_t {
    pub struct_size: u32,
    pub struct_version: u32,
    pub frame: emu_automation_frame_metadata_t,
    pub region_id: *const c_char,
    pub columns: u32,
    pub rows: u32,
    pub row_stride: u32,
    pub cells: *const emu_automation_text_cell_t,
    pub cell_count: usize,
    pub plain_utf8: *const c_char,
    pub plain_utf8_size: usize,
    pub adapter_owned: *mut c_void,
}

#[repr(C)]
#[derive(Clone, Copy)]
pub struct emu_automation_text_delta_t {
    pub struct_size: u32,
    pub struct_version: u32,
    pub x: u32,
    pub y: u32,
    pub before: emu_automation_text_cell_t,
    pub after: emu_automation_text_cell_t,
}

#[repr(C)]
#[derive(Clone, Copy)]
pub struct emu_automation_timing_t {
    pub kind: emu_automation_timing_kind_t,
    pub value: u64,
}

#[repr(C)]
#[derive(Clone, Copy)]
pub struct emu_automation_key_event_t {
    pub struct_size: u32,
    pub struct_version: u32,
    pub device_id: *const c_char,
    pub key_id: *const c_char,
    pub action: emu_automation_input_action_t,
    pub timing: emu_automation_timing_t,
}

#[repr(C)]
#[derive(Clone, Copy)]
pub struct emu_automation_controller_button_event_t {
    pub struct_size: u32,
    pub struct_version: u32,
    pub device_id: *const c_char,
    pub control_id: *const c_char,
    pub action: emu_automation_input_action_t,
    pub timing: emu_automation_timing_t,
}

#[repr(C)]
#[derive(Clone, Copy)]
pub struct emu_automation_event_t {
    pub struct_size: u32,
    pub struct_version: u32,
    pub sequence_number: u64,
    pub event_type: emu_automation_event_type_t,
    pub frame: emu_automation_frame_metadata_t,
    pub input_accepted: emu_automation_frame_metadata_t,
    pub input_applied: emu_automation_frame_metadata_t,
    pub device_id: *const c_char,
    pub control_id: *const c_char,
    pub region_id: *const c_char,
    pub change_x: u32,
    pub change_y: u32,
    pub change_width: u32,
    pub change_height: u32,
    pub change_cell_count: u32,
    pub text_deltas: *const emu_automation_text_delta_t,
    pub text_delta_count: usize,
    pub message: *const c_char,
    pub input_action: emu_automation_input_action_t,
    pub input_timing: emu_automation_timing_t,
    pub adapter_owned: *mut c_void,
}

#[repr(C)]
#[derive(Clone, Copy)]
pub struct emu_automation_register_value_t {
    pub struct_size: u32,
    pub struct_version: u32,
    pub name: [c_char; 32],
    pub hex_value: [c_char; 32],
    pub dec_value: [c_char; 32],
    pub has_dec: u8,
    pub changed: u8,
}

#[repr(C)]
#[derive(Clone, Copy)]
pub struct emu_automation_instruction_t {
    pub struct_size: u32,
    pub struct_version: u32,
    pub address: u64,
    pub bytes: [c_char; 32],
    pub text: [c_char; 96],
    pub symbol: [c_char; 64],
    pub has_symbol: u8,
    pub is_current_ip: u8,
    pub has_breakpoint: u8,
    pub branch_target: u64,
    pub has_branch_target: u8,
    pub changed_since_last_step: u8,
}

pub type emu_automation_event_callback_t =
    Option<unsafe extern "C" fn(event: *const emu_automation_event_t, user_data: *mut c_void)>;

unsafe extern "C" {
    pub fn emu_automation_abi_version() -> u32;
    pub fn emu_automation_result_name(result: emu_automation_result_t) -> *const c_char;
    pub fn emu_automation_machine_destroy(machine: *mut emu_automation_machine_t);
    pub fn emu_automation_machine_describe(
        machine: *mut emu_automation_machine_t,
        out_descriptor: *mut emu_automation_machine_descriptor_t,
    ) -> emu_automation_result_t;
    pub fn emu_automation_machine_capabilities(
        machine: *mut emu_automation_machine_t,
        out_capabilities: *mut emu_automation_capabilities_t,
    ) -> emu_automation_result_t;
    pub fn emu_automation_machine_character_mapping_count(
        machine: *mut emu_automation_machine_t,
        out_count: *mut usize,
    ) -> emu_automation_result_t;
    pub fn emu_automation_machine_character_mapping_descriptor(
        machine: *mut emu_automation_machine_t,
        index: usize,
        out_descriptor: *mut emu_automation_character_mapping_descriptor_t,
    ) -> emu_automation_result_t;
    pub fn emu_automation_machine_pause(
        machine: *mut emu_automation_machine_t,
    ) -> emu_automation_result_t;
    pub fn emu_automation_machine_resume(
        machine: *mut emu_automation_machine_t,
    ) -> emu_automation_result_t;
    pub fn emu_automation_machine_reset(
        machine: *mut emu_automation_machine_t,
        kind: emu_automation_reset_kind_t,
    ) -> emu_automation_result_t;
    pub fn emu_automation_machine_step_frame(
        machine: *mut emu_automation_machine_t,
    ) -> emu_automation_result_t;
    pub fn emu_automation_machine_run_frames(
        machine: *mut emu_automation_machine_t,
        frame_count: u64,
    ) -> emu_automation_result_t;
    pub fn emu_automation_screen_framebuffer(
        machine: *mut emu_automation_machine_t,
        out_snapshot: *mut emu_automation_framebuffer_snapshot_t,
    ) -> emu_automation_result_t;
    pub fn emu_automation_framebuffer_release(
        machine: *mut emu_automation_machine_t,
        snapshot: *mut emu_automation_framebuffer_snapshot_t,
    );
    pub fn emu_automation_screen_text_grid(
        machine: *mut emu_automation_machine_t,
        region_id: *const c_char,
        out_snapshot: *mut emu_automation_text_grid_snapshot_t,
    ) -> emu_automation_result_t;
    pub fn emu_automation_memory_read(
        machine: *mut emu_automation_machine_t,
        address: u64,
        out_bytes: *mut u8,
        size: usize,
    ) -> emu_automation_result_t;
    pub fn emu_automation_memory_write(
        machine: *mut emu_automation_machine_t,
        address: u64,
        bytes: *const u8,
        size: usize,
    ) -> emu_automation_result_t;
    pub fn emu_automation_execution_program_counter(
        machine: *mut emu_automation_machine_t,
        out_program_counter: *mut u64,
    ) -> emu_automation_result_t;
    pub fn emu_automation_execution_frame_metadata(
        machine: *mut emu_automation_machine_t,
        out_metadata: *mut emu_automation_frame_metadata_t,
    ) -> emu_automation_result_t;
    pub fn emu_automation_execution_current_instruction(
        machine: *mut emu_automation_machine_t,
        out_instruction: *mut emu_automation_instruction_t,
    ) -> emu_automation_result_t;
    pub fn emu_automation_register_count(
        machine: *mut emu_automation_machine_t,
        out_count: *mut usize,
    ) -> emu_automation_result_t;
    pub fn emu_automation_register_read(
        machine: *mut emu_automation_machine_t,
        out_registers: *mut emu_automation_register_value_t,
        register_capacity: usize,
        out_register_count: *mut usize,
    ) -> emu_automation_result_t;
    pub fn emu_automation_register_write(
        machine: *mut emu_automation_machine_t,
        register_name: *const c_char,
        value: u64,
    ) -> emu_automation_result_t;
    pub fn emu_automation_screen_text_view_count(
        machine: *mut emu_automation_machine_t,
        out_count: *mut usize,
    ) -> emu_automation_result_t;
    pub fn emu_automation_screen_text_view_descriptor(
        machine: *mut emu_automation_machine_t,
        index: usize,
        out_descriptor: *mut emu_automation_text_view_descriptor_t,
    ) -> emu_automation_result_t;
    pub fn emu_automation_text_grid_release(
        machine: *mut emu_automation_machine_t,
        snapshot: *mut emu_automation_text_grid_snapshot_t,
    );
    pub fn emu_automation_input_key(
        machine: *mut emu_automation_machine_t,
        event: *const emu_automation_key_event_t,
    ) -> emu_automation_result_t;
    pub fn emu_automation_input_controller_button(
        machine: *mut emu_automation_machine_t,
        event: *const emu_automation_controller_button_event_t,
    ) -> emu_automation_result_t;
    pub fn emu_automation_events_poll(
        machine: *mut emu_automation_machine_t,
        after_sequence: u64,
        out_event: *mut emu_automation_event_t,
    ) -> emu_automation_result_t;
    pub fn emu_automation_events_dispatch_available(
        machine: *mut emu_automation_machine_t,
        inout_after_sequence: *mut u64,
        max_events: usize,
        callback: emu_automation_event_callback_t,
        user_data: *mut c_void,
        out_dispatch_count: *mut usize,
    ) -> emu_automation_result_t;
    pub fn emu_automation_events_dispatch_matching(
        machine: *mut emu_automation_machine_t,
        inout_after_sequence: *mut u64,
        event_type: emu_automation_event_type_t,
        max_events: usize,
        callback: emu_automation_event_callback_t,
        user_data: *mut c_void,
        out_dispatch_count: *mut usize,
    ) -> emu_automation_result_t;
    pub fn emu_automation_subscription_create(
        machine: *mut emu_automation_machine_t,
        event_type: emu_automation_event_type_t,
        after_sequence: u64,
        callback: emu_automation_event_callback_t,
        user_data: *mut c_void,
        out_subscription: *mut *mut emu_automation_subscription_t,
    ) -> emu_automation_result_t;
    pub fn emu_automation_subscription_dispatch_available(
        subscription: *mut emu_automation_subscription_t,
        max_events: usize,
        out_dispatch_count: *mut usize,
    ) -> emu_automation_result_t;
    pub fn emu_automation_subscription_after_sequence(
        subscription: *const emu_automation_subscription_t,
    ) -> u64;
    pub fn emu_automation_subscription_set_after_sequence(
        subscription: *mut emu_automation_subscription_t,
        after_sequence: u64,
    ) -> emu_automation_result_t;
    pub fn emu_automation_subscription_destroy(
        subscription: *mut emu_automation_subscription_t,
    );
    pub fn emu_automation_event_release(
        machine: *mut emu_automation_machine_t,
        event: *mut emu_automation_event_t,
    );
}
