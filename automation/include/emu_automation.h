#ifndef EMU_AUTOMATION_H
#define EMU_AUTOMATION_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define EMU_AUTOMATION_ABI_VERSION 2u
#define EMU_AUTOMATION_STRUCT_VERSION 2u

typedef struct emu_automation_machine emu_automation_machine_t;
typedef struct emu_automation_subscription emu_automation_subscription_t;

typedef enum emu_automation_result {
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
    EMU_AUTOMATION_INTERNAL_ERROR = 15
} emu_automation_result_t;

typedef enum emu_automation_execution_state {
    EMU_AUTOMATION_EXECUTION_STOPPED = 0,
    EMU_AUTOMATION_EXECUTION_RUNNING = 1,
    EMU_AUTOMATION_EXECUTION_PAUSED = 2,
    EMU_AUTOMATION_EXECUTION_RESETTING = 3,
    EMU_AUTOMATION_EXECUTION_ERROR = 4
} emu_automation_execution_state_t;

typedef enum emu_automation_reset_kind {
    EMU_AUTOMATION_RESET_COLD = 0,
    EMU_AUTOMATION_RESET_WARM = 1
} emu_automation_reset_kind_t;

typedef enum emu_automation_pixel_format {
    EMU_AUTOMATION_PIXEL_FORMAT_UNKNOWN = 0,
    EMU_AUTOMATION_PIXEL_FORMAT_RGBA8888 = 1,
    EMU_AUTOMATION_PIXEL_FORMAT_BGRA8888 = 2,
    EMU_AUTOMATION_PIXEL_FORMAT_RGB565 = 3,
    EMU_AUTOMATION_PIXEL_FORMAT_INDEX8 = 4
} emu_automation_pixel_format_t;

typedef enum emu_automation_input_action {
    EMU_AUTOMATION_INPUT_RELEASE = 0,
    EMU_AUTOMATION_INPUT_PRESS = 1
} emu_automation_input_action_t;

typedef enum emu_automation_input_device_kind {
    EMU_AUTOMATION_INPUT_DEVICE_KEYBOARD = 0,
    EMU_AUTOMATION_INPUT_DEVICE_CONTROLLER = 1,
    EMU_AUTOMATION_INPUT_DEVICE_MOUSE = 2,
    EMU_AUTOMATION_INPUT_DEVICE_PADDLE = 3,
    EMU_AUTOMATION_INPUT_DEVICE_CONSOLE = 4
} emu_automation_input_device_kind_t;

typedef enum emu_automation_key_modifier_bits {
    EMU_AUTOMATION_KEY_MODIFIER_SHIFT = 1u << 0,
    EMU_AUTOMATION_KEY_MODIFIER_CTRL = 1u << 1,
    EMU_AUTOMATION_KEY_MODIFIER_ALT = 1u << 2,
    EMU_AUTOMATION_KEY_MODIFIER_META = 1u << 3
} emu_automation_key_modifier_bits_t;

typedef enum emu_automation_timing_kind {
    EMU_AUTOMATION_TIMING_IMMEDIATE = 0,
    EMU_AUTOMATION_TIMING_FRAME = 1,
    EMU_AUTOMATION_TIMING_CYCLE = 2,
    EMU_AUTOMATION_TIMING_DELAY_FRAMES = 3,
    EMU_AUTOMATION_TIMING_DELAY_CYCLES = 4
} emu_automation_timing_kind_t;

typedef enum emu_automation_event_type {
    EMU_AUTOMATION_EVENT_NONE = 0,
    EMU_AUTOMATION_EVENT_FRAME_COMPLETED = 1,
    EMU_AUTOMATION_EVENT_MACHINE_RESET = 2,
    EMU_AUTOMATION_EVENT_EXECUTION_STATE_CHANGED = 3,
    EMU_AUTOMATION_EVENT_INPUT_SUBMITTED = 4,
    EMU_AUTOMATION_EVENT_SCREEN_CHANGED = 5,
    EMU_AUTOMATION_EVENT_TEXT_CHANGED = 6,
    EMU_AUTOMATION_EVENT_MEDIA_ACTIVITY = 7,
    EMU_AUTOMATION_EVENT_DEBUG_MESSAGE = 8,
    EMU_AUTOMATION_EVENT_ERROR = 9
} emu_automation_event_type_t;

