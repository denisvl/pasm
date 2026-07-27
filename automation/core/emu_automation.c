#include "emu_automation_adapter.h"

#include <stdlib.h>
#include <string.h>

struct emu_automation_machine {
    emu_automation_adapter_t adapter;
};

static int has_capability(emu_automation_machine_t *machine, uint64_t bit)
{
    emu_automation_capabilities_t caps;
    emu_automation_result_t result;

    memset(&caps, 0, sizeof(caps));
    result = emu_automation_machine_capabilities(machine, &caps);
    return result == EMU_AUTOMATION_OK && (caps.feature_bits & bit) != 0u;
}

static void init_capabilities(emu_automation_capabilities_t *capabilities)
{
    memset(capabilities, 0, sizeof(*capabilities));
    capabilities->struct_size = (uint32_t)sizeof(*capabilities);
    capabilities->struct_version = EMU_AUTOMATION_STRUCT_VERSION;
}

uint32_t emu_automation_abi_version(void)
{
    return EMU_AUTOMATION_ABI_VERSION;
}

const char *emu_automation_result_name(emu_automation_result_t result)
{
    switch (result) {
    case EMU_AUTOMATION_OK: return "ok";
    case EMU_AUTOMATION_UNSUPPORTED: return "unsupported";
    case EMU_AUTOMATION_INVALID_ARGUMENT: return "invalid_argument";
    case EMU_AUTOMATION_INVALID_STATE: return "invalid_state";
    case EMU_AUTOMATION_NOT_RUNNING: return "not_running";
    case EMU_AUTOMATION_ALREADY_RUNNING: return "already_running";
    case EMU_AUTOMATION_NOT_READY: return "not_ready";
    case EMU_AUTOMATION_TIMEOUT: return "timeout";
    case EMU_AUTOMATION_MAPPING_UNAVAILABLE: return "mapping_unavailable";
    case EMU_AUTOMATION_CHARACTER_UNSUPPORTED: return "character_unsupported";
    case EMU_AUTOMATION_DEVICE_UNAVAILABLE: return "device_unavailable";
    case EMU_AUTOMATION_RESOURCE_UNAVAILABLE: return "resource_unavailable";
    case EMU_AUTOMATION_TRANSPORT_ERROR: return "transport_error";
    case EMU_AUTOMATION_SERIALIZATION_ERROR: return "serialization_error";
    case EMU_AUTOMATION_ADAPTER_ERROR: return "adapter_error";
    case EMU_AUTOMATION_INTERNAL_ERROR: return "internal_error";
    default: return "unknown";
    }
}

emu_automation_result_t emu_automation_attach_adapter(
    const emu_automation_adapter_t *adapter,
    emu_automation_machine_t **out_machine)
{
    emu_automation_machine_t *machine;

    if (adapter == NULL || out_machine == NULL) {
        return EMU_AUTOMATION_INVALID_ARGUMENT;
    }
    if (adapter->struct_size < sizeof(emu_automation_adapter_t) ||
        adapter->struct_version != EMU_AUTOMATION_STRUCT_VERSION) {
        return EMU_AUTOMATION_INVALID_ARGUMENT;
    }
    if (adapter->describe == NULL || adapter->capabilities == NULL) {
        return EMU_AUTOMATION_INVALID_ARGUMENT;
    }

    machine = (emu_automation_machine_t *)calloc(1u, sizeof(*machine));
    if (machine == NULL) {
        return EMU_AUTOMATION_INTERNAL_ERROR;
    }

    machine->adapter = *adapter;
    *out_machine = machine;
    return EMU_AUTOMATION_OK;
}

void emu_automation_machine_destroy(emu_automation_machine_t *machine)
{
    if (machine == NULL) {
        return;
    }
    if (machine->adapter.destroy_context != NULL) {
        machine->adapter.destroy_context(machine->adapter.context);
    }
    free(machine);
}

emu_automation_result_t emu_automation_machine_describe(
    emu_automation_machine_t *machine,
    emu_automation_machine_descriptor_t *out_descriptor)
{
    if (machine == NULL || out_descriptor == NULL) {
        return EMU_AUTOMATION_INVALID_ARGUMENT;
    }
    memset(out_descriptor, 0, sizeof(*out_descriptor));
    out_descriptor->struct_size = (uint32_t)sizeof(*out_descriptor);
    out_descriptor->struct_version = EMU_AUTOMATION_STRUCT_VERSION;
    init_capabilities(&out_descriptor->capabilities);
    return machine->adapter.describe(machine->adapter.context, out_descriptor);
}

