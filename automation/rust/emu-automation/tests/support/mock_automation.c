#include "emu_automation_adapter.h"

#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

typedef struct MockMachine {
    uint64_t frame;
    uint64_t next_sequence;
    uint32_t key_count;
    uint32_t button_count;
    uint32_t text_release_count;
    emu_automation_execution_state_t state;
    uint64_t program_counter;
    uint8_t mem_0200;
    uint8_t mem_0201;
    uint8_t pixels[16];
    emu_automation_text_cell_t cells[4];
    emu_automation_text_delta_t text_deltas[4];
    emu_automation_event_t events[32];
    size_t event_count;
} MockMachine;

static void mock_push_event(
    MockMachine *machine,
    emu_automation_event_type_t event_type,
    emu_automation_execution_state_t previous_execution_state,
    emu_automation_execution_state_t current_execution_state,
    const char *device_id,
    const char *control_id,
    const char *region_id,
    uint32_t change_x,
    uint32_t change_y,
    uint32_t change_width,
    uint32_t change_height,
    uint32_t change_cell_count,
    const char *message,
    emu_automation_input_action_t input_action,
    emu_automation_timing_t input_timing);
static emu_automation_result_t mock_capabilities(
    void *context,
    emu_automation_capabilities_t *out_capabilities);
static emu_automation_result_t mock_character_mapping_count(
    void *context,
    size_t *out_count);
static emu_automation_result_t mock_character_mapping_descriptor(
    void *context,
    size_t index,
    emu_automation_character_mapping_descriptor_t *out_descriptor);

static emu_automation_result_t mock_categories_describe(
    void *context,
    emu_automation_machine_descriptor_t *out_descriptor)
{
    (void)context;
    out_descriptor->machine_id = "mock-rust-categories";
    out_descriptor->system_id = "mock-system";
    out_descriptor->model_id = "mock-model";
    out_descriptor->region = "test";
    out_descriptor->video_standard = "text";
    out_descriptor->adapter_version = "rust-test-1";
    out_descriptor->configured_memory_bytes = 65536u;
    return mock_capabilities(context, &out_descriptor->capabilities);
}

static void mock_seed_category_events(MockMachine *machine)
{
    mock_push_event(
        machine,
        EMU_AUTOMATION_EVENT_MEDIA_ACTIVITY,
        0,
        0,
        NULL,
        NULL,
        NULL,
        0u, 0u, 0u, 0u, 0u,
        "disk activity",
        EMU_AUTOMATION_INPUT_RELEASE,
        (emu_automation_timing_t){EMU_AUTOMATION_TIMING_IMMEDIATE, 0u});
    mock_push_event(
        machine,
        EMU_AUTOMATION_EVENT_DEBUG_MESSAGE,
        0,
        0,
        NULL,
        NULL,
        NULL,
        0u, 0u, 0u, 0u, 0u,
        "debug trace",
        EMU_AUTOMATION_INPUT_RELEASE,
        (emu_automation_timing_t){EMU_AUTOMATION_TIMING_IMMEDIATE, 0u});
    mock_push_event(
        machine,
        EMU_AUTOMATION_EVENT_ERROR,
        0,
        0,
        NULL,
        NULL,
        NULL,
        0u, 0u, 0u, 0u, 0u,
        "adapter error",
        EMU_AUTOMATION_INPUT_RELEASE,
        (emu_automation_timing_t){EMU_AUTOMATION_TIMING_IMMEDIATE, 0u});
}

