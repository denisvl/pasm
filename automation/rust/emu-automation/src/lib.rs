use std::cell::RefCell;
use std::collections::BTreeSet;
use std::ffi::{CStr, CString};
use std::fmt;
use std::path::Path;
use std::ptr::NonNull;
use std::sync::Arc;

#[cfg(windows)]
use std::os::windows::ffi::OsStrExt;

#[cfg(feature = "serde")]
use serde::{Deserialize, Serialize};

pub use emu_automation_sys as sys;

#[cfg(feature = "serde")]
mod serde_support {
    use super::sys;
    use serde::{Deserialize, Deserializer, Serializer};

    pub mod execution_state {
        use super::*;
        pub fn serialize<S>(value: &sys::emu_automation_execution_state_t, serializer: S) -> Result<S::Ok, S::Error>
        where
            S: Serializer,
        {
            serializer.serialize_i32(*value as i32)
        }
        pub fn deserialize<'de, D>(deserializer: D) -> Result<sys::emu_automation_execution_state_t, D::Error>
        where
            D: Deserializer<'de>,
        {
            match i32::deserialize(deserializer)? {
                0 => Ok(sys::emu_automation_execution_state_t::EMU_AUTOMATION_EXECUTION_STOPPED),
                1 => Ok(sys::emu_automation_execution_state_t::EMU_AUTOMATION_EXECUTION_RUNNING),
                2 => Ok(sys::emu_automation_execution_state_t::EMU_AUTOMATION_EXECUTION_PAUSED),
                other => Err(serde::de::Error::custom(format!("invalid execution state value: {other}"))),
            }
        }
    }

    pub mod pixel_format {
        use super::*;
        pub fn serialize<S>(value: &sys::emu_automation_pixel_format_t, serializer: S) -> Result<S::Ok, S::Error>
        where
            S: Serializer,
        {
            serializer.serialize_i32(*value as i32)
        }
        pub fn deserialize<'de, D>(deserializer: D) -> Result<sys::emu_automation_pixel_format_t, D::Error>
        where
            D: Deserializer<'de>,
        {
            match i32::deserialize(deserializer)? {
                0 => Ok(sys::emu_automation_pixel_format_t::EMU_AUTOMATION_PIXEL_FORMAT_UNKNOWN),
                1 => Ok(sys::emu_automation_pixel_format_t::EMU_AUTOMATION_PIXEL_FORMAT_RGBA8888),
                2 => Ok(sys::emu_automation_pixel_format_t::EMU_AUTOMATION_PIXEL_FORMAT_BGRA8888),
                3 => Ok(sys::emu_automation_pixel_format_t::EMU_AUTOMATION_PIXEL_FORMAT_RGB565),
                other => Err(serde::de::Error::custom(format!("invalid pixel format value: {other}"))),
            }
        }
    }

    pub mod event_type {
        use super::*;
        pub fn serialize<S>(value: &sys::emu_automation_event_type_t, serializer: S) -> Result<S::Ok, S::Error>
        where
            S: Serializer,
        {
            serializer.serialize_i32(*value as i32)
        }
        pub fn deserialize<'de, D>(deserializer: D) -> Result<sys::emu_automation_event_type_t, D::Error>
        where
            D: Deserializer<'de>,
        {
            match i32::deserialize(deserializer)? {
                0 => Ok(sys::emu_automation_event_type_t::EMU_AUTOMATION_EVENT_NONE),
                1 => Ok(sys::emu_automation_event_type_t::EMU_AUTOMATION_EVENT_FRAME_COMPLETED),
                2 => Ok(sys::emu_automation_event_type_t::EMU_AUTOMATION_EVENT_MACHINE_RESET),
                3 => Ok(sys::emu_automation_event_type_t::EMU_AUTOMATION_EVENT_EXECUTION_STATE_CHANGED),
                4 => Ok(sys::emu_automation_event_type_t::EMU_AUTOMATION_EVENT_INPUT_SUBMITTED),
                5 => Ok(sys::emu_automation_event_type_t::EMU_AUTOMATION_EVENT_SCREEN_CHANGED),
                6 => Ok(sys::emu_automation_event_type_t::EMU_AUTOMATION_EVENT_TEXT_CHANGED),
                7 => Ok(sys::emu_automation_event_type_t::EMU_AUTOMATION_EVENT_MEDIA_ACTIVITY),
                8 => Ok(sys::emu_automation_event_type_t::EMU_AUTOMATION_EVENT_DEBUG_MESSAGE),
                9 => Ok(sys::emu_automation_event_type_t::EMU_AUTOMATION_EVENT_ERROR),
                other => Err(serde::de::Error::custom(format!("invalid event type value: {other}"))),
            }
        }
    }

    pub mod input_action {
        use super::*;
        pub fn serialize<S>(value: &sys::emu_automation_input_action_t, serializer: S) -> Result<S::Ok, S::Error>
        where
            S: Serializer,
        {
            serializer.serialize_i32(*value as i32)
        }
        pub fn deserialize<'de, D>(deserializer: D) -> Result<sys::emu_automation_input_action_t, D::Error>
        where
            D: Deserializer<'de>,
        {
            match i32::deserialize(deserializer)? {
                0 => Ok(sys::emu_automation_input_action_t::EMU_AUTOMATION_INPUT_RELEASE),
                1 => Ok(sys::emu_automation_input_action_t::EMU_AUTOMATION_INPUT_PRESS),
                other => Err(serde::de::Error::custom(format!("invalid input action value: {other}"))),
            }
        }
    }
}

type AbiVersionFn = unsafe extern "C" fn() -> u32;
type ResultNameFn =
    unsafe extern "C" fn(sys::emu_automation_result_t) -> *const std::ffi::c_char;
type MachineDestroyFn = unsafe extern "C" fn(*mut sys::emu_automation_machine_t);
type MachineDescribeFn = unsafe extern "C" fn(
    *mut sys::emu_automation_machine_t,
    *mut sys::emu_automation_machine_descriptor_t,
) -> sys::emu_automation_result_t;
type MachineCapabilitiesFn = unsafe extern "C" fn(
    *mut sys::emu_automation_machine_t,
    *mut sys::emu_automation_capabilities_t,
) -> sys::emu_automation_result_t;
type MachineCharacterMappingCountFn = unsafe extern "C" fn(
    *mut sys::emu_automation_machine_t,
    *mut usize,
) -> sys::emu_automation_result_t;
type MachineCharacterMappingDescriptorFn = unsafe extern "C" fn(
    *mut sys::emu_automation_machine_t,
    usize,
    *mut sys::emu_automation_character_mapping_descriptor_t,
) -> sys::emu_automation_result_t;
type MachinePauseFn =
    unsafe extern "C" fn(*mut sys::emu_automation_machine_t) -> sys::emu_automation_result_t;
type MachineResumeFn =
    unsafe extern "C" fn(*mut sys::emu_automation_machine_t) -> sys::emu_automation_result_t;
type MachineResetFn = unsafe extern "C" fn(
    *mut sys::emu_automation_machine_t,
    sys::emu_automation_reset_kind_t,
) -> sys::emu_automation_result_t;
type MachineStepFrameFn =
    unsafe extern "C" fn(*mut sys::emu_automation_machine_t) -> sys::emu_automation_result_t;
type MachineRunFramesFn = unsafe extern "C" fn(
    *mut sys::emu_automation_machine_t,
    u64,
) -> sys::emu_automation_result_t;
type ScreenFramebufferFn = unsafe extern "C" fn(
    *mut sys::emu_automation_machine_t,
    *mut sys::emu_automation_framebuffer_snapshot_t,
) -> sys::emu_automation_result_t;
type FramebufferReleaseFn = unsafe extern "C" fn(
    *mut sys::emu_automation_machine_t,
    *mut sys::emu_automation_framebuffer_snapshot_t,
);
type ScreenTextGridFn = unsafe extern "C" fn(
    *mut sys::emu_automation_machine_t,
    *const std::ffi::c_char,
    *mut sys::emu_automation_text_grid_snapshot_t,
) -> sys::emu_automation_result_t;
type MemoryReadFn = unsafe extern "C" fn(
    *mut sys::emu_automation_machine_t,
    u64,
    *mut u8,
    usize,
) -> sys::emu_automation_result_t;
type MemoryWriteFn = unsafe extern "C" fn(
    *mut sys::emu_automation_machine_t,
    u64,
    *const u8,
    usize,
) -> sys::emu_automation_result_t;
type ExecutionProgramCounterFn = unsafe extern "C" fn(
    *mut sys::emu_automation_machine_t,
    *mut u64,
) -> sys::emu_automation_result_t;
type ExecutionFrameMetadataFn = unsafe extern "C" fn(
    *mut sys::emu_automation_machine_t,
    *mut sys::emu_automation_frame_metadata_t,
) -> sys::emu_automation_result_t;
type ExecutionCurrentInstructionFn = unsafe extern "C" fn(
    *mut sys::emu_automation_machine_t,
    *mut sys::emu_automation_instruction_t,
) -> sys::emu_automation_result_t;
type RegisterCountFn = unsafe extern "C" fn(
    *mut sys::emu_automation_machine_t,
    *mut usize,
) -> sys::emu_automation_result_t;
type RegisterReadFn = unsafe extern "C" fn(
    *mut sys::emu_automation_machine_t,
    *mut sys::emu_automation_register_value_t,
    usize,
    *mut usize,
) -> sys::emu_automation_result_t;
type RegisterWriteFn = unsafe extern "C" fn(
    *mut sys::emu_automation_machine_t,
    *const std::ffi::c_char,
    u64,
) -> sys::emu_automation_result_t;
type ScreenTextViewCountFn = unsafe extern "C" fn(
    *mut sys::emu_automation_machine_t,
    *mut usize,
) -> sys::emu_automation_result_t;
type ScreenTextViewDescriptorFn = unsafe extern "C" fn(
    *mut sys::emu_automation_machine_t,
    usize,
    *mut sys::emu_automation_text_view_descriptor_t,
) -> sys::emu_automation_result_t;
type TextGridReleaseFn = unsafe extern "C" fn(
    *mut sys::emu_automation_machine_t,
    *mut sys::emu_automation_text_grid_snapshot_t,
);
type InputKeyFn = unsafe extern "C" fn(
    *mut sys::emu_automation_machine_t,
    *const sys::emu_automation_key_event_t,
) -> sys::emu_automation_result_t;
type InputControllerButtonFn = unsafe extern "C" fn(
    *mut sys::emu_automation_machine_t,
    *const sys::emu_automation_controller_button_event_t,
) -> sys::emu_automation_result_t;
type EventsPollFn = unsafe extern "C" fn(
    *mut sys::emu_automation_machine_t,
    u64,
    *mut sys::emu_automation_event_t,
) -> sys::emu_automation_result_t;
type EventsDispatchMatchingFn = unsafe extern "C" fn(
    *mut sys::emu_automation_machine_t,
    *mut u64,
    sys::emu_automation_event_type_t,
    usize,
    sys::emu_automation_event_callback_t,
    *mut std::ffi::c_void,
    *mut usize,
) -> sys::emu_automation_result_t;
type SubscriptionCreateFn = unsafe extern "C" fn(
    *mut sys::emu_automation_machine_t,
    sys::emu_automation_event_type_t,
    u64,
    sys::emu_automation_event_callback_t,
    *mut std::ffi::c_void,
    *mut *mut sys::emu_automation_subscription_t,
) -> sys::emu_automation_result_t;
type SubscriptionDispatchAvailableFn = unsafe extern "C" fn(
    *mut sys::emu_automation_subscription_t,
    usize,
    *mut usize,
) -> sys::emu_automation_result_t;
type SubscriptionAfterSequenceFn =
    unsafe extern "C" fn(*const sys::emu_automation_subscription_t) -> u64;
type SubscriptionSetAfterSequenceFn = unsafe extern "C" fn(
    *mut sys::emu_automation_subscription_t,
    u64,
) -> sys::emu_automation_result_t;
type SubscriptionDestroyFn =
    unsafe extern "C" fn(*mut sys::emu_automation_subscription_t);
type EventReleaseFn = unsafe extern "C" fn(
    *mut sys::emu_automation_machine_t,
    *mut sys::emu_automation_event_t,
);

#[derive(Clone)]
struct AutomationApi {
    result_name: ResultNameFn,
    machine_destroy: MachineDestroyFn,
    machine_describe: MachineDescribeFn,
    machine_capabilities: MachineCapabilitiesFn,
    machine_character_mapping_count: MachineCharacterMappingCountFn,
    machine_character_mapping_descriptor: MachineCharacterMappingDescriptorFn,
    machine_pause: MachinePauseFn,
    machine_resume: MachineResumeFn,
    machine_reset: MachineResetFn,
    machine_step_frame: MachineStepFrameFn,
    machine_run_frames: MachineRunFramesFn,
    screen_framebuffer: ScreenFramebufferFn,
    framebuffer_release: FramebufferReleaseFn,
    screen_text_grid: ScreenTextGridFn,
    memory_read: MemoryReadFn,
    memory_write: MemoryWriteFn,
    execution_program_counter: ExecutionProgramCounterFn,
    execution_frame_metadata: ExecutionFrameMetadataFn,
    execution_current_instruction: ExecutionCurrentInstructionFn,
    register_count: RegisterCountFn,
    register_read: RegisterReadFn,
    register_write: RegisterWriteFn,
    screen_text_view_count: ScreenTextViewCountFn,
    screen_text_view_descriptor: ScreenTextViewDescriptorFn,
    text_grid_release: TextGridReleaseFn,
    input_key: InputKeyFn,
    input_controller_button: InputControllerButtonFn,
    events_poll: EventsPollFn,
    events_dispatch_matching: EventsDispatchMatchingFn,
    subscription_create: SubscriptionCreateFn,
    subscription_dispatch_available: SubscriptionDispatchAvailableFn,
    subscription_after_sequence: SubscriptionAfterSequenceFn,
    subscription_set_after_sequence: SubscriptionSetAfterSequenceFn,
    subscription_destroy: SubscriptionDestroyFn,
    event_release: EventReleaseFn,
}

impl AutomationApi {
    fn linked() -> Result<Arc<Self>, LoadError> {
        let abi_version = unsafe { sys::emu_automation_abi_version() };
        if abi_version != sys::EMU_AUTOMATION_ABI_VERSION {
            return Err(LoadError::AbiVersion {
                expected: sys::EMU_AUTOMATION_ABI_VERSION,
                actual: abi_version,
            });
        }
        Ok(Arc::new(Self {
            result_name: sys::emu_automation_result_name,
            machine_destroy: sys::emu_automation_machine_destroy,
            machine_describe: sys::emu_automation_machine_describe,
            machine_capabilities: sys::emu_automation_machine_capabilities,
            machine_character_mapping_count: sys::emu_automation_machine_character_mapping_count,
            machine_character_mapping_descriptor:
                sys::emu_automation_machine_character_mapping_descriptor,
            machine_pause: sys::emu_automation_machine_pause,
            machine_resume: sys::emu_automation_machine_resume,
            machine_reset: sys::emu_automation_machine_reset,
            machine_step_frame: sys::emu_automation_machine_step_frame,
            machine_run_frames: sys::emu_automation_machine_run_frames,
            screen_framebuffer: sys::emu_automation_screen_framebuffer,
            framebuffer_release: sys::emu_automation_framebuffer_release,
            screen_text_grid: sys::emu_automation_screen_text_grid,
            memory_read: sys::emu_automation_memory_read,
            memory_write: sys::emu_automation_memory_write,
            execution_program_counter: sys::emu_automation_execution_program_counter,
            execution_frame_metadata: sys::emu_automation_execution_frame_metadata,
            execution_current_instruction: sys::emu_automation_execution_current_instruction,
            register_count: sys::emu_automation_register_count,
            register_read: sys::emu_automation_register_read,
            register_write: sys::emu_automation_register_write,
            screen_text_view_count: sys::emu_automation_screen_text_view_count,
            screen_text_view_descriptor: sys::emu_automation_screen_text_view_descriptor,
            text_grid_release: sys::emu_automation_text_grid_release,
            input_key: sys::emu_automation_input_key,
            input_controller_button: sys::emu_automation_input_controller_button,
            events_poll: sys::emu_automation_events_poll,
            events_dispatch_matching: sys::emu_automation_events_dispatch_matching,
            subscription_create: sys::emu_automation_subscription_create,
            subscription_dispatch_available: sys::emu_automation_subscription_dispatch_available,
            subscription_after_sequence: sys::emu_automation_subscription_after_sequence,
            subscription_set_after_sequence: sys::emu_automation_subscription_set_after_sequence,
            subscription_destroy: sys::emu_automation_subscription_destroy,
            event_release: sys::emu_automation_event_release,
        }))
    }
}

