import pathlib
import shutil
import subprocess
import textwrap

import pytest


BASE_DIR = pathlib.Path(__file__).resolve().parents[1]


MOCK_CALLER_C = r"""
#include "emu_automation_adapter.h"

#include <stdint.h>
#include <stdio.h>
#include <string.h>

typedef struct MockMachine {
    uint64_t frame;
    uint32_t reset_count;
    uint32_t key_count;
    uint32_t button_count;
    uint32_t text_release_count;
    emu_automation_execution_state_t state;
    uint8_t pixels[16];
    emu_automation_text_cell_t cells[4];
} MockMachine;

static emu_automation_result_t mock_capabilities(
    void *context,
    emu_automation_capabilities_t *out_capabilities)
{
    (void)context;
    out_capabilities->feature_bits =
        EMU_AUTOMATION_CAP_SCREEN_FRAMEBUFFER |
        EMU_AUTOMATION_CAP_INPUT_KEYBOARD |
        EMU_AUTOMATION_CAP_INPUT_CONTROLLER |
        EMU_AUTOMATION_CAP_EXEC_TIMING |
        EMU_AUTOMATION_CAP_EXEC_PAUSE |
        EMU_AUTOMATION_CAP_EXEC_RESUME |
        EMU_AUTOMATION_CAP_EXEC_RESET |
        EMU_AUTOMATION_CAP_EXEC_STEP_FRAME |
        EMU_AUTOMATION_CAP_EXEC_RUN_FRAMES |
        EMU_AUTOMATION_CAP_SCREEN_TEXT_GRID;
    return EMU_AUTOMATION_OK;
}

static emu_automation_result_t mock_describe(
    void *context,
    emu_automation_machine_descriptor_t *out_descriptor)
{
    (void)context;
    out_descriptor->machine_id = "mock-1";
    out_descriptor->system_id = "mock";
    out_descriptor->model_id = "model-a";
    out_descriptor->region = "test";
    out_descriptor->video_standard = "progressive";
    out_descriptor->adapter_version = "1";
    out_descriptor->configured_memory_bytes = 65536u;
    return mock_capabilities(context, &out_descriptor->capabilities);
}

static emu_automation_result_t mock_pause(void *context)
{
    ((MockMachine *)context)->state = EMU_AUTOMATION_EXECUTION_PAUSED;
    return EMU_AUTOMATION_OK;
}

static emu_automation_result_t mock_resume(void *context)
{
    ((MockMachine *)context)->state = EMU_AUTOMATION_EXECUTION_RUNNING;
    return EMU_AUTOMATION_OK;
}

static emu_automation_result_t mock_reset(void *context, emu_automation_reset_kind_t kind)
{
    MockMachine *machine = (MockMachine *)context;
    if (kind != EMU_AUTOMATION_RESET_COLD) {
        return EMU_AUTOMATION_UNSUPPORTED;
    }
    machine->frame = 0u;
    machine->reset_count++;
    machine->state = EMU_AUTOMATION_EXECUTION_PAUSED;
    return EMU_AUTOMATION_OK;
}

static emu_automation_result_t mock_step_frame(void *context)
{
    ((MockMachine *)context)->frame++;
    return EMU_AUTOMATION_OK;
}

static emu_automation_result_t mock_run_frames(void *context, uint64_t frame_count)
{
    ((MockMachine *)context)->frame += frame_count;
    return EMU_AUTOMATION_OK;
}

static emu_automation_result_t mock_capture_framebuffer(
    void *context,
    emu_automation_framebuffer_snapshot_t *out_snapshot)
{
    MockMachine *machine = (MockMachine *)context;
    machine->pixels[0] = (uint8_t)machine->frame;
    out_snapshot->frame.frame_number = machine->frame;
    out_snapshot->frame.execution_state = machine->state;
    out_snapshot->width = 2u;
    out_snapshot->height = 2u;
    out_snapshot->stride_bytes = 8u;
    out_snapshot->pixel_format = EMU_AUTOMATION_PIXEL_FORMAT_RGBA8888;
    out_snapshot->visible_area.width = 2u;
    out_snapshot->visible_area.height = 2u;
    out_snapshot->pixel_aspect_numerator = 1u;
    out_snapshot->pixel_aspect_denominator = 1u;
    out_snapshot->pixels = machine->pixels;
    out_snapshot->pixel_size = sizeof(machine->pixels);
    return EMU_AUTOMATION_OK;
}

static emu_automation_result_t mock_key(
    void *context,
    const emu_automation_key_event_t *event)
{
    MockMachine *machine = (MockMachine *)context;
    if (strcmp(event->key_id, "RETURN") != 0) {
        return EMU_AUTOMATION_MAPPING_UNAVAILABLE;
    }
    machine->key_count++;
    return EMU_AUTOMATION_OK;
}

static emu_automation_result_t mock_capture_text_grid(
    void *context,
    const char *region_id,
    emu_automation_text_grid_snapshot_t *out_snapshot)
{
    MockMachine *machine = (MockMachine *)context;
    if (region_id != NULL && strcmp(region_id, "main") != 0) {
        return EMU_AUTOMATION_UNSUPPORTED;
    }
    for (uint32_t i = 0u; i < 4u; ++i) {
        machine->cells[i].struct_size = sizeof(machine->cells[i]);
        machine->cells[i].struct_version = EMU_AUTOMATION_STRUCT_VERSION;
        machine->cells[i].native_code = (uint32_t)('A' + i);
        machine->cells[i].unicode_codepoint = (uint32_t)('A' + i);
        machine->cells[i].glyph_id = "mock_ascii";
        machine->cells[i].foreground_color = 1;
        machine->cells[i].background_color = 0;
        machine->cells[i].charset_id = "mock";
        machine->cells[i].source_address = 0x400u + i;
        machine->cells[i].confidence = 255u;
    }
    out_snapshot->frame.frame_number = machine->frame;
    out_snapshot->region_id = "main";
    out_snapshot->columns = 2u;
    out_snapshot->rows = 2u;
    out_snapshot->row_stride = 2u;
    out_snapshot->cells = machine->cells;
    out_snapshot->cell_count = 4u;
    out_snapshot->plain_utf8 = "AB\nCD";
    out_snapshot->plain_utf8_size = 5u;
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
    out_descriptor->charset_id = "mock";
    out_descriptor->native_encoding = "mock_ascii";
    out_descriptor->unicode_map = "ascii";
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
    return EMU_AUTOMATION_OK;
}

int main(void)
{
    MockMachine mock;
    emu_automation_adapter_t adapter;
    emu_automation_machine_t *machine = NULL;
    emu_automation_machine_descriptor_t descriptor;
    emu_automation_framebuffer_snapshot_t framebuffer;
    emu_automation_frame_metadata_t timing;
    emu_automation_text_view_descriptor_t text_descriptor;
    emu_automation_text_grid_snapshot_t text_grid;
    emu_automation_key_event_t key_event;
    emu_automation_controller_button_event_t button_event;
    size_t text_view_count = 0u;

    memset(&mock, 0, sizeof(mock));
    memset(&adapter, 0, sizeof(adapter));
    adapter.struct_size = sizeof(adapter);
    adapter.struct_version = EMU_AUTOMATION_STRUCT_VERSION;
    adapter.context = &mock;
    adapter.describe = mock_describe;
    adapter.capabilities = mock_capabilities;
    adapter.pause = mock_pause;
    adapter.resume = mock_resume;
    adapter.reset = mock_reset;
    adapter.step_frame = mock_step_frame;
    adapter.run_frames = mock_run_frames;
    adapter.capture_framebuffer = mock_capture_framebuffer;
    adapter.capture_text_grid = mock_capture_text_grid;
    adapter.read_frame_metadata = mock_read_frame_metadata;
    adapter.text_grid_view_count = mock_text_grid_view_count;
    adapter.text_grid_view_descriptor = mock_text_grid_view_descriptor;
    adapter.release_text_grid = mock_release_text_grid;
    adapter.submit_key = mock_key;
    adapter.submit_controller_button = mock_button;

    if (emu_automation_abi_version() != EMU_AUTOMATION_ABI_VERSION) return 1;
    if (emu_automation_attach_adapter(&adapter, &machine) != EMU_AUTOMATION_OK) return 2;
    if (emu_automation_machine_describe(machine, &descriptor) != EMU_AUTOMATION_OK) return 3;
    if (strcmp(descriptor.system_id, "mock") != 0) return 4;
    if ((descriptor.capabilities.feature_bits & EMU_AUTOMATION_CAP_EXEC_STEP_FRAME) == 0u) return 5;
    if (emu_automation_machine_reset(machine, EMU_AUTOMATION_RESET_COLD) != EMU_AUTOMATION_OK) return 6;
    if (emu_automation_machine_resume(machine) != EMU_AUTOMATION_OK) return 7;
    if (emu_automation_machine_step_frame(machine) != EMU_AUTOMATION_OK) return 8;
    if (emu_automation_machine_run_frames(machine, 4u) != EMU_AUTOMATION_OK) return 9;
    if (emu_automation_screen_framebuffer(machine, &framebuffer) != EMU_AUTOMATION_OK) return 10;
    if (framebuffer.frame.frame_number != 5u || framebuffer.pixels[0] != 5u) return 11;
    emu_automation_framebuffer_release(machine, &framebuffer);
    if (emu_automation_execution_frame_metadata(machine, &timing) != EMU_AUTOMATION_OK) return 25;
    if (timing.frame_number != 5u || timing.emulated_cycles != 500u || timing.emulated_time_ns != 5000u) return 26;
    if (emu_automation_screen_text_view_count(machine, &text_view_count) != EMU_AUTOMATION_OK) return 20;
    if (text_view_count != 1u) return 21;
    if (emu_automation_screen_text_view_descriptor(machine, 0u, &text_descriptor) != EMU_AUTOMATION_OK) return 22;
    if (strcmp(text_descriptor.region_id, "main") != 0 || text_descriptor.columns != 2u) return 23;
    if (strcmp(text_descriptor.native_encoding, "mock_ascii") != 0) return 24;
    if (emu_automation_screen_text_grid(machine, "main", &text_grid) != EMU_AUTOMATION_OK) return 15;
    if (text_grid.columns != 2u || text_grid.rows != 2u || text_grid.cell_count != 4u) return 16;
    if (text_grid.cells[0].native_code != 'A' || text_grid.cells[3].source_address != 0x403u) return 17;
    if (strcmp(text_grid.plain_utf8, "AB\nCD") != 0) return 18;
    emu_automation_text_grid_release(machine, &text_grid);
    if (mock.text_release_count != 1u || text_grid.cells != NULL) return 19;

    memset(&key_event, 0, sizeof(key_event));
    key_event.struct_size = sizeof(key_event);
    key_event.struct_version = EMU_AUTOMATION_STRUCT_VERSION;
    key_event.device_id = "keyboard";
    key_event.key_id = "RETURN";
    key_event.action = EMU_AUTOMATION_INPUT_PRESS;
    key_event.timing.kind = EMU_AUTOMATION_TIMING_IMMEDIATE;
    if (emu_automation_input_key(machine, &key_event) != EMU_AUTOMATION_OK) return 12;

    memset(&button_event, 0, sizeof(button_event));
    button_event.struct_size = sizeof(button_event);
    button_event.struct_version = EMU_AUTOMATION_STRUCT_VERSION;
    button_event.device_id = "joystick_port_1";
    button_event.control_id = "fire_1";
    button_event.action = EMU_AUTOMATION_INPUT_PRESS;
    button_event.timing.kind = EMU_AUTOMATION_TIMING_IMMEDIATE;
    if (emu_automation_input_controller_button(machine, &button_event) != EMU_AUTOMATION_OK) return 13;
    if (mock.key_count != 1u || mock.button_count != 1u) return 14;

    emu_automation_machine_destroy(machine);
    printf("%s %s %llu\n", descriptor.system_id, emu_automation_result_name(EMU_AUTOMATION_OK), (unsigned long long)mock.frame);
    return 0;
}
"""