static void mock_init_text_deltas(MockMachine *machine)
{
    static const uint32_t before_codes[4] = { 'W', 'X', 'Y', 'Z' };
    static const uint32_t after_codes[4] = { 'A', 'B', 'C', 'D' };
    for (uint32_t i = 0u; i < 4u; ++i) {
        emu_automation_text_delta_t *delta = &machine->text_deltas[i];
        uint32_t row = i / 2u;
        uint32_t col = i % 2u;
        memset(delta, 0, sizeof(*delta));
        delta->struct_size = sizeof(*delta);
        delta->struct_version = EMU_AUTOMATION_STRUCT_VERSION;
        delta->x = col;
        delta->y = row;
        delta->before.struct_size = sizeof(delta->before);
        delta->before.struct_version = EMU_AUTOMATION_STRUCT_VERSION;
        delta->before.native_code = before_codes[i];
        delta->before.unicode_codepoint = before_codes[i];
        delta->before.glyph_id = "mock_ascii";
        delta->before.foreground_color = 7;
        delta->before.background_color = 0;
        delta->before.attribute_flags = i;
        delta->before.charset_id = "mock_charset";
        delta->before.source_address = 0x0400u + i;
        delta->before.confidence = 255u;
        delta->after = delta->before;
        delta->after.native_code = after_codes[i];
        delta->after.unicode_codepoint = after_codes[i];
    }
}

static void mock_push_event(
    MockMachine *machine,
    emu_automation_event_type_t event_type,
    emu_automation_execution_state_t previous_execution_state,
    emu_automation_execution_state_t current_execution_state,
    const char *device_id,
    const char *control_id,
    const char *region_id,
    uint32_t change_x,
    uint32_t change_y,
    uint32_t change_width,
    uint32_t change_height,
    uint32_t change_cell_count,
    const char *message,
    emu_automation_input_action_t input_action,
    emu_automation_timing_t input_timing)
{
    emu_automation_event_t *event;
    if (machine->event_count >= (sizeof(machine->events) / sizeof(machine->events[0]))) {
        return;
    }
    event = &machine->events[machine->event_count++];
    memset(event, 0, sizeof(*event));
    event->struct_size = sizeof(*event);
    event->struct_version = EMU_AUTOMATION_STRUCT_VERSION;
    event->sequence_number = ++machine->next_sequence;
    event->event_type = event_type;
    event->previous_execution_state = previous_execution_state;
    event->current_execution_state = current_execution_state;
    event->frame.struct_size = sizeof(event->frame);
    event->frame.struct_version = EMU_AUTOMATION_STRUCT_VERSION;
    event->frame.frame_number = machine->frame;
    event->frame.execution_state = machine->state;
    event->input_accepted.struct_size = sizeof(event->input_accepted);
    event->input_accepted.struct_version = EMU_AUTOMATION_STRUCT_VERSION;
    event->input_applied.struct_size = sizeof(event->input_applied);
    event->input_applied.struct_version = EMU_AUTOMATION_STRUCT_VERSION;
    if (event_type == EMU_AUTOMATION_EVENT_INPUT_SUBMITTED) {
        event->input_accepted.frame_number = machine->frame;
        event->input_accepted.execution_state = machine->state;
        event->input_applied.frame_number = machine->frame;
        event->input_applied.execution_state = machine->state;
    }
    event->device_id = device_id;
    event->control_id = control_id;
    event->region_id = region_id;
    event->change_x = change_x;
    event->change_y = change_y;
    event->change_width = change_width;
    event->change_height = change_height;
    event->change_cell_count = change_cell_count;
    if (event_type == EMU_AUTOMATION_EVENT_TEXT_CHANGED && change_cell_count == 4u) {
        mock_init_text_deltas(machine);
        event->text_deltas = machine->text_deltas;
        event->text_delta_count = 4u;
    }
    event->message = message;
    event->input_action = input_action;
    event->input_timing = input_timing;
}