#[cfg(unix)]
struct DynamicLibrary {
    handle: *mut std::ffi::c_void,
}

#[cfg(windows)]
struct DynamicLibrary {
    handle: *mut std::ffi::c_void,
}

#[cfg(unix)]
impl Drop for DynamicLibrary {
    fn drop(&mut self) {
        unsafe { dlclose(self.handle) };
    }
}

#[cfg(windows)]
impl Drop for DynamicLibrary {
    fn drop(&mut self) {
        unsafe { FreeLibrary(self.handle) };
    }
}

#[cfg(unix)]
impl DynamicLibrary {
    fn open(path: &Path) -> Result<Self, LoadError> {
        let path = CString::new(path.as_os_str().as_encoded_bytes())
            .map_err(|_| LoadError::InvalidPath)?;
        let handle = unsafe { dlopen(path.as_ptr(), RTLD_NOW) };
        if handle.is_null() {
            return Err(LoadError::Dlopen(last_dl_error()));
        }
        Ok(Self { handle })
    }

    unsafe fn symbol<T>(&self, name: &[u8]) -> Result<T, LoadError>
    where
        T: Copy,
    {
        let symbol = dlsym(self.handle, name.as_ptr().cast());
        if symbol.is_null() {
            return Err(LoadError::MissingSymbol(
                String::from_utf8_lossy(&name[..name.len() - 1]).into_owned(),
            ));
        }
        Ok(std::mem::transmute_copy(&symbol))
    }
}

#[cfg(windows)]
impl DynamicLibrary {
    fn open(path: &Path) -> Result<Self, LoadError> {
        let mut wide: Vec<u16> = path.as_os_str().encode_wide().collect();
        wide.push(0);
        let handle = unsafe { LoadLibraryW(wide.as_ptr()) };
        if handle.is_null() {
            return Err(LoadError::Dlopen(last_dl_error()));
        }
        Ok(Self { handle })
    }

    unsafe fn symbol<T>(&self, name: &[u8]) -> Result<T, LoadError>
    where
        T: Copy,
    {
        let symbol = GetProcAddress(self.handle, name.as_ptr().cast());
        if symbol.is_null() {
            return Err(LoadError::MissingSymbol(
                String::from_utf8_lossy(&name[..name.len() - 1]).into_owned(),
            ));
        }
        Ok(std::mem::transmute_copy(&symbol))
    }
}

#[cfg(unix)]
struct LoadedApi {
    api: Arc<AutomationApi>,
    _library: DynamicLibrary,
}

#[cfg(windows)]
struct LoadedApi {
    api: Arc<AutomationApi>,
    _library: DynamicLibrary,
}

#[cfg(unix)]
impl LoadedApi {
    fn open(path: &Path) -> Result<Self, LoadError> {
        let library = DynamicLibrary::open(path)?;
        let abi_version: AbiVersionFn = unsafe { library.symbol(b"emu_automation_abi_version\0")? };
        let actual = unsafe { abi_version() };
        if actual != sys::EMU_AUTOMATION_ABI_VERSION {
            return Err(LoadError::AbiVersion {
                expected: sys::EMU_AUTOMATION_ABI_VERSION,
                actual,
            });
        }
        let api = AutomationApi {
            result_name: unsafe { library.symbol(b"emu_automation_result_name\0")? },
            machine_destroy: unsafe { library.symbol(b"emu_automation_machine_destroy\0")? },
            machine_describe: unsafe { library.symbol(b"emu_automation_machine_describe\0")? },
            machine_capabilities: unsafe { library.symbol(b"emu_automation_machine_capabilities\0")? },
            machine_character_mapping_count: unsafe {
                library.symbol(b"emu_automation_machine_character_mapping_count\0")?
            },
            machine_character_mapping_descriptor: unsafe {
                library.symbol(b"emu_automation_machine_character_mapping_descriptor\0")?
            },
            machine_pause: unsafe { library.symbol(b"emu_automation_machine_pause\0")? },
            machine_resume: unsafe { library.symbol(b"emu_automation_machine_resume\0")? },
            machine_reset: unsafe { library.symbol(b"emu_automation_machine_reset\0")? },
            machine_step_frame: unsafe { library.symbol(b"emu_automation_machine_step_frame\0")? },
            machine_run_frames: unsafe { library.symbol(b"emu_automation_machine_run_frames\0")? },
            screen_framebuffer: unsafe { library.symbol(b"emu_automation_screen_framebuffer\0")? },
            framebuffer_release: unsafe { library.symbol(b"emu_automation_framebuffer_release\0")? },
            screen_text_grid: unsafe { library.symbol(b"emu_automation_screen_text_grid\0")? },
            memory_read: unsafe { library.symbol(b"emu_automation_memory_read\0")? },
            memory_write: unsafe { library.symbol(b"emu_automation_memory_write\0")? },
            execution_program_counter: unsafe { library.symbol(b"emu_automation_execution_program_counter\0")? },
            execution_frame_metadata: unsafe { library.symbol(b"emu_automation_execution_frame_metadata\0")? },
            execution_current_instruction: unsafe { library.symbol(b"emu_automation_execution_current_instruction\0")? },
            register_count: unsafe { library.symbol(b"emu_automation_register_count\0")? },
            register_read: unsafe { library.symbol(b"emu_automation_register_read\0")? },
            register_write: unsafe { library.symbol(b"emu_automation_register_write\0")? },
            screen_text_view_count: unsafe { library.symbol(b"emu_automation_screen_text_view_count\0")? },
            screen_text_view_descriptor: unsafe { library.symbol(b"emu_automation_screen_text_view_descriptor\0")? },
            text_grid_release: unsafe { library.symbol(b"emu_automation_text_grid_release\0")? },
            input_key: unsafe { library.symbol(b"emu_automation_input_key\0")? },
            input_controller_button: unsafe { library.symbol(b"emu_automation_input_controller_button\0")? },
            events_poll: unsafe { library.symbol(b"emu_automation_events_poll\0")? },
            events_dispatch_matching: unsafe { library.symbol(b"emu_automation_events_dispatch_matching\0")? },
            subscription_create: unsafe { library.symbol(b"emu_automation_subscription_create\0")? },
            subscription_dispatch_available: unsafe {
                library.symbol(b"emu_automation_subscription_dispatch_available\0")?
            },
            subscription_after_sequence: unsafe {
                library.symbol(b"emu_automation_subscription_after_sequence\0")?
            },
            subscription_set_after_sequence: unsafe {
                library.symbol(b"emu_automation_subscription_set_after_sequence\0")?
            },
            subscription_destroy: unsafe { library.symbol(b"emu_automation_subscription_destroy\0")? },
            event_release: unsafe { library.symbol(b"emu_automation_event_release\0")? },
        };
        Ok(Self {
            api: Arc::new(api),
            _library: library,
        })
    }

    unsafe fn symbol<T>(&self, name: &[u8]) -> Result<T, LoadError>
    where
        T: Copy,
    {
        self._library.symbol(name)
    }
}

#[cfg(windows)]
impl LoadedApi {
    fn open(path: &Path) -> Result<Self, LoadError> {
        let library = DynamicLibrary::open(path)?;
        let abi_version: AbiVersionFn =
            unsafe { library.symbol(b"emu_automation_abi_version\0")? };
        let actual = unsafe { abi_version() };
        if actual != sys::EMU_AUTOMATION_ABI_VERSION {
            return Err(LoadError::AbiVersion {
                expected: sys::EMU_AUTOMATION_ABI_VERSION,
                actual,
            });
        }
        let api = AutomationApi {
            result_name: unsafe { library.symbol(b"emu_automation_result_name\0")? },
            machine_destroy: unsafe { library.symbol(b"emu_automation_machine_destroy\0")? },
            machine_describe: unsafe { library.symbol(b"emu_automation_machine_describe\0")? },
            machine_capabilities: unsafe {
                library.symbol(b"emu_automation_machine_capabilities\0")?
            },
            machine_character_mapping_count: unsafe {
                library.symbol(b"emu_automation_machine_character_mapping_count\0")?
            },
            machine_character_mapping_descriptor: unsafe {
                library.symbol(b"emu_automation_machine_character_mapping_descriptor\0")?
            },
            machine_pause: unsafe { library.symbol(b"emu_automation_machine_pause\0")? },
            machine_resume: unsafe { library.symbol(b"emu_automation_machine_resume\0")? },
            machine_reset: unsafe { library.symbol(b"emu_automation_machine_reset\0")? },
            machine_step_frame: unsafe { library.symbol(b"emu_automation_machine_step_frame\0")? },
            machine_run_frames: unsafe { library.symbol(b"emu_automation_machine_run_frames\0")? },
            screen_framebuffer: unsafe {
                library.symbol(b"emu_automation_screen_framebuffer\0")?
            },
            framebuffer_release: unsafe {
                library.symbol(b"emu_automation_framebuffer_release\0")?
            },
            screen_text_grid: unsafe { library.symbol(b"emu_automation_screen_text_grid\0")? },
            memory_read: unsafe { library.symbol(b"emu_automation_memory_read\0")? },
            memory_write: unsafe { library.symbol(b"emu_automation_memory_write\0")? },
            execution_program_counter: unsafe {
                library.symbol(b"emu_automation_execution_program_counter\0")?
            },
            execution_frame_metadata: unsafe {
                library.symbol(b"emu_automation_execution_frame_metadata\0")?
            },
            execution_current_instruction: unsafe {
                library.symbol(b"emu_automation_execution_current_instruction\0")?
            },
            register_count: unsafe { library.symbol(b"emu_automation_register_count\0")? },
            register_read: unsafe { library.symbol(b"emu_automation_register_read\0")? },
            register_write: unsafe { library.symbol(b"emu_automation_register_write\0")? },
            screen_text_view_count: unsafe {
                library.symbol(b"emu_automation_screen_text_view_count\0")?
            },
            screen_text_view_descriptor: unsafe {
                library.symbol(b"emu_automation_screen_text_view_descriptor\0")?
            },
            text_grid_release: unsafe { library.symbol(b"emu_automation_text_grid_release\0")? },
            input_key: unsafe { library.symbol(b"emu_automation_input_key\0")? },
            input_controller_button: unsafe {
                library.symbol(b"emu_automation_input_controller_button\0")?
            },
            events_poll: unsafe { library.symbol(b"emu_automation_events_poll\0")? },
            events_dispatch_matching: unsafe {
                library.symbol(b"emu_automation_events_dispatch_matching\0")?
            },
            subscription_create: unsafe {
                library.symbol(b"emu_automation_subscription_create\0")?
            },
            subscription_dispatch_available: unsafe {
                library.symbol(b"emu_automation_subscription_dispatch_available\0")?
            },
            subscription_after_sequence: unsafe {
                library.symbol(b"emu_automation_subscription_after_sequence\0")?
            },
            subscription_set_after_sequence: unsafe {
                library.symbol(b"emu_automation_subscription_set_after_sequence\0")?
            },
            subscription_destroy: unsafe {
                library.symbol(b"emu_automation_subscription_destroy\0")?
            },
            event_release: unsafe { library.symbol(b"emu_automation_event_release\0")? },
        };
        Ok(Self {
            api: Arc::new(api),
            _library: library,
        })
    }

    unsafe fn symbol<T>(&self, name: &[u8]) -> Result<T, LoadError>
    where
        T: Copy,
    {
        self._library.symbol(name)
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Error {
    pub operation: &'static str,
    pub code: sys::emu_automation_result_t,
    pub name: String,
}

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{} failed: {} ({:?})", self.operation, self.name, self.code)
    }
}

impl std::error::Error for Error {}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct WaitTimeoutError {
    pub description: String,
    pub frames_elapsed: u64,
    pub last_observation: Option<String>,
}

impl fmt::Display for WaitTimeoutError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            f,
            "Timed out waiting for {} after {} frames",
            self.description,
            self.frames_elapsed,
        )?;
        if let Some(last_observation) = &self.last_observation {
            write!(f, "; last observed: {last_observation}")?;
        }
        Ok(())
    }
}

impl std::error::Error for WaitTimeoutError {}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum WaitError {
    Automation(Error),
    Timeout(WaitTimeoutError),
}

impl fmt::Display for WaitError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Automation(error) => error.fmt(f),
            Self::Timeout(error) => error.fmt(f),
        }
    }
}

impl std::error::Error for WaitError {}

impl From<Error> for WaitError {
    fn from(value: Error) -> Self {
        Self::Automation(value)
    }
}

impl From<WaitTimeoutError> for WaitError {
    fn from(value: WaitTimeoutError) -> Self {
        Self::Timeout(value)
    }
}

type ConditionPredicate<T> = dyn FnMut(&Machine) -> Result<Option<T>, Error> + 'static;

pub struct Condition<T> {
    description: String,
    predicate: Box<ConditionPredicate<T>>,
}

impl<T> Condition<T> {
    pub fn new(
        description: impl Into<String>,
        predicate: impl FnMut(&Machine) -> Result<Option<T>, Error> + 'static,
    ) -> Self {
        Self {
            description: description.into(),
            predicate: Box::new(predicate),
        }
    }
}

impl<T: 'static> Condition<T> {
    pub fn or(self, other: Condition<T>) -> Condition<T> {
        let mut left = self.predicate;
        let mut right = other.predicate;
        Condition::new("any condition", move |machine| {
            if let Some(value) = left(machine)? {
                return Ok(Some(value));
            }
            right(machine)
        })
    }

    pub fn and<U: 'static>(self, other: Condition<U>) -> Condition<(T, U)> {
        let mut left = self.predicate;
        let mut right = other.predicate;
        Condition::new("all conditions", move |machine| {
            let Some(left_value) = left(machine)? else {
                return Ok(None);
            };
            let Some(right_value) = right(machine)? else {
                return Ok(None);
            };
            Ok(Some((left_value, right_value)))
        })
    }

    pub fn any(conditions: Vec<Condition<T>>) -> Condition<T> {
        assert!(!conditions.is_empty(), "at least one condition is required");
        let mut predicates = conditions
            .into_iter()
            .map(|condition| condition.predicate)
            .collect::<Vec<_>>();
        Condition::new("any condition", move |machine| {
            for predicate in &mut predicates {
                if let Some(value) = predicate(machine)? {
                    return Ok(Some(value));
                }
            }
            Ok(None)
        })
    }

    pub fn all(conditions: Vec<Condition<T>>) -> Condition<Vec<T>> {
        assert!(!conditions.is_empty(), "at least one condition is required");
        let mut predicates = conditions
            .into_iter()
            .map(|condition| condition.predicate)
            .collect::<Vec<_>>();
        Condition::new("all conditions", move |machine| {
            let mut results = Vec::with_capacity(predicates.len());
            for predicate in &mut predicates {
                let Some(value) = predicate(machine)? else {
                    return Ok(None);
                };
                results.push(value);
            }
            Ok(Some(results))
        })
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum LoadError {
    InvalidPath,
    AbiVersion { expected: u32, actual: u32 },
    MissingSymbol(String),
    Dlopen(String),
    Automation(Error),
    UnsupportedPlatform,
}

impl fmt::Display for LoadError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::InvalidPath => write!(f, "library path contains NUL"),
            Self::AbiVersion { expected, actual } => {
                write!(f, "automation ABI version mismatch: expected {expected}, got {actual}")
            }
            Self::MissingSymbol(symbol) => write!(f, "missing required symbol: {symbol}"),
            Self::Dlopen(message) => write!(f, "failed to load shared library: {message}"),
            Self::Automation(error) => error.fmt(f),
            Self::UnsupportedPlatform => {
                write!(f, "dynamic loading is currently only supported on Unix and Windows")
            }
        }
    }
}

impl std::error::Error for LoadError {}

#[cfg_attr(feature = "serde", derive(Serialize, Deserialize))]
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Capabilities {
    pub feature_bits: u64,
}

#[cfg_attr(feature = "serde", derive(Serialize, Deserialize))]
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct MachineDescriptor {
    pub machine_id: String,
    pub system_id: String,
    pub model_id: String,
    pub region: String,
    pub video_standard: String,
    pub adapter_version: String,
    pub configured_memory_bytes: u64,
    pub capabilities: Capabilities,
}