emu_automation_result_t emu_automation_machine_capabilities(
    emu_automation_machine_t *machine,
    emu_automation_capabilities_t *out_capabilities)
{
    if (machine == NULL || out_capabilities == NULL) {
        return EMU_AUTOMATION_INVALID_ARGUMENT;
    }
    init_capabilities(out_capabilities);
    return machine->adapter.capabilities(machine->adapter.context, out_capabilities);
}

emu_automation_result_t emu_automation_machine_pause(emu_automation_machine_t *machine)
{
    if (machine == NULL) {
        return EMU_AUTOMATION_INVALID_ARGUMENT;
    }
    if (machine->adapter.pause == NULL ||
        !has_capability(machine, EMU_AUTOMATION_CAP_EXEC_PAUSE)) {
        return EMU_AUTOMATION_UNSUPPORTED;
    }
    return machine->adapter.pause(machine->adapter.context);
}

emu_automation_result_t emu_automation_machine_resume(emu_automation_machine_t *machine)
{
    if (machine == NULL) {
        return EMU_AUTOMATION_INVALID_ARGUMENT;
    }
    if (machine->adapter.resume == NULL ||
        !has_capability(machine, EMU_AUTOMATION_CAP_EXEC_RESUME)) {
        return EMU_AUTOMATION_UNSUPPORTED;
    }
    return machine->adapter.resume(machine->adapter.context);
}

emu_automation_result_t emu_automation_machine_reset(
    emu_automation_machine_t *machine,
    emu_automation_reset_kind_t kind)
{
    if (machine == NULL) {
        return EMU_AUTOMATION_INVALID_ARGUMENT;
    }
    if (kind != EMU_AUTOMATION_RESET_COLD && kind != EMU_AUTOMATION_RESET_WARM) {
        return EMU_AUTOMATION_INVALID_ARGUMENT;
    }
    if (machine->adapter.reset == NULL ||
        !has_capability(machine, EMU_AUTOMATION_CAP_EXEC_RESET)) {
        return EMU_AUTOMATION_UNSUPPORTED;
    }
    return machine->adapter.reset(machine->adapter.context, kind);
}

emu_automation_result_t emu_automation_machine_step_frame(emu_automation_machine_t *machine)
{
    if (machine == NULL) {
        return EMU_AUTOMATION_INVALID_ARGUMENT;
    }
    if (machine->adapter.step_frame == NULL ||
        !has_capability(machine, EMU_AUTOMATION_CAP_EXEC_STEP_FRAME)) {
        return EMU_AUTOMATION_UNSUPPORTED;
    }
    return machine->adapter.step_frame(machine->adapter.context);
}

emu_automation_result_t emu_automation_machine_run_frames(
    emu_automation_machine_t *machine,
    uint64_t frame_count)
{
    if (machine == NULL) {
        return EMU_AUTOMATION_INVALID_ARGUMENT;
    }
    if (machine->adapter.run_frames == NULL ||
        !has_capability(machine, EMU_AUTOMATION_CAP_EXEC_RUN_FRAMES)) {
        return EMU_AUTOMATION_UNSUPPORTED;
    }
    return machine->adapter.run_frames(machine->adapter.context, frame_count);
}

emu_automation_result_t emu_automation_screen_framebuffer(
    emu_automation_machine_t *machine,
    emu_automation_framebuffer_snapshot_t *out_snapshot)
{
    if (machine == NULL || out_snapshot == NULL) {
        return EMU_AUTOMATION_INVALID_ARGUMENT;
    }
    if (machine->adapter.capture_framebuffer == NULL ||
        !has_capability(machine, EMU_AUTOMATION_CAP_SCREEN_FRAMEBUFFER)) {
        return EMU_AUTOMATION_UNSUPPORTED;
    }
    memset(out_snapshot, 0, sizeof(*out_snapshot));
    out_snapshot->struct_size = (uint32_t)sizeof(*out_snapshot);
    out_snapshot->struct_version = EMU_AUTOMATION_STRUCT_VERSION;
    out_snapshot->frame.struct_size = (uint32_t)sizeof(out_snapshot->frame);
    out_snapshot->frame.struct_version = EMU_AUTOMATION_STRUCT_VERSION;
    return machine->adapter.capture_framebuffer(machine->adapter.context, out_snapshot);
}

void emu_automation_framebuffer_release(
    emu_automation_machine_t *machine,
    emu_automation_framebuffer_snapshot_t *snapshot)
{
    if (machine == NULL || snapshot == NULL) {
        return;
    }
    if (machine->adapter.release_framebuffer != NULL) {
        machine->adapter.release_framebuffer(machine->adapter.context, snapshot);
    }
    memset(snapshot, 0, sizeof(*snapshot));
}