static emu_automation_result_t mock_capabilities(
    void *context,
    emu_automation_capabilities_t *out_capabilities)
{
    (void)context;
    out_capabilities->feature_bits =
        EMU_AUTOMATION_CAP_SCREEN_FRAMEBUFFER |
        EMU_AUTOMATION_CAP_INSPECT_MEMORY |
        EMU_AUTOMATION_CAP_INSPECT_MEMORY_WRITE |
        EMU_AUTOMATION_CAP_INSPECT_REGISTERS |
        EMU_AUTOMATION_CAP_EXEC_PROGRAM_COUNTER |
        EMU_AUTOMATION_CAP_EXEC_CURRENT_INSTRUCTION |
        EMU_AUTOMATION_CAP_EXEC_TIMING |
        EMU_AUTOMATION_CAP_INPUT_KEYBOARD |
        EMU_AUTOMATION_CAP_INPUT_CONTROLLER |
        EMU_AUTOMATION_CAP_EXEC_PAUSE |
        EMU_AUTOMATION_CAP_EXEC_RESUME |
        EMU_AUTOMATION_CAP_EXEC_RESET |
        EMU_AUTOMATION_CAP_EXEC_STEP_FRAME |
        EMU_AUTOMATION_CAP_EXEC_RUN_FRAMES |
        EMU_AUTOMATION_CAP_EVENTS_FRAME_COMPLETED |
        EMU_AUTOMATION_CAP_SCREEN_TEXT_GRID;
    return EMU_AUTOMATION_OK;
}

static emu_automation_result_t mock_character_mapping_count(
    void *context,
    size_t *out_count)
{
    (void)context;
    *out_count = 2u;
    return EMU_AUTOMATION_OK;
}

static emu_automation_result_t mock_character_mapping_descriptor(
    void *context,
    size_t index,
    emu_automation_character_mapping_descriptor_t *out_descriptor)
{
    (void)context;
    if (index > 1u) {
        return EMU_AUTOMATION_INVALID_ARGUMENT;
    }
    if (index == 0u) {
        out_descriptor->device_id = "keyboard";
        out_descriptor->unicode_codepoint = 'A';
        out_descriptor->native_code = 65u;
        out_descriptor->key_id = "K_A";
        out_descriptor->required_modifier_bits = EMU_AUTOMATION_KEY_MODIFIER_SHIFT;
        out_descriptor->shift_key_id = "K_SHIFT";
        return EMU_AUTOMATION_OK;
    }
    out_descriptor->device_id = "keyboard";
    out_descriptor->unicode_codepoint = 13u;
    out_descriptor->native_code = 13u;
    out_descriptor->key_id = "K_RETURN";
    out_descriptor->required_modifier_bits = 0u;
    out_descriptor->shift_key_id = "K_SHIFT";
    return EMU_AUTOMATION_OK;
}

static emu_automation_result_t mock_describe(
    void *context,
    emu_automation_machine_descriptor_t *out_descriptor)
{
    (void)context;
    out_descriptor->machine_id = "mock-rust-machine";
    out_descriptor->system_id = "mock-system";
    out_descriptor->model_id = "mock-model";
    out_descriptor->region = "test";
    out_descriptor->video_standard = "text";
    out_descriptor->adapter_version = "rust-test-1";
    out_descriptor->configured_memory_bytes = 65536u;
    return mock_capabilities(context, &out_descriptor->capabilities);
}

static emu_automation_result_t mock_pause(void *context)
{
    MockMachine *machine = (MockMachine *)context;
    emu_automation_execution_state_t previous_state = machine->state;
    machine->state = EMU_AUTOMATION_EXECUTION_PAUSED;
    mock_push_event(
        machine,
        EMU_AUTOMATION_EVENT_EXECUTION_STATE_CHANGED,
        previous_state,
        EMU_AUTOMATION_EXECUTION_PAUSED,
        NULL,
        NULL,
        NULL,
        0u, 0u, 0u, 0u, 0u,
        NULL,
        EMU_AUTOMATION_INPUT_RELEASE,
        (emu_automation_timing_t){EMU_AUTOMATION_TIMING_IMMEDIATE, 0u});
    return EMU_AUTOMATION_OK;
}

static emu_automation_result_t mock_resume(void *context)
{
    MockMachine *machine = (MockMachine *)context;
    emu_automation_execution_state_t previous_state = machine->state;
    machine->state = EMU_AUTOMATION_EXECUTION_RUNNING;
    mock_push_event(
        machine,
        EMU_AUTOMATION_EVENT_EXECUTION_STATE_CHANGED,
        previous_state,
        EMU_AUTOMATION_EXECUTION_RUNNING,
        NULL,
        NULL,
        NULL,
        0u, 0u, 0u, 0u, 0u,
        NULL,
        EMU_AUTOMATION_INPUT_RELEASE,
        (emu_automation_timing_t){EMU_AUTOMATION_TIMING_IMMEDIATE, 0u});
    return EMU_AUTOMATION_OK;
}