#[cfg_attr(feature = "serde", derive(Serialize, Deserialize))]
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CharacterMappingDescriptor {
    pub device_id: String,
    pub unicode_codepoint: u32,
    pub native_code: u32,
    pub key_id: String,
    pub required_modifier_bits: u32,
    pub shift_key_id: String,
    pub ctrl_key_id: String,
    pub alt_key_id: String,
    pub meta_key_id: String,
}

#[cfg_attr(feature = "serde", derive(Serialize, Deserialize))]
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FrameMetadata {
    pub frame_number: u64,
    pub emulated_cycles: u64,
    pub emulated_time_ns: u64,
    #[cfg_attr(feature = "serde", serde(with = "serde_support::execution_state"))]
    pub execution_state: sys::emu_automation_execution_state_t,
}

#[cfg_attr(feature = "serde", derive(Serialize, Deserialize))]
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RegisterValue {
    pub name: String,
    pub hex_value: String,
    pub dec_value: String,
    pub has_dec: bool,
    pub changed: bool,
}

#[cfg_attr(feature = "serde", derive(Serialize, Deserialize))]
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct InstructionInfo {
    pub address: u64,
    pub bytes_text: String,
    pub text: String,
    pub symbol: String,
    pub has_symbol: bool,
    pub is_current_ip: bool,
    pub has_breakpoint: bool,
    pub branch_target: u64,
    pub has_branch_target: bool,
    pub changed_since_last_step: bool,
}

#[cfg_attr(feature = "serde", derive(Serialize, Deserialize))]
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Rect {
    pub x: i32,
    pub y: i32,
    pub width: u32,
    pub height: u32,
}

#[cfg_attr(feature = "serde", derive(Serialize, Deserialize))]
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FramebufferSnapshot {
    pub frame: FrameMetadata,
    pub width: u32,
    pub height: u32,
    pub stride_bytes: u32,
    #[cfg_attr(feature = "serde", serde(with = "serde_support::pixel_format"))]
    pub pixel_format: sys::emu_automation_pixel_format_t,
    pub visible_area: Rect,
    pub pixel_aspect_numerator: u32,
    pub pixel_aspect_denominator: u32,
    pub pixels: Vec<u8>,
}

#[cfg_attr(feature = "serde", derive(Serialize, Deserialize))]
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TextViewDescriptor {
    pub region_id: String,
    pub columns: u32,
    pub rows: u32,
    pub row_stride: u32,
    pub charset_id: String,
    pub native_encoding: String,
    pub unicode_map: String,
}

#[cfg_attr(feature = "serde", derive(Serialize, Deserialize))]
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TextCell {
    pub native_code: u32,
    pub unicode_codepoint: u32,
    pub text: String,
    pub glyph_id: String,
    pub foreground_color: i32,
    pub background_color: i32,
    pub attribute_flags: u32,
    pub charset_id: String,
    pub source_address: u64,
    pub confidence: u8,
}

#[cfg_attr(feature = "serde", derive(Serialize, Deserialize))]
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TextDelta {
    pub x: u32,
    pub y: u32,
    pub before: TextCell,
    pub after: TextCell,
}

#[cfg_attr(feature = "serde", derive(Serialize, Deserialize))]
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TextGridSnapshot {
    pub region_id: String,
    pub columns: u32,
    pub rows: u32,
    pub row_stride: u32,
    pub plain: String,
    pub cells: Vec<TextCell>,
    pub frame: FrameMetadata,
}

#[cfg_attr(feature = "serde", derive(Serialize, Deserialize))]
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AutomationEvent {
    pub sequence_number: u64,
    #[cfg_attr(feature = "serde", serde(with = "serde_support::event_type"))]
    pub event_type: sys::emu_automation_event_type_t,
    pub frame: FrameMetadata,
    pub input_accepted: FrameMetadata,
    pub input_applied: FrameMetadata,
    pub device_id: String,
    pub control_id: String,
    pub region_id: String,
    pub change_x: u32,
    pub change_y: u32,
    pub change_width: u32,
    pub change_height: u32,
    pub change_cell_count: u32,
    pub text_deltas: Vec<TextDelta>,
    pub message: String,
    #[cfg_attr(feature = "serde", serde(with = "serde_support::input_action"))]
    pub input_action: sys::emu_automation_input_action_t,
    pub input_timing: Timing,
}

impl AutomationEvent {
    pub fn is_type(&self, event_type: sys::emu_automation_event_type_t) -> bool {
        self.event_type == event_type
    }

    pub fn is_screen_changed(&self) -> bool {
        self.is_type(sys::emu_automation_event_type_t::EMU_AUTOMATION_EVENT_SCREEN_CHANGED)
    }

    pub fn is_text_changed(&self) -> bool {
        self.is_type(sys::emu_automation_event_type_t::EMU_AUTOMATION_EVENT_TEXT_CHANGED)
    }
}

pub struct Keyboard<'a> {
    machine: &'a Machine,
}

impl<'a> Keyboard<'a> {
    pub fn press(&self, key_id: &str, device_id: Option<&str>) -> Result<(), Error> {
        self.machine.key(
            key_id,
            sys::emu_automation_input_action_t::EMU_AUTOMATION_INPUT_PRESS,
            device_id,
        )
    }

    pub fn release(&self, key_id: &str, device_id: Option<&str>) -> Result<(), Error> {
        self.machine.key(
            key_id,
            sys::emu_automation_input_action_t::EMU_AUTOMATION_INPUT_RELEASE,
            device_id,
        )
    }

    pub fn tap(
        &self,
        key_id: &str,
        device_id: Option<&str>,
        preset: Option<TapTimingPreset>,
    ) -> Result<(), Error> {
        self.machine.tap_key(key_id, device_id, preset)
    }

    pub fn type_text(
        &self,
        text: &str,
        device_id: Option<&str>,
        preset: Option<TapTimingPreset>,
    ) -> Result<(), Error> {
        self.machine.type_text(text, device_id, preset)
    }

    pub fn release_all(&self, device_id: Option<&str>) -> Result<usize, Error> {
        self.machine.release_all_keys(device_id)
    }
}

pub struct Controller<'a> {
    machine: &'a Machine,
}

impl<'a> Controller<'a> {
    pub fn press(&self, control_id: &str, device_id: Option<&str>) -> Result<(), Error> {
        self.machine.controller_button(
            control_id,
            sys::emu_automation_input_action_t::EMU_AUTOMATION_INPUT_PRESS,
            device_id,
        )
    }

    pub fn release(&self, control_id: &str, device_id: Option<&str>) -> Result<(), Error> {
        self.machine.controller_button(
            control_id,
            sys::emu_automation_input_action_t::EMU_AUTOMATION_INPUT_RELEASE,
            device_id,
        )
    }

    pub fn tap(
        &self,
        control_id: &str,
        device_id: Option<&str>,
        preset: Option<TapTimingPreset>,
    ) -> Result<(), Error> {
        self.machine.tap_controller_button(control_id, device_id, preset)
    }

    pub fn release_all(&self, device_id: Option<&str>) -> Result<usize, Error> {
        self.machine.release_all_controller_buttons(device_id)
    }
}

#[cfg_attr(feature = "serde", derive(Serialize, Deserialize))]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Timing {
    Immediate,
    Frame(u64),
    Cycle(u64),
    DelayFrames(u64),
    DelayCycles(u64),
}

impl Timing {
    fn from_raw(raw: sys::emu_automation_timing_t) -> Self {
        match raw.kind {
            sys::emu_automation_timing_kind_t::EMU_AUTOMATION_TIMING_IMMEDIATE => Self::Immediate,
            sys::emu_automation_timing_kind_t::EMU_AUTOMATION_TIMING_FRAME => Self::Frame(raw.value),
            sys::emu_automation_timing_kind_t::EMU_AUTOMATION_TIMING_CYCLE => Self::Cycle(raw.value),
            sys::emu_automation_timing_kind_t::EMU_AUTOMATION_TIMING_DELAY_FRAMES => {
                Self::DelayFrames(raw.value)
            }
            sys::emu_automation_timing_kind_t::EMU_AUTOMATION_TIMING_DELAY_CYCLES => {
                Self::DelayCycles(raw.value)
            }
        }
    }

    fn raw(self) -> sys::emu_automation_timing_t {
        match self {
            Self::Immediate => sys::emu_automation_timing_t {
                kind: sys::emu_automation_timing_kind_t::EMU_AUTOMATION_TIMING_IMMEDIATE,
                value: 0,
            },
            Self::Frame(value) => sys::emu_automation_timing_t {
                kind: sys::emu_automation_timing_kind_t::EMU_AUTOMATION_TIMING_FRAME,
                value,
            },
            Self::Cycle(value) => sys::emu_automation_timing_t {
                kind: sys::emu_automation_timing_kind_t::EMU_AUTOMATION_TIMING_CYCLE,
                value,
            },
            Self::DelayFrames(value) => sys::emu_automation_timing_t {
                kind: sys::emu_automation_timing_kind_t::EMU_AUTOMATION_TIMING_DELAY_FRAMES,
                value,
            },
            Self::DelayCycles(value) => sys::emu_automation_timing_t {
                kind: sys::emu_automation_timing_kind_t::EMU_AUTOMATION_TIMING_DELAY_CYCLES,
                value,
            },
        }
    }
}

#[cfg_attr(feature = "serde", derive(Serialize, Deserialize))]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct TapTimingPreset {
    pub press_timing: Timing,
    pub release_timing: Timing,
}

impl TapTimingPreset {
    pub fn immediate() -> Self {
        Self {
            press_timing: Timing::Immediate,
            release_timing: Timing::Immediate,
        }
    }

