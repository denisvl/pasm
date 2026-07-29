import pathlib
import shutil
import struct
import subprocess
import sys
import textwrap
import zlib
import asyncio

import ctypes

import pytest

from src.pasm_automation import (
    AutomationError,
    AutomationEvent,
    AutomationLibrary,
    CharacterMappingDescriptor,
    DebugView,
    InspectionView,
    InputSequence,
    Subscription,
    AutomationTimeoutError,
    EventType,
    FrameMetadata,
    InputTapPreset,
    InputTiming,
    RecordingHeader,
    ReplayMismatchError,
    SessionRecording,
    attach,
    create,
    load_library,
)


BASE_DIR = pathlib.Path(__file__).resolve().parents[1]


class _SequenceRecorder:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def key(self, key_id, *, action="press", device_id=None, timing_kind=0, timing_value=0):
        self.calls.append(("key", key_id, action, device_id, timing_kind, timing_value))

    def controller_button(
        self,
        control_id,
        *,
        action="press",
        device_id=None,
        timing_kind=0,
        timing_value=0,
    ):
        self.calls.append(
            ("controller", control_id, action, device_id, timing_kind, timing_value)
        )

    def run_frames(self, frame_count):
        self.calls.append(("run_frames", frame_count))


MOCK_SHARED_C = r"""
#include "emu_automation_adapter.h"

#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

typedef struct MockMachine {
    uint64_t frame;
    uint64_t program_counter;
    uint64_t next_sequence;
    uint32_t key_count;
    uint32_t button_count;
    uint32_t release_count;
    emu_automation_execution_state_t state;
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
    out_descriptor->machine_id = "mock-categories";
    out_descriptor->system_id = "mock-system";
    out_descriptor->model_id = "mock-model";
    out_descriptor->region = "test";
    out_descriptor->video_standard = "text";
    out_descriptor->adapter_version = "test-1";
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
        delta->before.glyph_id = "ascii";
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
        EMU_AUTOMATION_CAP_SCREEN_TEXT_GRID |
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
        EMU_AUTOMATION_CAP_EVENTS_FRAME_COMPLETED;
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

static emu_automation_result_t mock_capture_framebuffer(
    void *context,
    emu_automation_framebuffer_snapshot_t *out_snapshot)
{
    MockMachine *machine = (MockMachine *)context;
    for (uint32_t i = 0u; i < sizeof(machine->pixels); ++i) {
        machine->pixels[i] = (uint8_t)i;
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

static emu_automation_result_t mock_describe(
    void *context,
    emu_automation_machine_descriptor_t *out_descriptor)
{
    (void)context;
    out_descriptor->machine_id = "mock-machine";
    out_descriptor->system_id = "mock-system";
    out_descriptor->model_id = "mock-model";
    out_descriptor->region = "test";
    out_descriptor->video_standard = "text";
    out_descriptor->adapter_version = "test-1";
    out_descriptor->configured_memory_bytes = 65536u;
    return mock_capabilities(context, &out_descriptor->capabilities);
}

static emu_automation_result_t mock_text_grid_view_count(
    void *context,
    size_t *out_count)
{
    (void)context;
    *out_count = 1u;
    return EMU_AUTOMATION_OK;
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

static emu_automation_result_t mock_reset(
    void *context,
    emu_automation_reset_kind_t kind)
{
    MockMachine *machine = (MockMachine *)context;
    emu_automation_execution_state_t previous_state = machine->state;
    if (kind != EMU_AUTOMATION_RESET_COLD) {
        return EMU_AUTOMATION_UNSUPPORTED;
    }
    machine->frame = 0u;
    machine->program_counter = 0x0200u;
    machine->state = EMU_AUTOMATION_EXECUTION_PAUSED;
    machine->mem_0200 = 0x00u;
    machine->mem_0201 = 0x99u;
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
    if (machine->frame == 3u && machine->mem_0200 == 0x00u) {
        machine->mem_0200 = 0x42u;
    }
    if (machine->state == EMU_AUTOMATION_EXECUTION_RUNNING && machine->frame >= 2u) {
        machine->state = EMU_AUTOMATION_EXECUTION_PAUSED;
        mock_push_event(
            machine,
            EMU_AUTOMATION_EVENT_EXECUTION_STATE_CHANGED,
            EMU_AUTOMATION_EXECUTION_RUNNING,
            EMU_AUTOMATION_EXECUTION_PAUSED,
            NULL,
            NULL,
            NULL,
            0u, 0u, 0u, 0u, 0u,
            NULL,
            EMU_AUTOMATION_INPUT_RELEASE,
            (emu_automation_timing_t){EMU_AUTOMATION_TIMING_IMMEDIATE, 0u});
    }
    if (machine->frame == 3u) {
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

static emu_automation_result_t mock_run_frames(
    void *context,
    uint64_t frame_count)
{
    MockMachine *machine = (MockMachine *)context;
    uint64_t i;
    for (i = 0u; i < frame_count; ++i) {
        machine->frame++;
        machine->program_counter++;
        if (machine->frame == 3u && machine->mem_0200 == 0x00u) {
            machine->mem_0200 = 0x42u;
        }
        if (machine->state == EMU_AUTOMATION_EXECUTION_RUNNING && machine->frame >= 2u) {
            machine->state = EMU_AUTOMATION_EXECUTION_PAUSED;
            mock_push_event(
                machine,
                EMU_AUTOMATION_EVENT_EXECUTION_STATE_CHANGED,
                EMU_AUTOMATION_EXECUTION_RUNNING,
                EMU_AUTOMATION_EXECUTION_PAUSED,
                NULL,
                NULL,
                NULL,
                0u, 0u, 0u, 0u, 0u,
                NULL,
                EMU_AUTOMATION_INPUT_RELEASE,
                (emu_automation_timing_t){EMU_AUTOMATION_TIMING_IMMEDIATE, 0u});
        }
        if (machine->frame == 3u) {
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
        machine->cells[i].glyph_id = "ascii";
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

static void mock_release_text_grid(
    void *context,
    emu_automation_text_grid_snapshot_t *snapshot)
{
    MockMachine *machine = (MockMachine *)context;
    if (snapshot != NULL && snapshot->cells == machine->cells) {
        machine->release_count++;
    }
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
"""


