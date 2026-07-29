#ifndef EMU_AUTOMATION_ADAPTER_H
#define EMU_AUTOMATION_ADAPTER_H

#include "emu_automation.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct emu_automation_adapter {
    uint32_t struct_size;
    uint32_t struct_version;
    void *context;
    void (*destroy_context)(void *context);

    emu_automation_result_t (*describe)(
        void *context,
        emu_automation_machine_descriptor_t *out_descriptor);
    emu_automation_result_t (*capabilities)(
        void *context,
        emu_automation_capabilities_t *out_capabilities);
    emu_automation_result_t (*character_mapping_count)(
        void *context,
        size_t *out_count);
    emu_automation_result_t (*character_mapping_descriptor)(
        void *context,
        size_t index,
        emu_automation_character_mapping_descriptor_t *out_descriptor);

    emu_automation_result_t (*pause)(void *context);
    emu_automation_result_t (*resume)(void *context);
    emu_automation_result_t (*reset)(void *context, emu_automation_reset_kind_t kind);
    emu_automation_result_t (*step_frame)(void *context);
    emu_automation_result_t (*run_frames)(void *context, uint64_t frame_count);

    emu_automation_result_t (*capture_framebuffer)(
        void *context,
        emu_automation_framebuffer_snapshot_t *out_snapshot);
    void (*release_framebuffer)(
        void *context,
        emu_automation_framebuffer_snapshot_t *snapshot);

    emu_automation_result_t (*capture_text_grid)(
        void *context,
        const char *region_id,
        emu_automation_text_grid_snapshot_t *out_snapshot);
    emu_automation_result_t (*read_memory)(
        void *context,
        uint64_t address,
        uint8_t *out_bytes,
        size_t size);
    emu_automation_result_t (*write_memory)(
        void *context,
        uint64_t address,
        const uint8_t *bytes,
        size_t size);
    emu_automation_result_t (*read_program_counter)(
        void *context,
        uint64_t *out_program_counter);
    emu_automation_result_t (*read_frame_metadata)(
        void *context,
        emu_automation_frame_metadata_t *out_metadata);
    emu_automation_result_t (*read_current_instruction)(
        void *context,
        emu_automation_instruction_t *out_instruction);
    emu_automation_result_t (*register_count)(
        void *context,
        size_t *out_count);
    emu_automation_result_t (*read_registers)(
        void *context,
        emu_automation_register_value_t *out_registers,
        size_t register_capacity,
        size_t *out_register_count);
    emu_automation_result_t (*write_register)(
        void *context,
        const char *register_name,
        uint64_t value);
    emu_automation_result_t (*set_breakpoint)(
        void *context,
        uint64_t address,
        uint8_t enabled);
    emu_automation_result_t (*text_grid_view_count)(
        void *context,
        size_t *out_count);
    emu_automation_result_t (*text_grid_view_descriptor)(
        void *context,
        size_t index,
        emu_automation_text_view_descriptor_t *out_descriptor);
    void (*release_text_grid)(
        void *context,
        emu_automation_text_grid_snapshot_t *snapshot);

    emu_automation_result_t (*submit_key)(
        void *context,
        const emu_automation_key_event_t *event);
    emu_automation_result_t (*submit_controller_button)(
        void *context,
        const emu_automation_controller_button_event_t *event);
    emu_automation_result_t (*poll_event)(
        void *context,
        uint64_t after_sequence,
        emu_automation_event_t *out_event);
    void (*release_event)(
        void *context,
        emu_automation_event_t *event);
} emu_automation_adapter_t;

emu_automation_result_t emu_automation_attach_adapter(
    const emu_automation_adapter_t *adapter,
    emu_automation_machine_t **out_machine);

#ifdef __cplusplus
}
#endif

#endif