    pub fn hold_frames(frame_count: u64) -> Self {
        Self {
            press_timing: Timing::Immediate,
            release_timing: Timing::DelayFrames(frame_count),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
enum InputStep {
    Key {
        key_id: String,
        action: sys::emu_automation_input_action_t,
        device_id: Option<String>,
        timing: Timing,
    },
    ControllerButton {
        control_id: String,
        action: sys::emu_automation_input_action_t,
        device_id: Option<String>,
        timing: Timing,
    },
    WaitFrames(u64),
}

#[cfg_attr(feature = "serde", derive(Serialize, Deserialize))]
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct InputLogStep {
    pub kind: String,
    pub target_id: String,
    pub action: String,
    pub device_id: String,
    pub timing: Timing,
    pub frame_count: u64,
}

#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct InputSequence {
    steps: Vec<InputStep>,
}

impl InputSequence {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn key_down(
        &mut self,
        key_id: impl Into<String>,
        device_id: Option<&str>,
        timing: Timing,
    ) -> &mut Self {
        self.steps.push(InputStep::Key {
            key_id: key_id.into(),
            action: sys::emu_automation_input_action_t::EMU_AUTOMATION_INPUT_PRESS,
            device_id: device_id.map(str::to_string),
            timing,
        });
        self
    }

    pub fn key_up(
        &mut self,
        key_id: impl Into<String>,
        device_id: Option<&str>,
        timing: Timing,
    ) -> &mut Self {
        self.steps.push(InputStep::Key {
            key_id: key_id.into(),
            action: sys::emu_automation_input_action_t::EMU_AUTOMATION_INPUT_RELEASE,
            device_id: device_id.map(str::to_string),
            timing,
        });
        self
    }

    pub fn tap_key(
        &mut self,
        key_id: impl Into<String>,
        device_id: Option<&str>,
        press_timing: Timing,
        release_timing: Timing,
    ) -> &mut Self {
        let key_id = key_id.into();
        self.key_down(key_id.clone(), device_id, press_timing);
        self.key_up(key_id, device_id, release_timing);
        self
    }

    pub fn tap_key_with_preset(
        &mut self,
        key_id: impl Into<String>,
        device_id: Option<&str>,
        preset: TapTimingPreset,
    ) -> &mut Self {
        self.tap_key(key_id, device_id, preset.press_timing, preset.release_timing)
    }

    pub fn type_text(
        &mut self,
        machine: &Machine,
        text: &str,
        device_id: Option<&str>,
        preset: TapTimingPreset,
    ) -> Result<&mut Self, Error> {
        for ch in text.chars() {
            let mapping = machine.character_mapping_for_char(ch, device_id)?;
            if (mapping.required_modifier_bits & sys::EMU_AUTOMATION_KEY_MODIFIER_SHIFT) != 0 {
                if mapping.shift_key_id.is_empty() {
                    return Err(simple_error(
                        "emu_automation_machine_character_mapping_descriptor",
                        sys::emu_automation_result_t::EMU_AUTOMATION_MAPPING_UNAVAILABLE,
                    ));
                }
                self.key_down(mapping.shift_key_id.clone(), device_id, Timing::Immediate);
            }
            if (mapping.required_modifier_bits & sys::EMU_AUTOMATION_KEY_MODIFIER_CTRL) != 0 {
                if mapping.ctrl_key_id.is_empty() {
                    return Err(simple_error(
                        "emu_automation_machine_character_mapping_descriptor",
                        sys::emu_automation_result_t::EMU_AUTOMATION_MAPPING_UNAVAILABLE,
                    ));
                }
                self.key_down(mapping.ctrl_key_id.clone(), device_id, Timing::Immediate);
            }
            if (mapping.required_modifier_bits & sys::EMU_AUTOMATION_KEY_MODIFIER_ALT) != 0 {
                if mapping.alt_key_id.is_empty() {
                    return Err(simple_error(
                        "emu_automation_machine_character_mapping_descriptor",
                        sys::emu_automation_result_t::EMU_AUTOMATION_MAPPING_UNAVAILABLE,
                    ));
                }
                self.key_down(mapping.alt_key_id.clone(), device_id, Timing::Immediate);
            }
            if (mapping.required_modifier_bits & sys::EMU_AUTOMATION_KEY_MODIFIER_META) != 0 {
                if mapping.meta_key_id.is_empty() {
                    return Err(simple_error(
                        "emu_automation_machine_character_mapping_descriptor",
                        sys::emu_automation_result_t::EMU_AUTOMATION_MAPPING_UNAVAILABLE,
                    ));
                }
                self.key_down(mapping.meta_key_id.clone(), device_id, Timing::Immediate);
            }
            self.tap_key_with_preset(mapping.key_id.clone(), device_id, preset);
            if (mapping.required_modifier_bits & sys::EMU_AUTOMATION_KEY_MODIFIER_META) != 0 {
                self.key_up(mapping.meta_key_id.clone(), device_id, Timing::Immediate);
            }
            if (mapping.required_modifier_bits & sys::EMU_AUTOMATION_KEY_MODIFIER_ALT) != 0 {
                self.key_up(mapping.alt_key_id.clone(), device_id, Timing::Immediate);
            }
            if (mapping.required_modifier_bits & sys::EMU_AUTOMATION_KEY_MODIFIER_CTRL) != 0 {
                self.key_up(mapping.ctrl_key_id.clone(), device_id, Timing::Immediate);
            }
            if (mapping.required_modifier_bits & sys::EMU_AUTOMATION_KEY_MODIFIER_SHIFT) != 0 {
                self.key_up(mapping.shift_key_id.clone(), device_id, Timing::Immediate);
            }
        }
        Ok(self)
    }

    pub fn tap_controller_with_preset(
        &mut self,
        control_id: impl Into<String>,
        device_id: Option<&str>,
        preset: TapTimingPreset,
    ) -> &mut Self {
        let control_id = control_id.into();
        self.controller_down(control_id.clone(), device_id, preset.press_timing);
        self.controller_up(control_id, device_id, preset.release_timing);
        self
    }

    pub fn controller_down(
        &mut self,
        control_id: impl Into<String>,
        device_id: Option<&str>,
        timing: Timing,
    ) -> &mut Self {
        self.steps.push(InputStep::ControllerButton {
            control_id: control_id.into(),
            action: sys::emu_automation_input_action_t::EMU_AUTOMATION_INPUT_PRESS,
            device_id: device_id.map(str::to_string),
            timing,
        });
        self
    }

    pub fn controller_up(
        &mut self,
        control_id: impl Into<String>,
        device_id: Option<&str>,
        timing: Timing,
    ) -> &mut Self {
        self.steps.push(InputStep::ControllerButton {
            control_id: control_id.into(),
            action: sys::emu_automation_input_action_t::EMU_AUTOMATION_INPUT_RELEASE,
            device_id: device_id.map(str::to_string),
            timing,
        });
        self
    }

    pub fn wait_frames(&mut self, frame_count: u64) -> &mut Self {
        self.steps.push(InputStep::WaitFrames(frame_count));
        self
    }

    pub fn release_all_keys(&mut self, device_id: Option<&str>) -> &mut Self {
        self.steps.push(InputStep::Key {
            key_id: String::new(),
            action: sys::emu_automation_input_action_t::EMU_AUTOMATION_INPUT_RELEASE,
            device_id: device_id.map(str::to_string),
            timing: Timing::Immediate,
        });
        self
    }

    pub fn release_all_controller_buttons(&mut self, device_id: Option<&str>) -> &mut Self {
        self.steps.push(InputStep::ControllerButton {
            control_id: String::new(),
            action: sys::emu_automation_input_action_t::EMU_AUTOMATION_INPUT_RELEASE,
            device_id: device_id.map(str::to_string),
            timing: Timing::Immediate,
        });
        self
    }

    pub fn steps(&self) -> Vec<InputLogStep> {
        self.steps.iter().map(input_step_to_log_step).collect()
    }

    pub fn to_log_payload(&self) -> Vec<String> {
        self.steps()
            .into_iter()
            .map(|step| input_log_step_to_json(&step))
            .collect()
    }

    pub fn to_jsonl(&self) -> String {
        self.to_log_payload()
            .into_iter()
            .map(|line| format!("{line}\n"))
            .collect()
    }

    pub fn from_log_payload(lines: &[String]) -> Result<Self, Error> {
        let mut sequence = Self::new();
        for line in lines {
            let step = input_log_step_from_json(line)?;
            push_log_step(&mut sequence, step)?;
        }
        Ok(sequence)
    }

    pub fn from_jsonl(text: &str) -> Result<Self, Error> {
        let lines = text
            .lines()
            .map(str::trim)
            .filter(|line| !line.is_empty())
            .map(str::to_string)
            .collect::<Vec<_>>();
        Self::from_log_payload(&lines)
    }

    pub fn play(&self, machine: &Machine) -> Result<(), Error> {
        for step in &self.steps {
            match step {
                InputStep::Key {
                    key_id,
                    action,
                    device_id,
                    timing,
                } if key_id.is_empty()
                    && *action == sys::emu_automation_input_action_t::EMU_AUTOMATION_INPUT_RELEASE =>
                {
                    machine.release_all_keys(device_id.as_deref())?;
                }
                InputStep::Key {
                    key_id,
                    action,
                    device_id,
                    timing,
                } => machine.key_with_timing(key_id, *action, device_id.as_deref(), *timing)?,
                InputStep::ControllerButton {
                    control_id,
                    action,
                    device_id,
                    timing,
                } if control_id.is_empty()
                    && *action == sys::emu_automation_input_action_t::EMU_AUTOMATION_INPUT_RELEASE =>
                {
                    machine.release_all_controller_buttons(device_id.as_deref())?;
                }
                InputStep::ControllerButton {
                    control_id,
                    action,
                    device_id,
                    timing,
                } => machine.controller_button_with_timing(
                    control_id,
                    *action,
                    device_id.as_deref(),
                    *timing,
                )?,
                InputStep::WaitFrames(frame_count) => machine.run_frames(*frame_count)?,
            }
        }
        Ok(())
    }
}

fn input_step_to_log_step(step: &InputStep) -> InputLogStep {
    match step {
        InputStep::Key {
            key_id,
            action,
            device_id,
            timing,
        } => InputLogStep {
            kind: "key".to_string(),
            target_id: key_id.clone(),
            action: if *action == sys::emu_automation_input_action_t::EMU_AUTOMATION_INPUT_PRESS {
                "press".to_string()
            } else {
                "release".to_string()
            },
            device_id: device_id.clone().unwrap_or_default(),
            timing: *timing,
            frame_count: 0,
        },
        InputStep::ControllerButton {
            control_id,
            action,
            device_id,
            timing,
        } => InputLogStep {
            kind: "controller_button".to_string(),
            target_id: control_id.clone(),
            action: if *action == sys::emu_automation_input_action_t::EMU_AUTOMATION_INPUT_PRESS {
                "press".to_string()
            } else {
                "release".to_string()
            },
            device_id: device_id.clone().unwrap_or_default(),
            timing: *timing,
            frame_count: 0,
        },
        InputStep::WaitFrames(frame_count) => InputLogStep {
            kind: "wait_frames".to_string(),
            target_id: String::new(),
            action: String::new(),
            device_id: String::new(),
            timing: Timing::Immediate,
            frame_count: *frame_count,
        },
    }
}

fn push_log_step(sequence: &mut InputSequence, step: InputLogStep) -> Result<(), Error> {
    let device_id = if step.device_id.is_empty() {
        None
    } else {
        Some(step.device_id.as_str())
    };
    match step.kind.as_str() {
        "key" => match step.action.as_str() {
            "press" => {
                sequence.key_down(step.target_id, device_id, step.timing);
                Ok(())
            }
            "release" if step.target_id.is_empty() => {
                sequence.release_all_keys(device_id);
                Ok(())
            }
            "release" => {
                sequence.key_up(step.target_id, device_id, step.timing);
                Ok(())
            }
            _ => Err(simple_error(
                "input_sequence.from_log_payload",
                sys::emu_automation_result_t::EMU_AUTOMATION_SERIALIZATION_ERROR,
            )),
        },
        "controller_button" => match step.action.as_str() {
            "press" => {
                sequence.controller_down(step.target_id, device_id, step.timing);
                Ok(())
            }
            "release" if step.target_id.is_empty() => {
                sequence.release_all_controller_buttons(device_id);
                Ok(())
            }
            "release" => {
                sequence.controller_up(step.target_id, device_id, step.timing);
                Ok(())
            }
            _ => Err(simple_error(
                "input_sequence.from_log_payload",
                sys::emu_automation_result_t::EMU_AUTOMATION_SERIALIZATION_ERROR,
            )),
        },
        "wait_frames" => {
            sequence.wait_frames(step.frame_count);
            Ok(())
        }
        _ => Err(simple_error(
            "input_sequence.from_log_payload",
            sys::emu_automation_result_t::EMU_AUTOMATION_SERIALIZATION_ERROR,
        )),
    }
}

fn input_log_step_to_json(step: &InputLogStep) -> String {
    format!(
        "{{\"action\":\"{}\",\"device_id\":\"{}\",\"frame_count\":{},\"kind\":\"{}\",\"target_id\":\"{}\",\"timing\":{{\"kind\":{},\"value\":{}}}}}",
        json_escape(&step.action),
        json_escape(&step.device_id),
        step.frame_count,
        json_escape(&step.kind),
        json_escape(&step.target_id),
        timing_kind_to_i32(step.timing.raw().kind),
        step.timing.raw().value
    )
}

fn input_log_step_from_json(line: &str) -> Result<InputLogStep, Error> {
    let kind = extract_json_string(line, "kind")?;
    let target_id = extract_json_string(line, "target_id")?;
    let action = extract_json_string(line, "action")?;
    let device_id = extract_json_string(line, "device_id")?;
    let frame_count = extract_json_u64(line, "frame_count")?;
    let timing_block = extract_json_object_block(line, "timing")?;
    let timing_kind = extract_json_i32(timing_block, "kind")?;
    let timing_value = extract_json_u64(timing_block, "value")?;
    Ok(InputLogStep {
        kind,
        target_id,
        action,
        device_id,
        timing: Timing::from_raw(sys::emu_automation_timing_t {
            kind: timing_kind_from_i32(timing_kind)?,
            value: timing_value,
        }),
        frame_count,
    })
}

pub struct Run<'a> {
    machine: &'a Machine,
}

impl<'a> Run<'a> {
    pub fn frame(&self) -> Result<(), Error> {
        self.machine.step_frame()
    }

    pub fn frames(&self, frame_count: u64) -> Result<(), Error> {
        self.machine.run_frames(frame_count)
    }

    pub fn until<T, F>(
        &self,
        timeout_frames: u64,
        step_frames: u64,
        description: impl Into<String>,
        mut predicate: F,
    ) -> Result<T, WaitError>
    where
        F: FnMut(&Machine) -> Result<Option<T>, Error>,
    {
        self.machine
            .wait_until(timeout_frames, step_frames, description, |machine| predicate(machine))
    }
}

pub struct Conditions;

impl Conditions {
    pub fn screen_contains(&self, text: impl Into<String>, region_id: Option<&str>) -> Condition<TextGridSnapshot> {
        let text = text.into();
        let region_id = region_id.map(str::to_string);
        let description = format!("text {text:?}");
        Condition::new(description, move |machine| {
            let snapshot = machine.text_grid(region_id.as_deref())?;
            if snapshot.plain.contains(&text) {
                Ok(Some(snapshot))
            } else {
                Ok(None)
            }
        })
    }

    pub fn text_disappears(
        &self,
        text: impl Into<String>,
        region_id: Option<&str>,
    ) -> Condition<TextGridSnapshot> {
        let text = text.into();
        let region_id = region_id.map(str::to_string);
        let description = format!("text {text:?} absent");
        Condition::new(description, move |machine| {
            let snapshot = machine.text_grid(region_id.as_deref())?;
            if !snapshot.plain.contains(&text) {
                Ok(Some(snapshot))
            } else {
                Ok(None)
            }
        })
    }

    pub fn stable_text(
        &self,
        region_id: Option<&str>,
        stable_frames: u64,
    ) -> Condition<TextGridSnapshot> {
        let region_id = region_id.map(str::to_string);
        let mut last_key: Option<(String, u32, u32, u32, String, Vec<TextCell>)> = None;
        let mut last_frame = 0u64;
        let mut stable_for = 0u64;
        Condition::new(
            format!("stable text in {}", region_id.as_deref().unwrap_or("default text region")),
            move |machine| {
                let snapshot = machine.text_grid(region_id.as_deref())?;
                if stable_frames == 0 {
                    return Ok(Some(snapshot));
                }
                let current_key = text_grid_key(&snapshot);
                if let Some(previous_key) = &last_key {
                    let frame_delta = snapshot.frame.frame_number.saturating_sub(last_frame);
                    if &current_key == previous_key {
                        stable_for += frame_delta;
                        if stable_for >= stable_frames {
                            last_frame = snapshot.frame.frame_number;
                            last_key = Some(current_key);
                            return Ok(Some(snapshot));
                        }
                    } else {
                        stable_for = 0;
                    }
                }
                last_frame = snapshot.frame.frame_number;
                last_key = Some(current_key);
                Ok(None)
            },
        )
    }

    pub fn stable_framebuffer(&self, stable_frames: u64) -> Condition<FramebufferSnapshot> {
        let mut last_key: Option<(
            u32,
            u32,
            u32,
            sys::emu_automation_pixel_format_t,
            Rect,
            u32,
            u32,
            Vec<u8>,
        )> = None;
        let mut last_frame = 0u64;
        let mut stable_for = 0u64;
        Condition::new("stable framebuffer", move |machine| {
            let snapshot = machine.framebuffer()?;
            if stable_frames == 0 {
                return Ok(Some(snapshot));
            }
            let current_key = framebuffer_key(&snapshot);
            if let Some(previous_key) = &last_key {
                let frame_delta = snapshot.frame.frame_number.saturating_sub(last_frame);
                if &current_key == previous_key {
                    stable_for += frame_delta;
                    if stable_for >= stable_frames {
                        last_frame = snapshot.frame.frame_number;
                        last_key = Some(current_key);
                        return Ok(Some(snapshot));
                    }
                } else {
                    stable_for = 0;
                }
            }
            last_frame = snapshot.frame.frame_number;
            last_key = Some(current_key);
            Ok(None)
        })
    }

    pub fn event_type(
        &self,
        event_type: sys::emu_automation_event_type_t,
        after_sequence: u64,
    ) -> Condition<AutomationEvent> {
        let mut after_sequence = after_sequence;
        Condition::new(format!("event type {:?}", event_type), move |machine| {
            loop {
                let Some(event) = machine.poll_event(after_sequence)? else {
                    return Ok(None);
                };
                after_sequence = event.sequence_number;
                if event.event_type == event_type {
                    return Ok(Some(event));
                }
            }
        })
    }

    pub fn screen_changed(&self, after_sequence: u64) -> Condition<AutomationEvent> {
        self.event_type(
            sys::emu_automation_event_type_t::EMU_AUTOMATION_EVENT_SCREEN_CHANGED,
            after_sequence,
        )
    }

    pub fn text_changed(&self, after_sequence: u64) -> Condition<AutomationEvent> {
        self.event_type(
            sys::emu_automation_event_type_t::EMU_AUTOMATION_EVENT_TEXT_CHANGED,
            after_sequence,
        )
    }

    pub fn media_activity(&self, after_sequence: u64) -> Condition<AutomationEvent> {
        self.event_type(
            sys::emu_automation_event_type_t::EMU_AUTOMATION_EVENT_MEDIA_ACTIVITY,
            after_sequence,
        )
    }

    pub fn memory_value(&self, address: u64, expected: impl AsRef<[u8]>) -> Condition<Vec<u8>> {
        let expected = expected.as_ref().to_vec();
        let description = format!("memory 0x{address:X} == {}", hex_bytes(&expected));
        Condition::new(description, move |machine| {
            let current = machine.read_memory(address, expected.len())?;
            if current == expected {
                Ok(Some(current))
            } else {
                Ok(None)
            }
        })
    }
}

pub struct Wait<'a> {
    machine: &'a Machine,
}

impl<'a> Wait<'a> {
    pub fn until<T>(&self, condition: Condition<T>, timeout_frames: u64, step_frames: u64) -> Result<T, WaitError> {
        let Condition {
            description,
            mut predicate,
        } = condition;
        self.machine
            .wait_until(timeout_frames, step_frames, description, move |machine| predicate(machine))
    }
}

pub struct Screen<'a> {
    machine: &'a Machine,
}

impl<'a> Screen<'a> {
    pub fn framebuffer(&self) -> Result<FramebufferSnapshot, Error> {
        self.machine.framebuffer()
    }

    pub fn text_views(&self) -> Result<Vec<TextViewDescriptor>, Error> {
        self.machine.text_views()
    }

    pub fn text(&self, region_id: Option<&str>) -> Result<TextGridSnapshot, Error> {
        self.machine.text_grid(region_id)
    }

    pub fn wait_for_text(
        &self,
        text: &str,
        region_id: Option<&str>,
        timeout_frames: u64,
        step_frames: u64,
    ) -> Result<TextGridSnapshot, WaitError> {
        self.machine
            .wait_for_text(text, region_id, timeout_frames, step_frames)
    }

    pub fn wait_for_text_disappearance(
        &self,
        text: &str,
        region_id: Option<&str>,
        timeout_frames: u64,
        step_frames: u64,
    ) -> Result<TextGridSnapshot, WaitError> {
        self.machine
            .wait_for_text_disappearance(text, region_id, timeout_frames, step_frames)
    }

    pub fn wait_for_stable_text(
        &self,
        region_id: Option<&str>,
        stable_frames: u64,
        timeout_frames: u64,
        step_frames: u64,
    ) -> Result<TextGridSnapshot, WaitError> {
        self.machine
            .wait_for_stable_text(region_id, stable_frames, timeout_frames, step_frames)
    }

    pub fn wait_for_stable_framebuffer(
        &self,
        stable_frames: u64,
        timeout_frames: u64,
        step_frames: u64,
    ) -> Result<FramebufferSnapshot, WaitError> {
        self.machine
            .wait_for_stable_framebuffer(stable_frames, timeout_frames, step_frames)
    }

    pub fn poll_event(&self, after_sequence: u64) -> Result<Option<AutomationEvent>, Error> {
        self.machine.poll_event(after_sequence)
    }

    pub fn events(&self, after_sequence: u64) -> EventPoller<'a> {
        EventPoller::new(self.machine, after_sequence)
    }

    pub fn subscribe<F>(
        &self,
        event_type: sys::emu_automation_event_type_t,
        after_sequence: u64,
        callback: F,
    ) -> Result<Subscription<'a, F>, Error>
    where
        F: FnMut(&AutomationEvent),
    {
        self.machine.subscribe(event_type, after_sequence, callback)
    }

    pub fn wait_for_event(
        &self,
        event_type: sys::emu_automation_event_type_t,
        after_sequence: u64,
        timeout_frames: u64,
        step_frames: u64,
    ) -> Result<AutomationEvent, WaitError> {
        self.machine
            .wait_for_event(event_type, after_sequence, timeout_frames, step_frames)
    }

    pub fn wait_for_screen_changed(
        &self,
        after_sequence: u64,
        timeout_frames: u64,
        step_frames: u64,
    ) -> Result<AutomationEvent, WaitError> {
        self.wait_for_event(
            sys::emu_automation_event_type_t::EMU_AUTOMATION_EVENT_SCREEN_CHANGED,
            after_sequence,
            timeout_frames,
            step_frames,
        )
    }

    pub fn wait_for_text_changed(
        &self,
        after_sequence: u64,
        timeout_frames: u64,
        step_frames: u64,
    ) -> Result<AutomationEvent, WaitError> {
        self.wait_for_event(
            sys::emu_automation_event_type_t::EMU_AUTOMATION_EVENT_TEXT_CHANGED,
            after_sequence,
            timeout_frames,
            step_frames,
        )
    }

    pub fn wait_for_media_activity(
        &self,
        after_sequence: u64,
        timeout_frames: u64,
        step_frames: u64,
    ) -> Result<AutomationEvent, WaitError> {
        self.wait_for_event(
            sys::emu_automation_event_type_t::EMU_AUTOMATION_EVENT_MEDIA_ACTIVITY,
            after_sequence,
            timeout_frames,
            step_frames,
        )
    }
}