def _png_chunks(data: bytes) -> list[tuple[bytes, bytes]]:
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    offset = 8
    chunks: list[tuple[bytes, bytes]] = []
    while offset < len(data):
        size = struct.unpack(">I", data[offset : offset + 4])[0]
        chunk_type = data[offset + 4 : offset + 8]
        payload = data[offset + 8 : offset + 8 + size]
        chunks.append((chunk_type, payload))
        offset += 12 + size
    return chunks


def _compile_mock_shared(tmp_path: pathlib.Path) -> pathlib.Path:
    cc = shutil.which("cc")
    if cc is None:
        pytest.skip("cc is required for ctypes automation binding test")

    source = tmp_path / "mock_automation.c"
    source.write_text(textwrap.dedent(MOCK_SHARED_C), encoding="utf-8")
    suffix = ".dylib" if sys.platform == "darwin" else ".so"
    shared = tmp_path / f"libmock_automation{suffix}"
    subprocess.run(
        [
            cc,
            "-shared",
            "-fPIC",
            "-std=c11",
            "-Wall",
            "-Wextra",
            "-I",
            str(BASE_DIR / "automation/include"),
            str(BASE_DIR / "automation/core/emu_automation.c"),
            str(source),
            "-o",
            str(shared),
        ],
        cwd=BASE_DIR,
        check=True,
    )
    return shared


def test_ctypes_binding_copies_and_releases_text_grid_snapshot(tmp_path):
    library = AutomationLibrary(_compile_mock_shared(tmp_path))

    with library.create_machine("emu_test_create_text_machine") as machine:
        descriptor = machine.describe()
        assert descriptor.machine_id == "mock-machine"
        assert descriptor.capabilities.feature_bits != 0
        assert machine.character_mappings() == [
            CharacterMappingDescriptor(
                device_id="keyboard",
                unicode_codepoint=65,
                native_code=65,
                key_id="K_A",
                required_modifier_bits=1,
                shift_key_id="K_SHIFT",
                ctrl_key_id="",
                alt_key_id="",
                meta_key_id="",
            ),
            CharacterMappingDescriptor(
                device_id="keyboard",
                unicode_codepoint=13,
                native_code=13,
                key_id="K_RETURN",
                required_modifier_bits=0,
                shift_key_id="K_SHIFT",
                ctrl_key_id="",
                alt_key_id="",
                meta_key_id="",
            ),
        ]

        machine.reset()
        machine.resume()
        machine.run.frame()
        machine.run.frames(41)
        machine.pause()
        machine.keyboard.tap("RETURN")
        machine.controller.press("fire_1", device_id="joystick_port_1")

        framebuffer = machine.screen.framebuffer()
        assert framebuffer.width == 2
        assert framebuffer.height == 2
        assert framebuffer.stride_bytes == 8
        assert framebuffer.frame.frame_number == 42
        assert framebuffer.visible_area.width == 2
        assert framebuffer.pixels[:4] == bytes([0, 1, 2, 3])
        assert framebuffer.to_rgba8888()[:4] == bytes([0, 1, 2, 3])

        screenshot = tmp_path / "framebuffer.png"
        framebuffer.save_png(screenshot)
        chunks = _png_chunks(screenshot.read_bytes())
        assert chunks[0][0] == b"IHDR"
        assert struct.unpack(">IIBBBBB", chunks[0][1]) == (2, 2, 8, 6, 0, 0, 0)
        idat = b"".join(payload for chunk_type, payload in chunks if chunk_type == b"IDAT")
        assert zlib.decompress(idat) == bytes(
            [
                0,
                0,
                1,
                2,
                3,
                4,
                5,
                6,
                7,
                0,
                8,
                9,
                10,
                11,
                12,
                13,
                14,
                15,
            ]
        )

        views = machine.screen.text_views()
        assert len(views) == 1
        assert views[0].region_id == "main"
        assert views[0].columns == 2
        assert views[0].charset_id == "mock_charset"


def test_keyboard_type_text_uses_character_mappings(tmp_path):
    library = AutomationLibrary(_compile_mock_shared(tmp_path))

    with library.create_machine("emu_test_create_text_machine") as machine:
        machine.keyboard.type_text("A\r")

        seen = []
        after_sequence = 0
        while True:
            event = machine.poll_event(after_sequence)
            if event is None:
                break
            after_sequence = event.sequence_number
            if event.event_type == EventType.INPUT_SUBMITTED:
                seen.append((event.control_id, event.input_action))

        assert seen == [
            ("K_SHIFT", 1),
            ("K_A", 1),
            ("K_A", 0),
            ("K_SHIFT", 0),
            ("K_RETURN", 1),
            ("K_RETURN", 0),
        ]