static emu_automation_result_t mock_reset(void *context, emu_automation_reset_kind_t kind)
{
    MockMachine *machine = (MockMachine *)context;
    emu_automation_execution_state_t previous_state = machine->state;
    if (kind != EMU_AUTOMATION_RESET_COLD) {
        return EMU_AUTOMATION_UNSUPPORTED;
    }
    machine->frame = 0u;
    machine->program_counter = 0x0200u;
    machine->mem_0200 = 0x00u;
    machine->mem_0201 = 0x99u;
    machine->state = EMU_AUTOMATION_EXECUTION_PAUSED;
    mock_push_event(
        machine,
        EMU_AUTOMATION_EVENT_MACHINE_RESET,
        previous_state,
        EMU_AUTOMATION_EXECUTION_PAUSED,
        NULL,
        NULL,
        NULL,
        0u, 0u, 0u, 0u, 0u,
        NULL,
        EMU_AUTOMATION_INPUT_RELEASE,
        (emu_automation_timing_t){EMU_AUTOMATION_TIMING_IMMEDIATE, 0u});
    return EMU_AUTOMATION_OK;
}

static emu_automation_result_t mock_step_frame(void *context)
{
    MockMachine *machine = (MockMachine *)context;
    machine->frame++;
    machine->program_counter++;
    if (machine->frame == 3u) {
        if (machine->mem_0200 == 0x00u) {
            machine->mem_0200 = 0x42u;
        }
        mock_push_event(
            machine,
            EMU_AUTOMATION_EVENT_TEXT_CHANGED,
            0,
            0,
            NULL,
            NULL,
            "main",
            0u, 0u, 2u, 2u, 4u,
            NULL,
            EMU_AUTOMATION_INPUT_RELEASE,
            (emu_automation_timing_t){EMU_AUTOMATION_TIMING_IMMEDIATE, 0u});
        mock_push_event(
            machine,
            EMU_AUTOMATION_EVENT_SCREEN_CHANGED,
            0,
            0,
            NULL,
            NULL,
            "main",
            0u, 0u, 2u, 2u, 4u,
            NULL,
            EMU_AUTOMATION_INPUT_RELEASE,
            (emu_automation_timing_t){EMU_AUTOMATION_TIMING_IMMEDIATE, 0u});
    }
    mock_push_event(
        machine,
        EMU_AUTOMATION_EVENT_FRAME_COMPLETED,
        0,
        0,
        NULL,
        NULL,
        NULL,
        0u, 0u, 0u, 0u, 0u,
        NULL,
        EMU_AUTOMATION_INPUT_RELEASE,
        (emu_automation_timing_t){EMU_AUTOMATION_TIMING_IMMEDIATE, 0u});
    return EMU_AUTOMATION_OK;
}

static emu_automation_result_t mock_run_frames(void *context, uint64_t frame_count)
{
    MockMachine *machine = (MockMachine *)context;
    uint64_t i;
    for (i = 0u; i < frame_count; ++i) {
        machine->frame++;
        machine->program_counter++;
        if (machine->frame == 3u) {
            if (machine->mem_0200 == 0x00u) {
                machine->mem_0200 = 0x42u;
            }
            mock_push_event(
                machine,
                EMU_AUTOMATION_EVENT_TEXT_CHANGED,
                0,
                0,
                NULL,
                NULL,
                "main",
                0u, 0u, 2u, 2u, 4u,
                NULL,
                EMU_AUTOMATION_INPUT_RELEASE,
                (emu_automation_timing_t){EMU_AUTOMATION_TIMING_IMMEDIATE, 0u});
            mock_push_event(
                machine,
                EMU_AUTOMATION_EVENT_SCREEN_CHANGED,
                0,
                0,
                NULL,
                NULL,
                "main",
                0u, 0u, 2u, 2u, 4u,
                NULL,
                EMU_AUTOMATION_INPUT_RELEASE,
                (emu_automation_timing_t){EMU_AUTOMATION_TIMING_IMMEDIATE, 0u});
        }
        mock_push_event(
            machine,
            EMU_AUTOMATION_EVENT_FRAME_COMPLETED,
            0,
            0,
            NULL,
            NULL,
            NULL,
            0u, 0u, 0u, 0u, 0u,
            NULL,
            EMU_AUTOMATION_INPUT_RELEASE,
            (emu_automation_timing_t){EMU_AUTOMATION_TIMING_IMMEDIATE, 0u});
    }
    return EMU_AUTOMATION_OK;
}

