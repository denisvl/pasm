#ifndef EMU_AUTOMATION_H
#define EMU_AUTOMATION_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define EMU_AUTOMATION_ABI_VERSION 1u
#define EMU_AUTOMATION_STRUCT_VERSION 1u

typedef struct emu_automation_machine emu_automation_machine_t;

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

typedef enum emu_automation_timing_kind {
    EMU_AUTOMATION_TIMING_IMMEDIATE = 0,
    EMU_AUTOMATION_TIMING_FRAME = 1,
    EMU_AUTOMATION_TIMING_CYCLE = 2,
    EMU_AUTOMATION_TIMING_DELAY_FRAMES = 3,
    EMU_AUTOMATION_TIMING_DELAY_CYCLES = 4
} emu_automation_timing_kind_t;

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
    EMU_AUTOMATION_CAP_SCREEN_TEXT_GRID = 1u << 9
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

typedef struct emu_automation_input_device_descriptor {
    uint32_t struct_size;
    uint32_t struct_version;
    const char *device_id;
    const char *display_name;
    emu_automation_input_device_kind_t kind;
    uint32_t port_index;
    uint32_t control_count;
} emu_automation_input_device_descriptor_t;

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

uint32_t emu_automation_abi_version(void);
const char *emu_automation_result_name(emu_automation_result_t result);

void emu_automation_machine_destroy(emu_automation_machine_t *machine);

emu_automation_result_t emu_automation_machine_describe(
    emu_automation_machine_t *machine,
    emu_automation_machine_descriptor_t *out_descriptor);

emu_automation_result_t emu_automation_machine_capabilities(
    emu_automation_machine_t *machine,
    emu_automation_capabilities_t *out_capabilities);

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

emu_automation_result_t emu_automation_input_key(
    emu_automation_machine_t *machine,
    const emu_automation_key_event_t *event);
emu_automation_result_t emu_automation_input_controller_button(
    emu_automation_machine_t *machine,
    const emu_automation_controller_button_event_t *event);

#ifdef __cplusplus
}
#endif

#endif