def _compile_and_run(tmp_path: pathlib.Path, compiler: str, suffix: str, extra_flags: list[str]) -> str:
    if shutil.which(compiler) is None:
        pytest.skip(f"{compiler} is not available")

    source = tmp_path / f"mock_caller{suffix}"
    binary = tmp_path / "mock_caller"
    source.write_text(MOCK_CALLER_C, encoding="utf-8")
    command = [
        compiler,
        *extra_flags,
        "-I",
        str(BASE_DIR / "automation" / "include"),
        str(BASE_DIR / "automation" / "core" / "emu_automation.c"),
        str(source),
        "-o",
        str(binary),
    ]
    subprocess.run(command, check=True)
    result = subprocess.run([str(binary)], check=True, text=True, capture_output=True)
    return result.stdout.strip()


def test_automation_c_abi_drives_mock_machine_from_c(tmp_path):
    assert _compile_and_run(tmp_path, "cc", ".c", ["-std=c11", "-Wall", "-Wextra"]) == "mock ok 5"


def test_automation_c_abi_headers_are_cpp_compatible(tmp_path):
    assert _compile_and_run(tmp_path, "c++", ".cpp", ["-std=c++17", "-Wall", "-Wextra"]) == "mock ok 5"


def test_automation_c_abi_rejects_invalid_adapter(tmp_path):
    if shutil.which("cc") is None:
        pytest.skip("cc is not available")

    source = tmp_path / "invalid_adapter.c"
    binary = tmp_path / "invalid_adapter"
    source.write_text(
        textwrap.dedent(
            """
            #include "emu_automation_adapter.h"

            int main(void) {
                emu_automation_adapter_t adapter = {0};
                emu_automation_machine_t *machine = (emu_automation_machine_t *)1;
                adapter.struct_size = sizeof(adapter);
                adapter.struct_version = EMU_AUTOMATION_STRUCT_VERSION;
                adapter.context = 0;
                adapter.destroy_context = 0;
                adapter.describe = 0;
                adapter.capabilities = 0;
                return emu_automation_attach_adapter(&adapter, &machine) == EMU_AUTOMATION_INVALID_ARGUMENT
                    && machine == (emu_automation_machine_t *)1 ? 0 : 1;
            }
            """
        ),
        encoding="utf-8",
    )
    subprocess.run(
        [
            "cc",
            "-std=c11",
            "-Wall",
            "-Wextra",
            "-I",
            str(BASE_DIR / "automation" / "include"),
            str(BASE_DIR / "automation" / "core" / "emu_automation.c"),
            str(source),
            "-o",
            str(binary),
        ],
        check=True,
    )
    subprocess.run([str(binary)], check=True)