pub struct EventPoller<'a> {
    machine: &'a Machine,
    after_sequence: u64,
}

struct SubscriptionState<F>
where
    F: FnMut(&AutomationEvent),
{
    callback: F,
}

struct DispatchMatchingState<'a, F>
where
    F: FnMut(&AutomationEvent),
{
    callback: &'a mut F,
}

unsafe extern "C" fn dispatch_matching_trampoline<F>(
    raw_event: *const sys::emu_automation_event_t,
    user_data: *mut std::ffi::c_void,
) where
    F: FnMut(&AutomationEvent),
{
    let state = &mut *(user_data as *mut DispatchMatchingState<'_, F>);
    let raw = &*raw_event;
    let event = AutomationEvent {
        sequence_number: raw.sequence_number,
        event_type: raw.event_type,
        frame: FrameMetadata {
            frame_number: raw.frame.frame_number,
            emulated_cycles: raw.frame.emulated_cycles,
            emulated_time_ns: raw.frame.emulated_time_ns,
            execution_state: raw.frame.execution_state,
        },
        input_accepted: FrameMetadata {
            frame_number: raw.input_accepted.frame_number,
            emulated_cycles: raw.input_accepted.emulated_cycles,
            emulated_time_ns: raw.input_accepted.emulated_time_ns,
            execution_state: raw.input_accepted.execution_state,
        },
        input_applied: FrameMetadata {
            frame_number: raw.input_applied.frame_number,
            emulated_cycles: raw.input_applied.emulated_cycles,
            emulated_time_ns: raw.input_applied.emulated_time_ns,
            execution_state: raw.input_applied.execution_state,
        },
        device_id: c_string(raw.device_id),
        control_id: c_string(raw.control_id),
        region_id: c_string(raw.region_id),
        change_x: raw.change_x,
        change_y: raw.change_y,
        change_width: raw.change_width,
        change_height: raw.change_height,
        change_cell_count: raw.change_cell_count,
        text_deltas: copy_text_deltas(raw),
        message: c_string(raw.message),
        input_action: raw.input_action,
        input_timing: Timing::from_raw(raw.input_timing),
    };
    (state.callback)(&event);
}

unsafe extern "C" fn subscription_trampoline<F>(
    raw_event: *const sys::emu_automation_event_t,
    user_data: *mut std::ffi::c_void,
) where
    F: FnMut(&AutomationEvent),
{
    let state = &mut *(user_data as *mut SubscriptionState<F>);
    let raw = &*raw_event;
    let event = AutomationEvent {
        sequence_number: raw.sequence_number,
        event_type: raw.event_type,
        frame: FrameMetadata {
            frame_number: raw.frame.frame_number,
            emulated_cycles: raw.frame.emulated_cycles,
            emulated_time_ns: raw.frame.emulated_time_ns,
            execution_state: raw.frame.execution_state,
        },
        input_accepted: FrameMetadata {
            frame_number: raw.input_accepted.frame_number,
            emulated_cycles: raw.input_accepted.emulated_cycles,
            emulated_time_ns: raw.input_accepted.emulated_time_ns,
            execution_state: raw.input_accepted.execution_state,
        },
        input_applied: FrameMetadata {
            frame_number: raw.input_applied.frame_number,
            emulated_cycles: raw.input_applied.emulated_cycles,
            emulated_time_ns: raw.input_applied.emulated_time_ns,
            execution_state: raw.input_applied.execution_state,
        },
        device_id: c_string(raw.device_id),
        control_id: c_string(raw.control_id),
        region_id: c_string(raw.region_id),
        change_x: raw.change_x,
        change_y: raw.change_y,
        change_width: raw.change_width,
        change_height: raw.change_height,
        change_cell_count: raw.change_cell_count,
        text_deltas: copy_text_deltas(raw),
        message: c_string(raw.message),
        input_action: raw.input_action,
        input_timing: Timing::from_raw(raw.input_timing),
    };
    (state.callback)(&event);
}

pub struct Subscription<'a, F>
where
    F: FnMut(&AutomationEvent),
{
    raw: NonNull<sys::emu_automation_subscription_t>,
    api: Arc<AutomationApi>,
    _machine: &'a Machine,
    _state: Box<SubscriptionState<F>>,
}

impl<'a, F> Subscription<'a, F>
where
    F: FnMut(&AutomationEvent),
{
    pub fn after_sequence(&self) -> u64 {
        unsafe { (self.api.subscription_after_sequence)(self.raw.as_ptr()) }
    }

    pub fn set_after_sequence(&mut self, after_sequence: u64) -> Result<(), Error> {
        check_with_api(
            unsafe { (self.api.subscription_set_after_sequence)(self.raw.as_ptr(), after_sequence) },
            "emu_automation_subscription_set_after_sequence",
            &self.api,
        )
    }

    pub fn dispatch_available(&mut self, max_events: usize) -> Result<usize, Error> {
        let mut count = 0usize;
        check_with_api(
            unsafe {
                (self.api.subscription_dispatch_available)(self.raw.as_ptr(), max_events, &mut count)
            },
            "emu_automation_subscription_dispatch_available",
            &self.api,
        )?;
        Ok(count)
    }
}

impl<'a, F> Drop for Subscription<'a, F>
where
    F: FnMut(&AutomationEvent),
{
    fn drop(&mut self) {
        unsafe { (self.api.subscription_destroy)(self.raw.as_ptr()) };
    }
}

impl<'a> EventPoller<'a> {
    pub fn new(machine: &'a Machine, after_sequence: u64) -> Self {
        Self {
            machine,
            after_sequence,
        }
    }

    pub fn after_sequence(&self) -> u64 {
        self.after_sequence
    }

    pub fn poll_next(&mut self) -> Result<Option<AutomationEvent>, Error> {
        let event = self.machine.poll_event(self.after_sequence)?;
        if let Some(ref event) = event {
            self.after_sequence = event.sequence_number;
        }
        Ok(event)
    }

    pub fn collect_available(&mut self) -> Result<Vec<AutomationEvent>, Error> {
        let mut events = Vec::new();
        while let Some(event) = self.poll_next()? {
            events.push(event);
        }
        Ok(events)
    }

    pub fn dispatch_available<F>(&mut self, mut callback: F) -> Result<usize, Error>
    where
        F: FnMut(&AutomationEvent),
    {
        let mut count = 0usize;
        while let Some(event) = self.poll_next()? {
            callback(&event);
            count += 1;
        }
        Ok(count)
    }

    pub fn dispatch_matching<F>(
        &mut self,
        event_type: sys::emu_automation_event_type_t,
        max_events: usize,
        mut callback: F,
    ) -> Result<usize, Error>
    where
        F: FnMut(&AutomationEvent),
    {
        let (after_sequence, count) = self.machine.dispatch_matching_events(
            self.after_sequence,
            event_type,
            max_events,
            &mut callback,
        )?;
        self.after_sequence = after_sequence;
        Ok(count)
    }

    pub fn into_receiver(self, step_frames: u64) -> EventReceiver<'a> {
        EventReceiver::new(self.machine, self.after_sequence, step_frames)
    }
}

pub struct EventReceiver<'a> {
    machine: &'a Machine,
    after_sequence: u64,
    step_frames: u64,
}

impl<'a> EventReceiver<'a> {
    pub fn new(machine: &'a Machine, after_sequence: u64, step_frames: u64) -> Self {
        assert!(step_frames > 0, "step_frames must be positive");
        Self {
            machine,
            after_sequence,
            step_frames,
        }
    }

    pub fn after_sequence(&self) -> u64 {
        self.after_sequence
    }

    pub fn try_recv(&mut self) -> Result<Option<AutomationEvent>, Error> {
        let event = self.machine.poll_event(self.after_sequence)?;
        if let Some(ref event) = event {
            self.after_sequence = event.sequence_number;
        }
        Ok(event)
    }

    pub fn recv(&mut self, timeout_frames: u64) -> Result<AutomationEvent, WaitError> {
        let mut frames_elapsed = 0u64;
        loop {
            if let Some(event) = self.try_recv()? {
                return Ok(event);
            }
            if frames_elapsed >= timeout_frames {
                return Err(WaitTimeoutError {
                    description: "event receiver".to_string(),
                    frames_elapsed,
                    last_observation: None,
                }
                .into());
            }
            let frames_to_run = self.step_frames.min(timeout_frames - frames_elapsed);
            self.machine.run_frames(frames_to_run)?;
            frames_elapsed += frames_to_run;
        }
    }
}

pub struct Machine {
    raw: NonNull<sys::emu_automation_machine_t>,
    api: Arc<AutomationApi>,
    pressed_keys: RefCell<BTreeSet<(Option<String>, String)>>,
    pressed_controller_buttons: RefCell<BTreeSet<(Option<String>, String)>>,
}

impl Machine {
    pub fn from_raw_owned(raw: *mut sys::emu_automation_machine_t) -> Option<Self> {
        let api = AutomationApi::linked().ok()?;
        Self::from_raw_with_api(raw, api)
    }

    fn from_raw_with_api(raw: *mut sys::emu_automation_machine_t, api: Arc<AutomationApi>) -> Option<Self> {
        NonNull::new(raw).map(|raw| Self {
            raw,
            api,
            pressed_keys: RefCell::new(BTreeSet::new()),
            pressed_controller_buttons: RefCell::new(BTreeSet::new()),
        })
    }

    pub fn as_raw(&self) -> *mut sys::emu_automation_machine_t {
        self.raw.as_ptr()
    }