static emu_automation_result_t mock_capture_framebuffer(
    void *context,
    emu_automation_framebuffer_snapshot_t *out_snapshot)
{
    MockMachine *machine = (MockMachine *)context;
    for (uint32_t i = 0u; i < sizeof(machine->pixels); ++i) {
        machine->pixels[i] = (uint8_t)(machine->frame + i);
    }
    out_snapshot->frame.frame_number = machine->frame;
    out_snapshot->frame.execution_state = machine->state;
    out_snapshot->width = 2u;
    out_snapshot->height = 2u;
    out_snapshot->stride_bytes = 8u;
    out_snapshot->pixel_format = EMU_AUTOMATION_PIXEL_FORMAT_RGBA8888;
    out_snapshot->visible_area.x = 0;
    out_snapshot->visible_area.y = 0;
    out_snapshot->visible_area.width = 2u;
    out_snapshot->visible_area.height = 2u;
    out_snapshot->pixel_aspect_numerator = 1u;
    out_snapshot->pixel_aspect_denominator = 1u;
    out_snapshot->pixels = machine->pixels;
    out_snapshot->pixel_size = sizeof(machine->pixels);
    return EMU_AUTOMATION_OK;
}

static emu_automation_result_t mock_capture_text_grid(
    void *context,
    const char *region_id,
    emu_automation_text_grid_snapshot_t *out_snapshot)
{
    MockMachine *machine = (MockMachine *)context;
    uint32_t char_base = machine->frame >= 3u ? (uint32_t)'A' : (uint32_t)'W';
    if (region_id != NULL && strcmp(region_id, "main") != 0) {
        return EMU_AUTOMATION_UNSUPPORTED;
    }
    for (uint32_t i = 0u; i < 4u; ++i) {
        machine->cells[i].struct_size = sizeof(machine->cells[i]);
        machine->cells[i].struct_version = EMU_AUTOMATION_STRUCT_VERSION;
        machine->cells[i].native_code = char_base + i;
        machine->cells[i].unicode_codepoint = char_base + i;
        machine->cells[i].glyph_id = "mock_ascii";
        machine->cells[i].foreground_color = 7;
        machine->cells[i].background_color = 0;
        machine->cells[i].attribute_flags = i;
        machine->cells[i].charset_id = "mock_charset";
        machine->cells[i].source_address = 0x0400u + i;
        machine->cells[i].confidence = 255u;
    }
    out_snapshot->frame.frame_number = machine->frame;
    out_snapshot->frame.emulated_cycles = 1234u;
    out_snapshot->frame.emulated_time_ns = 5678u;
    out_snapshot->frame.execution_state = machine->state;
    out_snapshot->region_id = "main";
    out_snapshot->columns = 2u;
    out_snapshot->rows = 2u;
    out_snapshot->row_stride = 2u;
    out_snapshot->cells = machine->cells;
    out_snapshot->cell_count = 4u;
    out_snapshot->plain_utf8 = machine->frame >= 3u ? "AB\nCD" : "WX\nYZ";
    out_snapshot->plain_utf8_size = 5u;
    return EMU_AUTOMATION_OK;
}