def test_input_sequence_type_text_uses_character_mappings():
    from src.pasm_automation.ctypes_api import InputSequence, Machine

    machine = _SequenceRecorder()
    machine.character_mappings = lambda: [  # type: ignore[attr-defined]
        CharacterMappingDescriptor(
            device_id="keyboard",
            unicode_codepoint=65,
            native_code=65,
            key_id="K_A",
            required_modifier_bits=1,
            shift_key_id="K_SHIFT",
            ctrl_key_id="",
            alt_key_id="",
            meta_key_id="",
        ),
        CharacterMappingDescriptor(
            device_id="keyboard",
            unicode_codepoint=13,
            native_code=13,
            key_id="K_RETURN",
            required_modifier_bits=0,
            shift_key_id="K_SHIFT",
            ctrl_key_id="",
            alt_key_id="",
            meta_key_id="",
        ),
    ]
    machine._character_mapping_for_char = Machine._character_mapping_for_char.__get__(  # type: ignore[attr-defined]
        machine, Machine
    )

    sequence = InputSequence(machine)  # type: ignore[arg-type]
    sequence.type_text("A\r")
    sequence.play()

    assert machine.calls == [
        ("key", "K_SHIFT", "press", None, 0, 0),
        ("key", "K_A", "press", None, 0, 0),
        ("key", "K_A", "release", None, 0, 0),
        ("key", "K_SHIFT", "release", None, 0, 0),
        ("key", "K_RETURN", "press", None, 0, 0),
        ("key", "K_RETURN", "release", None, 0, 0),
    ]


def test_ctypes_binding_waits_for_text_by_advancing_frames(tmp_path):
    library = AutomationLibrary(_compile_mock_shared(tmp_path))

    with library.create_machine("emu_test_create_text_machine") as machine:
        machine.reset()
        assert machine.screen.text("main").plain == "WX\nYZ"

        snapshot = machine.screen.wait_for_text("AB", region_id="main", timeout_frames=3)
        assert snapshot.plain == "AB\nCD"
        assert snapshot.frame_number == 3

        with pytest.raises(AutomationTimeoutError) as excinfo:
            machine.screen.wait_for_text("NEVER", region_id="main", timeout_frames=2)
        assert "last observed: text frame=5 plain='AB\\\\nCD'" in str(excinfo.value)
        assert excinfo.value.final_observation is not None
        assert excinfo.value.final_observation.plain == "AB\nCD"


def test_ctypes_binding_waits_for_text_disappearance(tmp_path):
    library = AutomationLibrary(_compile_mock_shared(tmp_path))

    with library.create_machine("emu_test_create_text_machine") as machine:
        machine.reset()

        snapshot = machine.screen.wait_for_text_disappearance(
            "WX",
            region_id="main",
            timeout_frames=3,
        )
        assert snapshot.plain == "AB\nCD"
        assert snapshot.frame_number == 3

    with library.create_machine("emu_test_create_text_machine") as machine:
        machine.reset()
        snapshot = machine.wait.text_disappears(
            "WX",
            region_id="main",
            timeout_frames=3,
        )
        assert snapshot.plain == "AB\nCD"
        assert snapshot.frame_number == 3


def test_ctypes_binding_reads_memory_and_waits_for_memory_value(tmp_path):
    library = AutomationLibrary(_compile_mock_shared(tmp_path))

    with library.create_machine("emu_test_create_text_machine") as machine:
        machine.reset()
        assert machine.read_memory(0x0200, 2) == b"\x00\x99"

        current = machine.wait_for_memory_value(0x0200, b"\x42\x99", timeout_frames=3)
        assert current == b"\x42\x99"

    with library.create_machine("emu_test_create_text_machine") as machine:
        machine.reset()
        current = machine.wait.memory_value(0x0200, b"\x42\x99", timeout_frames=3)
        assert current == b"\x42\x99"

        with pytest.raises(AutomationTimeoutError, match="last observed: 42") as excinfo:
            machine.wait_for_memory_value(0x0200, 0x43, timeout_frames=2)
        assert excinfo.value.final_observation == b"\x42"


def test_ctypes_binding_reads_and_waits_for_program_counter(tmp_path):
    library = AutomationLibrary(_compile_mock_shared(tmp_path))

    with library.create_machine("emu_test_create_text_machine") as machine:
        machine.reset()
        assert machine.read_program_counter() == 0x0200

        current = machine.wait_for_program_counter(0x0203, timeout_frames=3)
        assert current == 0x0203

    with library.create_machine("emu_test_create_text_machine") as machine:
        machine.reset()
        current = machine.wait.program_counter(0x0203, timeout_frames=3)
        assert current == 0x0203

        with pytest.raises(AutomationTimeoutError, match="last observed: 0x204") as excinfo:
            machine.wait_for_program_counter(0x0205, timeout_frames=1)
        assert excinfo.value.final_observation == 0x0204


def test_ctypes_binding_supports_cycle_and_emulated_time_wait_timeouts(tmp_path):
    library = AutomationLibrary(_compile_mock_shared(tmp_path))

    with library.create_machine("emu_test_create_text_machine") as machine:
        machine.reset()
        metadata = machine.read_frame_metadata()
        assert metadata.frame_number == 0
        assert metadata.emulated_cycles == 0
        assert metadata.emulated_time_ns == 0

        current = machine.wait_for_memory_value(0x0200, b"\x42\x99", timeout_cycles=300)
        assert current == b"\x42\x99"

    with library.create_machine("emu_test_create_text_machine") as machine:
        machine.reset()
        current = machine.wait.memory_value(0x0200, b"\x42\x99", timeout_emulated_time_ns=3000)
        assert current == b"\x42\x99"

    with library.create_machine("emu_test_create_text_machine") as machine:
        machine.reset()
        with pytest.raises(AutomationTimeoutError, match="last observed: 0099") as excinfo:
            machine.wait_for_memory_value(0x0200, b"\x42\x99", timeout_cycles=200)
        assert excinfo.value.final_observation == b"\x00\x99"