    pub fn keyboard(&self) -> Keyboard<'_> {
        Keyboard { machine: self }
    }

    pub fn controller(&self) -> Controller<'_> {
        Controller { machine: self }
    }

    pub fn run(&self) -> Run<'_> {
        Run { machine: self }
    }

    pub fn conditions(&self) -> Conditions {
        Conditions
    }

    pub fn wait(&self) -> Wait<'_> {
        Wait { machine: self }
    }

    pub fn screen(&self) -> Screen<'_> {
        Screen { machine: self }
    }

    pub fn sequence(&self) -> InputSequence {
        InputSequence::new()
    }

    pub fn describe(&self) -> Result<MachineDescriptor, Error> {
        let mut raw = sys::emu_automation_machine_descriptor_t {
            struct_size: std::mem::size_of::<sys::emu_automation_machine_descriptor_t>() as u32,
            struct_version: sys::EMU_AUTOMATION_STRUCT_VERSION,
            machine_id: std::ptr::null(),
            system_id: std::ptr::null(),
            model_id: std::ptr::null(),
            region: std::ptr::null(),
            video_standard: std::ptr::null(),
            adapter_version: std::ptr::null(),
            configured_memory_bytes: 0,
            capabilities: sys::emu_automation_capabilities_t {
                struct_size: std::mem::size_of::<sys::emu_automation_capabilities_t>() as u32,
                struct_version: sys::EMU_AUTOMATION_STRUCT_VERSION,
                feature_bits: 0,
            },
        };
        check_with_api(
            unsafe { (self.api.machine_describe)(self.as_raw(), &mut raw) },
            "emu_automation_machine_describe",
            &self.api,
        )?;
        Ok(MachineDescriptor {
            machine_id: c_string(raw.machine_id),
            system_id: c_string(raw.system_id),
            model_id: c_string(raw.model_id),
            region: c_string(raw.region),
            video_standard: c_string(raw.video_standard),
            adapter_version: c_string(raw.adapter_version),
            configured_memory_bytes: raw.configured_memory_bytes,
            capabilities: Capabilities {
                feature_bits: raw.capabilities.feature_bits,
            },
        })
    }

    pub fn capabilities(&self) -> Result<Capabilities, Error> {
        let mut raw = sys::emu_automation_capabilities_t {
            struct_size: std::mem::size_of::<sys::emu_automation_capabilities_t>() as u32,
            struct_version: sys::EMU_AUTOMATION_STRUCT_VERSION,
            feature_bits: 0,
        };
        check_with_api(
            unsafe { (self.api.machine_capabilities)(self.as_raw(), &mut raw) },
            "emu_automation_machine_capabilities",
            &self.api,
        )?;
        Ok(Capabilities {
            feature_bits: raw.feature_bits,
        })
    }

    pub fn character_mappings(&self) -> Result<Vec<CharacterMappingDescriptor>, Error> {
        let mut count = 0usize;
        check_with_api(
            unsafe { (self.api.machine_character_mapping_count)(self.as_raw(), &mut count) },
            "emu_automation_machine_character_mapping_count",
            &self.api,
        )?;
        let mut mappings = Vec::with_capacity(count);
        for index in 0..count {
            let mut raw = sys::emu_automation_character_mapping_descriptor_t {
                struct_size: std::mem::size_of::<sys::emu_automation_character_mapping_descriptor_t>()
                    as u32,
                struct_version: sys::EMU_AUTOMATION_STRUCT_VERSION,
                device_id: std::ptr::null(),
                unicode_codepoint: 0,
                native_code: 0,
                key_id: std::ptr::null(),
                required_modifier_bits: 0,
                shift_key_id: std::ptr::null(),
                ctrl_key_id: std::ptr::null(),
                alt_key_id: std::ptr::null(),
                meta_key_id: std::ptr::null(),
            };
            check_with_api(
                unsafe {
                    (self.api.machine_character_mapping_descriptor)(self.as_raw(), index, &mut raw)
                },
                "emu_automation_machine_character_mapping_descriptor",
                &self.api,
            )?;
            mappings.push(CharacterMappingDescriptor {
                device_id: c_string(raw.device_id),
                unicode_codepoint: raw.unicode_codepoint,
                native_code: raw.native_code,
                key_id: c_string(raw.key_id),
                required_modifier_bits: raw.required_modifier_bits,
                shift_key_id: c_string(raw.shift_key_id),
                ctrl_key_id: c_string(raw.ctrl_key_id),
                alt_key_id: c_string(raw.alt_key_id),
                meta_key_id: c_string(raw.meta_key_id),
            });
        }
        Ok(mappings)
    }

    fn character_mapping_for_char(
        &self,
        ch: char,
        device_id: Option<&str>,
    ) -> Result<CharacterMappingDescriptor, Error> {
        let codepoint = ch as u32;
        for mapping in self.character_mappings()? {
            if mapping.unicode_codepoint != codepoint {
                continue;
            }
            if let Some(device_id) = device_id {
                if !mapping.device_id.is_empty() && mapping.device_id != device_id {
                    continue;
                }
            }
            return Ok(mapping);
        }
        Err(simple_error(
            "emu_automation_machine_character_mapping_descriptor",
            sys::emu_automation_result_t::EMU_AUTOMATION_CHARACTER_UNSUPPORTED,
        ))
    }

    pub fn pause(&self) -> Result<(), Error> {
        check_with_api(
            unsafe { (self.api.machine_pause)(self.as_raw()) },
            "emu_automation_machine_pause",
            &self.api,
        )
    }

    pub fn resume(&self) -> Result<(), Error> {
        check_with_api(
            unsafe { (self.api.machine_resume)(self.as_raw()) },
            "emu_automation_machine_resume",
            &self.api,
        )
    }

    pub fn reset(&self, kind: sys::emu_automation_reset_kind_t) -> Result<(), Error> {
        check_with_api(
            unsafe { (self.api.machine_reset)(self.as_raw(), kind) },
            "emu_automation_machine_reset",
            &self.api,
        )
    }

    pub fn step_frame(&self) -> Result<(), Error> {
        check_with_api(
            unsafe { (self.api.machine_step_frame)(self.as_raw()) },
            "emu_automation_machine_step_frame",
            &self.api,
        )
    }

    pub fn run_frames(&self, frame_count: u64) -> Result<(), Error> {
        check_with_api(
            unsafe { (self.api.machine_run_frames)(self.as_raw(), frame_count) },
            "emu_automation_machine_run_frames",
            &self.api,
        )
    }

    pub fn key(
        &self,
        key_id: &str,
        action: sys::emu_automation_input_action_t,
        device_id: Option<&str>,
    ) -> Result<(), Error> {
        self.key_with_timing(key_id, action, device_id, Timing::Immediate)
    }

    pub fn key_with_timing(
        &self,
        key_id: &str,
        action: sys::emu_automation_input_action_t,
        device_id: Option<&str>,
        timing: Timing,
    ) -> Result<(), Error> {
        let tracked_device_id = device_id.map(str::to_string);
        let tracked_key_id = key_id.to_string();
        let key_id = CString::new(key_id).expect("key id contains NUL");
        let device_id = device_id.map(|value| CString::new(value).expect("device id contains NUL"));
        let event = sys::emu_automation_key_event_t {
            struct_size: std::mem::size_of::<sys::emu_automation_key_event_t>() as u32,
            struct_version: sys::EMU_AUTOMATION_STRUCT_VERSION,
            device_id: device_id
                .as_ref()
                .map_or(std::ptr::null(), |value| value.as_ptr()),
            key_id: key_id.as_ptr(),
            action,
            timing: timing.raw(),
        };
        check_with_api(
            unsafe { (self.api.input_key)(self.as_raw(), &event) },
            "emu_automation_input_key",
            &self.api,
        )?;
        let token = (tracked_device_id, tracked_key_id);
        match action {
            sys::emu_automation_input_action_t::EMU_AUTOMATION_INPUT_PRESS => {
                self.pressed_keys.borrow_mut().insert(token);
            }
            sys::emu_automation_input_action_t::EMU_AUTOMATION_INPUT_RELEASE => {
                self.pressed_keys.borrow_mut().remove(&token);
            }
        }
        Ok(())
    }

    pub fn tap_key(
        &self,
        key_id: &str,
        device_id: Option<&str>,
        preset: Option<TapTimingPreset>,
    ) -> Result<(), Error> {
        let preset = preset.unwrap_or_else(TapTimingPreset::immediate);
        self.key_with_timing(
            key_id,
            sys::emu_automation_input_action_t::EMU_AUTOMATION_INPUT_PRESS,
            device_id,
            preset.press_timing,
        )?;
        self.key_with_timing(
            key_id,
            sys::emu_automation_input_action_t::EMU_AUTOMATION_INPUT_RELEASE,
            device_id,
            preset.release_timing,
        )
    }

    pub fn type_text(
        &self,
        text: &str,
        device_id: Option<&str>,
        preset: Option<TapTimingPreset>,
    ) -> Result<(), Error> {
        let preset = preset.unwrap_or_else(TapTimingPreset::immediate);
        for ch in text.chars() {
            let mapping = self.character_mapping_for_char(ch, device_id)?;
            let mut pressed_modifiers: Vec<&str> = Vec::new();
            if (mapping.required_modifier_bits & sys::EMU_AUTOMATION_KEY_MODIFIER_SHIFT) != 0 {
                if mapping.shift_key_id.is_empty() {
                    return Err(simple_error(
                        "emu_automation_machine_character_mapping_descriptor",
                        sys::emu_automation_result_t::EMU_AUTOMATION_MAPPING_UNAVAILABLE,
                    ));
                }
                self.key(
                    &mapping.shift_key_id,
                    sys::emu_automation_input_action_t::EMU_AUTOMATION_INPUT_PRESS,
                    device_id,
                )?;
                pressed_modifiers.push(mapping.shift_key_id.as_str());
            }
            if (mapping.required_modifier_bits & sys::EMU_AUTOMATION_KEY_MODIFIER_CTRL) != 0 {
                if mapping.ctrl_key_id.is_empty() {
                    return Err(simple_error(
                        "emu_automation_machine_character_mapping_descriptor",
                        sys::emu_automation_result_t::EMU_AUTOMATION_MAPPING_UNAVAILABLE,
                    ));
                }
                self.key(
                    &mapping.ctrl_key_id,
                    sys::emu_automation_input_action_t::EMU_AUTOMATION_INPUT_PRESS,
                    device_id,
                )?;
                pressed_modifiers.push(mapping.ctrl_key_id.as_str());
            }
            if (mapping.required_modifier_bits & sys::EMU_AUTOMATION_KEY_MODIFIER_ALT) != 0 {
                if mapping.alt_key_id.is_empty() {
                    return Err(simple_error(
                        "emu_automation_machine_character_mapping_descriptor",
                        sys::emu_automation_result_t::EMU_AUTOMATION_MAPPING_UNAVAILABLE,
                    ));
                }
                self.key(
                    &mapping.alt_key_id,
                    sys::emu_automation_input_action_t::EMU_AUTOMATION_INPUT_PRESS,
                    device_id,
                )?;
                pressed_modifiers.push(mapping.alt_key_id.as_str());
            }
            if (mapping.required_modifier_bits & sys::EMU_AUTOMATION_KEY_MODIFIER_META) != 0 {
                if mapping.meta_key_id.is_empty() {
                    return Err(simple_error(
                        "emu_automation_machine_character_mapping_descriptor",
                        sys::emu_automation_result_t::EMU_AUTOMATION_MAPPING_UNAVAILABLE,
                    ));
                }
                self.key(
                    &mapping.meta_key_id,
                    sys::emu_automation_input_action_t::EMU_AUTOMATION_INPUT_PRESS,
                    device_id,
                )?;
                pressed_modifiers.push(mapping.meta_key_id.as_str());
            }
            self.tap_key(&mapping.key_id, device_id, Some(preset.clone()))?;
            for modifier_key_id in pressed_modifiers.into_iter().rev() {
                self.key(
                    modifier_key_id,
                    sys::emu_automation_input_action_t::EMU_AUTOMATION_INPUT_RELEASE,
                    device_id,
                )?;
            }
        }
        Ok(())
    }

    pub fn release_all_keys(&self, device_id: Option<&str>) -> Result<usize, Error> {
        let target = device_id.map(str::to_string);
        let to_release: Vec<_> = self
            .pressed_keys
            .borrow()
            .iter()
            .filter(|(tracked_device_id, _)| target.is_none() || *tracked_device_id == target)
            .cloned()
            .collect();
        for (tracked_device_id, key_id) in to_release.iter().rev() {
            self.key(
                key_id,
                sys::emu_automation_input_action_t::EMU_AUTOMATION_INPUT_RELEASE,
                tracked_device_id.as_deref(),
            )?;
        }
        Ok(to_release.len())
    }

    pub fn controller_button(
        &self,
        control_id: &str,
        action: sys::emu_automation_input_action_t,
        device_id: Option<&str>,
    ) -> Result<(), Error> {
        self.controller_button_with_timing(control_id, action, device_id, Timing::Immediate)
    }

    pub fn controller_button_with_timing(
        &self,
        control_id: &str,
        action: sys::emu_automation_input_action_t,
        device_id: Option<&str>,
        timing: Timing,
    ) -> Result<(), Error> {
        let tracked_device_id = device_id.map(str::to_string);
        let tracked_control_id = control_id.to_string();
        let control_id = CString::new(control_id).expect("control id contains NUL");
        let device_id = device_id.map(|value| CString::new(value).expect("device id contains NUL"));
        let event = sys::emu_automation_controller_button_event_t {
            struct_size: std::mem::size_of::<sys::emu_automation_controller_button_event_t>() as u32,
            struct_version: sys::EMU_AUTOMATION_STRUCT_VERSION,
            device_id: device_id
                .as_ref()
                .map_or(std::ptr::null(), |value| value.as_ptr()),
            control_id: control_id.as_ptr(),
            action,
            timing: timing.raw(),
        };
        check_with_api(
            unsafe { (self.api.input_controller_button)(self.as_raw(), &event) },
            "emu_automation_input_controller_button",
            &self.api,
        )?;
        let token = (tracked_device_id, tracked_control_id);
        match action {
            sys::emu_automation_input_action_t::EMU_AUTOMATION_INPUT_PRESS => {
                self.pressed_controller_buttons.borrow_mut().insert(token);
            }
            sys::emu_automation_input_action_t::EMU_AUTOMATION_INPUT_RELEASE => {
                self.pressed_controller_buttons.borrow_mut().remove(&token);
            }
        }
        Ok(())
    }

    pub fn release_all_controller_buttons(&self, device_id: Option<&str>) -> Result<usize, Error> {
        let target = device_id.map(str::to_string);
        let to_release: Vec<_> = self
            .pressed_controller_buttons
            .borrow()
            .iter()
            .filter(|(tracked_device_id, _)| target.is_none() || *tracked_device_id == target)
            .cloned()
            .collect();
        for (tracked_device_id, control_id) in to_release.iter().rev() {
            self.controller_button(
                control_id,
                sys::emu_automation_input_action_t::EMU_AUTOMATION_INPUT_RELEASE,
                tracked_device_id.as_deref(),
            )?;
        }
        Ok(to_release.len())
    }

    pub fn tap_controller_button(
        &self,
        control_id: &str,
        device_id: Option<&str>,
        preset: Option<TapTimingPreset>,
    ) -> Result<(), Error> {
        let preset = preset.unwrap_or_else(TapTimingPreset::immediate);
        self.controller_button_with_timing(
            control_id,
            sys::emu_automation_input_action_t::EMU_AUTOMATION_INPUT_PRESS,
            device_id,
            preset.press_timing,
        )?;
        self.controller_button_with_timing(
            control_id,
            sys::emu_automation_input_action_t::EMU_AUTOMATION_INPUT_RELEASE,
            device_id,
            preset.release_timing,
        )
    }

    pub fn framebuffer(&self) -> Result<FramebufferSnapshot, Error> {
        let mut raw = sys::emu_automation_framebuffer_snapshot_t {
            struct_size: std::mem::size_of::<sys::emu_automation_framebuffer_snapshot_t>() as u32,
            struct_version: sys::EMU_AUTOMATION_STRUCT_VERSION,
            frame: empty_frame(),
            width: 0,
            height: 0,
            stride_bytes: 0,
            pixel_format: sys::emu_automation_pixel_format_t::EMU_AUTOMATION_PIXEL_FORMAT_UNKNOWN,
            visible_area: sys::emu_automation_rect_t {
                x: 0,
                y: 0,
                width: 0,
                height: 0,
            },
            pixel_aspect_numerator: 0,
            pixel_aspect_denominator: 0,
            pixels: std::ptr::null(),
            pixel_size: 0,
            adapter_owned: std::ptr::null_mut(),
        };
        check_with_api(
            unsafe { (self.api.screen_framebuffer)(self.as_raw(), &mut raw) },
            "emu_automation_screen_framebuffer",
            &self.api,
        )?;
        let snapshot = copy_framebuffer(&raw);
        unsafe { (self.api.framebuffer_release)(self.as_raw(), &mut raw) };
        Ok(snapshot)
    }

    pub fn text_views(&self) -> Result<Vec<TextViewDescriptor>, Error> {
        let mut count = 0usize;
        check_with_api(
            unsafe { (self.api.screen_text_view_count)(self.as_raw(), &mut count) },
            "emu_automation_screen_text_view_count",
            &self.api,
        )?;
        let mut views = Vec::with_capacity(count);
        for index in 0..count {
            let mut raw = sys::emu_automation_text_view_descriptor_t {
                struct_size: std::mem::size_of::<sys::emu_automation_text_view_descriptor_t>() as u32,
                struct_version: sys::EMU_AUTOMATION_STRUCT_VERSION,
                region_id: std::ptr::null(),
                columns: 0,
                rows: 0,
                row_stride: 0,
                charset_id: std::ptr::null(),
                native_encoding: std::ptr::null(),
                unicode_map: std::ptr::null(),
            };
            check_with_api(
                unsafe { (self.api.screen_text_view_descriptor)(self.as_raw(), index, &mut raw) },
                "emu_automation_screen_text_view_descriptor",
                &self.api,
            )?;
            views.push(TextViewDescriptor {
                region_id: c_string(raw.region_id),
                columns: raw.columns,
                rows: raw.rows,
                row_stride: raw.row_stride,
                charset_id: c_string(raw.charset_id),
                native_encoding: c_string(raw.native_encoding),
                unicode_map: c_string(raw.unicode_map),
            });
        }
        Ok(views)
    }

    pub fn text_grid(&self, region_id: Option<&str>) -> Result<TextGridSnapshot, Error> {
        let region = region_id.map(|value| CString::new(value).expect("region id contains NUL"));
        let region_ptr = region
            .as_ref()
            .map_or(std::ptr::null(), |value| value.as_ptr());
        let mut raw = sys::emu_automation_text_grid_snapshot_t {
            struct_size: std::mem::size_of::<sys::emu_automation_text_grid_snapshot_t>() as u32,
            struct_version: sys::EMU_AUTOMATION_STRUCT_VERSION,
            frame: empty_frame(),
            region_id: std::ptr::null(),
            columns: 0,
            rows: 0,
            row_stride: 0,
            cells: std::ptr::null(),
            cell_count: 0,
            plain_utf8: std::ptr::null(),
            plain_utf8_size: 0,
            adapter_owned: std::ptr::null_mut(),
        };
        check_with_api(
            unsafe { (self.api.screen_text_grid)(self.as_raw(), region_ptr, &mut raw) },
            "emu_automation_screen_text_grid",
            &self.api,
        )?;
        let snapshot = copy_text_grid(&raw);
        unsafe { (self.api.text_grid_release)(self.as_raw(), &mut raw) };
        Ok(snapshot)
    }

    pub fn read_memory(&self, address: u64, size: usize) -> Result<Vec<u8>, Error> {
        if size == 0 {
            return Ok(Vec::new());
        }
        let mut bytes = vec![0u8; size];
        check_with_api(
            unsafe { (self.api.memory_read)(self.as_raw(), address, bytes.as_mut_ptr(), size) },
            "emu_automation_memory_read",
            &self.api,
        )?;
        Ok(bytes)
    }

    pub fn write_memory(&self, address: u64, bytes: &[u8]) -> Result<(), Error> {
        if bytes.is_empty() {
            return Ok(());
        }
        check_with_api(
            unsafe { (self.api.memory_write)(self.as_raw(), address, bytes.as_ptr(), bytes.len()) },
            "emu_automation_memory_write",
            &self.api,
        )
    }

    pub fn read_program_counter(&self) -> Result<u64, Error> {
        let mut value = 0u64;
        check_with_api(
            unsafe { (self.api.execution_program_counter)(self.as_raw(), &mut value) },
            "emu_automation_execution_program_counter",
            &self.api,
        )?;
        Ok(value)
    }

    pub fn read_frame_metadata(&self) -> Result<FrameMetadata, Error> {
        let mut raw = empty_frame();
        check_with_api(
            unsafe { (self.api.execution_frame_metadata)(self.as_raw(), &mut raw) },
            "emu_automation_execution_frame_metadata",
            &self.api,
        )?;
        Ok(FrameMetadata {
            frame_number: raw.frame_number,
            emulated_cycles: raw.emulated_cycles,
            emulated_time_ns: raw.emulated_time_ns,
            execution_state: raw.execution_state,
        })
    }

    pub fn read_current_instruction(&self) -> Result<InstructionInfo, Error> {
        let mut raw = sys::emu_automation_instruction_t {
            struct_size: std::mem::size_of::<sys::emu_automation_instruction_t>() as u32,
            struct_version: sys::EMU_AUTOMATION_STRUCT_VERSION,
            address: 0,
            bytes: [0; 32],
            text: [0; 96],
            symbol: [0; 64],
            has_symbol: 0,
            is_current_ip: 0,
            has_breakpoint: 0,
            branch_target: 0,
            has_branch_target: 0,
            changed_since_last_step: 0,
        };
        check_with_api(
            unsafe { (self.api.execution_current_instruction)(self.as_raw(), &mut raw) },
            "emu_automation_execution_current_instruction",
            &self.api,
        )?;
        Ok(InstructionInfo {
            address: raw.address,
            bytes_text: c_string_buf(&raw.bytes),
            text: c_string_buf(&raw.text),
            symbol: c_string_buf(&raw.symbol),
            has_symbol: raw.has_symbol != 0,
            is_current_ip: raw.is_current_ip != 0,
            has_breakpoint: raw.has_breakpoint != 0,
            branch_target: raw.branch_target,
            has_branch_target: raw.has_branch_target != 0,
            changed_since_last_step: raw.changed_since_last_step != 0,
        })
    }

    pub fn read_registers(&self) -> Result<Vec<RegisterValue>, Error> {
        let mut count = 0usize;
        check_with_api(
            unsafe { (self.api.register_count)(self.as_raw(), &mut count) },
            "emu_automation_register_count",
            &self.api,
        )?;
        if count == 0 {
            return Ok(Vec::new());
        }
        let mut raw_rows = vec![
            sys::emu_automation_register_value_t {
                struct_size: std::mem::size_of::<sys::emu_automation_register_value_t>() as u32,
                struct_version: sys::EMU_AUTOMATION_STRUCT_VERSION,
                name: [0; 32],
                hex_value: [0; 32],
                dec_value: [0; 32],
                has_dec: 0,
                changed: 0,
            };
            count
        ];
        let mut out_count = 0usize;
        check_with_api(
            unsafe {
                (self.api.register_read)(
                    self.as_raw(),
                    raw_rows.as_mut_ptr(),
                    raw_rows.len(),
                    &mut out_count,
                )
            },
            "emu_automation_register_read",
            &self.api,
        )?;
        raw_rows.truncate(out_count);
        Ok(raw_rows
            .into_iter()
            .map(|raw| RegisterValue {
                name: c_string_buf(&raw.name),
                hex_value: c_string_buf(&raw.hex_value),
                dec_value: c_string_buf(&raw.dec_value),
                has_dec: raw.has_dec != 0,
                changed: raw.changed != 0,
            })
            .collect())
    }

    pub fn write_register(&self, register_name: &str, value: u64) -> Result<(), Error> {
        let name = CString::new(register_name).expect("register name contains NUL");
        check_with_api(
            unsafe { (self.api.register_write)(self.as_raw(), name.as_ptr(), value) },
            "emu_automation_register_write",
            &self.api,
        )
    }

    pub fn wait_until<T, F>(
        &self,
        timeout_frames: u64,
        step_frames: u64,
        description: impl Into<String>,
        mut predicate: F,
    ) -> Result<T, WaitError>
    where
        F: FnMut(&Machine) -> Result<Option<T>, Error>,
    {
        assert!(step_frames > 0, "step_frames must be positive");
        let description = description.into();
        let mut frames_elapsed = 0u64;
        loop {
            if let Some(value) = predicate(self)? {
                return Ok(value);
            }
            if frames_elapsed >= timeout_frames {
                return Err(WaitTimeoutError {
                    description,
                    frames_elapsed,
                    last_observation: None,
                }
                .into());
            }
            let frames_to_run = step_frames.min(timeout_frames - frames_elapsed);
            self.run_frames(frames_to_run)?;
            frames_elapsed += frames_to_run;
        }
    }

    pub fn wait_for_text(
        &self,
        text: &str,
        region_id: Option<&str>,
        timeout_frames: u64,
        step_frames: u64,
    ) -> Result<TextGridSnapshot, WaitError> {
        assert!(step_frames > 0, "step_frames must be positive");
        let mut frames_elapsed = 0u64;
        loop {
            let snapshot = self.text_grid(region_id)?;
            let last_observation = Some(summarize_text_grid(&snapshot));
            if snapshot.plain.contains(text) {
                return Ok(snapshot);
            }
            if frames_elapsed >= timeout_frames {
                return Err(WaitTimeoutError {
                    description: format!("text {text:?}"),
                    frames_elapsed,
                    last_observation,
                }
                .into());
            }
            let frames_to_run = step_frames.min(timeout_frames - frames_elapsed);
            self.run_frames(frames_to_run)?;
            frames_elapsed += frames_to_run;
        }
    }

    pub fn wait_for_text_disappearance(
        &self,
        text: &str,
        region_id: Option<&str>,
        timeout_frames: u64,
        step_frames: u64,
    ) -> Result<TextGridSnapshot, WaitError> {
        assert!(step_frames > 0, "step_frames must be positive");
        let mut frames_elapsed = 0u64;
        loop {
            let snapshot = self.text_grid(region_id)?;
            let last_observation = Some(summarize_text_grid(&snapshot));
            if !snapshot.plain.contains(text) {
                return Ok(snapshot);
            }
            if frames_elapsed >= timeout_frames {
                return Err(WaitTimeoutError {
                    description: format!("text {text:?} absent"),
                    frames_elapsed,
                    last_observation,
                }
                .into());
            }
            let frames_to_run = step_frames.min(timeout_frames - frames_elapsed);
            self.run_frames(frames_to_run)?;
            frames_elapsed += frames_to_run;
        }
    }

    pub fn wait_for_memory_value(
        &self,
        address: u64,
        expected: &[u8],
        timeout_frames: u64,
        step_frames: u64,
    ) -> Result<Vec<u8>, WaitError> {
        let expected = expected.to_vec();
        assert!(step_frames > 0, "step_frames must be positive");
        let mut frames_elapsed = 0u64;
        loop {
            let current = self.read_memory(address, expected.len())?;
            let last_observation = Some(hex_bytes(&current));
            if current == expected {
                return Ok(current);
            }
            if frames_elapsed >= timeout_frames {
                return Err(WaitTimeoutError {
                    description: format!("memory 0x{address:X} == {}", hex_bytes(&expected)),
                    frames_elapsed,
                    last_observation,
                }
                .into());
            }
            let frames_to_run = step_frames.min(timeout_frames - frames_elapsed);
            self.run_frames(frames_to_run)?;
            frames_elapsed += frames_to_run;
        }
    }

    pub fn wait_for_stable_text(
        &self,
        region_id: Option<&str>,
        stable_frames: u64,
        timeout_frames: u64,
        step_frames: u64,
    ) -> Result<TextGridSnapshot, WaitError> {
        assert!(step_frames > 0, "step_frames must be positive");
        let mut snapshot = self.text_grid(region_id)?;
        if stable_frames == 0 {
            return Ok(snapshot);
        }

        let mut last_key = text_grid_key(&snapshot);
        let mut last_frame = snapshot.frame.frame_number;
        let mut stable_for = 0u64;
        let mut frames_elapsed = 0u64;

        loop {
            if frames_elapsed >= timeout_frames {
                return Err(WaitTimeoutError {
                    description: format!(
                        "stable text in {}",
                        region_id.unwrap_or("default text region")
                    ),
                    frames_elapsed,
                    last_observation: Some(summarize_text_grid(&snapshot)),
                }
                .into());
            }
            let frames_to_run = step_frames.min(timeout_frames - frames_elapsed);
            self.run_frames(frames_to_run)?;
            frames_elapsed += frames_to_run;
            snapshot = self.text_grid(region_id)?;
            let current_key = text_grid_key(&snapshot);
            let frame_delta = snapshot.frame.frame_number.saturating_sub(last_frame);
            if current_key == last_key {
                stable_for += frame_delta;
                if stable_for >= stable_frames {
                    return Ok(snapshot);
                }
            } else {
                last_key = current_key;
                stable_for = 0;
            }
            last_frame = snapshot.frame.frame_number;
        }
    }

    pub fn wait_for_stable_framebuffer(
        &self,
        stable_frames: u64,
        timeout_frames: u64,
        step_frames: u64,
    ) -> Result<FramebufferSnapshot, WaitError> {
        assert!(step_frames > 0, "step_frames must be positive");
        let mut snapshot = self.framebuffer()?;
        if stable_frames == 0 {
            return Ok(snapshot);
        }

        let mut last_key = framebuffer_key(&snapshot);
        let mut last_frame = snapshot.frame.frame_number;
        let mut stable_for = 0u64;
        let mut frames_elapsed = 0u64;

        loop {
            if frames_elapsed >= timeout_frames {
                return Err(WaitTimeoutError {
                    description: "stable framebuffer".to_string(),
                    frames_elapsed,
                    last_observation: Some(summarize_framebuffer(&snapshot)),
                }
                .into());
            }
            let frames_to_run = step_frames.min(timeout_frames - frames_elapsed);
            self.run_frames(frames_to_run)?;
            frames_elapsed += frames_to_run;
            snapshot = self.framebuffer()?;
            let current_key = framebuffer_key(&snapshot);
            let frame_delta = snapshot.frame.frame_number.saturating_sub(last_frame);
            if current_key == last_key {
                stable_for += frame_delta;
                if stable_for >= stable_frames {
                    return Ok(snapshot);
                }
            } else {
                last_key = current_key;
                stable_for = 0;
            }
            last_frame = snapshot.frame.frame_number;
        }
    }

    pub fn poll_event(&self, after_sequence: u64) -> Result<Option<AutomationEvent>, Error> {
        let mut raw = sys::emu_automation_event_t {
            struct_size: std::mem::size_of::<sys::emu_automation_event_t>() as u32,
            struct_version: sys::EMU_AUTOMATION_STRUCT_VERSION,
            sequence_number: 0,
            event_type: sys::emu_automation_event_type_t::EMU_AUTOMATION_EVENT_NONE,
            frame: empty_frame(),
            input_accepted: empty_frame(),
            input_applied: empty_frame(),
            device_id: std::ptr::null(),
            control_id: std::ptr::null(),
            region_id: std::ptr::null(),
            change_x: 0,
            change_y: 0,
            change_width: 0,
            change_height: 0,
            change_cell_count: 0,
            text_deltas: std::ptr::null(),
            text_delta_count: 0,
            message: std::ptr::null(),
            input_action: sys::emu_automation_input_action_t::EMU_AUTOMATION_INPUT_RELEASE,
            input_timing: sys::emu_automation_timing_t {
                kind: sys::emu_automation_timing_kind_t::EMU_AUTOMATION_TIMING_IMMEDIATE,
                value: 0,
            },
            adapter_owned: std::ptr::null_mut(),
        };
        let result = unsafe { (self.api.events_poll)(self.as_raw(), after_sequence, &mut raw) };
        if result == sys::emu_automation_result_t::EMU_AUTOMATION_TIMEOUT {
            return Ok(None);
        }
        check_with_api(result, "emu_automation_events_poll", &self.api)?;
        let event = AutomationEvent {
            sequence_number: raw.sequence_number,
            event_type: raw.event_type,
            frame: FrameMetadata {
                frame_number: raw.frame.frame_number,
                emulated_cycles: raw.frame.emulated_cycles,
                emulated_time_ns: raw.frame.emulated_time_ns,
                execution_state: raw.frame.execution_state,
            },
            input_accepted: FrameMetadata {
                frame_number: raw.input_accepted.frame_number,
                emulated_cycles: raw.input_accepted.emulated_cycles,
                emulated_time_ns: raw.input_accepted.emulated_time_ns,
                execution_state: raw.input_accepted.execution_state,
            },
            input_applied: FrameMetadata {
                frame_number: raw.input_applied.frame_number,
                emulated_cycles: raw.input_applied.emulated_cycles,
                emulated_time_ns: raw.input_applied.emulated_time_ns,
                execution_state: raw.input_applied.execution_state,
            },
            device_id: c_string(raw.device_id),
            control_id: c_string(raw.control_id),
            region_id: c_string(raw.region_id),
            change_x: raw.change_x,
            change_y: raw.change_y,
            change_width: raw.change_width,
            change_height: raw.change_height,
            change_cell_count: raw.change_cell_count,
            text_deltas: copy_text_deltas(&raw),
            message: c_string(raw.message),
            input_action: raw.input_action,
            input_timing: Timing::from_raw(raw.input_timing),
        };
        unsafe { (self.api.event_release)(self.as_raw(), &mut raw) };
        Ok(Some(event))
    }

    pub fn wait_for_event(
        &self,
        event_type: sys::emu_automation_event_type_t,
        after_sequence: u64,
        timeout_frames: u64,
        step_frames: u64,
    ) -> Result<AutomationEvent, WaitError> {
        assert!(step_frames > 0, "step_frames must be positive");
        let mut sequence = after_sequence;
        let mut frames_elapsed = 0u64;
        let mut last_observation = None;
        loop {
            if let Some(event) = self.poll_event(sequence)? {
                sequence = event.sequence_number;
                last_observation = Some(summarize_event(&event));
                if event.event_type == event_type {
                    return Ok(event);
                }
                continue;
            }
            if frames_elapsed >= timeout_frames {
                return Err(WaitTimeoutError {
                    description: format!("event type {:?}", event_type),
                    frames_elapsed,
                    last_observation,
                }
                .into());
            }
            let frames_to_run = step_frames.min(timeout_frames - frames_elapsed);
            self.run_frames(frames_to_run)?;
            frames_elapsed += frames_to_run;
        }
    }

    fn dispatch_matching_events<F>(
        &self,
        after_sequence: u64,
        event_type: sys::emu_automation_event_type_t,
        max_events: usize,
        callback: &mut F,
    ) -> Result<(u64, usize), Error>
    where
        F: FnMut(&AutomationEvent),
    {
        let mut sequence = after_sequence;
        let mut count = 0usize;
        let mut state = DispatchMatchingState { callback };
        let result = unsafe {
            (self.api.events_dispatch_matching)(
                self.as_raw(),
                &mut sequence,
                event_type,
                max_events,
                Some(dispatch_matching_trampoline::<F>),
                (&mut state as *mut DispatchMatchingState<'_, F>).cast(),
                &mut count,
            )
        };
        check_with_api(result, "emu_automation_events_dispatch_matching", &self.api)?;
        Ok((sequence, count))
    }

    pub fn subscribe<F>(
        &self,
        event_type: sys::emu_automation_event_type_t,
        after_sequence: u64,
        callback: F,
    ) -> Result<Subscription<'_, F>, Error>
    where
        F: FnMut(&AutomationEvent),
    {
        let mut raw = std::ptr::null_mut();
        let mut state = Box::new(SubscriptionState { callback });
        let result = unsafe {
            (self.api.subscription_create)(
                self.as_raw(),
                event_type,
                after_sequence,
                Some(subscription_trampoline::<F>),
                (&mut *state as *mut SubscriptionState<F>).cast(),
                &mut raw,
            )
        };
        if let Err(error) = check_with_api(result, "emu_automation_subscription_create", &self.api) {
            drop(state);
            return Err(error);
        }
        let raw = NonNull::new(raw).expect("subscription_create returned null");
        Ok(Subscription {
            raw,
            api: Arc::clone(&self.api),
            _machine: self,
            _state: state,
        })
    }
}