def test_automation_c_abi_event_subscription_core_api(tmp_path):
    if shutil.which("cc") is None:
        pytest.skip("cc is not available")

    source = tmp_path / "subscription_api.c"
    binary = tmp_path / "subscription_api"
    source.write_text(
        textwrap.dedent(
            r"""
            #include "emu_automation_adapter.h"

            #include <stdint.h>
            #include <stdlib.h>
            #include <string.h>

            typedef struct MockMachine {
                uint64_t frame;
                uint64_t next_sequence;
                emu_automation_execution_state_t state;
                emu_automation_event_t events[16];
                size_t event_count;
            } MockMachine;

            typedef struct SeenEvents {
                uint64_t sequences[8];
                size_t count;
            } SeenEvents;

            static void mock_push_event(
                MockMachine *machine,
                emu_automation_event_type_t event_type,
                emu_automation_execution_state_t previous_execution_state,
                emu_automation_execution_state_t current_execution_state)
            {
                emu_automation_event_t *event;
                if (machine->event_count >= (sizeof(machine->events) / sizeof(machine->events[0]))) return;
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
            }

            static emu_automation_result_t mock_describe(
                void *context,
                emu_automation_machine_descriptor_t *out_descriptor)
            {
                (void)context;
                out_descriptor->machine_id = "sub-machine";
                out_descriptor->system_id = "sub-system";
                out_descriptor->model_id = "sub-model";
                out_descriptor->region = "";
                out_descriptor->video_standard = "";
                out_descriptor->adapter_version = "1";
                out_descriptor->configured_memory_bytes = 65536u;
                return EMU_AUTOMATION_OK;
            }

            static emu_automation_result_t mock_capabilities(
                void *context,
                emu_automation_capabilities_t *out_capabilities)
            {
                (void)context;
                out_capabilities->feature_bits =
                    EMU_AUTOMATION_CAP_EXEC_RESET |
                    EMU_AUTOMATION_CAP_EXEC_RUN_FRAMES |
                    EMU_AUTOMATION_CAP_EVENTS_FRAME_COMPLETED;
                return EMU_AUTOMATION_OK;
            }

            static emu_automation_result_t mock_reset(void *context, emu_automation_reset_kind_t kind)
            {
                MockMachine *machine = (MockMachine *)context;
                if (kind != EMU_AUTOMATION_RESET_COLD) return EMU_AUTOMATION_UNSUPPORTED;
                machine->frame = 0u;
                machine->state = EMU_AUTOMATION_EXECUTION_PAUSED;
                mock_push_event(
                    machine,
                    EMU_AUTOMATION_EVENT_MACHINE_RESET,
                    0,
                    EMU_AUTOMATION_EXECUTION_PAUSED);
                return EMU_AUTOMATION_OK;
            }

            static emu_automation_result_t mock_run_frames(void *context, uint64_t frame_count)
            {
                MockMachine *machine = (MockMachine *)context;
                for (uint64_t i = 0u; i < frame_count; ++i) {
                    machine->frame++;
                    if (machine->frame == 2u) {
                        mock_push_event(machine, EMU_AUTOMATION_EVENT_TEXT_CHANGED, 0, 0);
                    }
                    mock_push_event(machine, EMU_AUTOMATION_EVENT_FRAME_COMPLETED, 0, 0);
                }
                return EMU_AUTOMATION_OK;
            }

            static emu_automation_result_t mock_poll_event(
                void *context,
                uint64_t after_sequence,
                emu_automation_event_t *out_event)
            {
                MockMachine *machine = (MockMachine *)context;
                for (size_t i = 0u; i < machine->event_count; ++i) {
                    if (machine->events[i].sequence_number > after_sequence) {
                        *out_event = machine->events[i];
                        return EMU_AUTOMATION_OK;
                    }
                }
                return EMU_AUTOMATION_TIMEOUT;
            }

            static void on_event(const emu_automation_event_t *event, void *user_data)
            {
                SeenEvents *seen = (SeenEvents *)user_data;
                if (seen->count < (sizeof(seen->sequences) / sizeof(seen->sequences[0]))) {
                    seen->sequences[seen->count++] = event->sequence_number;
                }
            }

            int main(void)
            {
                MockMachine mock;
                SeenEvents seen;
                emu_automation_adapter_t adapter;
                emu_automation_machine_t *machine = NULL;
                emu_automation_subscription_t *subscription = NULL;
                size_t count = 0u;

                memset(&mock, 0, sizeof(mock));
                memset(&seen, 0, sizeof(seen));
                memset(&adapter, 0, sizeof(adapter));
                adapter.struct_size = sizeof(adapter);
                adapter.struct_version = EMU_AUTOMATION_STRUCT_VERSION;
                adapter.context = &mock;
                adapter.describe = mock_describe;
                adapter.capabilities = mock_capabilities;
                adapter.reset = mock_reset;
                adapter.run_frames = mock_run_frames;
                adapter.poll_event = mock_poll_event;

                if (emu_automation_attach_adapter(&adapter, &machine) != EMU_AUTOMATION_OK) return 1;
                if (emu_automation_machine_reset(machine, EMU_AUTOMATION_RESET_COLD) != EMU_AUTOMATION_OK) return 2;
                if (emu_automation_machine_run_frames(machine, 3u) != EMU_AUTOMATION_OK) return 3;
                if (emu_automation_subscription_create(
                        machine,
                        EMU_AUTOMATION_EVENT_FRAME_COMPLETED,
                        0u,
                        on_event,
                        &seen,
                        &subscription) != EMU_AUTOMATION_OK) return 4;
                if (emu_automation_subscription_dispatch_available(subscription, 0u, &count) != EMU_AUTOMATION_OK) return 5;
                if (count != 3u) return 6;
                if (seen.count != 3u) return 7;
                if (seen.sequences[0] != 2u || seen.sequences[1] != 4u || seen.sequences[2] != 5u) return 8;
                if (emu_automation_subscription_after_sequence(subscription) != 5u) return 9;
                if (emu_automation_subscription_dispatch_available(subscription, 0u, &count) != EMU_AUTOMATION_OK) return 10;
                if (count != 0u) return 11;
                if (emu_automation_subscription_set_after_sequence(subscription, 1u) != EMU_AUTOMATION_OK) return 12;
                if (emu_automation_subscription_after_sequence(subscription) != 1u) return 13;
                if (emu_automation_subscription_dispatch_available(subscription, 1u, &count) != EMU_AUTOMATION_OK) return 14;
                if (count != 1u) return 15;
                if (emu_automation_subscription_after_sequence(subscription) != 2u) return 16;
                emu_automation_machine_destroy(machine);
                if (emu_automation_subscription_dispatch_available(subscription, 0u, &count) != EMU_AUTOMATION_INVALID_STATE) return 17;
                emu_automation_subscription_destroy(subscription);
                return 0;
            }
            """
        ),
        encoding="utf-8",
    )
    subprocess.run(
        [
            "cc",
            "-std=c11",
            "-Wall",
            "-Wextra",
            "-I",
            str(BASE_DIR / "automation" / "include"),
            str(BASE_DIR / "automation" / "core" / "emu_automation.c"),
            str(source),
            "-o",
            str(binary),
        ],
        check=True,
    )
    subprocess.run([str(binary)], check=True)


