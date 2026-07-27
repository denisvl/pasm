import ctypes
import pathlib
import shutil
import subprocess
import sys
import textwrap

import pytest

from src.pasm_automation import AutomationError, AutomationLibrary


BASE_DIR = pathlib.Path(__file__).resolve().parents[1]


MOCK_SHARED_C = r"""
#include "emu_automation_adapter.h"

#include <stdint.h>
#include <stdlib.h>
#include <string.h>

typedef struct MockMachine {
    uint64_t frame;
    uint32_t key_count;
    uint32_t button_count;
    uint32_t release_count;
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
        EMU_AUTOMATION_CAP_SCREEN_TEXT_GRID |
        EMU_AUTOMATION_CAP_SCREEN_FRAMEBUFFER |
        EMU_AUTOMATION_CAP_INPUT_KEYBOARD |
        EMU_AUTOMATION_CAP_INPUT_CONTROLLER |
        EMU_AUTOMATION_CAP_EXEC_PAUSE |
        EMU_AUTOMATION_CAP_EXEC_RESUME |
        EMU_AUTOMATION_CAP_EXEC_RESET |
        EMU_AUTOMATION_CAP_EXEC_STEP_FRAME |
        EMU_AUTOMATION_CAP_EXEC_RUN_FRAMES;
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
    ((MockMachine *)context)->state = EMU_AUTOMATION_EXECUTION_PAUSED;
    return EMU_AUTOMATION_OK;
}

static emu_automation_result_t mock_resume(void *context)
{
    ((MockMachine *)context)->state = EMU_AUTOMATION_EXECUTION_RUNNING;
    return EMU_AUTOMATION_OK;
}

static emu_automation_result_t mock_reset(
    void *context,
    emu_automation_reset_kind_t kind)
{
    MockMachine *machine = (MockMachine *)context;
    if (kind != EMU_AUTOMATION_RESET_COLD) {
        return EMU_AUTOMATION_UNSUPPORTED;
    }
    machine->frame = 0u;
    machine->state = EMU_AUTOMATION_EXECUTION_PAUSED;
    return EMU_AUTOMATION_OK;
}

static emu_automation_result_t mock_step_frame(void *context)
{
    ((MockMachine *)context)->frame++;
    return EMU_AUTOMATION_OK;
}

static emu_automation_result_t mock_run_frames(
    void *context,
    uint64_t frame_count)
{
    ((MockMachine *)context)->frame += frame_count;
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
    if (region_id != NULL && strcmp(region_id, "main") != 0) {
        return EMU_AUTOMATION_UNSUPPORTED;
    }

    for (uint32_t i = 0u; i < 4u; ++i) {
        machine->cells[i].struct_size = sizeof(machine->cells[i]);
        machine->cells[i].struct_version = EMU_AUTOMATION_STRUCT_VERSION;
        machine->cells[i].native_code = (uint32_t)('A' + i);
        machine->cells[i].unicode_codepoint = (uint32_t)('A' + i);
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
    out_snapshot->plain_utf8 = "AB\nCD";
    out_snapshot->plain_utf8_size = 5u;
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
    adapter.pause = mock_pause;
    adapter.resume = mock_resume;
    adapter.reset = mock_reset;
    adapter.step_frame = mock_step_frame;
    adapter.run_frames = mock_run_frames;
    adapter.capture_framebuffer = mock_capture_framebuffer;
    adapter.capture_text_grid = mock_capture_text_grid;
    adapter.release_text_grid = mock_release_text_grid;
    adapter.text_grid_view_count = mock_text_grid_view_count;
    adapter.text_grid_view_descriptor = mock_text_grid_view_descriptor;
    adapter.submit_key = mock_key;
    adapter.submit_controller_button = mock_button;
    return emu_automation_attach_adapter(&adapter, out_machine);
}
"""


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
    library.cdll.emu_test_create_text_machine.argtypes = [
        ctypes.POINTER(ctypes.c_void_p),
    ]
    library.cdll.emu_test_create_text_machine.restype = ctypes.c_int

    handle = ctypes.c_void_p()
    library.check(
        library.cdll.emu_test_create_text_machine(ctypes.byref(handle)),
        "emu_test_create_text_machine",
    )

    with library.machine(handle) as machine:
        descriptor = machine.describe()
        assert descriptor.machine_id == "mock-machine"
        assert descriptor.capabilities.feature_bits != 0

        machine.reset()
        machine.resume()
        machine.step_frame()
        machine.run_frames(41)
        machine.pause()
        machine.tap_key("RETURN")
        machine.controller_button("fire_1", device_id="joystick_port_1")

        framebuffer = machine.capture_framebuffer()
        assert framebuffer.width == 2
        assert framebuffer.height == 2
        assert framebuffer.stride_bytes == 8
        assert framebuffer.frame.frame_number == 42
        assert framebuffer.visible_area.width == 2
        assert framebuffer.pixels[:4] == bytes([0, 1, 2, 3])

        views = machine.text_views()
        assert len(views) == 1
        assert views[0].region_id == "main"
        assert views[0].columns == 2
        assert views[0].charset_id == "mock_charset"

        snapshot = machine.capture_text_grid("main")
        assert snapshot.region_id == "main"
        assert snapshot.plain == "AB\nCD"
        assert snapshot.columns == 2
        assert snapshot.rows == 2
        assert snapshot.frame_number == 42
        assert snapshot.emulated_cycles == 1234
        assert snapshot.execution_state == 2
        assert snapshot.cells[0].text == "A"
        assert snapshot.cells[1].native_code == ord("B")
        assert snapshot.cells[3].source_address == 0x0403
        assert snapshot.cells[3].attribute_flags == 3

        with pytest.raises(AutomationError, match="unsupported"):
            machine.capture_text_grid("missing")
        with pytest.raises(AutomationError, match="mapping_unavailable"):
            machine.key("ESCAPE")