def test_ctypes_binding_waits_for_breakpoint_and_watchpoint_pause(tmp_path):
    library = AutomationLibrary(_compile_mock_shared(tmp_path))

    with library.create_machine("emu_test_create_text_machine") as machine:
        machine.reset()
        machine.resume()
        metadata = machine.wait_for_breakpoint(timeout_frames=2)
        assert metadata.execution_state == 2
        assert metadata.frame_number == 2
        assert machine.read_program_counter() == 0x0202

    with library.create_machine("emu_test_create_text_machine") as machine:
        machine.reset()
        machine.resume()
        metadata = machine.wait.watchpoint(program_counter=0x0202, timeout_frames=2)
        assert metadata.execution_state == 2
        assert metadata.frame_number == 2

    with library.create_machine("emu_test_create_text_machine") as machine:
        machine.reset()
        machine.resume()
        with pytest.raises(
            AutomationTimeoutError,
            match="Timed out waiting for debug pause at program counter 0x0205",
        ):
            machine.wait_for_breakpoint(program_counter=0x0205, timeout_frames=2)


def test_ctypes_binding_waits_for_stable_text_and_framebuffer(tmp_path):
    library = AutomationLibrary(_compile_mock_shared(tmp_path))

    with library.create_machine("emu_test_create_text_machine") as machine:
        machine.reset()
        machine.run.frames(3)

        text = machine.screen.wait_for_stable_text(
            region_id="main",
            stable_frames=2,
            timeout_frames=4,
        )
        assert text.plain == "AB\nCD"
        assert text.frame_number == 5

        framebuffer = machine.screen.wait_for_stable_framebuffer(
            stable_frames=2,
            timeout_frames=2,
        )
        assert framebuffer.frame.frame_number == 7

        with pytest.raises(AutomationTimeoutError) as excinfo:
            machine.screen.wait_for_stable_text(
                region_id="main",
                stable_frames=3,
                timeout_frames=2,
            )
        assert "last observed: text frame=9 plain='AB\\\\nCD'" in str(excinfo.value)
        assert excinfo.value.final_observation is not None
        assert excinfo.value.final_observation.plain == "AB\nCD"


def test_ctypes_binding_composes_wait_conditions(tmp_path):
    library = AutomationLibrary(_compile_mock_shared(tmp_path))

    with library.create_machine("emu_test_create_text_machine") as machine:
        machine.reset()

        text = (
            machine.wait.any(
                machine.conditions.screen_contains("AB", region_id="main"),
                machine.conditions.screen_contains("READY", region_id="main"),
            )
            .timeout_frames(3)
            .run()
        )
        assert text.plain == "AB\nCD"
        assert text.frame_number == 3

        machine.reset()
        stable_text, direct_text = (
            machine.wait.all(
                machine.conditions.stable_text(region_id="main", stable_frames=2),
                machine.conditions.screen_contains("AB", region_id="main"),
            )
            .timeout_frames(5)
            .run()
        )
        assert stable_text.plain == "AB\nCD"
        assert direct_text.plain == "AB\nCD"
        assert stable_text.frame_number == 5

        machine.reset()
        text = machine.wait.screen_contains(
            "AB",
            region_id="main",
            timeout_frames=3,
        )
        assert text.frame_number == 3


def test_ctypes_binding_polls_frame_events(tmp_path):
    library = AutomationLibrary(_compile_mock_shared(tmp_path))

    with library.create_machine("emu_test_create_text_machine") as machine:
        machine.reset()
        assert machine.poll_event(0) == AutomationEvent(
            sequence_number=1,
            event_type=2,
            frame=FrameMetadata(0, 0, 0, 2),
            previous_execution_state=0,
            current_execution_state=2,
            device_id="",
            control_id="",
            region_id="",
            change_x=0,
            change_y=0,
            change_width=0,
            change_height=0,
            change_cell_count=0,
            input_action=0,
        )
        machine.run.frames(2)

        assert machine.poll_event(1) == AutomationEvent(
            sequence_number=2,
            event_type=1,
            frame=FrameMetadata(1, 0, 0, 2),
            device_id="",
            control_id="",
            region_id="",
            change_x=0,
            change_y=0,
            change_width=0,
            change_height=0,
            change_cell_count=0,
            input_action=0,
        )
        assert machine.poll_event(2) == AutomationEvent(
            sequence_number=3,
            event_type=1,
            frame=FrameMetadata(2, 0, 0, 2),
            device_id="",
            control_id="",
            region_id="",
            change_x=0,
            change_y=0,
            change_width=0,
            change_height=0,
            change_cell_count=0,
            input_action=0,
        )
        machine.resume()
        assert machine.poll_event(3) == AutomationEvent(
            sequence_number=4,
            event_type=3,
            frame=FrameMetadata(2, 0, 0, 1),
            previous_execution_state=2,
            current_execution_state=1,
            device_id="",
            control_id="",
            region_id="",
            change_x=0,
            change_y=0,
            change_width=0,
            change_height=0,
            change_cell_count=0,
            input_action=0,
        )
        machine.keyboard.press("RETURN")
        assert machine.poll_event(4) == AutomationEvent(
            sequence_number=5,
            event_type=4,
            frame=FrameMetadata(2, 0, 0, 1),
            input_accepted=FrameMetadata(2, 0, 0, 1),
            input_applied=FrameMetadata(2, 0, 0, 1),
            device_id="",
            control_id="RETURN",
            region_id="",
            change_x=0,
            change_y=0,
            change_width=0,
            change_height=0,
            change_cell_count=0,
            input_action=1,
            input_timing=InputTiming.immediate(),
        )
        assert machine.poll_event(5) is None