enum {
    EMU_AUTOMATION_CAP_SCREEN_FRAMEBUFFER = 1u << 0,
    EMU_AUTOMATION_CAP_INPUT_KEYBOARD = 1u << 1,
    EMU_AUTOMATION_CAP_INPUT_CONTROLLER = 1u << 2,
    EMU_AUTOMATION_CAP_EXEC_PAUSE = 1u << 3,
    EMU_AUTOMATION_CAP_EXEC_RESUME = 1u << 4,
    EMU_AUTOMATION_CAP_EXEC_RESET = 1u << 5,
    EMU_AUTOMATION_CAP_EXEC_STEP_FRAME = 1u << 6,
    EMU_AUTOMATION_CAP_EXEC_RUN_FRAMES = 1u << 7,
    EMU_AUTOMATION_CAP_EVENTS_FRAME_COMPLETED = 1u << 8,
    EMU_AUTOMATION_CAP_SCREEN_TEXT_GRID = 1u << 9,
    EMU_AUTOMATION_CAP_INSPECT_MEMORY = 1u << 10,
    EMU_AUTOMATION_CAP_EXEC_PROGRAM_COUNTER = 1u << 11,
    EMU_AUTOMATION_CAP_EXEC_TIMING = 1u << 12,
    EMU_AUTOMATION_CAP_INSPECT_MEMORY_WRITE = 1u << 13,
    EMU_AUTOMATION_CAP_INSPECT_REGISTERS = 1u << 14,
    EMU_AUTOMATION_CAP_EXEC_CURRENT_INSTRUCTION = 1u << 15,
    EMU_AUTOMATION_CAP_DEBUG_BREAKPOINTS = 1u << 16,
    EMU_AUTOMATION_CAP_DEBUG_WATCHPOINTS = 1u << 17
};

typedef struct emu_automation_error {
    uint32_t struct_size;
    uint32_t struct_version;
    emu_automation_result_t code;
    const char *operation;
    const char *message;
    const char *native_detail;
    int32_t native_code;
} emu_automation_error_t;

typedef struct emu_automation_capabilities {
    uint32_t struct_size;
    uint32_t struct_version;
    uint64_t feature_bits;
} emu_automation_capabilities_t;

typedef struct emu_automation_machine_descriptor {
    uint32_t struct_size;
    uint32_t struct_version;
    const char *machine_id;
    const char *system_id;
    const char *model_id;
    const char *region;
    const char *video_standard;
    const char *adapter_version;
    uint64_t configured_memory_bytes;
    emu_automation_capabilities_t capabilities;
} emu_automation_machine_descriptor_t;

typedef struct emu_automation_frame_metadata {
    uint32_t struct_size;
    uint32_t struct_version;
    uint64_t frame_number;
    uint64_t emulated_cycles;
    uint64_t emulated_time_ns;
    emu_automation_execution_state_t execution_state;
} emu_automation_frame_metadata_t;

typedef struct emu_automation_rect {
    int32_t x;
    int32_t y;
    uint32_t width;
    uint32_t height;
} emu_automation_rect_t;

typedef struct emu_automation_framebuffer_snapshot {
    uint32_t struct_size;
    uint32_t struct_version;
    emu_automation_frame_metadata_t frame;
    uint32_t width;
    uint32_t height;
    uint32_t stride_bytes;
    emu_automation_pixel_format_t pixel_format;
    emu_automation_rect_t visible_area;
    uint32_t pixel_aspect_numerator;
    uint32_t pixel_aspect_denominator;
    const uint8_t *pixels;
    size_t pixel_size;
    void *adapter_owned;
} emu_automation_framebuffer_snapshot_t;

typedef struct emu_automation_text_cell {
    uint32_t struct_size;
    uint32_t struct_version;
    uint32_t native_code;
    uint32_t unicode_codepoint;
    const char *glyph_id;
    int32_t foreground_color;
    int32_t background_color;
    uint32_t attribute_flags;
    const char *charset_id;
    uint64_t source_address;
    uint8_t confidence;
} emu_automation_text_cell_t;

typedef struct emu_automation_text_view_descriptor {
    uint32_t struct_size;
    uint32_t struct_version;
    const char *region_id;
    uint32_t columns;
    uint32_t rows;
    uint32_t row_stride;
    const char *charset_id;
    const char *native_encoding;
    const char *unicode_map;
} emu_automation_text_view_descriptor_t;

typedef struct emu_automation_text_grid_snapshot {
    uint32_t struct_size;
    uint32_t struct_version;
    emu_automation_frame_metadata_t frame;
    const char *region_id;
    uint32_t columns;
    uint32_t rows;
    uint32_t row_stride;
    const emu_automation_text_cell_t *cells;
    size_t cell_count;
    const char *plain_utf8;
    size_t plain_utf8_size;
    void *adapter_owned;
} emu_automation_text_grid_snapshot_t;

typedef struct emu_automation_text_delta {
    uint32_t struct_size;
    uint32_t struct_version;
    uint32_t x;
    uint32_t y;
    emu_automation_text_cell_t before;
    emu_automation_text_cell_t after;
} emu_automation_text_delta_t;