impl Drop for Machine {
    fn drop(&mut self) {
        unsafe { (self.api.machine_destroy)(self.as_raw()) };
    }
}

pub fn check(
    code: sys::emu_automation_result_t,
    operation: &'static str,
) -> Result<(), Error> {
    let api = AutomationApi::linked().expect("linked automation api");
    check_with_api(code, operation, &api)
}

fn check_with_api(
    code: sys::emu_automation_result_t,
    operation: &'static str,
    api: &AutomationApi,
) -> Result<(), Error> {
    if code == sys::emu_automation_result_t::EMU_AUTOMATION_OK {
        return Ok(());
    }
    let name = unsafe { c_string((api.result_name)(code)) };
    Err(Error {
        operation,
        code,
        name,
    })
}

#[cfg(any(unix, windows))]
pub struct Library {
    loaded: LoadedApi,
}

#[cfg(any(unix, windows))]
impl Library {
    pub fn open(path: impl AsRef<Path>) -> Result<Self, LoadError> {
        Ok(Self {
            loaded: LoadedApi::open(path.as_ref())?,
        })
    }

    pub fn create_machine(&self, create_symbol: &str) -> Result<Machine, LoadError> {
        let symbol = CString::new(create_symbol).map_err(|_| LoadError::InvalidPath)?;
        let symbol_name = symbol.into_bytes_with_nul();
        let create: unsafe extern "C" fn(
            *mut *mut sys::emu_automation_machine_t,
        ) -> sys::emu_automation_result_t = unsafe { self.loaded.symbol(&symbol_name)? };
        let mut raw = std::ptr::null_mut();
        let result = unsafe { create(&mut raw) };
        check_with_api(result, "create_machine", &self.loaded.api).map_err(LoadError::Automation)?;
        Machine::from_raw_with_api(raw, Arc::clone(&self.loaded.api))
            .ok_or(LoadError::Automation(Error {
                operation: "create_machine",
                code: sys::emu_automation_result_t::EMU_AUTOMATION_INTERNAL_ERROR,
                name: "null_machine".to_string(),
            }))
    }
}

#[cfg(not(any(unix, windows)))]
pub struct Library;