def test_ctypes_binding_event_iterator_drains_available_events(tmp_path):
    library = AutomationLibrary(_compile_mock_shared(tmp_path))

    with library.create_machine("emu_test_create_text_machine") as machine:
        machine.reset()
        machine.run.frames(2)
        iterator = machine.events()
        events = iterator.collect_available()
        assert [event.sequence_number for event in events] == [1, 2, 3]
        assert [event.event_type for event in events] == [2, 1, 1]
        assert iterator.after_sequence == 3
        assert list(iterator) == []

        machine.resume()
        machine.keyboard.press("RETURN")
        follow_up = iterator.collect_available()
        assert [event.sequence_number for event in follow_up] == [4, 5]
        assert [event.event_type for event in follow_up] == [3, 4]


def test_ctypes_binding_event_iterator_dispatches_callbacks(tmp_path):
    library = AutomationLibrary(_compile_mock_shared(tmp_path))

    with library.create_machine("emu_test_create_text_machine") as machine:
        machine.reset()
        machine.run.frames(2)
        iterator = machine.events()
        seen: list[tuple[int, int]] = []

        count = iterator.dispatch_available(
            lambda event: seen.append((event.sequence_number, event.event_type))
        )

        assert count == 3
        assert seen == [(1, 2), (2, 1), (3, 1)]
        assert iterator.after_sequence == 3


def test_ctypes_binding_core_dispatch_available_callback(tmp_path):
    library = AutomationLibrary(_compile_mock_shared(tmp_path))

    with library.create_machine("emu_test_create_text_machine") as machine:
        machine.reset()
        machine.run.frames(2)
        seen: list[tuple[int, int]] = []
        after_sequence, count = machine.dispatch_events(
            lambda event: seen.append((event.sequence_number, event.event_type)),
            after_sequence=0,
        )

        assert count == 3
        assert after_sequence == 3
        assert seen == [(1, 2), (2, 1), (3, 1)]


def test_ctypes_binding_core_dispatch_matching_callback(tmp_path):
    library = AutomationLibrary(_compile_mock_shared(tmp_path))

    with library.create_machine("emu_test_create_text_machine") as machine:
        machine.reset()
        machine.run.frames(2)
        seen: list[tuple[int, int]] = []
        after_sequence, count = machine.dispatch_events(
            lambda event: seen.append((event.sequence_number, event.event_type)),
            after_sequence=0,
            event_type=EventType.FRAME_COMPLETED,
        )

        assert count == 2
        assert after_sequence == 3
        assert seen == [(2, 1), (3, 1)]


def test_ctypes_binding_subscription_dispatches_matching_events(tmp_path):
    library = AutomationLibrary(_compile_mock_shared(tmp_path))

    with library.create_machine("emu_test_create_text_machine") as machine:
        machine.reset()
        machine.run.frames(2)
        seen: list[tuple[int, int]] = []
        with machine.subscribe(
            lambda event: seen.append((event.sequence_number, event.event_type)),
            event_type=EventType.FRAME_COMPLETED,
        ) as subscription:
            assert isinstance(subscription, Subscription)
            assert subscription.after_sequence == 0
            count = subscription.dispatch_available()
            assert count == 2
            assert seen == [(2, 1), (3, 1)]
            assert subscription.after_sequence == 3
            subscription.set_after_sequence(1)
            assert subscription.after_sequence == 1
            count = subscription.dispatch_available(max_events=1)
            assert count == 1
            assert subscription.after_sequence == 2


def test_ctypes_binding_async_event_iterator_receives_event(tmp_path):
    library = AutomationLibrary(_compile_mock_shared(tmp_path))

    async def run() -> None:
        with library.create_machine("emu_test_create_text_machine") as machine:
            machine.reset()
            events = machine.screen.async_events(step_frames=1)
            first = await events.recv(timeout_frames=0)
            assert first.type == EventType.MACHINE_RESET

            second = await events.recv(timeout_frames=2)
            assert second.type == EventType.FRAME_COMPLETED
            assert second.frame.frame_number == 1

    asyncio.run(run())


def test_ctypes_binding_waits_for_screen_changed_event(tmp_path):
    library = AutomationLibrary(_compile_mock_shared(tmp_path))

    with library.create_machine("emu_test_create_text_machine") as machine:
        machine.reset()
        event = machine.screen.wait_for_event(
            EventType.SCREEN_CHANGED,
            timeout_frames=3,
        )
        assert event.sequence_number == 5
        assert event.event_type == EventType.SCREEN_CHANGED
        assert event.type == EventType.SCREEN_CHANGED
        assert event.frame.frame_number == 3
        assert event.region_id == "main"
        assert (event.change_x, event.change_y, event.change_width, event.change_height) == (
            0,
            0,
            2,
            2,
        )
        assert event.change_cell_count == 4
        assert event.text_deltas == ()

        machine.reset()
        event = machine.wait.screen_changed(
            after_sequence=event.sequence_number,
            timeout_frames=3,
        )
        assert event.type == EventType.SCREEN_CHANGED
        assert event.region_id == "main"
        assert (event.change_x, event.change_y, event.change_width, event.change_height) == (
            0,
            0,
            2,
            2,
        )
        assert event.change_cell_count == 4
        assert event.text_deltas == ()

        machine.reset()
        after_sequence = event.sequence_number
        latest = []
        while True:
            reset_event = machine.poll_event(after_sequence)
            assert reset_event is not None
            after_sequence = reset_event.sequence_number
            latest.append(reset_event)
            if reset_event.event_type == 2:
                break
        assert reset_event == AutomationEvent(
            sequence_number=after_sequence,
            event_type=2,
            frame=FrameMetadata(0, 0, 0, 2),
            device_id="",
            control_id="",
            region_id="",
            change_x=0,
            change_y=0,
            change_width=0,
            change_height=0,
            change_cell_count=0,
            input_action=0,
        )
        with pytest.raises(AutomationTimeoutError, match="event type 5"):
            machine.screen.wait_for_event(
                EventType.SCREEN_CHANGED,
                after_sequence=after_sequence,
                timeout_frames=2,
            )