def test_automation_c_abi_subscription_rejects_reentrant_dispatch(tmp_path):
    if shutil.which("cc") is None:
        pytest.skip("cc is not available")

    source = tmp_path / "subscription_reentrant.c"
    binary = tmp_path / "subscription_reentrant"
    source.write_text(
        textwrap.dedent(
            r"""
            #include "emu_automation_adapter.h"

            #include <stdint.h>
            #include <stdlib.h>
            #include <string.h>

            typedef struct MockMachine {
                uint64_t next_sequence;
                emu_automation_event_t events[4];
                size_t event_count;
            } MockMachine;

            typedef struct CallbackState {
                emu_automation_subscription_t *subscription;
                int nested_result;
                size_t nested_count;
            } CallbackState;

            static void mock_push_event(
                MockMachine *machine,
                emu_automation_event_type_t event_type,
                emu_automation_execution_state_t previous_execution_state,
                emu_automation_execution_state_t current_execution_state)
            {
                emu_automation_event_t *event = &machine->events[machine->event_count++];
                memset(event, 0, sizeof(*event));
                event->struct_size = sizeof(*event);
                event->struct_version = EMU_AUTOMATION_STRUCT_VERSION;
                event->sequence_number = ++machine->next_sequence;
                event->event_type = event_type;
                event->previous_execution_state = previous_execution_state;
                event->current_execution_state = current_execution_state;
                event->frame.struct_size = sizeof(event->frame);
                event->frame.struct_version = EMU_AUTOMATION_STRUCT_VERSION;
                event->input_accepted.struct_size = sizeof(event->input_accepted);
                event->input_accepted.struct_version = EMU_AUTOMATION_STRUCT_VERSION;
                event->input_applied.struct_size = sizeof(event->input_applied);
                event->input_applied.struct_version = EMU_AUTOMATION_STRUCT_VERSION;
            }

            static emu_automation_result_t mock_describe(
                void *context,
                emu_automation_machine_descriptor_t *out_descriptor)
            {
                (void)context;
                out_descriptor->machine_id = "reentrant-machine";
                out_descriptor->system_id = "reentrant-system";
                out_descriptor->model_id = "reentrant-model";
                out_descriptor->region = "";
                out_descriptor->video_standard = "";
                out_descriptor->adapter_version = "1";
                out_descriptor->configured_memory_bytes = 65536u;
                return EMU_AUTOMATION_OK;
            }

            static emu_automation_result_t mock_capabilities(
                void *context,
                emu_automation_capabilities_t *out_capabilities)
            {
                (void)context;
                out_capabilities->feature_bits = EMU_AUTOMATION_CAP_EVENTS_FRAME_COMPLETED;
                return EMU_AUTOMATION_OK;
            }

            static emu_automation_result_t mock_poll_event(
                void *context,
                uint64_t after_sequence,
                emu_automation_event_t *out_event)
            {
                MockMachine *machine = (MockMachine *)context;
                for (size_t i = 0u; i < machine->event_count; ++i) {
                    if (machine->events[i].sequence_number > after_sequence) {
                        *out_event = machine->events[i];
                        return EMU_AUTOMATION_OK;
                    }
                }
                return EMU_AUTOMATION_TIMEOUT;
            }

            static void on_event(const emu_automation_event_t *event, void *user_data)
            {
                CallbackState *state = (CallbackState *)user_data;
                (void)event;
                state->nested_result = emu_automation_subscription_dispatch_available(
                    state->subscription,
                    1u,
                    &state->nested_count);
            }

            int main(void)
            {
                MockMachine mock;
                CallbackState state;
                emu_automation_adapter_t adapter;
                emu_automation_machine_t *machine = NULL;
                emu_automation_subscription_t *subscription = NULL;
                size_t count = 0u;

                memset(&mock, 0, sizeof(mock));
                memset(&state, 0, sizeof(state));
                memset(&adapter, 0, sizeof(adapter));
                adapter.struct_size = sizeof(adapter);
                adapter.struct_version = EMU_AUTOMATION_STRUCT_VERSION;
                adapter.context = &mock;
                adapter.describe = mock_describe;
                adapter.capabilities = mock_capabilities;
                adapter.poll_event = mock_poll_event;

                mock_push_event(&mock, EMU_AUTOMATION_EVENT_FRAME_COMPLETED, 0, 0);

                if (emu_automation_attach_adapter(&adapter, &machine) != EMU_AUTOMATION_OK) return 1;
                if (emu_automation_subscription_create(
                        machine,
                        EMU_AUTOMATION_EVENT_FRAME_COMPLETED,
                        0u,
                        on_event,
                        &state,
                        &subscription) != EMU_AUTOMATION_OK) return 2;
                state.subscription = subscription;
                if (emu_automation_subscription_dispatch_available(subscription, 1u, &count) != EMU_AUTOMATION_OK) return 3;
                if (count != 1u) return 4;
                if (state.nested_result != EMU_AUTOMATION_INVALID_STATE) return 5;
                if (state.nested_count != 0u) return 6;
                emu_automation_subscription_destroy(subscription);
                emu_automation_machine_destroy(machine);
                return 0;
            }
            """
        ),
        encoding="utf-8",
    )
    subprocess.run(
        [
            "cc",
            "-std=c11",
            "-Wall",
            "-Wextra",
            "-I",
            str(BASE_DIR / "automation" / "include"),
            str(BASE_DIR / "automation" / "core" / "emu_automation.c"),
            str(source),
            "-o",
            str(binary),
        ],
        check=True,
    )
    subprocess.run([str(binary)], check=True)