static emu_automation_result_t mock_read_memory(
    void *context,
    uint64_t address,
    uint8_t *out_bytes,
    size_t size)
{
    MockMachine *machine = (MockMachine *)context;
    if (out_bytes == NULL) {
        return EMU_AUTOMATION_INVALID_ARGUMENT;
    }
    for (size_t i = 0u; i < size; ++i) {
        uint64_t current_address = address + (uint64_t)i;
        if (current_address == 0x0200u) {
            out_bytes[i] = machine->mem_0200;
        } else if (current_address == 0x0201u) {
            out_bytes[i] = machine->mem_0201;
        } else {
            out_bytes[i] = 0x00u;
        }
    }
    return EMU_AUTOMATION_OK;
}

static emu_automation_result_t mock_write_memory(
    void *context,
    uint64_t address,
    const uint8_t *bytes,
    size_t size)
{
    MockMachine *machine = (MockMachine *)context;
    if (bytes == NULL) {
        return EMU_AUTOMATION_INVALID_ARGUMENT;
    }
    for (size_t i = 0u; i < size; ++i) {
        uint64_t current_address = address + (uint64_t)i;
        if (current_address == 0x0200u) {
            machine->mem_0200 = bytes[i];
        } else if (current_address == 0x0201u) {
            machine->mem_0201 = bytes[i];
        }
    }
    return EMU_AUTOMATION_OK;
}

static emu_automation_result_t mock_read_program_counter(
    void *context,
    uint64_t *out_program_counter)
{
    MockMachine *machine = (MockMachine *)context;
    if (out_program_counter == NULL) {
        return EMU_AUTOMATION_INVALID_ARGUMENT;
    }
    *out_program_counter = machine->program_counter;
    return EMU_AUTOMATION_OK;
}

static emu_automation_result_t mock_read_frame_metadata(
    void *context,
    emu_automation_frame_metadata_t *out_metadata)
{
    MockMachine *machine = (MockMachine *)context;
    if (out_metadata == NULL) {
        return EMU_AUTOMATION_INVALID_ARGUMENT;
    }
    out_metadata->frame_number = machine->frame;
    out_metadata->emulated_cycles = machine->frame * 100u;
    out_metadata->emulated_time_ns = machine->frame * 1000u;
    out_metadata->execution_state = machine->state;
    return EMU_AUTOMATION_OK;
}

static emu_automation_result_t mock_read_current_instruction(
    void *context,
    emu_automation_instruction_t *out_instruction)
{
    MockMachine *machine = (MockMachine *)context;
    if (out_instruction == NULL) {
        return EMU_AUTOMATION_INVALID_ARGUMENT;
    }
    memset(out_instruction, 0, sizeof(*out_instruction));
    out_instruction->struct_size = sizeof(*out_instruction);
    out_instruction->struct_version = EMU_AUTOMATION_STRUCT_VERSION;
    out_instruction->address = machine->program_counter;
    snprintf(out_instruction->bytes, sizeof(out_instruction->bytes), "EA");
    snprintf(out_instruction->text, sizeof(out_instruction->text), "NOP");
    out_instruction->is_current_ip = 1u;
    return EMU_AUTOMATION_OK;
}

static emu_automation_result_t mock_register_count(
    void *context,
    size_t *out_count)
{
    (void)context;
    if (out_count == NULL) {
        return EMU_AUTOMATION_INVALID_ARGUMENT;
    }
    *out_count = 2u;
    return EMU_AUTOMATION_OK;
}

static emu_automation_result_t mock_read_registers(
    void *context,
    emu_automation_register_value_t *out_registers,
    size_t register_capacity,
    size_t *out_register_count)
{
    MockMachine *machine = (MockMachine *)context;
    if (out_register_count == NULL) {
        return EMU_AUTOMATION_INVALID_ARGUMENT;
    }
    *out_register_count = 2u;
    if (register_capacity == 0u) {
        return EMU_AUTOMATION_OK;
    }
    if (out_registers == NULL || register_capacity < 2u) {
        return EMU_AUTOMATION_INVALID_ARGUMENT;
    }
    memset(out_registers, 0, sizeof(*out_registers) * 2u);
    snprintf(out_registers[0].name, sizeof(out_registers[0].name), "PC");
    snprintf(out_registers[0].hex_value, sizeof(out_registers[0].hex_value), "0x%04llX", (unsigned long long)machine->program_counter);
    snprintf(out_registers[0].dec_value, sizeof(out_registers[0].dec_value), "%llu", (unsigned long long)machine->program_counter);
    out_registers[0].has_dec = 1u;
    snprintf(out_registers[1].name, sizeof(out_registers[1].name), "FRAME");
    snprintf(out_registers[1].hex_value, sizeof(out_registers[1].hex_value), "0x%llX", (unsigned long long)machine->frame);
    snprintf(out_registers[1].dec_value, sizeof(out_registers[1].dec_value), "%llu", (unsigned long long)machine->frame);
    out_registers[1].has_dec = 1u;
    return EMU_AUTOMATION_OK;
}