def test_ctypes_binding_waits_for_text_changed_event(tmp_path):
    library = AutomationLibrary(_compile_mock_shared(tmp_path))

    with library.create_machine("emu_test_create_text_machine") as machine:
        machine.reset()
        event = machine.screen.wait_for_text_changed(timeout_frames=3)
        assert event.type == EventType.TEXT_CHANGED
        assert event.frame.frame_number == 3
        assert event.region_id == "main"
        assert (event.change_x, event.change_y, event.change_width, event.change_height) == (
            0,
            0,
            2,
            2,
        )
        assert event.change_cell_count == 4

        machine.reset()
        event = machine.wait.text_changed(timeout_frames=3)
        assert event.type == EventType.TEXT_CHANGED
        assert event.region_id == "main"
        assert (event.change_x, event.change_y, event.change_width, event.change_height) == (
            0,
            0,
            2,
            2,
        )
        assert event.change_cell_count == 4


def test_ctypes_binding_polls_media_debug_and_error_events(tmp_path):
    library = AutomationLibrary(_compile_mock_shared(tmp_path))

    with library.create_machine("emu_test_create_category_machine") as machine:
        media = machine.poll_event(0)
        assert media is not None
        assert media.type == EventType.MEDIA_ACTIVITY
        assert media.message == "disk activity"

        debug = machine.poll_event(media.sequence_number)
        assert debug is not None
        assert debug.type == EventType.DEBUG_MESSAGE
        assert debug.message == "debug trace"

        error = machine.poll_event(debug.sequence_number)
        assert error is not None
        assert error.type == EventType.ERROR
        assert error.message == "adapter error"

        assert machine.poll_event(error.sequence_number) is None


def test_ctypes_binding_waits_for_media_activity_event(tmp_path):
    library = AutomationLibrary(_compile_mock_shared(tmp_path))

    with library.create_machine("emu_test_create_category_machine") as machine:
        event = machine.screen.wait_for_media_activity(timeout_frames=0)
        assert event.type == EventType.MEDIA_ACTIVITY
        assert event.message == "disk activity"

    with library.create_machine("emu_test_create_category_machine") as machine:
        event = machine.wait.media_activity(
            after_sequence=0,
            timeout_frames=0,
        )
        assert event.type == EventType.MEDIA_ACTIVITY
        assert event.message == "disk activity"


def test_module_level_helpers_create_and_attach_machine(tmp_path):
    shared = _compile_mock_shared(tmp_path)

    library = load_library(shared)
    assert isinstance(library, AutomationLibrary)

    with create(shared, "emu_test_create_text_machine") as machine:
        assert machine.describe().system_id == "mock-system"

    handle = ctypes.c_void_p()
    library.cdll.emu_test_create_text_machine.argtypes = [ctypes.POINTER(ctypes.c_void_p)]
    library.cdll.emu_test_create_text_machine.restype = ctypes.c_int
    library.check(
        library.cdll.emu_test_create_text_machine(ctypes.byref(handle)),
        "emu_test_create_text_machine",
    )

    with attach(shared, handle) as machine:
        assert machine.screen.text("main").plain == "WX\nYZ"


def test_input_sequence_replays_explicit_steps():
    from src.pasm_automation.ctypes_api import InputSequence

    machine = _SequenceRecorder()
    sequence = InputSequence(machine)  # type: ignore[arg-type]
    sequence.key_down("A", timing=InputTiming.frame(12))
    sequence.wait_frames(3)
    sequence.key_up("A", timing=InputTiming.delay_frames(1))
    sequence.controller_down(
        "fire_1",
        device_id="joystick_port_1",
        timing=InputTiming.cycle(99),
    )
    sequence.play()

    assert machine.calls == [
        ("key", "A", "press", None, 1, 12),
        ("run_frames", 3),
        ("key", "A", "release", None, 3, 1),
        ("controller", "fire_1", "press", "joystick_port_1", 2, 99),
    ]


def test_input_tap_preset_applies_press_and_release_timing():
    from src.pasm_automation.ctypes_api import InputSequence

    machine = _SequenceRecorder()
    preset = InputTapPreset.hold_frames(2)
    sequence = InputSequence(machine)  # type: ignore[arg-type]
    sequence.tap_key("A", preset=preset)
    sequence.play()

    assert machine.calls == [
        ("key", "A", "press", None, 0, 0),
        ("key", "A", "release", None, 3, 2),
    ]


def test_controller_tap_preset_applies_press_and_release_timing():
    from src.pasm_automation.ctypes_api import InputSequence

    machine = _SequenceRecorder()
    preset = InputTapPreset.hold_frames(2)
    sequence = InputSequence(machine)  # type: ignore[arg-type]
    sequence.tap_controller("fire_1", device_id="joystick_port_1", preset=preset)
    sequence.play()

    assert machine.calls == [
        ("controller", "fire_1", "press", "joystick_port_1", 0, 0),
        ("controller", "fire_1", "release", "joystick_port_1", 3, 2),
    ]


