#include "emu_automation_adapter.h"

#include <stddef.h>
#include <stdlib.h>
#include <string.h>

struct emu_automation_machine {
    emu_automation_adapter_t adapter;
    struct emu_automation_subscription *subscriptions;
};

struct emu_automation_subscription {
    emu_automation_machine_t *machine;
    emu_automation_event_type_t event_type;
    uint64_t after_sequence;
    emu_automation_event_callback_t callback;
    void *user_data;
    uint8_t dispatch_active;
    struct emu_automation_subscription *next;
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

static void init_frame_metadata(emu_automation_frame_metadata_t *frame)
{
    memset(frame, 0, sizeof(*frame));
    frame->struct_size = (uint32_t)sizeof(*frame);
    frame->struct_version = EMU_AUTOMATION_STRUCT_VERSION;
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
    if (adapter->struct_size < offsetof(emu_automation_adapter_t, describe) ||
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

    memset(&machine->adapter, 0, sizeof(machine->adapter));
    memcpy(
        &machine->adapter,
        adapter,
        adapter->struct_size < sizeof(machine->adapter)
            ? adapter->struct_size
            : sizeof(machine->adapter));
    *out_machine = machine;
    return EMU_AUTOMATION_OK;
}

void emu_automation_machine_destroy(emu_automation_machine_t *machine)
{
    struct emu_automation_subscription *subscription;
    struct emu_automation_subscription *next;
    if (machine == NULL) {
        return;
    }
    subscription = machine->subscriptions;
    while (subscription != NULL) {
        next = subscription->next;
        subscription->machine = NULL;
        subscription->next = NULL;
        subscription = next;
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

emu_automation_result_t emu_automation_machine_character_mapping_count(
    emu_automation_machine_t *machine,
    size_t *out_count)
{
    if (machine == NULL || out_count == NULL) {
        return EMU_AUTOMATION_INVALID_ARGUMENT;
    }
    *out_count = 0u;
    if (machine->adapter.character_mapping_count == NULL) {
        return EMU_AUTOMATION_UNSUPPORTED;
    }
    return machine->adapter.character_mapping_count(machine->adapter.context, out_count);
}

emu_automation_result_t emu_automation_machine_character_mapping_descriptor(
    emu_automation_machine_t *machine,
    size_t index,
    emu_automation_character_mapping_descriptor_t *out_descriptor)
{
    if (machine == NULL || out_descriptor == NULL) {
        return EMU_AUTOMATION_INVALID_ARGUMENT;
    }
    if (machine->adapter.character_mapping_descriptor == NULL) {
        return EMU_AUTOMATION_UNSUPPORTED;
    }
    memset(out_descriptor, 0, sizeof(*out_descriptor));
    out_descriptor->struct_size = (uint32_t)sizeof(*out_descriptor);
    out_descriptor->struct_version = EMU_AUTOMATION_STRUCT_VERSION;
    return machine->adapter.character_mapping_descriptor(
        machine->adapter.context,
        index,
        out_descriptor);
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

emu_automation_result_t emu_automation_memory_read(
    emu_automation_machine_t *machine,
    uint64_t address,
    uint8_t *out_bytes,
    size_t size)
{
    if (machine == NULL || out_bytes == NULL) {
        return EMU_AUTOMATION_INVALID_ARGUMENT;
    }
    if (size == 0u) {
        return EMU_AUTOMATION_OK;
    }
    if (machine->adapter.read_memory == NULL ||
        !has_capability(machine, EMU_AUTOMATION_CAP_INSPECT_MEMORY)) {
        return EMU_AUTOMATION_UNSUPPORTED;
    }
    return machine->adapter.read_memory(machine->adapter.context, address, out_bytes, size);
}

emu_automation_result_t emu_automation_memory_write(
    emu_automation_machine_t *machine,
    uint64_t address,
    const uint8_t *bytes,
    size_t size)
{
    if (machine == NULL || bytes == NULL) {
        return EMU_AUTOMATION_INVALID_ARGUMENT;
    }
    if (size == 0u) {
        return EMU_AUTOMATION_OK;
    }
    if (machine->adapter.write_memory == NULL ||
        !has_capability(machine, EMU_AUTOMATION_CAP_INSPECT_MEMORY_WRITE)) {
        return EMU_AUTOMATION_UNSUPPORTED;
    }
    return machine->adapter.write_memory(machine->adapter.context, address, bytes, size);
}

emu_automation_result_t emu_automation_execution_program_counter(
    emu_automation_machine_t *machine,
    uint64_t *out_program_counter)
{
    if (machine == NULL || out_program_counter == NULL) {
        return EMU_AUTOMATION_INVALID_ARGUMENT;
    }
    *out_program_counter = 0u;
    if (machine->adapter.read_program_counter == NULL ||
        !has_capability(machine, EMU_AUTOMATION_CAP_EXEC_PROGRAM_COUNTER)) {
        return EMU_AUTOMATION_UNSUPPORTED;
    }
    return machine->adapter.read_program_counter(machine->adapter.context, out_program_counter);
}

emu_automation_result_t emu_automation_execution_frame_metadata(
    emu_automation_machine_t *machine,
    emu_automation_frame_metadata_t *out_metadata)
{
    if (machine == NULL || out_metadata == NULL) {
        return EMU_AUTOMATION_INVALID_ARGUMENT;
    }
    init_frame_metadata(out_metadata);
    if (machine->adapter.read_frame_metadata == NULL ||
        !has_capability(machine, EMU_AUTOMATION_CAP_EXEC_TIMING)) {
        return EMU_AUTOMATION_UNSUPPORTED;
    }
    return machine->adapter.read_frame_metadata(machine->adapter.context, out_metadata);
}

emu_automation_result_t emu_automation_execution_current_instruction(
    emu_automation_machine_t *machine,
    emu_automation_instruction_t *out_instruction)
{
    if (machine == NULL || out_instruction == NULL) {
        return EMU_AUTOMATION_INVALID_ARGUMENT;
    }
    memset(out_instruction, 0, sizeof(*out_instruction));
    out_instruction->struct_size = (uint32_t)sizeof(*out_instruction);
    out_instruction->struct_version = EMU_AUTOMATION_STRUCT_VERSION;
    if (machine->adapter.read_current_instruction == NULL ||
        !has_capability(machine, EMU_AUTOMATION_CAP_EXEC_CURRENT_INSTRUCTION)) {
        return EMU_AUTOMATION_UNSUPPORTED;
    }
    return machine->adapter.read_current_instruction(machine->adapter.context, out_instruction);
}

emu_automation_result_t emu_automation_register_count(
    emu_automation_machine_t *machine,
    size_t *out_count)
{
    if (machine == NULL || out_count == NULL) {
        return EMU_AUTOMATION_INVALID_ARGUMENT;
    }
    *out_count = 0u;
    if (machine->adapter.register_count == NULL ||
        !has_capability(machine, EMU_AUTOMATION_CAP_INSPECT_REGISTERS)) {
        return EMU_AUTOMATION_UNSUPPORTED;
    }
    return machine->adapter.register_count(machine->adapter.context, out_count);
}

emu_automation_result_t emu_automation_register_read(
    emu_automation_machine_t *machine,
    emu_automation_register_value_t *out_registers,
    size_t register_capacity,
    size_t *out_register_count)
{
    size_t i;
    if (machine == NULL || out_register_count == NULL) {
        return EMU_AUTOMATION_INVALID_ARGUMENT;
    }
    *out_register_count = 0u;
    if (register_capacity > 0u && out_registers == NULL) {
        return EMU_AUTOMATION_INVALID_ARGUMENT;
    }
    if (machine->adapter.read_registers == NULL ||
        !has_capability(machine, EMU_AUTOMATION_CAP_INSPECT_REGISTERS)) {
        return EMU_AUTOMATION_UNSUPPORTED;
    }
    for (i = 0u; i < register_capacity; ++i) {
        memset(&out_registers[i], 0, sizeof(out_registers[i]));
        out_registers[i].struct_size = (uint32_t)sizeof(out_registers[i]);
        out_registers[i].struct_version = EMU_AUTOMATION_STRUCT_VERSION;
    }
    return machine->adapter.read_registers(
        machine->adapter.context,
        out_registers,
        register_capacity,
        out_register_count);
}

emu_automation_result_t emu_automation_register_write(
    emu_automation_machine_t *machine,
    const char *register_name,
    uint64_t value)
{
    if (machine == NULL || register_name == NULL || register_name[0] == '\0') {
        return EMU_AUTOMATION_INVALID_ARGUMENT;
    }
    if (machine->adapter.write_register == NULL ||
        !has_capability(machine, EMU_AUTOMATION_CAP_INSPECT_REGISTERS)) {
        return EMU_AUTOMATION_UNSUPPORTED;
    }
    return machine->adapter.write_register(machine->adapter.context, register_name, value);
}

emu_automation_result_t emu_automation_breakpoint_set(
    emu_automation_machine_t *machine,
    uint64_t address,
    uint8_t enabled)
{
    if (machine == NULL) {
        return EMU_AUTOMATION_INVALID_ARGUMENT;
    }
    if (enabled > 1u) {
        return EMU_AUTOMATION_INVALID_ARGUMENT;
    }
    if (machine->adapter.set_breakpoint == NULL ||
        !has_capability(machine, EMU_AUTOMATION_CAP_DEBUG_BREAKPOINTS)) {
        return EMU_AUTOMATION_UNSUPPORTED;
    }
    return machine->adapter.set_breakpoint(machine->adapter.context, address, enabled);
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

emu_automation_result_t emu_automation_events_poll(
    emu_automation_machine_t *machine,
    uint64_t after_sequence,
    emu_automation_event_t *out_event)
{
    if (machine == NULL || out_event == NULL) {
        return EMU_AUTOMATION_INVALID_ARGUMENT;
    }
    if (machine->adapter.poll_event == NULL) {
        return EMU_AUTOMATION_UNSUPPORTED;
    }
    memset(out_event, 0, sizeof(*out_event));
    out_event->struct_size = (uint32_t)sizeof(*out_event);
    out_event->struct_version = EMU_AUTOMATION_STRUCT_VERSION;
    init_frame_metadata(&out_event->frame);
    init_frame_metadata(&out_event->input_accepted);
    init_frame_metadata(&out_event->input_applied);
    return machine->adapter.poll_event(machine->adapter.context, after_sequence, out_event);
}

emu_automation_result_t emu_automation_events_dispatch_available(
    emu_automation_machine_t *machine,
    uint64_t *inout_after_sequence,
    size_t max_events,
    emu_automation_event_callback_t callback,
    void *user_data,
    size_t *out_dispatch_count)
{
    emu_automation_event_t event;
    uint64_t after_sequence;
    size_t count = 0u;
    emu_automation_result_t result;

    if (machine == NULL || inout_after_sequence == NULL || callback == NULL) {
        return EMU_AUTOMATION_INVALID_ARGUMENT;
    }

    after_sequence = *inout_after_sequence;
    while (max_events == 0u || count < max_events) {
        memset(&event, 0, sizeof(event));
        result = emu_automation_events_poll(machine, after_sequence, &event);
        if (result == EMU_AUTOMATION_TIMEOUT) {
            break;
        }
        if (result != EMU_AUTOMATION_OK) {
            if (out_dispatch_count != NULL) {
                *out_dispatch_count = count;
            }
            return result;
        }
        callback(&event, user_data);
        after_sequence = event.sequence_number;
        count += 1u;
        emu_automation_event_release(machine, &event);
    }

    *inout_after_sequence = after_sequence;
    if (out_dispatch_count != NULL) {
        *out_dispatch_count = count;
    }
    return EMU_AUTOMATION_OK;
}

emu_automation_result_t emu_automation_events_dispatch_matching(
    emu_automation_machine_t *machine,
    uint64_t *inout_after_sequence,
    emu_automation_event_type_t event_type,
    size_t max_events,
    emu_automation_event_callback_t callback,
    void *user_data,
    size_t *out_dispatch_count)
{
    emu_automation_event_t event;
    uint64_t after_sequence;
    size_t count = 0u;
    emu_automation_result_t result;

    if (machine == NULL || inout_after_sequence == NULL || callback == NULL) {
        return EMU_AUTOMATION_INVALID_ARGUMENT;
    }

    after_sequence = *inout_after_sequence;
    while (max_events == 0u || count < max_events) {
        memset(&event, 0, sizeof(event));
        result = emu_automation_events_poll(machine, after_sequence, &event);
        if (result == EMU_AUTOMATION_TIMEOUT) {
            break;
        }
        if (result != EMU_AUTOMATION_OK) {
            if (out_dispatch_count != NULL) {
                *out_dispatch_count = count;
            }
            return result;
        }
        after_sequence = event.sequence_number;
        if (event_type == EMU_AUTOMATION_EVENT_NONE || event.event_type == event_type) {
            callback(&event, user_data);
            count += 1u;
        }
        emu_automation_event_release(machine, &event);
    }

    *inout_after_sequence = after_sequence;
    if (out_dispatch_count != NULL) {
        *out_dispatch_count = count;
    }
    return EMU_AUTOMATION_OK;
}

emu_automation_result_t emu_automation_subscription_create(
    emu_automation_machine_t *machine,
    emu_automation_event_type_t event_type,
    uint64_t after_sequence,
    emu_automation_event_callback_t callback,
    void *user_data,
    emu_automation_subscription_t **out_subscription)
{
    emu_automation_subscription_t *subscription;
    if (machine == NULL || callback == NULL || out_subscription == NULL) {
        return EMU_AUTOMATION_INVALID_ARGUMENT;
    }
    subscription = (emu_automation_subscription_t *)calloc(1u, sizeof(*subscription));
    if (subscription == NULL) {
        return EMU_AUTOMATION_INTERNAL_ERROR;
    }
    subscription->machine = machine;
    subscription->event_type = event_type;
    subscription->after_sequence = after_sequence;
    subscription->callback = callback;
    subscription->user_data = user_data;
    subscription->next = machine->subscriptions;
    machine->subscriptions = subscription;
    *out_subscription = subscription;
    return EMU_AUTOMATION_OK;
}

emu_automation_result_t emu_automation_subscription_dispatch_available(
    emu_automation_subscription_t *subscription,
    size_t max_events,
    size_t *out_dispatch_count)
{
    if (subscription == NULL || subscription->callback == NULL) {
        return EMU_AUTOMATION_INVALID_ARGUMENT;
    }
    if (subscription->machine == NULL) {
        if (out_dispatch_count != NULL) {
            *out_dispatch_count = 0u;
        }
        return EMU_AUTOMATION_INVALID_STATE;
    }
    if (subscription->dispatch_active != 0u) {
        if (out_dispatch_count != NULL) {
            *out_dispatch_count = 0u;
        }
        return EMU_AUTOMATION_INVALID_STATE;
    }
    subscription->dispatch_active = 1u;
    {
        emu_automation_result_t result = emu_automation_events_dispatch_matching(
            subscription->machine,
            &subscription->after_sequence,
            subscription->event_type,
            max_events,
            subscription->callback,
            subscription->user_data,
            out_dispatch_count);
        subscription->dispatch_active = 0u;
        return result;
    }
}

uint64_t emu_automation_subscription_after_sequence(
    const emu_automation_subscription_t *subscription)
{
    if (subscription == NULL) {
        return 0u;
    }
    return subscription->after_sequence;
}

emu_automation_result_t emu_automation_subscription_set_after_sequence(
    emu_automation_subscription_t *subscription,
    uint64_t after_sequence)
{
    if (subscription == NULL) {
        return EMU_AUTOMATION_INVALID_ARGUMENT;
    }
    subscription->after_sequence = after_sequence;
    return EMU_AUTOMATION_OK;
}

void emu_automation_subscription_destroy(emu_automation_subscription_t *subscription)
{
    emu_automation_machine_t *machine;
    emu_automation_subscription_t **link;
    if (subscription == NULL) {
        return;
    }
    machine = subscription->machine;
    if (machine != NULL) {
        link = &machine->subscriptions;
        while (*link != NULL) {
            if (*link == subscription) {
                *link = subscription->next;
                break;
            }
            link = &(*link)->next;
        }
    }
    free(subscription);
}

void emu_automation_event_release(
    emu_automation_machine_t *machine,
    emu_automation_event_t *event)
{
    if (machine == NULL || event == NULL) {
        return;
    }
    if (machine->adapter.release_event != NULL) {
        machine->adapter.release_event(machine->adapter.context, event);
    }
    memset(event, 0, sizeof(*event));
}