static emu_automation_result_t mock_write_register(
    void *context,
    const char *register_name,
    uint64_t value)
{
    MockMachine *machine = (MockMachine *)context;
    if (register_name == NULL) {
        return EMU_AUTOMATION_INVALID_ARGUMENT;
    }
    if (strcmp(register_name, "PC") == 0) {
        machine->program_counter = value;
        return EMU_AUTOMATION_OK;
    }
    return EMU_AUTOMATION_UNSUPPORTED;
}

static void mock_release_text_grid(
    void *context,
    emu_automation_text_grid_snapshot_t *snapshot)
{
    MockMachine *machine = (MockMachine *)context;
    if (snapshot != NULL && snapshot->cells == machine->cells) {
        machine->text_release_count++;
    }
}

static emu_automation_result_t mock_text_grid_view_count(void *context, size_t *out_count)
{
    (void)context;
    *out_count = 1u;
    return EMU_AUTOMATION_OK;
}

static emu_automation_result_t mock_text_grid_view_descriptor(
    void *context,
    size_t index,
    emu_automation_text_view_descriptor_t *out_descriptor)
{
    (void)context;
    if (index != 0u) {
        return EMU_AUTOMATION_INVALID_ARGUMENT;
    }
    out_descriptor->region_id = "main";
    out_descriptor->columns = 2u;
    out_descriptor->rows = 2u;
    out_descriptor->row_stride = 2u;
    out_descriptor->charset_id = "mock_charset";
    out_descriptor->native_encoding = "mock_screen_code";
    out_descriptor->unicode_map = "ascii";
    return EMU_AUTOMATION_OK;
}

static emu_automation_result_t mock_key(
    void *context,
    const emu_automation_key_event_t *event)
{
    MockMachine *machine = (MockMachine *)context;
    const char *submitted_key_id = NULL;
    if (strcmp(event->key_id, "RETURN") != 0 &&
        strcmp(event->key_id, "K_A") != 0 &&
        strcmp(event->key_id, "K_SHIFT") != 0 &&
        strcmp(event->key_id, "K_RETURN") != 0) {
        return EMU_AUTOMATION_MAPPING_UNAVAILABLE;
    }
    if (strcmp(event->key_id, "RETURN") == 0) submitted_key_id = "RETURN";
    else if (strcmp(event->key_id, "K_A") == 0) submitted_key_id = "K_A";
    else if (strcmp(event->key_id, "K_SHIFT") == 0) submitted_key_id = "K_SHIFT";
    else submitted_key_id = "K_RETURN";
    machine->key_count++;
    mock_push_event(
        machine,
        EMU_AUTOMATION_EVENT_INPUT_SUBMITTED,
        0,
        0,
        event->device_id != NULL ? event->device_id : NULL,
        submitted_key_id,
        NULL,
        0u, 0u, 0u, 0u, 0u,
        NULL,
        event->action,
        event->timing);
    return EMU_AUTOMATION_OK;
}