def test_input_sequence_replays_release_all_steps():
    from src.pasm_automation.ctypes_api import InputSequence

    machine = _SequenceRecorder()
    machine.release_all_keys = lambda *, device_id=None: machine.calls.append(
        ("release_all_keys", device_id)
    )
    machine.release_all_controller_buttons = lambda *, device_id=None: machine.calls.append(
        ("release_all_controller_buttons", device_id)
    )
    sequence = InputSequence(machine)  # type: ignore[arg-type]
    sequence.key_down("A")
    sequence.release_all_keys()
    sequence.controller_down("fire_1", device_id="joystick_port_1")
    sequence.release_all_controller_buttons(device_id="joystick_port_1")
    sequence.play()

    assert machine.calls == [
        ("key", "A", "press", None, 0, 0),
        ("release_all_keys", None),
        ("controller", "fire_1", "press", "joystick_port_1", 0, 0),
        ("release_all_controller_buttons", "joystick_port_1"),
    ]


def test_input_sequence_jsonl_round_trips_and_replays():
    from src.pasm_automation.ctypes_api import InputSequence

    recorder_a = _SequenceRecorder()
    original = InputSequence(recorder_a)  # type: ignore[arg-type]
    original.key_down("A", timing=InputTiming.frame(12))
    original.wait_frames(3)
    original.key_up("A", timing=InputTiming.delay_frames(1))
    original.controller_down(
        "fire_1",
        device_id="joystick_port_1",
        timing=InputTiming.cycle(99),
    )
    original.release_all_controller_buttons(device_id="joystick_port_1")

    jsonl = original.to_jsonl()

    recorder_b = _SequenceRecorder()
    recorder_b.release_all_controller_buttons = lambda *, device_id=None: recorder_b.calls.append(
        ("release_all_controller_buttons", device_id)
    )
    replayed = InputSequence.from_jsonl(recorder_b, jsonl)  # type: ignore[arg-type]
    replayed.play()

    assert recorder_b.calls == [
        ("key", "A", "press", None, 1, 12),
        ("run_frames", 3),
        ("key", "A", "release", None, 3, 1),
        ("controller", "fire_1", "press", "joystick_port_1", 2, 99),
        ("release_all_controller_buttons", "joystick_port_1"),
    ]


def test_input_sequence_log_payload_round_trips():
    from src.pasm_automation.ctypes_api import InputLogStep, InputSequence

    machine = _SequenceRecorder()
    sequence = InputSequence(machine)  # type: ignore[arg-type]
    sequence.key_down("A")
    sequence.release_all_keys()

    restored = InputSequence.from_log_payload(machine, sequence.to_log_payload())  # type: ignore[arg-type]

    assert restored.steps() == (
        InputLogStep(
            kind="key",
            target_id="A",
            action="press",
            device_id="",
            timing=InputTiming.immediate(),
            frame_count=0,
        ),
        InputLogStep(
            kind="release_all_keys",
            target_id="",
            action="release",
            device_id="",
            timing=InputTiming.immediate(),
            frame_count=0,
        ),
    )


def test_input_sequence_jsonl_replay_is_deterministic(tmp_path):
    shared = _compile_mock_shared(tmp_path)
    library = AutomationLibrary(shared)
    handle_a = ctypes.c_void_p()
    handle_b = ctypes.c_void_p()
    library.cdll.emu_test_create_text_machine.argtypes = [ctypes.POINTER(ctypes.c_void_p)]
    library.cdll.emu_test_create_text_machine.restype = ctypes.c_int
    library.check(
        library.cdll.emu_test_create_text_machine(ctypes.byref(handle_a)),
        "emu_test_create_text_machine",
    )
    library.check(
        library.cdll.emu_test_create_text_machine(ctypes.byref(handle_b)),
        "emu_test_create_text_machine",
    )

    def capture_schedule(machine) -> list[tuple]:
        from src.pasm_automation.ctypes_api import EventType, InputSequence

        original = InputSequence(machine)
        original.key_down("RETURN", timing=InputTiming.frame(12))
        original.wait_frames(3)
        original.key_up("RETURN", timing=InputTiming.delay_frames(1))
        original.controller_down(
            "fire_1",
            device_id="joystick_port_1",
            timing=InputTiming.cycle(99),
        )
        log = original.to_jsonl()
        replayed = InputSequence.from_jsonl(machine, log)
        replayed.play()

        schedule = []
        after_sequence = 0
        while True:
            event = machine.poll_event(after_sequence)
            if event is None:
                break
            after_sequence = event.sequence_number
            if event.event_type == EventType.INPUT_SUBMITTED:
                schedule.append(
                    (
                        event.sequence_number,
                        event.frame.frame_number,
                        event.control_id,
                        event.input_action,
                        event.input_timing.kind,
                        event.input_timing.value,
                    )
                )
        return schedule

    with attach(shared, handle_a) as machine_a, attach(shared, handle_b) as machine_b:
        schedule_a = capture_schedule(machine_a)
        schedule_b = capture_schedule(machine_b)

    assert schedule_a == schedule_b == [
        (1, 0, "RETURN", 1, 1, 12),
        (7, 3, "RETURN", 0, 3, 1),
        (8, 3, "fire_1", 1, 2, 99),
    ]