#[cfg(not(any(unix, windows)))]
impl Library {
    pub fn open(_path: impl AsRef<Path>) -> Result<Self, LoadError> {
        Err(LoadError::UnsupportedPlatform)
    }
}

#[cfg(unix)]
const RTLD_NOW: i32 = 2;

#[cfg(unix)]
unsafe extern "C" {
    fn dlopen(filename: *const std::ffi::c_char, flags: i32) -> *mut std::ffi::c_void;
    fn dlsym(
        handle: *mut std::ffi::c_void,
        symbol: *const std::ffi::c_char,
    ) -> *mut std::ffi::c_void;
    fn dlclose(handle: *mut std::ffi::c_void) -> i32;
    fn dlerror() -> *const std::ffi::c_char;
}

#[cfg(unix)]
fn last_dl_error() -> String {
    let error = unsafe { dlerror() };
    c_string(error)
}

#[cfg(windows)]
fn last_dl_error() -> String {
    format!("Win32 error {}", unsafe { GetLastError() })
}

#[cfg(windows)]
unsafe extern "system" {
    fn LoadLibraryW(lp_lib_file_name: *const u16) -> *mut std::ffi::c_void;
    fn GetProcAddress(
        h_module: *mut std::ffi::c_void,
        lp_proc_name: *const std::ffi::c_char,
    ) -> *mut std::ffi::c_void;
    fn FreeLibrary(h_lib_module: *mut std::ffi::c_void) -> i32;
    fn GetLastError() -> u32;
}

fn empty_frame() -> sys::emu_automation_frame_metadata_t {
    sys::emu_automation_frame_metadata_t {
        struct_size: std::mem::size_of::<sys::emu_automation_frame_metadata_t>() as u32,
        struct_version: sys::EMU_AUTOMATION_STRUCT_VERSION,
        frame_number: 0,
        emulated_cycles: 0,
        emulated_time_ns: 0,
        execution_state: sys::emu_automation_execution_state_t::EMU_AUTOMATION_EXECUTION_STOPPED,
    }
}

fn hex_bytes(bytes: &[u8]) -> String {
    bytes
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect::<Vec<_>>()
        .join("")
}

fn summarize_text_grid(snapshot: &TextGridSnapshot) -> String {
    format!(
        "text frame={} plain={:?}",
        snapshot.frame.frame_number,
        snapshot.plain
    )
}

fn summarize_framebuffer(snapshot: &FramebufferSnapshot) -> String {
    format!(
        "framebuffer frame={} size={}x{} format={:?}",
        snapshot.frame.frame_number,
        snapshot.width,
        snapshot.height,
        snapshot.pixel_format
    )
}

fn summarize_event(event: &AutomationEvent) -> String {
    format!(
        "event sequence={} type={:?} frame={}",
        event.sequence_number,
        event.event_type,
        event.frame.frame_number
    )
}

fn json_escape(text: &str) -> String {
    let mut out = String::with_capacity(text.len());
    for ch in text.chars() {
        match ch {
            '\\' => out.push_str("\\\\"),
            '"' => out.push_str("\\\""),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            _ => out.push(ch),
        }
    }
    out
}

fn extract_json_object_block<'a>(text: &'a str, key: &str) -> Result<&'a str, Error> {
    let marker = format!("\"{key}\":{{");
    let start = text.find(&marker).ok_or_else(|| {
        simple_error(
            "input_sequence.from_jsonl",
            sys::emu_automation_result_t::EMU_AUTOMATION_SERIALIZATION_ERROR,
        )
    })?;
    let body_start = start + marker.len() - 1;
    let mut depth = 0usize;
    for (offset, ch) in text[body_start..].char_indices() {
        match ch {
            '{' => depth += 1,
            '}' => {
                depth -= 1;
                if depth == 0 {
                    return Ok(&text[body_start..=body_start + offset]);
                }
            }
            _ => {}
        }
    }
    Err(simple_error(
        "input_sequence.from_jsonl",
        sys::emu_automation_result_t::EMU_AUTOMATION_SERIALIZATION_ERROR,
    ))
}

fn extract_json_string(text: &str, key: &str) -> Result<String, Error> {
    let marker = format!("\"{key}\":\"");
    let start = text.find(&marker).ok_or_else(|| {
        simple_error(
            "input_sequence.from_jsonl",
            sys::emu_automation_result_t::EMU_AUTOMATION_SERIALIZATION_ERROR,
        )
    })? + marker.len();
    let tail = &text[start..];
    let end = tail.find('"').ok_or_else(|| {
        simple_error(
            "input_sequence.from_jsonl",
            sys::emu_automation_result_t::EMU_AUTOMATION_SERIALIZATION_ERROR,
        )
    })?;
    Ok(tail[..end]
        .replace("\\\"", "\"")
        .replace("\\n", "\n")
        .replace("\\r", "\r")
        .replace("\\t", "\t")
        .replace("\\\\", "\\"))
}

fn extract_json_u64(text: &str, key: &str) -> Result<u64, Error> {
    let marker = format!("\"{key}\":");
    let start = text.find(&marker).ok_or_else(|| {
        simple_error(
            "input_sequence.from_jsonl",
            sys::emu_automation_result_t::EMU_AUTOMATION_SERIALIZATION_ERROR,
        )
    })? + marker.len();
    let tail = &text[start..];
    let end = tail.find([',', '}']).unwrap_or(tail.len());
    tail[..end].trim().parse::<u64>().map_err(|_| {
        simple_error(
            "input_sequence.from_jsonl",
            sys::emu_automation_result_t::EMU_AUTOMATION_SERIALIZATION_ERROR,
        )
    })
}

fn extract_json_i32(text: &str, key: &str) -> Result<i32, Error> {
    let marker = format!("\"{key}\":");
    let start = text.find(&marker).ok_or_else(|| {
        simple_error(
            "input_sequence.from_jsonl",
            sys::emu_automation_result_t::EMU_AUTOMATION_SERIALIZATION_ERROR,
        )
    })? + marker.len();
    let tail = &text[start..];
    let end = tail.find([',', '}']).unwrap_or(tail.len());
    tail[..end].trim().parse::<i32>().map_err(|_| {
        simple_error(
            "input_sequence.from_jsonl",
            sys::emu_automation_result_t::EMU_AUTOMATION_SERIALIZATION_ERROR,
        )
    })
}

fn timing_kind_to_i32(kind: sys::emu_automation_timing_kind_t) -> i32 {
    match kind {
        sys::emu_automation_timing_kind_t::EMU_AUTOMATION_TIMING_IMMEDIATE => 0,
        sys::emu_automation_timing_kind_t::EMU_AUTOMATION_TIMING_FRAME => 1,
        sys::emu_automation_timing_kind_t::EMU_AUTOMATION_TIMING_CYCLE => 2,
        sys::emu_automation_timing_kind_t::EMU_AUTOMATION_TIMING_DELAY_FRAMES => 3,
        sys::emu_automation_timing_kind_t::EMU_AUTOMATION_TIMING_DELAY_CYCLES => 4,
    }
}

fn timing_kind_from_i32(value: i32) -> Result<sys::emu_automation_timing_kind_t, Error> {
    match value {
        0 => Ok(sys::emu_automation_timing_kind_t::EMU_AUTOMATION_TIMING_IMMEDIATE),
        1 => Ok(sys::emu_automation_timing_kind_t::EMU_AUTOMATION_TIMING_FRAME),
        2 => Ok(sys::emu_automation_timing_kind_t::EMU_AUTOMATION_TIMING_CYCLE),
        3 => Ok(sys::emu_automation_timing_kind_t::EMU_AUTOMATION_TIMING_DELAY_FRAMES),
        4 => Ok(sys::emu_automation_timing_kind_t::EMU_AUTOMATION_TIMING_DELAY_CYCLES),
        _ => Err(simple_error(
            "input_sequence.from_jsonl",
            sys::emu_automation_result_t::EMU_AUTOMATION_SERIALIZATION_ERROR,
        )),
    }
}

fn simple_error(operation: &'static str, code: sys::emu_automation_result_t) -> Error {
    Error {
        operation,
        code,
        name: format!("{code:?}").to_lowercase(),
    }
}

fn copy_text_grid(raw: &sys::emu_automation_text_grid_snapshot_t) -> TextGridSnapshot {
    let cells = if raw.cells.is_null() {
        Vec::new()
    } else {
        let slice = unsafe { std::slice::from_raw_parts(raw.cells, raw.cell_count) };
        slice.iter().map(copy_text_cell).collect()
    };

    let plain = if raw.plain_utf8.is_null() {
        String::new()
    } else {
        let bytes = unsafe {
            std::slice::from_raw_parts(raw.plain_utf8.cast::<u8>(), raw.plain_utf8_size)
        };
        String::from_utf8_lossy(bytes).into_owned()
    };

    TextGridSnapshot {
        region_id: c_string(raw.region_id),
        columns: raw.columns,
        rows: raw.rows,
        row_stride: raw.row_stride,
        plain,
        cells,
        frame: FrameMetadata {
            frame_number: raw.frame.frame_number,
            emulated_cycles: raw.frame.emulated_cycles,
            emulated_time_ns: raw.frame.emulated_time_ns,
            execution_state: raw.frame.execution_state,
        },
    }
}

fn text_grid_key(snapshot: &TextGridSnapshot) -> (String, u32, u32, u32, String, Vec<TextCell>) {
    (
        snapshot.region_id.clone(),
        snapshot.columns,
        snapshot.rows,
        snapshot.row_stride,
        snapshot.plain.clone(),
        snapshot.cells.clone(),
    )
}

fn copy_text_cell(raw: &sys::emu_automation_text_cell_t) -> TextCell {
    TextCell {
        native_code: raw.native_code,
        unicode_codepoint: raw.unicode_codepoint,
        text: char::from_u32(raw.unicode_codepoint)
            .map(|value| value.to_string())
            .unwrap_or_default(),
        glyph_id: c_string(raw.glyph_id),
        foreground_color: raw.foreground_color,
        background_color: raw.background_color,
        attribute_flags: raw.attribute_flags,
        charset_id: c_string(raw.charset_id),
        source_address: raw.source_address,
        confidence: raw.confidence,
    }
}

fn copy_text_deltas(raw: &sys::emu_automation_event_t) -> Vec<TextDelta> {
    if raw.text_deltas.is_null() || raw.text_delta_count == 0 {
        return Vec::new();
    }
    let slice = unsafe { std::slice::from_raw_parts(raw.text_deltas, raw.text_delta_count) };
    slice
        .iter()
        .map(|delta| TextDelta {
            x: delta.x,
            y: delta.y,
            before: copy_text_cell(&delta.before),
            after: copy_text_cell(&delta.after),
        })
        .collect()
}

fn copy_framebuffer(raw: &sys::emu_automation_framebuffer_snapshot_t) -> FramebufferSnapshot {
    let pixels = if raw.pixels.is_null() || raw.pixel_size == 0 {
        Vec::new()
    } else {
        unsafe { std::slice::from_raw_parts(raw.pixels, raw.pixel_size) }.to_vec()
    };
    FramebufferSnapshot {
        frame: FrameMetadata {
            frame_number: raw.frame.frame_number,
            emulated_cycles: raw.frame.emulated_cycles,
            emulated_time_ns: raw.frame.emulated_time_ns,
            execution_state: raw.frame.execution_state,
        },
        width: raw.width,
        height: raw.height,
        stride_bytes: raw.stride_bytes,
        pixel_format: raw.pixel_format,
        visible_area: Rect {
            x: raw.visible_area.x,
            y: raw.visible_area.y,
            width: raw.visible_area.width,
            height: raw.visible_area.height,
        },
        pixel_aspect_numerator: raw.pixel_aspect_numerator,
        pixel_aspect_denominator: raw.pixel_aspect_denominator,
        pixels,
    }
}

fn framebuffer_key(
    snapshot: &FramebufferSnapshot,
) -> (
    u32,
    u32,
    u32,
    sys::emu_automation_pixel_format_t,
    Rect,
    u32,
    u32,
    Vec<u8>,
) {
    (
        snapshot.width,
        snapshot.height,
        snapshot.stride_bytes,
        snapshot.pixel_format,
        snapshot.visible_area.clone(),
        snapshot.pixel_aspect_numerator,
        snapshot.pixel_aspect_denominator,
        snapshot.pixels.clone(),
    )
}

fn c_string(ptr: *const std::ffi::c_char) -> String {
    if ptr.is_null() {
        return String::new();
    }
    unsafe { CStr::from_ptr(ptr) }.to_string_lossy().into_owned()
}

fn c_string_buf(buf: &[std::ffi::c_char]) -> String {
    let len = buf.iter().position(|&ch| ch == 0).unwrap_or(buf.len());
    let bytes: Vec<u8> = buf[..len].iter().map(|&ch| ch as u8).collect();
    String::from_utf8_lossy(&bytes).into_owned()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::ffi::c_char;

    #[test]
    fn copy_framebuffer_clones_pixel_bytes() {
        let pixels = [1u8, 2, 3, 4];
        let raw = sys::emu_automation_framebuffer_snapshot_t {
            struct_size: std::mem::size_of::<sys::emu_automation_framebuffer_snapshot_t>() as u32,
            struct_version: sys::EMU_AUTOMATION_STRUCT_VERSION,
            frame: empty_frame(),
            width: 1,
            height: 1,
            stride_bytes: 4,
            pixel_format: sys::emu_automation_pixel_format_t::EMU_AUTOMATION_PIXEL_FORMAT_RGBA8888,
            visible_area: sys::emu_automation_rect_t {
                x: 0,
                y: 0,
                width: 1,
                height: 1,
            },
            pixel_aspect_numerator: 1,
            pixel_aspect_denominator: 1,
            pixels: pixels.as_ptr(),
            pixel_size: pixels.len(),
            adapter_owned: std::ptr::null_mut(),
        };
        let snapshot = copy_framebuffer(&raw);
        assert_eq!(snapshot.pixels, pixels);
        assert_eq!(snapshot.pixel_format, sys::emu_automation_pixel_format_t::EMU_AUTOMATION_PIXEL_FORMAT_RGBA8888);
    }

    #[test]
    fn copy_text_grid_clones_cells_and_plain_text() {
        static REGION: &[u8] = b"main\0";
        static GLYPH: &[u8] = b"ascii\0";
        static CHARSET: &[u8] = b"mock_charset\0";
        static PLAIN: &[u8] = b"AB\nCD";
        let cells = [
            sys::emu_automation_text_cell_t {
                struct_size: std::mem::size_of::<sys::emu_automation_text_cell_t>() as u32,
                struct_version: sys::EMU_AUTOMATION_STRUCT_VERSION,
                native_code: 'A' as u32,
                unicode_codepoint: 'A' as u32,
                glyph_id: GLYPH.as_ptr().cast::<c_char>(),
                foreground_color: 7,
                background_color: 0,
                attribute_flags: 1,
                charset_id: CHARSET.as_ptr().cast::<c_char>(),
                source_address: 0x400,
                confidence: 255,
            },
            sys::emu_automation_text_cell_t {
                struct_size: std::mem::size_of::<sys::emu_automation_text_cell_t>() as u32,
                struct_version: sys::EMU_AUTOMATION_STRUCT_VERSION,
                native_code: 'B' as u32,
                unicode_codepoint: 'B' as u32,
                glyph_id: GLYPH.as_ptr().cast::<c_char>(),
                foreground_color: 7,
                background_color: 0,
                attribute_flags: 2,
                charset_id: CHARSET.as_ptr().cast::<c_char>(),
                source_address: 0x401,
                confidence: 255,
            },
        ];
        let raw = sys::emu_automation_text_grid_snapshot_t {
            struct_size: std::mem::size_of::<sys::emu_automation_text_grid_snapshot_t>() as u32,
            struct_version: sys::EMU_AUTOMATION_STRUCT_VERSION,
            frame: empty_frame(),
            region_id: REGION.as_ptr().cast::<c_char>(),
            columns: 2,
            rows: 1,
            row_stride: 2,
            cells: cells.as_ptr(),
            cell_count: cells.len(),
            plain_utf8: PLAIN.as_ptr().cast::<c_char>(),
            plain_utf8_size: PLAIN.len(),
            adapter_owned: std::ptr::null_mut(),
        };
        let snapshot = copy_text_grid(&raw);
        assert_eq!(snapshot.region_id, "main");
        assert_eq!(snapshot.plain, "AB\nCD");
        assert_eq!(snapshot.cells.len(), 2);
        assert_eq!(snapshot.cells[0].text, "A");
        assert_eq!(snapshot.cells[1].source_address, 0x401);
    }
}