static emu_automation_result_t mock_button(
    void *context,
    const emu_automation_controller_button_event_t *event)
{
    MockMachine *machine = (MockMachine *)context;
    if (strcmp(event->control_id, "fire_1") != 0) {
        return EMU_AUTOMATION_MAPPING_UNAVAILABLE;
    }
    machine->button_count++;
    mock_push_event(
        machine,
        EMU_AUTOMATION_EVENT_INPUT_SUBMITTED,
        0,
        0,
        event->device_id != NULL ? event->device_id : NULL,
        "fire_1",
        NULL,
        0u, 0u, 0u, 0u, 0u,
        NULL,
        event->action,
        event->timing);
    return EMU_AUTOMATION_OK;
}

static emu_automation_result_t mock_poll_event(
    void *context,
    uint64_t after_sequence,
    emu_automation_event_t *out_event)
{
    MockMachine *machine = (MockMachine *)context;
    size_t i;
    for (i = 0u; i < machine->event_count; ++i) {
        if (machine->events[i].sequence_number > after_sequence) {
            *out_event = machine->events[i];
            return EMU_AUTOMATION_OK;
        }
    }
    return EMU_AUTOMATION_TIMEOUT;
}

static void mock_destroy(void *context)
{
    free(context);
}

emu_automation_result_t emu_test_create_text_machine(
    emu_automation_machine_t **out_machine)
{
    MockMachine *context = (MockMachine *)calloc(1u, sizeof(*context));
    emu_automation_adapter_t adapter;
    if (context == NULL) {
        return EMU_AUTOMATION_INTERNAL_ERROR;
    }
    memset(&adapter, 0, sizeof(adapter));
    adapter.struct_size = sizeof(adapter);
    adapter.struct_version = EMU_AUTOMATION_STRUCT_VERSION;
    adapter.context = context;
    adapter.destroy_context = mock_destroy;
    adapter.describe = mock_describe;
    adapter.capabilities = mock_capabilities;
    adapter.character_mapping_count = mock_character_mapping_count;
    adapter.character_mapping_descriptor = mock_character_mapping_descriptor;
    adapter.pause = mock_pause;
    adapter.resume = mock_resume;
    adapter.reset = mock_reset;
    adapter.step_frame = mock_step_frame;
    adapter.run_frames = mock_run_frames;
    adapter.capture_framebuffer = mock_capture_framebuffer;
    adapter.capture_text_grid = mock_capture_text_grid;
    adapter.release_text_grid = mock_release_text_grid;
    adapter.read_memory = mock_read_memory;
    adapter.write_memory = mock_write_memory;
    adapter.read_program_counter = mock_read_program_counter;
    adapter.read_frame_metadata = mock_read_frame_metadata;
    adapter.read_current_instruction = mock_read_current_instruction;
    adapter.register_count = mock_register_count;
    adapter.read_registers = mock_read_registers;
    adapter.write_register = mock_write_register;
    adapter.text_grid_view_count = mock_text_grid_view_count;
    adapter.text_grid_view_descriptor = mock_text_grid_view_descriptor;
    adapter.submit_key = mock_key;
    adapter.submit_controller_button = mock_button;
    adapter.poll_event = mock_poll_event;
    return emu_automation_attach_adapter(&adapter, out_machine);
}

emu_automation_result_t emu_test_create_category_machine(
    emu_automation_machine_t **out_machine)
{
    MockMachine *context = (MockMachine *)calloc(1u, sizeof(*context));
    emu_automation_adapter_t adapter;
    if (context == NULL) {
        return EMU_AUTOMATION_INTERNAL_ERROR;
    }
    memset(&adapter, 0, sizeof(adapter));
    memset(context, 0, sizeof(*context));
    context->state = EMU_AUTOMATION_EXECUTION_PAUSED;
    mock_seed_category_events(context);
    adapter.struct_size = sizeof(adapter);
    adapter.struct_version = EMU_AUTOMATION_STRUCT_VERSION;
    adapter.context = context;
    adapter.destroy_context = mock_destroy;
    adapter.describe = mock_categories_describe;
    adapter.capabilities = mock_capabilities;
    adapter.character_mapping_count = mock_character_mapping_count;
    adapter.character_mapping_descriptor = mock_character_mapping_descriptor;
    adapter.poll_event = mock_poll_event;
    return emu_automation_attach_adapter(&adapter, out_machine);
}