emu_automation_result_t emu_automation_screen_text_grid(
    emu_automation_machine_t *machine,
    const char *region_id,
    emu_automation_text_grid_snapshot_t *out_snapshot)
{
    if (machine == NULL || out_snapshot == NULL) {
        return EMU_AUTOMATION_INVALID_ARGUMENT;
    }
    if (machine->adapter.capture_text_grid == NULL ||
        !has_capability(machine, EMU_AUTOMATION_CAP_SCREEN_TEXT_GRID)) {
        return EMU_AUTOMATION_UNSUPPORTED;
    }
    memset(out_snapshot, 0, sizeof(*out_snapshot));
    out_snapshot->struct_size = (uint32_t)sizeof(*out_snapshot);
    out_snapshot->struct_version = EMU_AUTOMATION_STRUCT_VERSION;
    out_snapshot->frame.struct_size = (uint32_t)sizeof(out_snapshot->frame);
    out_snapshot->frame.struct_version = EMU_AUTOMATION_STRUCT_VERSION;
    return machine->adapter.capture_text_grid(
        machine->adapter.context,
        region_id,
        out_snapshot);
}

emu_automation_result_t emu_automation_screen_text_view_count(
    emu_automation_machine_t *machine,
    size_t *out_count)
{
    if (machine == NULL || out_count == NULL) {
        return EMU_AUTOMATION_INVALID_ARGUMENT;
    }
    *out_count = 0u;
    if (machine->adapter.text_grid_view_count == NULL ||
        !has_capability(machine, EMU_AUTOMATION_CAP_SCREEN_TEXT_GRID)) {
        return EMU_AUTOMATION_UNSUPPORTED;
    }
    return machine->adapter.text_grid_view_count(machine->adapter.context, out_count);
}

emu_automation_result_t emu_automation_screen_text_view_descriptor(
    emu_automation_machine_t *machine,
    size_t index,
    emu_automation_text_view_descriptor_t *out_descriptor)
{
    if (machine == NULL || out_descriptor == NULL) {
        return EMU_AUTOMATION_INVALID_ARGUMENT;
    }
    if (machine->adapter.text_grid_view_descriptor == NULL ||
        !has_capability(machine, EMU_AUTOMATION_CAP_SCREEN_TEXT_GRID)) {
        return EMU_AUTOMATION_UNSUPPORTED;
    }
    memset(out_descriptor, 0, sizeof(*out_descriptor));
    out_descriptor->struct_size = (uint32_t)sizeof(*out_descriptor);
    out_descriptor->struct_version = EMU_AUTOMATION_STRUCT_VERSION;
    return machine->adapter.text_grid_view_descriptor(
        machine->adapter.context,
        index,
        out_descriptor);
}

void emu_automation_text_grid_release(
    emu_automation_machine_t *machine,
    emu_automation_text_grid_snapshot_t *snapshot)
{
    if (machine == NULL || snapshot == NULL) {
        return;
    }
    if (machine->adapter.release_text_grid != NULL) {
        machine->adapter.release_text_grid(machine->adapter.context, snapshot);
    }
    memset(snapshot, 0, sizeof(*snapshot));
}

emu_automation_result_t emu_automation_input_key(
    emu_automation_machine_t *machine,
    const emu_automation_key_event_t *event)
{
    if (machine == NULL || event == NULL || event->key_id == NULL) {
        return EMU_AUTOMATION_INVALID_ARGUMENT;
    }
    if (event->action != EMU_AUTOMATION_INPUT_PRESS &&
        event->action != EMU_AUTOMATION_INPUT_RELEASE) {
        return EMU_AUTOMATION_INVALID_ARGUMENT;
    }
    if (machine->adapter.submit_key == NULL ||
        !has_capability(machine, EMU_AUTOMATION_CAP_INPUT_KEYBOARD)) {
        return EMU_AUTOMATION_UNSUPPORTED;
    }
    return machine->adapter.submit_key(machine->adapter.context, event);
}

emu_automation_result_t emu_automation_input_controller_button(
    emu_automation_machine_t *machine,
    const emu_automation_controller_button_event_t *event)
{
    if (machine == NULL || event == NULL || event->control_id == NULL) {
        return EMU_AUTOMATION_INVALID_ARGUMENT;
    }
    if (event->action != EMU_AUTOMATION_INPUT_PRESS &&
        event->action != EMU_AUTOMATION_INPUT_RELEASE) {
        return EMU_AUTOMATION_INVALID_ARGUMENT;
    }
    if (machine->adapter.submit_controller_button == NULL ||
        !has_capability(machine, EMU_AUTOMATION_CAP_INPUT_CONTROLLER)) {
        return EMU_AUTOMATION_UNSUPPORTED;
    }
    return machine->adapter.submit_controller_button(machine->adapter.context, event);
}