def test_session_recording_jsonl_round_trips():
    event = AutomationEvent(
        sequence_number=7,
        event_type=int(EventType.INPUT_SUBMITTED),
        frame=FrameMetadata(3, 99, 1000, 2),
        input_accepted=FrameMetadata(3, 99, 1000, 2),
        input_applied=FrameMetadata(3, 99, 1000, 2),
        device_id="kbd",
        control_id="RETURN",
        region_id="text0",
        change_x=0,
        change_y=0,
        change_width=1,
        change_height=1,
        change_cell_count=1,
        input_action=1,
        input_timing=InputTiming.frame(12),
        previous_execution_state=1,
        current_execution_state=2,
        message="submitted",
    )
    recorder = _SequenceRecorder()
    sequence = InputSequence(recorder)  # type: ignore[arg-type]
    sequence.key_down("RETURN", timing=InputTiming.frame(12))
    recording = SessionRecording(
        header=RecordingHeader(
            machine_id="mock-machine",
            system_id="mock-system",
            model_id="mock-model",
            adapter_version="test-1",
            configured_memory_bytes=65536,
        ),
        input_steps=sequence.steps(),
        events=(event,),
    )

    restored = SessionRecording.from_jsonl(recorder, recording.to_jsonl())  # type: ignore[arg-type]

    assert restored == recording


def test_machine_record_and_replay_recording(tmp_path):
    shared = _compile_mock_shared(tmp_path)
    library = AutomationLibrary(shared)
    handle_a = ctypes.c_void_p()
    handle_b = ctypes.c_void_p()
    library.cdll.emu_test_create_text_machine.argtypes = [ctypes.POINTER(ctypes.c_void_p)]
    library.cdll.emu_test_create_text_machine.restype = ctypes.c_int
    library.check(
        library.cdll.emu_test_create_text_machine(ctypes.byref(handle_a)),
        "emu_test_create_text_machine",
    )
    library.check(
        library.cdll.emu_test_create_text_machine(ctypes.byref(handle_b)),
        "emu_test_create_text_machine",
    )

    with attach(shared, handle_a) as machine_a, attach(shared, handle_b) as machine_b:
        sequence = machine_a.sequence()
        sequence.key_down("RETURN", timing=InputTiming.frame(12))
        sequence.wait_frames(3)
        sequence.key_up("RETURN", timing=InputTiming.delay_frames(1))
        recording = machine_a.record(sequence)
        observed = machine_b.replay_recording(recording)

    assert tuple(recording.events) == observed
    assert recording.header.machine_id == "mock-machine"
    assert recording.input_steps == sequence.steps()


def test_replay_recording_reports_event_mismatch(tmp_path):
    shared = _compile_mock_shared(tmp_path)
    library = AutomationLibrary(shared)
    handle_a = ctypes.c_void_p()
    handle_b = ctypes.c_void_p()
    library.cdll.emu_test_create_text_machine.argtypes = [ctypes.POINTER(ctypes.c_void_p)]
    library.cdll.emu_test_create_text_machine.restype = ctypes.c_int
    library.check(
        library.cdll.emu_test_create_text_machine(ctypes.byref(handle_a)),
        "emu_test_create_text_machine",
    )
    library.check(
        library.cdll.emu_test_create_text_machine(ctypes.byref(handle_b)),
        "emu_test_create_text_machine",
    )

    with attach(shared, handle_a) as machine_a, attach(shared, handle_b) as machine_b:
        sequence = machine_a.sequence()
        sequence.key_down("RETURN", timing=InputTiming.frame(12))
        recording = machine_a.record(sequence)
        mutated = SessionRecording(
            header=recording.header,
            input_steps=recording.input_steps,
            events=(
                AutomationEvent(
                    **{
                        **recording.events[0].__dict__,
                        "control_id": "BROKEN",
                    }
                ),
            ),
        )

        with pytest.raises(ReplayMismatchError, match="replay event mismatch"):
            machine_b.replay_recording(mutated)


def test_machine_inspection_and_debug_views_delegate(tmp_path):
    library = AutomationLibrary(_compile_mock_shared(tmp_path))

    with library.create_machine("emu_test_create_text_machine") as machine:
        machine.reset()
        assert isinstance(machine.inspect, InspectionView)
        assert isinstance(machine.debug, DebugView)
        assert machine.inspect.read_memory(0x0200, 2) == b"\x00\x99"
        assert machine.inspect.program_counter() == 0x0200
        assert machine.inspect.frame_metadata() == FrameMetadata(0, 0, 0, 2)
        machine.inspect.write_memory(0x0200, b"\x55\x66")
        assert machine.inspect.read_memory(0x0200, 2) == b"\x55\x66"
        assert machine.inspect.current_instruction().text == "NOP"
        assert machine.inspect.current_instruction().address == 0x0200
        assert machine.inspect.registers()[0].name == "PC"
        machine.inspect.write_register("PC", 0x0333)
        assert machine.inspect.program_counter() == 0x0333
        machine.resume()
        assert machine.debug.wait_for_breakpoint(timeout_frames=2) == FrameMetadata(2, 200, 2000, 2)


def test_ctypes_binding_releases_tracked_inputs(tmp_path):
    library = AutomationLibrary(_compile_mock_shared(tmp_path))

    with library.create_machine("emu_test_create_text_machine") as machine:
        machine.keyboard.press("RETURN")
        machine.controller.press("fire_1", device_id="joystick_port_1")

        assert machine.keyboard.release_all() == 1
        assert machine.controller.release_all(device_id="joystick_port_1") == 1
        assert machine.keyboard.release_all() == 0
        assert machine.controller.release_all() == 0