typedef struct emu_automation_input_device_descriptor {
    uint32_t struct_size;
    uint32_t struct_version;
    const char *device_id;
    const char *display_name;
    emu_automation_input_device_kind_t kind;
    uint32_t port_index;
    uint32_t control_count;
} emu_automation_input_device_descriptor_t;

typedef struct emu_automation_character_mapping_descriptor {
    uint32_t struct_size;
    uint32_t struct_version;
    const char *device_id;
    uint32_t unicode_codepoint;
    uint32_t native_code;
    const char *key_id;
    uint32_t required_modifier_bits;
    const char *shift_key_id;
    const char *ctrl_key_id;
    const char *alt_key_id;
    const char *meta_key_id;
} emu_automation_character_mapping_descriptor_t;

typedef struct emu_automation_timing {
    emu_automation_timing_kind_t kind;
    uint64_t value;
} emu_automation_timing_t;

typedef struct emu_automation_key_event {
    uint32_t struct_size;
    uint32_t struct_version;
    const char *device_id;
    const char *key_id;
    emu_automation_input_action_t action;
    emu_automation_timing_t timing;
} emu_automation_key_event_t;

typedef struct emu_automation_controller_button_event {
    uint32_t struct_size;
    uint32_t struct_version;
    const char *device_id;
    const char *control_id;
    emu_automation_input_action_t action;
    emu_automation_timing_t timing;
} emu_automation_controller_button_event_t;

typedef struct emu_automation_event {
    uint32_t struct_size;
    uint32_t struct_version;
    uint64_t sequence_number;
    emu_automation_event_type_t event_type;
    emu_automation_frame_metadata_t frame;
    emu_automation_frame_metadata_t input_accepted;
    emu_automation_frame_metadata_t input_applied;
    const char *device_id;
    const char *control_id;
    const char *region_id;
    uint32_t change_x;
    uint32_t change_y;
    uint32_t change_width;
    uint32_t change_height;
    uint32_t change_cell_count;
    const emu_automation_text_delta_t *text_deltas;
    size_t text_delta_count;
    const char *message;
    emu_automation_input_action_t input_action;
    emu_automation_timing_t input_timing;
    emu_automation_execution_state_t previous_execution_state;
    emu_automation_execution_state_t current_execution_state;
    void *adapter_owned;
} emu_automation_event_t;

typedef struct emu_automation_register_value {
    uint32_t struct_size;
    uint32_t struct_version;
    char name[32];
    char hex_value[32];
    char dec_value[32];
    uint8_t has_dec;
    uint8_t changed;
} emu_automation_register_value_t;

typedef struct emu_automation_instruction {
    uint32_t struct_size;
    uint32_t struct_version;
    uint64_t address;
    char bytes[32];
    char text[96];
    char symbol[64];
    uint8_t has_symbol;
    uint8_t is_current_ip;
    uint8_t has_breakpoint;
    uint64_t branch_target;
    uint8_t has_branch_target;
    uint8_t changed_since_last_step;
} emu_automation_instruction_t;

typedef void (*emu_automation_event_callback_t)(
    const emu_automation_event_t *event,
    void *user_data);

/*
 * Subscription callbacks are invoked only when the caller explicitly pumps a
 * subscription or dispatch helper. The core does not start threads or
 * background dispatch loops.
 *
 * Callback and threading contract for the current ABI:
 * - callbacks run synchronously on the same thread that called the dispatch
 *   function
 * - callbacks must not recursively dispatch the same subscription while a
 *   callback is already active for it
 * - callbacks must not use a subscription after it has been destroyed
 * - cross-thread use of the same machine or subscription handle is currently
 *   unsupported unless the embedding layer provides its own serialization
 */

uint32_t emu_automation_abi_version(void);
const char *emu_automation_result_name(emu_automation_result_t result);

void emu_automation_machine_destroy(emu_automation_machine_t *machine);

emu_automation_result_t emu_automation_machine_describe(
    emu_automation_machine_t *machine,
    emu_automation_machine_descriptor_t *out_descriptor);

emu_automation_result_t emu_automation_machine_capabilities(
    emu_automation_machine_t *machine,
    emu_automation_capabilities_t *out_capabilities);
emu_automation_result_t emu_automation_machine_character_mapping_count(
    emu_automation_machine_t *machine,
    size_t *out_count);
emu_automation_result_t emu_automation_machine_character_mapping_descriptor(
    emu_automation_machine_t *machine,
    size_t index,
    emu_automation_character_mapping_descriptor_t *out_descriptor);

emu_automation_result_t emu_automation_machine_pause(emu_automation_machine_t *machine);
emu_automation_result_t emu_automation_machine_resume(emu_automation_machine_t *machine);
emu_automation_result_t emu_automation_machine_reset(
    emu_automation_machine_t *machine,
    emu_automation_reset_kind_t kind);
emu_automation_result_t emu_automation_machine_step_frame(emu_automation_machine_t *machine);
emu_automation_result_t emu_automation_machine_run_frames(
    emu_automation_machine_t *machine,
    uint64_t frame_count);

emu_automation_result_t emu_automation_screen_framebuffer(
    emu_automation_machine_t *machine,
    emu_automation_framebuffer_snapshot_t *out_snapshot);
void emu_automation_framebuffer_release(
    emu_automation_machine_t *machine,
    emu_automation_framebuffer_snapshot_t *snapshot);

emu_automation_result_t emu_automation_screen_text_grid(
    emu_automation_machine_t *machine,
    const char *region_id,
    emu_automation_text_grid_snapshot_t *out_snapshot);
emu_automation_result_t emu_automation_screen_text_view_count(
    emu_automation_machine_t *machine,
    size_t *out_count);
emu_automation_result_t emu_automation_screen_text_view_descriptor(
    emu_automation_machine_t *machine,
    size_t index,
    emu_automation_text_view_descriptor_t *out_descriptor);
void emu_automation_text_grid_release(
    emu_automation_machine_t *machine,
    emu_automation_text_grid_snapshot_t *snapshot);

emu_automation_result_t emu_automation_memory_read(
    emu_automation_machine_t *machine,
    uint64_t address,
    uint8_t *out_bytes,
    size_t size);
emu_automation_result_t emu_automation_memory_write(
    emu_automation_machine_t *machine,
    uint64_t address,
    const uint8_t *bytes,
    size_t size);

emu_automation_result_t emu_automation_execution_program_counter(
    emu_automation_machine_t *machine,
    uint64_t *out_program_counter);

emu_automation_result_t emu_automation_execution_frame_metadata(
    emu_automation_machine_t *machine,
    emu_automation_frame_metadata_t *out_metadata);
emu_automation_result_t emu_automation_execution_current_instruction(
    emu_automation_machine_t *machine,
    emu_automation_instruction_t *out_instruction);
emu_automation_result_t emu_automation_register_count(
    emu_automation_machine_t *machine,
    size_t *out_count);
emu_automation_result_t emu_automation_register_read(
    emu_automation_machine_t *machine,
    emu_automation_register_value_t *out_registers,
    size_t register_capacity,
    size_t *out_register_count);
emu_automation_result_t emu_automation_register_write(
    emu_automation_machine_t *machine,
    const char *register_name,
    uint64_t value);
emu_automation_result_t emu_automation_breakpoint_set(
    emu_automation_machine_t *machine,
    uint64_t address,
    uint8_t enabled);

emu_automation_result_t emu_automation_input_key(
    emu_automation_machine_t *machine,
    const emu_automation_key_event_t *event);
emu_automation_result_t emu_automation_input_controller_button(
    emu_automation_machine_t *machine,
    const emu_automation_controller_button_event_t *event);
emu_automation_result_t emu_automation_events_poll(
    emu_automation_machine_t *machine,
    uint64_t after_sequence,
    emu_automation_event_t *out_event);
emu_automation_result_t emu_automation_events_dispatch_available(
    emu_automation_machine_t *machine,
    uint64_t *inout_after_sequence,
    size_t max_events,
    emu_automation_event_callback_t callback,
    void *user_data,
    size_t *out_dispatch_count);
emu_automation_result_t emu_automation_events_dispatch_matching(
    emu_automation_machine_t *machine,
    uint64_t *inout_after_sequence,
    emu_automation_event_type_t event_type,
    size_t max_events,
    emu_automation_event_callback_t callback,
    void *user_data,
    size_t *out_dispatch_count);
emu_automation_result_t emu_automation_subscription_create(
    emu_automation_machine_t *machine,
    emu_automation_event_type_t event_type,
    uint64_t after_sequence,
    emu_automation_event_callback_t callback,
    void *user_data,
    emu_automation_subscription_t **out_subscription);
emu_automation_result_t emu_automation_subscription_dispatch_available(
    emu_automation_subscription_t *subscription,
    size_t max_events,
    size_t *out_dispatch_count);
uint64_t emu_automation_subscription_after_sequence(
    const emu_automation_subscription_t *subscription);
emu_automation_result_t emu_automation_subscription_set_after_sequence(
    emu_automation_subscription_t *subscription,
    uint64_t after_sequence);
void emu_automation_subscription_destroy(
    emu_automation_subscription_t *subscription);
void emu_automation_event_release(
    emu_automation_machine_t *machine,
    emu_automation_event_t *event);

#ifdef __cplusplus
}
#endif

#endif
