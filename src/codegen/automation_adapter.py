"""Generate the emulator automation adapter bridge."""

from __future__ import annotations

from typing import Any, Dict


def _escape_c_string(value: object) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def _automation_text_views(isa_data: Dict[str, Any]) -> list[dict[str, Any]]:
    automation = (isa_data.get("system", {}) or {}).get("automation", {}) or {}
    screen = automation.get("screen", {}) or {}
    views = screen.get("text_views", []) or []
    return [view for view in views if isinstance(view, dict)]


def _automation_framebuffer(isa_data: Dict[str, Any]) -> dict[str, Any] | None:
    automation = (isa_data.get("system", {}) or {}).get("automation", {}) or {}
    screen = automation.get("screen", {}) or {}
    framebuffer = screen.get("framebuffer", {}) or {}
    if not isinstance(framebuffer, dict):
        return None
    if not str(framebuffer.get("source_component", "")).strip():
        return None
    if not (
        str(framebuffer.get("source_handler", "")).strip()
        or str(framebuffer.get("source_signal", "")).strip()
    ):
        return None
    if int(framebuffer.get("width", 0) or 0) <= 0 or int(framebuffer.get("height", 0) or 0) <= 0:
        return None
    return framebuffer


def _first_supported_text_view(isa_data: Dict[str, Any]) -> dict[str, Any] | None:
    for view in _automation_text_views(isa_data):
        memory = view.get("memory", {}) or {}
        source = str(memory.get("source", "")).strip()
        if source not in {"system_memory", "component_memory", "callback"}:
            continue
        if source in {"component_memory", "callback"}:
            if not str(memory.get("component", "")).strip():
                continue
            if not str(memory.get("read_callback", "")).strip():
                continue
        layout = str(memory.get("address_layout", "linear")).strip()
        if layout not in {"linear", "bit_interleaved_rows", "tile_name_table"}:
            continue
        return view
    return None


def _c_text_view_table(text_views: list[dict[str, Any]]) -> tuple[bool, str]:
    rows: list[str] = []
    for view in text_views:
        memory = view.get("memory", {}) or {}
        source = str(memory.get("source", "")).strip()
        if source not in {"system_memory", "component_memory", "callback"}:
            continue
        if source in {"component_memory", "callback"}:
            if not str(memory.get("component", "")).strip():
                continue
            if not str(memory.get("read_callback", "")).strip():
                continue
        layout = str(memory.get("address_layout", "linear")).strip()
        if layout not in {"linear", "bit_interleaved_rows", "tile_name_table"}:
            continue
        if layout == "bit_interleaved_rows":
            layout_id = "PASM_AUTOMATION_TEXT_LAYOUT_BIT_INTERLEAVED_ROWS"
        elif layout == "tile_name_table":
            layout_id = "PASM_AUTOMATION_TEXT_LAYOUT_TILE_NAME_TABLE"
        else:
            layout_id = "PASM_AUTOMATION_TEXT_LAYOUT_LINEAR"
        if source == "component_memory":
            source_id = "PASM_AUTOMATION_TEXT_SOURCE_COMPONENT_MEMORY"
        elif source == "callback":
            source_id = "PASM_AUTOMATION_TEXT_SOURCE_CALLBACK"
        else:
            source_id = "PASM_AUTOMATION_TEXT_SOURCE_SYSTEM_MEMORY"
        callback_offset_mode = str(memory.get("callback_offset_mode", "address")).strip()
        if callback_offset_mode == "cell_index":
            callback_offset_mode_id = "PASM_AUTOMATION_TEXT_CALLBACK_OFFSET_CELL_INDEX"
        else:
            callback_offset_mode_id = "PASM_AUTOMATION_TEXT_CALLBACK_OFFSET_ADDRESS"
        row_stride = int(view.get("row_stride", view.get("columns", 1)))
        column_multiplier = int(memory.get("column_multiplier", 1))
        rows.append(
            "    { "
            f"\"{_escape_c_string(view.get('id', 'text'))}\", "
            f"(uint32_t){int(view.get('columns', 1))}u, "
            f"(uint32_t){int(view.get('rows', 1))}u, "
            f"(uint32_t){row_stride}u, "
            f"(uint64_t){int(memory.get('base', 0))}ull, "
            f"(uint64_t){int(memory.get('alternate_base', memory.get('base', 0)))}ull, "
            f"{source_id}, "
            f"{layout_id}, "
            f"(uint32_t){int(memory.get('row_low_mask', 0))}u, "
            f"(uint32_t){int(memory.get('row_low_shift', 0))}u, "
            f"(uint32_t){int(memory.get('row_high_shift', 0))}u, "
            f"(uint32_t){int(memory.get('row_high_multiplier', 0))}u, "
            f"(uint32_t){column_multiplier}u, "
            f"{callback_offset_mode_id}, "
            f"\"{_escape_c_string(memory.get('component', ''))}\", "
            f"\"{_escape_c_string(memory.get('read_callback', ''))}\", "
            f"\"{_escape_c_string(view.get('charset', ''))}\", "
            f"\"{_escape_c_string(view.get('native_encoding', ''))}\", "
            f"\"{_escape_c_string(view.get('unicode_map', ''))}\" "
            "}"
        )
    if not rows:
        return False, ""
    return True, ",\n".join(rows)


def generate_automation_adapter(isa_data: Dict[str, Any], cpu_name: str) -> tuple[str, str]:
    """Generate C sources that adapt the debug ABI to the automation ABI."""

    cpu_prefix = cpu_name.lower()
    guard = f"{cpu_name.upper()}_AUTOMATION_ADAPTER_H"
    memory_default_size = int(isa_data.get("memory", {}).get("default_size", 65536))
    system_name = _escape_c_string(
        isa_data.get("system", {}).get("metadata", {}).get("name", "system")
    )
    framebuffer = _automation_framebuffer(isa_data)
    default_text_view = _first_supported_text_view(isa_data)
    supports_text_grid, text_view_rows = _c_text_view_table(_automation_text_views(isa_data))
    text_event_context_fields = ""
    if default_text_view is not None:
        default_text_cell_count = int(default_text_view.get("columns", 1)) * int(
            default_text_view.get("rows", 1)
        )
        text_event_context_fields = (
            f"\n    uint8_t last_text_cells[{default_text_cell_count}u];"
            "\n    uint8_t last_text_cells_valid;"
        )
    text_grid_capability = "\n        EMU_AUTOMATION_CAP_SCREEN_TEXT_GRID |" if supports_text_grid else ""
    framebuffer_capability = (
        "\n        EMU_AUTOMATION_CAP_SCREEN_FRAMEBUFFER |" if framebuffer is not None else ""
    )
    event_capability = "\n        EMU_AUTOMATION_CAP_EVENTS_FRAME_COMPLETED |"
    framebuffer_adapter_members = (
        f"\n    adapter.capture_framebuffer = {cpu_prefix}_automation_capture_framebuffer;"
        f"\n    adapter.release_framebuffer = {cpu_prefix}_automation_release_framebuffer;"
        if framebuffer is not None
        else ""
    )
    text_grid_adapter_members = (
        f"\n    adapter.capture_text_grid = {cpu_prefix}_automation_capture_text_grid;"
        f"\n    adapter.read_memory = {cpu_prefix}_automation_read_memory;"
        f"\n    adapter.text_grid_view_count = {cpu_prefix}_automation_text_grid_view_count;"
        f"\n    adapter.text_grid_view_descriptor = {cpu_prefix}_automation_text_grid_view_descriptor;"
        f"\n    adapter.release_text_grid = {cpu_prefix}_automation_release_text_grid;"
        if supports_text_grid
        else ""
    )
    event_adapter_members = (
        f"\n    adapter.poll_event = {cpu_prefix}_automation_poll_event;"
        f"\n    adapter.release_event = {cpu_prefix}_automation_release_event;"
    )
    framebuffer_impl = (
        _generate_framebuffer_impl(cpu_name, cpu_prefix) if framebuffer is not None else ""
    )
    framebuffer_frame_counter_decl = (
        f"""
static int {cpu_prefix}_automation_framebuffer_frame_number(
    {cpu_name}AutomationDebugContext *ctx,
    uint64_t *out_frame_number)
{{
    PASMDebugFramebuffer framebuffer;
    if (ctx == NULL || ctx->cpu == NULL || out_frame_number == NULL) return -1;
    memset(&framebuffer, 0, sizeof(framebuffer));
    if (pasm_dbg_capture_framebuffer(ctx->cpu, &framebuffer) != 0) return -1;
    *out_frame_number = framebuffer.frame_number;
    pasm_dbg_release_framebuffer(ctx->cpu, &framebuffer);
    return 0;
}}
"""
        if framebuffer is not None
        else ""
    )
    framebuffer_frame_before_line = (
        f"    if ({cpu_prefix}_automation_framebuffer_frame_number(ctx, &before_fb_frame) == 0) have_before_fb_frame = 1u;"
        if framebuffer is not None
        else ""
    )
    framebuffer_frame_after_block = (
        f"""        if ({cpu_prefix}_automation_framebuffer_frame_number(ctx, &after_fb_frame) == 0 &&
            (have_before_fb_frame == 0u || after_fb_frame > before_fb_frame)) {{
            {cpu_prefix}_automation_emit_screen_events(ctx);
            {cpu_prefix}_automation_push_event(
                ctx,
                EMU_AUTOMATION_EVENT_FRAME_COMPLETED,
                0,
                0,
                NULL,
                0u, 0u, 0u, 0u, 0u,
                NULL, 0u, NULL);
            (void)pasm_dbg_pause(ctx->cpu);
            return EMU_AUTOMATION_OK;
        }}
"""
        if framebuffer is not None
        else ""
    )
    frame_index_completion_block = (
        f"""        if (after.frame_index > before.frame_index) {{
            {cpu_prefix}_automation_emit_screen_events(ctx);
            {cpu_prefix}_automation_push_event(
                ctx,
                EMU_AUTOMATION_EVENT_FRAME_COMPLETED,
                0,
                0,
                NULL,
                0u, 0u, 0u, 0u, 0u,
                NULL, 0u, NULL);
            (void)pasm_dbg_pause(ctx->cpu);
            return EMU_AUTOMATION_OK;
        }}
"""
        if framebuffer is None
        else ""
    )
    text_grid_impl = _generate_text_grid_impl(cpu_name, cpu_prefix, text_view_rows) if supports_text_grid else ""
    inspection_impl = _generate_inspection_impl(cpu_name, cpu_prefix)
    text_event_impl = (
        _generate_text_event_impl(cpu_name, cpu_prefix)
        if supports_text_grid
        else (
            f"""
static void {cpu_prefix}_automation_initialize_text_events(
    {cpu_name}AutomationDebugContext *ctx)
{{
    (void)ctx;
}}

static void {cpu_prefix}_automation_emit_screen_events(
    {cpu_name}AutomationDebugContext *ctx)
{{
    (void)ctx;
}}
"""
        )
    )

    header = f"""/*
 * Auto-generated automation adapter
 * Generated by PASM
 */

#ifndef {guard}
#define {guard}

#include <stddef.h>
#include "{cpu_name}_debug_abi.h"
#include "emu_automation_adapter.h"

#ifdef __cplusplus
extern "C" {{
#endif

emu_automation_result_t {cpu_prefix}_automation_attach_debug(
    CPUState *cpu,
    emu_automation_machine_t **out_machine);

emu_automation_result_t {cpu_prefix}_automation_create(
    size_t memory_size,
    emu_automation_machine_t **out_machine);

#ifdef __cplusplus
}}
#endif

#endif /* {guard} */
"""

    impl = f"""/*
 * Auto-generated automation adapter
 * Generated by PASM
 */

#include "{cpu_name}_automation_adapter.h"

#include <stdlib.h>
#include <string.h>

typedef struct {cpu_name}AutomationDebugContext {{
    CPUState *cpu;
    uint8_t owns_cpu;
    uint64_t next_sequence;
    uint64_t last_text_hash;
    uint8_t last_text_hash_valid;
{text_event_context_fields}
    emu_automation_event_t events[64];
    size_t event_count;
}} {cpu_name}AutomationDebugContext;

typedef struct {cpu_name}AutomationEventOwned {{
    emu_automation_text_delta_t *text_deltas;
    size_t text_delta_count;
}} {cpu_name}AutomationEventOwned;

static emu_automation_execution_state_t {cpu_prefix}_automation_map_mode(uint8_t mode);
static int {cpu_prefix}_automation_core_snapshot(
    CPUState *cpu,
    PASMDebugSnapshotCore *out_core);
static void {cpu_prefix}_automation_initialize_text_events(
    {cpu_name}AutomationDebugContext *ctx);
static void {cpu_prefix}_automation_emit_screen_events(
    {cpu_name}AutomationDebugContext *ctx);
static void {cpu_prefix}_automation_release_event_owned(
    {cpu_name}AutomationEventOwned *owned);
static emu_automation_result_t {cpu_prefix}_automation_character_mapping_count(
    void *context,
    size_t *out_count);
static emu_automation_result_t {cpu_prefix}_automation_character_mapping_descriptor(
    void *context,
    size_t index,
    emu_automation_character_mapping_descriptor_t *out_descriptor);
static emu_automation_result_t {cpu_prefix}_automation_read_program_counter(
    void *context,
    uint64_t *out_program_counter);
static emu_automation_result_t {cpu_prefix}_automation_read_frame_metadata(
    void *context,
    emu_automation_frame_metadata_t *out_metadata);
static emu_automation_result_t {cpu_prefix}_automation_write_memory(
    void *context,
    uint64_t address,
    const uint8_t *bytes,
    size_t size);
static emu_automation_result_t {cpu_prefix}_automation_read_current_instruction(
    void *context,
    emu_automation_instruction_t *out_instruction);
static emu_automation_result_t {cpu_prefix}_automation_register_count(
    void *context,
    size_t *out_count);
static emu_automation_result_t {cpu_prefix}_automation_read_registers(
    void *context,
    emu_automation_register_value_t *out_registers,
    size_t register_capacity,
    size_t *out_register_count);
static emu_automation_result_t {cpu_prefix}_automation_write_register(
    void *context,
    const char *register_name,
    uint64_t value);
static emu_automation_result_t {cpu_prefix}_automation_set_breakpoint(
    void *context,
    uint64_t address,
    uint8_t enabled);
{f"""static int {cpu_prefix}_automation_framebuffer_frame_number(
    {cpu_name}AutomationDebugContext *ctx,
    uint64_t *out_frame_number);
""" if framebuffer is not None else ""}

static void {cpu_prefix}_automation_push_event(
    {cpu_name}AutomationDebugContext *ctx,
    emu_automation_event_type_t event_type,
    emu_automation_execution_state_t previous_execution_state,
    emu_automation_execution_state_t current_execution_state,
    const char *region_id,
    uint32_t change_x,
    uint32_t change_y,
    uint32_t change_width,
    uint32_t change_height,
    uint32_t change_cell_count,
    emu_automation_text_delta_t *text_deltas,
    size_t text_delta_count,
    {cpu_name}AutomationEventOwned *owned_payload)
{{
    emu_automation_event_t *event;
    PASMDebugSnapshotCore core;
    if (ctx == NULL || ctx->event_count >= (sizeof(ctx->events) / sizeof(ctx->events[0]))) {{
        return;
    }}
    event = &ctx->events[ctx->event_count++];
    memset(event, 0, sizeof(*event));
    event->struct_size = (uint32_t)sizeof(*event);
    event->struct_version = EMU_AUTOMATION_STRUCT_VERSION;
    event->sequence_number = ++ctx->next_sequence;
    event->event_type = event_type;
    event->region_id = region_id;
    event->change_x = change_x;
    event->change_y = change_y;
    event->change_width = change_width;
    event->change_height = change_height;
    event->change_cell_count = change_cell_count;
    event->text_deltas = text_deltas;
    event->text_delta_count = text_delta_count;
    event->previous_execution_state = previous_execution_state;
    event->current_execution_state = current_execution_state;
    event->adapter_owned = owned_payload;
    event->frame.struct_size = (uint32_t)sizeof(event->frame);
    event->frame.struct_version = EMU_AUTOMATION_STRUCT_VERSION;
    event->input_accepted.struct_size = (uint32_t)sizeof(event->input_accepted);
    event->input_accepted.struct_version = EMU_AUTOMATION_STRUCT_VERSION;
    event->input_applied.struct_size = (uint32_t)sizeof(event->input_applied);
    event->input_applied.struct_version = EMU_AUTOMATION_STRUCT_VERSION;
    if ({cpu_prefix}_automation_core_snapshot(ctx->cpu, &core) == 0) {{
        event->frame.frame_number = core.frame_index;
        event->frame.emulated_cycles = core.total_cycles;
        event->frame.execution_state = {cpu_prefix}_automation_map_mode(core.mode);
        if (event_type == EMU_AUTOMATION_EVENT_INPUT_SUBMITTED) {{
            event->input_accepted.frame_number = core.frame_index;
            event->input_accepted.emulated_cycles = core.total_cycles;
            event->input_accepted.execution_state = {cpu_prefix}_automation_map_mode(core.mode);
            event->input_applied.frame_number = core.frame_index;
            event->input_applied.emulated_cycles = core.total_cycles;
            event->input_applied.execution_state = {cpu_prefix}_automation_map_mode(core.mode);
        }}
    }}
}}

static void {cpu_prefix}_automation_release_event_owned(
    {cpu_name}AutomationEventOwned *owned)
{{
    if (owned == NULL) return;
    free(owned->text_deltas);
    free(owned);
}}

static emu_automation_execution_state_t {cpu_prefix}_automation_map_mode(uint8_t mode)
{{
    switch (mode) {{
    case PASM_DBG_RUNNING: return EMU_AUTOMATION_EXECUTION_RUNNING;
    case PASM_DBG_PAUSED: return EMU_AUTOMATION_EXECUTION_PAUSED;
    case PASM_DBG_STEPPING: return EMU_AUTOMATION_EXECUTION_RUNNING;
    case PASM_DBG_EXITED: return EMU_AUTOMATION_EXECUTION_STOPPED;
    case PASM_DBG_ERROR: return EMU_AUTOMATION_EXECUTION_ERROR;
    default: return EMU_AUTOMATION_EXECUTION_ERROR;
    }}
}}

static int {cpu_prefix}_automation_core_snapshot(
    CPUState *cpu,
    PASMDebugSnapshotCore *out_core)
{{
    if (cpu == NULL || out_core == NULL) return -1;
    memset(out_core, 0, sizeof(*out_core));
    return pasm_dbg_snapshot_fill(
        cpu,
        out_core,
        NULL, 0u,
        NULL, 0u,
        NULL, 0u,
        NULL, 0u,
        NULL, 0u,
        NULL, 0u,
        NULL, 0u,
        NULL, 0u,
        NULL, 0u,
        NULL, 0u,
        NULL, 0u
    );
}}

static emu_automation_result_t {cpu_prefix}_automation_describe(
    void *context,
    emu_automation_machine_descriptor_t *out_descriptor)
{{
    {cpu_name}AutomationDebugContext *ctx = ({cpu_name}AutomationDebugContext *)context;
    PASMDebugSnapshotCore core;
    if (ctx == NULL || ctx->cpu == NULL || out_descriptor == NULL) {{
        return EMU_AUTOMATION_INVALID_ARGUMENT;
    }}
    if ({cpu_prefix}_automation_core_snapshot(ctx->cpu, &core) != 0) {{
        return EMU_AUTOMATION_ADAPTER_ERROR;
    }}
    out_descriptor->machine_id = "debug-abi";
    out_descriptor->system_id = pasm_dbg_system_name();
    out_descriptor->model_id = "{system_name}";
    out_descriptor->region = "";
    out_descriptor->video_standard = "";
    out_descriptor->adapter_version = "debug-abi-v1";
    out_descriptor->configured_memory_bytes = {memory_default_size}ull;
    out_descriptor->capabilities.feature_bits ={event_capability}{framebuffer_capability}{text_grid_capability}
        EMU_AUTOMATION_CAP_EXEC_TIMING |
        EMU_AUTOMATION_CAP_INSPECT_MEMORY |
        EMU_AUTOMATION_CAP_INSPECT_MEMORY_WRITE |
        EMU_AUTOMATION_CAP_INSPECT_REGISTERS |
        EMU_AUTOMATION_CAP_EXEC_PAUSE |
        EMU_AUTOMATION_CAP_EXEC_RESUME |
        EMU_AUTOMATION_CAP_EXEC_CURRENT_INSTRUCTION |
        EMU_AUTOMATION_CAP_EXEC_PROGRAM_COUNTER |
        EMU_AUTOMATION_CAP_DEBUG_BREAKPOINTS |
        EMU_AUTOMATION_CAP_EXEC_RESET |
        EMU_AUTOMATION_CAP_EXEC_STEP_FRAME |
        EMU_AUTOMATION_CAP_EXEC_RUN_FRAMES;
    (void)core;
    return EMU_AUTOMATION_OK;
}}

static emu_automation_result_t {cpu_prefix}_automation_capabilities(
    void *context,
    emu_automation_capabilities_t *out_capabilities)
{{
    emu_automation_machine_descriptor_t descriptor;
    memset(&descriptor, 0, sizeof(descriptor));
    descriptor.struct_size = (uint32_t)sizeof(descriptor);
    descriptor.struct_version = EMU_AUTOMATION_STRUCT_VERSION;
    descriptor.capabilities.struct_size = (uint32_t)sizeof(descriptor.capabilities);
    descriptor.capabilities.struct_version = EMU_AUTOMATION_STRUCT_VERSION;
    if ({cpu_prefix}_automation_describe(context, &descriptor) != EMU_AUTOMATION_OK) {{
        return EMU_AUTOMATION_ADAPTER_ERROR;
    }}
    out_capabilities->feature_bits = descriptor.capabilities.feature_bits;
    return EMU_AUTOMATION_OK;
}}

static emu_automation_result_t {cpu_prefix}_automation_character_mapping_count(
    void *context,
    size_t *out_count)
{{
    {cpu_name}AutomationDebugContext *ctx = ({cpu_name}AutomationDebugContext *)context;
    size_t count = 0u;
    if (ctx == NULL || out_count == NULL) {{
        return EMU_AUTOMATION_INVALID_ARGUMENT;
    }}
    if (pasm_dbg_character_mapping_count(ctx->cpu, &count) != 0) {{
        return EMU_AUTOMATION_UNSUPPORTED;
    }}
    *out_count = count;
    return EMU_AUTOMATION_OK;
}}

static emu_automation_result_t {cpu_prefix}_automation_character_mapping_descriptor(
    void *context,
    size_t index,
    emu_automation_character_mapping_descriptor_t *out_descriptor)
{{
    {cpu_name}AutomationDebugContext *ctx = ({cpu_name}AutomationDebugContext *)context;
    PASMDebugCharacterMapping mapping;
    if (ctx == NULL || out_descriptor == NULL) {{
        return EMU_AUTOMATION_INVALID_ARGUMENT;
    }}
    memset(&mapping, 0, sizeof(mapping));
    if (pasm_dbg_character_mapping_descriptor(ctx->cpu, index, &mapping) != 0) {{
        return EMU_AUTOMATION_INVALID_ARGUMENT;
    }}
    out_descriptor->device_id = mapping.device_id;
    out_descriptor->unicode_codepoint = mapping.unicode_codepoint;
    out_descriptor->native_code = mapping.native_code;
    out_descriptor->key_id = mapping.key_id;
    out_descriptor->required_modifier_bits = mapping.required_modifier_bits;
    out_descriptor->shift_key_id = mapping.shift_key_id;
    out_descriptor->ctrl_key_id = mapping.ctrl_key_id;
    out_descriptor->alt_key_id = mapping.alt_key_id;
    out_descriptor->meta_key_id = mapping.meta_key_id;
    return EMU_AUTOMATION_OK;
}}

static emu_automation_result_t {cpu_prefix}_automation_pause(void *context)
{{
    {cpu_name}AutomationDebugContext *ctx = ({cpu_name}AutomationDebugContext *)context;
    PASMDebugSnapshotCore before;
    if (ctx == NULL || ctx->cpu == NULL) return EMU_AUTOMATION_INVALID_ARGUMENT;
    if ({cpu_prefix}_automation_core_snapshot(ctx->cpu, &before) != 0) return EMU_AUTOMATION_ADAPTER_ERROR;
    if (pasm_dbg_pause(ctx->cpu) != 0) return EMU_AUTOMATION_ADAPTER_ERROR;
    {cpu_prefix}_automation_push_event(
        ctx,
        EMU_AUTOMATION_EVENT_EXECUTION_STATE_CHANGED,
        {cpu_prefix}_automation_map_mode(before.mode),
        EMU_AUTOMATION_EXECUTION_PAUSED,
        NULL,
        0u, 0u, 0u, 0u, 0u,
        NULL, 0u, NULL);
    return EMU_AUTOMATION_OK;
}}

static emu_automation_result_t {cpu_prefix}_automation_resume(void *context)
{{
    {cpu_name}AutomationDebugContext *ctx = ({cpu_name}AutomationDebugContext *)context;
    PASMDebugSnapshotCore before;
    if (ctx == NULL || ctx->cpu == NULL) return EMU_AUTOMATION_INVALID_ARGUMENT;
    if ({cpu_prefix}_automation_core_snapshot(ctx->cpu, &before) != 0) return EMU_AUTOMATION_ADAPTER_ERROR;
    if (pasm_dbg_run(ctx->cpu) != 0) return EMU_AUTOMATION_ADAPTER_ERROR;
    {cpu_prefix}_automation_push_event(
        ctx,
        EMU_AUTOMATION_EVENT_EXECUTION_STATE_CHANGED,
        {cpu_prefix}_automation_map_mode(before.mode),
        EMU_AUTOMATION_EXECUTION_RUNNING,
        NULL,
        0u, 0u, 0u, 0u, 0u,
        NULL, 0u, NULL);
    return EMU_AUTOMATION_OK;
}}

static emu_automation_result_t {cpu_prefix}_automation_reset(
    void *context,
    emu_automation_reset_kind_t kind)
{{
    {cpu_name}AutomationDebugContext *ctx = ({cpu_name}AutomationDebugContext *)context;
    PASMDebugSnapshotCore before;
    if (ctx == NULL || ctx->cpu == NULL) return EMU_AUTOMATION_INVALID_ARGUMENT;
    if (kind != EMU_AUTOMATION_RESET_COLD && kind != EMU_AUTOMATION_RESET_WARM) {{
        return EMU_AUTOMATION_INVALID_ARGUMENT;
    }}
    if ({cpu_prefix}_automation_core_snapshot(ctx->cpu, &before) != 0) return EMU_AUTOMATION_ADAPTER_ERROR;
    pasm_dbg_reset(ctx->cpu);
    if (pasm_dbg_pause(ctx->cpu) != 0) return EMU_AUTOMATION_ADAPTER_ERROR;
    ctx->last_text_hash_valid = 0u;
    {cpu_prefix}_automation_initialize_text_events(ctx);
    {cpu_prefix}_automation_push_event(
        ctx,
        EMU_AUTOMATION_EVENT_MACHINE_RESET,
        {cpu_prefix}_automation_map_mode(before.mode),
        EMU_AUTOMATION_EXECUTION_PAUSED,
        NULL,
        0u, 0u, 0u, 0u, 0u,
        NULL, 0u, NULL);
    return EMU_AUTOMATION_OK;
}}

static emu_automation_result_t {cpu_prefix}_automation_step_frame(void *context)
{{
    {cpu_name}AutomationDebugContext *ctx = ({cpu_name}AutomationDebugContext *)context;
    PASMDebugSnapshotCore before;
    PASMDebugSnapshotCore after;
    uint64_t before_fb_frame = 0u;
    uint64_t after_fb_frame = 0u;
    uint8_t have_before_fb_frame = 0u;
    uint64_t cycle_slice;
    uint64_t max_slices = 600u;
    uint8_t mode = PASM_DBG_ERROR;

    if (ctx == NULL || ctx->cpu == NULL) return EMU_AUTOMATION_INVALID_ARGUMENT;
    if ({cpu_prefix}_automation_core_snapshot(ctx->cpu, &before) != 0) {{
        return EMU_AUTOMATION_ADAPTER_ERROR;
    }}
{framebuffer_frame_before_line}
    cycle_slice = before.system_clock_hz / 600u;
    if (cycle_slice == 0u) cycle_slice = 1024u;

    for (uint64_t i = 0u; i < max_slices; ++i) {{
        if (pasm_dbg_run_for_cycles(ctx->cpu, cycle_slice, &mode) != 0) {{
            return EMU_AUTOMATION_ADAPTER_ERROR;
        }}
        if ({cpu_prefix}_automation_core_snapshot(ctx->cpu, &after) != 0) {{
            return EMU_AUTOMATION_ADAPTER_ERROR;
        }}
{framebuffer_frame_after_block}
        if (mode == PASM_DBG_PAUSED && after.frame_index == before.frame_index) {{
            {cpu_prefix}_automation_push_event(
                ctx,
                EMU_AUTOMATION_EVENT_EXECUTION_STATE_CHANGED,
                EMU_AUTOMATION_EXECUTION_RUNNING,
                EMU_AUTOMATION_EXECUTION_PAUSED,
                NULL,
                0u, 0u, 0u, 0u, 0u,
                NULL, 0u, NULL);
            return EMU_AUTOMATION_OK;
        }}
{frame_index_completion_block}
        if (mode == PASM_DBG_EXITED || mode == PASM_DBG_ERROR) {{
            return EMU_AUTOMATION_ADAPTER_ERROR;
        }}
    }}

    (void)pasm_dbg_pause(ctx->cpu);
    return EMU_AUTOMATION_TIMEOUT;
}}

static emu_automation_result_t {cpu_prefix}_automation_run_frames(
    void *context,
    uint64_t frame_count)
{{
    for (uint64_t i = 0u; i < frame_count; ++i) {{
        emu_automation_result_t result = {cpu_prefix}_automation_step_frame(context);
        if (result != EMU_AUTOMATION_OK) return result;
    }}
    return EMU_AUTOMATION_OK;
}}

{framebuffer_frame_counter_decl}
{framebuffer_impl}
{text_grid_impl}
{inspection_impl}
{text_event_impl}

static emu_automation_result_t {cpu_prefix}_automation_poll_event(
    void *context,
    uint64_t after_sequence,
    emu_automation_event_t *out_event)
{{
    {cpu_name}AutomationDebugContext *ctx = ({cpu_name}AutomationDebugContext *)context;
    if (ctx == NULL || out_event == NULL) return EMU_AUTOMATION_INVALID_ARGUMENT;
    for (size_t i = 0u; i < ctx->event_count; ++i) {{
        if (ctx->events[i].sequence_number > after_sequence) {{
            *out_event = ctx->events[i];
            return EMU_AUTOMATION_OK;
        }}
    }}
    return EMU_AUTOMATION_TIMEOUT;
}}

static void {cpu_prefix}_automation_release_event(
    void *context,
    emu_automation_event_t *event)
{{
    {cpu_name}AutomationEventOwned *owned;
    (void)context;
    if (event != NULL) {{
        owned = ({cpu_name}AutomationEventOwned *)event->adapter_owned;
        {cpu_prefix}_automation_release_event_owned(owned);
        event->text_deltas = NULL;
        event->text_delta_count = 0u;
        event->device_id = NULL;
        event->control_id = NULL;
        event->region_id = NULL;
        event->adapter_owned = NULL;
    }}
}}

static void {cpu_prefix}_automation_destroy_context(void *context)
{{
    {cpu_name}AutomationDebugContext *ctx = ({cpu_name}AutomationDebugContext *)context;
    if (ctx == NULL) return;
    if (ctx->owns_cpu != 0u && ctx->cpu != NULL) {{
        pasm_dbg_destroy(ctx->cpu);
    }}
    free(ctx);
}}

static emu_automation_result_t {cpu_prefix}_automation_attach_context(
    CPUState *cpu,
    uint8_t owns_cpu,
    emu_automation_machine_t **out_machine)
{{
    {cpu_name}AutomationDebugContext *ctx;
    emu_automation_adapter_t adapter;
    emu_automation_result_t result;

    if (cpu == NULL || out_machine == NULL) return EMU_AUTOMATION_INVALID_ARGUMENT;

    ctx = ({cpu_name}AutomationDebugContext *)calloc(1u, sizeof(*ctx));
    if (ctx == NULL) return EMU_AUTOMATION_INTERNAL_ERROR;
    ctx->cpu = cpu;
    ctx->owns_cpu = owns_cpu;
    {cpu_prefix}_automation_initialize_text_events(ctx);

    memset(&adapter, 0, sizeof(adapter));
    adapter.struct_size = (uint32_t)sizeof(adapter);
    adapter.struct_version = EMU_AUTOMATION_STRUCT_VERSION;
    adapter.context = ctx;
    adapter.destroy_context = {cpu_prefix}_automation_destroy_context;
    adapter.describe = {cpu_prefix}_automation_describe;
    adapter.capabilities = {cpu_prefix}_automation_capabilities;
    adapter.character_mapping_count = {cpu_prefix}_automation_character_mapping_count;
    adapter.character_mapping_descriptor = {cpu_prefix}_automation_character_mapping_descriptor;
    adapter.pause = {cpu_prefix}_automation_pause;
    adapter.resume = {cpu_prefix}_automation_resume;
    adapter.reset = {cpu_prefix}_automation_reset;
    adapter.step_frame = {cpu_prefix}_automation_step_frame;
    adapter.run_frames = {cpu_prefix}_automation_run_frames;
    adapter.write_memory = {cpu_prefix}_automation_write_memory;
    adapter.read_program_counter = {cpu_prefix}_automation_read_program_counter;
    adapter.read_frame_metadata = {cpu_prefix}_automation_read_frame_metadata;
    adapter.read_current_instruction = {cpu_prefix}_automation_read_current_instruction;
    adapter.register_count = {cpu_prefix}_automation_register_count;
    adapter.read_registers = {cpu_prefix}_automation_read_registers;
    adapter.write_register = {cpu_prefix}_automation_write_register;
    adapter.set_breakpoint = {cpu_prefix}_automation_set_breakpoint;
{framebuffer_adapter_members}
{text_grid_adapter_members}
{event_adapter_members}

    result = emu_automation_attach_adapter(&adapter, out_machine);
    if (result != EMU_AUTOMATION_OK) {{
        {cpu_prefix}_automation_destroy_context(ctx);
    }}
    return result;
}}

emu_automation_result_t {cpu_prefix}_automation_attach_debug(
    CPUState *cpu,
    emu_automation_machine_t **out_machine)
{{
    return {cpu_prefix}_automation_attach_context(cpu, 0u, out_machine);
}}

emu_automation_result_t {cpu_prefix}_automation_create(
    size_t memory_size,
    emu_automation_machine_t **out_machine)
{{
    CPUState *cpu;
    if (out_machine == NULL) return EMU_AUTOMATION_INVALID_ARGUMENT;
    if (memory_size == 0u) memory_size = {memory_default_size}u;
    cpu = pasm_dbg_create(memory_size);
    if (cpu == NULL) return EMU_AUTOMATION_INTERNAL_ERROR;
    return {cpu_prefix}_automation_attach_context(cpu, 1u, out_machine);
}}
"""

    return header, impl


def _generate_framebuffer_impl(cpu_name: str, cpu_prefix: str) -> str:
    return f"""
static emu_automation_result_t {cpu_prefix}_automation_capture_framebuffer(
    void *context,
    emu_automation_framebuffer_snapshot_t *out_snapshot)
{{
    {cpu_name}AutomationDebugContext *ctx = ({cpu_name}AutomationDebugContext *)context;
    PASMDebugFramebuffer framebuffer;
    if (ctx == NULL || ctx->cpu == NULL || out_snapshot == NULL) {{
        return EMU_AUTOMATION_INVALID_ARGUMENT;
    }}
    memset(&framebuffer, 0, sizeof(framebuffer));
    if (pasm_dbg_capture_framebuffer(ctx->cpu, &framebuffer) != 0) {{
        return EMU_AUTOMATION_UNSUPPORTED;
    }}
    memset(out_snapshot, 0, sizeof(*out_snapshot));
    out_snapshot->struct_size = (uint32_t)sizeof(*out_snapshot);
    out_snapshot->struct_version = EMU_AUTOMATION_STRUCT_VERSION;
    out_snapshot->frame.struct_size = (uint32_t)sizeof(out_snapshot->frame);
    out_snapshot->frame.struct_version = EMU_AUTOMATION_STRUCT_VERSION;
    out_snapshot->frame.frame_number = framebuffer.frame_number;
    out_snapshot->width = framebuffer.width;
    out_snapshot->height = framebuffer.height;
    out_snapshot->stride_bytes = framebuffer.stride_bytes;
    out_snapshot->pixel_format = (emu_automation_pixel_format_t)framebuffer.pixel_format;
    out_snapshot->visible_area.x = 0u;
    out_snapshot->visible_area.y = 0u;
    out_snapshot->visible_area.width = framebuffer.width;
    out_snapshot->visible_area.height = framebuffer.height;
    out_snapshot->pixel_aspect_numerator = 1u;
    out_snapshot->pixel_aspect_denominator = 1u;
    out_snapshot->pixels = framebuffer.pixels;
    out_snapshot->pixel_size = framebuffer.pixel_size;
    return EMU_AUTOMATION_OK;
}}

static void {cpu_prefix}_automation_release_framebuffer(
    void *context,
    emu_automation_framebuffer_snapshot_t *snapshot)
{{
    {cpu_name}AutomationDebugContext *ctx = ({cpu_name}AutomationDebugContext *)context;
    PASMDebugFramebuffer framebuffer;
    if (ctx == NULL || ctx->cpu == NULL || snapshot == NULL) return;
    memset(&framebuffer, 0, sizeof(framebuffer));
    framebuffer.pixels = snapshot->pixels;
    framebuffer.pixel_size = snapshot->pixel_size;
    pasm_dbg_release_framebuffer(ctx->cpu, &framebuffer);
    snapshot->pixels = NULL;
    snapshot->pixel_size = 0u;
}}
"""


def _generate_text_grid_impl(cpu_name: str, cpu_prefix: str, text_view_rows: str) -> str:
    return f"""
typedef enum {cpu_name}AutomationTextLayout {{
    PASM_AUTOMATION_TEXT_LAYOUT_LINEAR = 0,
    PASM_AUTOMATION_TEXT_LAYOUT_BIT_INTERLEAVED_ROWS = 1,
    PASM_AUTOMATION_TEXT_LAYOUT_TILE_NAME_TABLE = 2
}} {cpu_name}AutomationTextLayout;

typedef enum {cpu_name}AutomationTextSource {{
    PASM_AUTOMATION_TEXT_SOURCE_SYSTEM_MEMORY = 0,
    PASM_AUTOMATION_TEXT_SOURCE_COMPONENT_MEMORY = 1,
    PASM_AUTOMATION_TEXT_SOURCE_CALLBACK = 2
}} {cpu_name}AutomationTextSource;

typedef enum {cpu_name}AutomationTextCallbackOffsetMode {{
    PASM_AUTOMATION_TEXT_CALLBACK_OFFSET_ADDRESS = 0,
    PASM_AUTOMATION_TEXT_CALLBACK_OFFSET_CELL_INDEX = 1
}} {cpu_name}AutomationTextCallbackOffsetMode;

typedef struct {cpu_name}AutomationTextView {{
    const char *id;
    uint32_t columns;
    uint32_t rows;
    uint32_t row_stride;
    uint64_t base;
    uint64_t alternate_base;
    {cpu_name}AutomationTextSource source;
    {cpu_name}AutomationTextLayout layout;
    uint32_t row_low_mask;
    uint32_t row_low_shift;
    uint32_t row_high_shift;
    uint32_t row_high_multiplier;
    uint32_t column_multiplier;
    {cpu_name}AutomationTextCallbackOffsetMode callback_offset_mode;
    const char *component_id;
    const char *read_callback;
    const char *charset_id;
    const char *native_encoding;
    const char *unicode_map;
}} {cpu_name}AutomationTextView;

typedef struct {cpu_name}AutomationTextGridOwned {{
    emu_automation_text_cell_t *cells;
    char *plain;
}} {cpu_name}AutomationTextGridOwned;

static const {cpu_name}AutomationTextView {cpu_prefix}_automation_text_views[] = {{
{text_view_rows}
}};

static const size_t {cpu_prefix}_automation_text_view_count =
    sizeof({cpu_prefix}_automation_text_views) / sizeof({cpu_prefix}_automation_text_views[0]);

static const {cpu_name}AutomationTextView *{cpu_prefix}_automation_find_text_view(const char *region_id)
{{
    if ({cpu_prefix}_automation_text_view_count == 0u) return NULL;
    if (region_id == NULL || region_id[0] == '\\0') {{
        return &{cpu_prefix}_automation_text_views[0];
    }}
    for (size_t i = 0u; i < {cpu_prefix}_automation_text_view_count; ++i) {{
        if (strcmp({cpu_prefix}_automation_text_views[i].id, region_id) == 0) {{
            return &{cpu_prefix}_automation_text_views[i];
        }}
    }}
    return NULL;
}}

static uint64_t {cpu_prefix}_automation_text_address(
    const {cpu_name}AutomationTextView *view,
    uint32_t row,
    uint32_t column)
{{
    uint32_t column_multiplier = (view->column_multiplier == 0u) ? 1u : view->column_multiplier;
    if (view->layout == PASM_AUTOMATION_TEXT_LAYOUT_BIT_INTERLEAVED_ROWS) {{
        return view->base +
            ((uint64_t)(row & view->row_low_mask) << view->row_low_shift) +
            ((uint64_t)(row >> view->row_high_shift) * (uint64_t)view->row_high_multiplier) +
            ((uint64_t)column * (uint64_t)column_multiplier);
    }}
    if (view->layout == PASM_AUTOMATION_TEXT_LAYOUT_TILE_NAME_TABLE) {{
        return view->base + ((uint64_t)row * (uint64_t)view->row_stride) +
            ((uint64_t)column * (uint64_t)column_multiplier);
    }}
    return view->base + ((uint64_t)row * (uint64_t)view->row_stride) +
        ((uint64_t)column * (uint64_t)column_multiplier);
}}

static uint64_t {cpu_prefix}_automation_text_callback_arg(
    const {cpu_name}AutomationTextView *view,
    uint32_t row,
    uint32_t column,
    uint64_t address)
{{
    uint32_t column_multiplier = (view->column_multiplier == 0u) ? 1u : view->column_multiplier;
    if (view->callback_offset_mode == PASM_AUTOMATION_TEXT_CALLBACK_OFFSET_CELL_INDEX) {{
        return ((uint64_t)row * (uint64_t)view->row_stride) +
            ((uint64_t)column * (uint64_t)column_multiplier);
    }}
    return address;
}}

static emu_automation_result_t {cpu_prefix}_automation_read_text_native_code(
    {cpu_name}AutomationDebugContext *ctx,
    const {cpu_name}AutomationTextView *view,
    uint64_t read_arg,
    uint8_t *out_native_code)
{{
    if (ctx == NULL || ctx->cpu == NULL || view == NULL || out_native_code == NULL) {{
        return EMU_AUTOMATION_INVALID_ARGUMENT;
    }}
    if (view->source == PASM_AUTOMATION_TEXT_SOURCE_SYSTEM_MEMORY) {{
        if (pasm_dbg_read_memory(ctx->cpu, read_arg, out_native_code, 1u) != 0) {{
            return EMU_AUTOMATION_ADAPTER_ERROR;
        }}
        return EMU_AUTOMATION_OK;
    }}
    if (
        (view->source == PASM_AUTOMATION_TEXT_SOURCE_COMPONENT_MEMORY ||
         view->source == PASM_AUTOMATION_TEXT_SOURCE_CALLBACK) &&
        view->component_id != NULL && view->component_id[0] != '\\0' &&
        view->read_callback != NULL && view->read_callback[0] != '\\0'
    ) {{
        uint64_t args[1] = {{ read_arg }};
        *out_native_code = (uint8_t)(
            cpu_component_dispatch_callback(
                ctx->cpu,
                view->component_id,
                view->read_callback,
                args,
                1u
            ) & 0xFFu
        );
        return EMU_AUTOMATION_OK;
    }}
    return EMU_AUTOMATION_UNSUPPORTED;
}}

static uint32_t {cpu_prefix}_automation_apple2_codepoint(uint8_t native_code)
{{
    uint8_t ascii = (uint8_t)(native_code & 0x7Fu);
    if (ascii < 0x20u) ascii = (uint8_t)(ascii + 0x40u);
    if (ascii >= 0x20u && ascii <= 0x5Fu) return (uint32_t)ascii;
    return 0xFFFDu;
}}

static uint32_t {cpu_prefix}_automation_text_codepoint(
    const {cpu_name}AutomationTextView *view,
    uint8_t native_code)
{{
    if (view->unicode_map != NULL && strcmp(view->unicode_map, "apple2_text") == 0) {{
        return {cpu_prefix}_automation_apple2_codepoint(native_code);
    }}
    if (native_code >= 0x20u && native_code <= 0x7Eu) return (uint32_t)native_code;
    return 0xFFFDu;
}}

static uint32_t {cpu_prefix}_automation_text_attributes(
    const {cpu_name}AutomationTextView *view,
    uint8_t native_code)
{{
    if (view->unicode_map != NULL && strcmp(view->unicode_map, "apple2_text") == 0) {{
        if (native_code < 0x40u) return 1u;
        if (native_code < 0x80u) return 2u;
    }}
    return 0u;
}}

static void {cpu_prefix}_automation_fill_text_cell(
    const {cpu_name}AutomationTextView *view,
    uint32_t row,
    uint32_t col,
    uint8_t native_code,
    emu_automation_text_cell_t *out_cell)
{{
    uint64_t address;
    uint32_t codepoint;
    if (view == NULL || out_cell == NULL) return;
    address = {cpu_prefix}_automation_text_address(view, row, col);
    codepoint = {cpu_prefix}_automation_text_codepoint(view, native_code);
    memset(out_cell, 0, sizeof(*out_cell));
    out_cell->struct_size = (uint32_t)sizeof(*out_cell);
    out_cell->struct_version = EMU_AUTOMATION_STRUCT_VERSION;
    out_cell->native_code = (uint32_t)native_code;
    out_cell->unicode_codepoint = codepoint;
    out_cell->glyph_id = view->unicode_map;
    out_cell->foreground_color = -1;
    out_cell->background_color = -1;
    out_cell->attribute_flags = {cpu_prefix}_automation_text_attributes(view, native_code);
    out_cell->charset_id = view->charset_id;
    out_cell->source_address = address;
    out_cell->confidence = (codepoint == 0xFFFDu) ? 64u : 255u;
}}

static char {cpu_prefix}_automation_plain_char(uint32_t codepoint)
{{
    if (codepoint >= 0x20u && codepoint <= 0x7Eu) return (char)codepoint;
    return '?';
}}

static emu_automation_result_t {cpu_prefix}_automation_capture_text_grid(
    void *context,
    const char *region_id,
    emu_automation_text_grid_snapshot_t *out_snapshot)
{{
    {cpu_name}AutomationDebugContext *ctx = ({cpu_name}AutomationDebugContext *)context;
    const {cpu_name}AutomationTextView *view;
    {cpu_name}AutomationTextGridOwned *owned;
    PASMDebugSnapshotCore core;
    size_t cell_count;
    size_t plain_size;
    size_t plain_index = 0u;

    if (ctx == NULL || ctx->cpu == NULL || out_snapshot == NULL) {{
        return EMU_AUTOMATION_INVALID_ARGUMENT;
    }}
    view = {cpu_prefix}_automation_find_text_view(region_id);
    if (view == NULL) return EMU_AUTOMATION_UNSUPPORTED;
    if (view->columns == 0u || view->rows == 0u) return EMU_AUTOMATION_INVALID_STATE;
    cell_count = (size_t)view->columns * (size_t)view->rows;
    plain_size = cell_count + ((view->rows > 0u) ? (size_t)(view->rows - 1u) : 0u);

    owned = ({cpu_name}AutomationTextGridOwned *)calloc(1u, sizeof(*owned));
    if (owned == NULL) return EMU_AUTOMATION_INTERNAL_ERROR;
    owned->cells = (emu_automation_text_cell_t *)calloc(cell_count, sizeof(*owned->cells));
    owned->plain = (char *)calloc(plain_size + 1u, sizeof(*owned->plain));
    if (owned->cells == NULL || owned->plain == NULL) {{
        free(owned->cells);
        free(owned->plain);
        free(owned);
        return EMU_AUTOMATION_INTERNAL_ERROR;
    }}

    if ({cpu_prefix}_automation_core_snapshot(ctx->cpu, &core) != 0) {{
        free(owned->cells);
        free(owned->plain);
        free(owned);
        return EMU_AUTOMATION_ADAPTER_ERROR;
    }}

    for (uint32_t row = 0u; row < view->rows; ++row) {{
        for (uint32_t col = 0u; col < view->columns; ++col) {{
            size_t index = ((size_t)row * (size_t)view->columns) + (size_t)col;
            uint64_t address = {cpu_prefix}_automation_text_address(view, row, col);
            uint64_t read_arg = {cpu_prefix}_automation_text_callback_arg(view, row, col, address);
            uint8_t native_code = 0u;
            uint32_t codepoint;
            if ({cpu_prefix}_automation_read_text_native_code(ctx, view, read_arg, &native_code) != EMU_AUTOMATION_OK) {{
                free(owned->cells);
                free(owned->plain);
                free(owned);
                return EMU_AUTOMATION_ADAPTER_ERROR;
            }}
            codepoint = {cpu_prefix}_automation_text_codepoint(view, native_code);
            {cpu_prefix}_automation_fill_text_cell(view, row, col, native_code, &owned->cells[index]);
            owned->plain[plain_index++] = {cpu_prefix}_automation_plain_char(codepoint);
        }}
        if (row + 1u < view->rows) owned->plain[plain_index++] = '\\n';
    }}

    out_snapshot->frame.frame_number = core.frame_index;
    out_snapshot->frame.emulated_cycles = core.total_cycles;
    out_snapshot->frame.execution_state = {cpu_prefix}_automation_map_mode(core.mode);
    out_snapshot->region_id = view->id;
    out_snapshot->columns = view->columns;
    out_snapshot->rows = view->rows;
    out_snapshot->row_stride = view->row_stride;
    out_snapshot->cells = owned->cells;
    out_snapshot->cell_count = cell_count;
    out_snapshot->plain_utf8 = owned->plain;
    out_snapshot->plain_utf8_size = plain_index;
    out_snapshot->adapter_owned = owned;
    return EMU_AUTOMATION_OK;
}}

static emu_automation_result_t {cpu_prefix}_automation_text_grid_view_count(
    void *context,
    size_t *out_count)
{{
    (void)context;
    if (out_count == NULL) return EMU_AUTOMATION_INVALID_ARGUMENT;
    *out_count = {cpu_prefix}_automation_text_view_count;
    return EMU_AUTOMATION_OK;
}}

static emu_automation_result_t {cpu_prefix}_automation_text_grid_view_descriptor(
    void *context,
    size_t index,
    emu_automation_text_view_descriptor_t *out_descriptor)
{{
    const {cpu_name}AutomationTextView *view;
    (void)context;
    if (out_descriptor == NULL) return EMU_AUTOMATION_INVALID_ARGUMENT;
    if (index >= {cpu_prefix}_automation_text_view_count) return EMU_AUTOMATION_INVALID_ARGUMENT;
    view = &{cpu_prefix}_automation_text_views[index];
    out_descriptor->region_id = view->id;
    out_descriptor->columns = view->columns;
    out_descriptor->rows = view->rows;
    out_descriptor->row_stride = view->row_stride;
    out_descriptor->charset_id = view->charset_id;
    out_descriptor->native_encoding = view->native_encoding;
    out_descriptor->unicode_map = view->unicode_map;
    return EMU_AUTOMATION_OK;
}}

static void {cpu_prefix}_automation_release_text_grid(
    void *context,
    emu_automation_text_grid_snapshot_t *snapshot)
{{
    {cpu_name}AutomationTextGridOwned *owned;
    (void)context;
    if (snapshot == NULL || snapshot->adapter_owned == NULL) return;
    owned = ({cpu_name}AutomationTextGridOwned *)snapshot->adapter_owned;
    free(owned->cells);
    free(owned->plain);
    free(owned);
}}
"""


def _generate_inspection_impl(cpu_name: str, cpu_prefix: str) -> str:
    return f"""

static emu_automation_result_t {cpu_prefix}_automation_read_memory(
    void *context,
    uint64_t address,
    uint8_t *out_bytes,
    size_t size)
{{
    {cpu_name}AutomationDebugContext *ctx = ({cpu_name}AutomationDebugContext *)context;
    if (ctx == NULL || ctx->cpu == NULL || out_bytes == NULL) return EMU_AUTOMATION_INVALID_ARGUMENT;
    if (size == 0u) return EMU_AUTOMATION_OK;
    if (pasm_dbg_read_memory(ctx->cpu, address, out_bytes, size) != 0) {{
        return EMU_AUTOMATION_ADAPTER_ERROR;
    }}
    return EMU_AUTOMATION_OK;
}}

static emu_automation_result_t {cpu_prefix}_automation_write_memory(
    void *context,
    uint64_t address,
    const uint8_t *bytes,
    size_t size)
{{
    {cpu_name}AutomationDebugContext *ctx = ({cpu_name}AutomationDebugContext *)context;
    if (ctx == NULL || ctx->cpu == NULL || bytes == NULL) return EMU_AUTOMATION_INVALID_ARGUMENT;
    if (size == 0u) return EMU_AUTOMATION_OK;
    if (pasm_dbg_write_memory(ctx->cpu, address, bytes, size) != 0) {{
        return EMU_AUTOMATION_ADAPTER_ERROR;
    }}
    return EMU_AUTOMATION_OK;
}}

static emu_automation_result_t {cpu_prefix}_automation_read_program_counter(
    void *context,
    uint64_t *out_program_counter)
{{
    {cpu_name}AutomationDebugContext *ctx = ({cpu_name}AutomationDebugContext *)context;
    PASMDebugSnapshotCore core;
    if (ctx == NULL || ctx->cpu == NULL || out_program_counter == NULL) return EMU_AUTOMATION_INVALID_ARGUMENT;
    if ({cpu_prefix}_automation_core_snapshot(ctx->cpu, &core) != 0) {{
        return EMU_AUTOMATION_ADAPTER_ERROR;
    }}
    *out_program_counter = core.pc;
    return EMU_AUTOMATION_OK;
}}

static emu_automation_result_t {cpu_prefix}_automation_read_frame_metadata(
    void *context,
    emu_automation_frame_metadata_t *out_metadata)
{{
    {cpu_name}AutomationDebugContext *ctx = ({cpu_name}AutomationDebugContext *)context;
    PASMDebugSnapshotCore core;
    if (ctx == NULL || ctx->cpu == NULL || out_metadata == NULL) return EMU_AUTOMATION_INVALID_ARGUMENT;
    if ({cpu_prefix}_automation_core_snapshot(ctx->cpu, &core) != 0) {{
        return EMU_AUTOMATION_ADAPTER_ERROR;
    }}
    out_metadata->frame_number = core.frame_index;
    out_metadata->emulated_cycles = core.total_cycles;
    out_metadata->emulated_time_ns = 0u;
    out_metadata->execution_state = {cpu_prefix}_automation_map_mode(core.mode);
    return EMU_AUTOMATION_OK;
}}

static emu_automation_result_t {cpu_prefix}_automation_read_current_instruction(
    void *context,
    emu_automation_instruction_t *out_instruction)
{{
    {cpu_name}AutomationDebugContext *ctx = ({cpu_name}AutomationDebugContext *)context;
    PASMDebugSnapshotCore core;
    PASMDebugDisasmRow row;
    if (ctx == NULL || ctx->cpu == NULL || out_instruction == NULL) return EMU_AUTOMATION_INVALID_ARGUMENT;
    memset(&row, 0, sizeof(row));
    if (pasm_dbg_snapshot_fill(
            ctx->cpu,
            &core,
            &row, 1u,
            NULL, 0u,
            NULL, 0u,
            NULL, 0u,
            NULL, 0u,
            NULL, 0u,
            NULL, 0u,
            NULL, 0u,
            NULL, 0u,
            NULL, 0u,
            NULL, 0u) != 0) {{
        return EMU_AUTOMATION_ADAPTER_ERROR;
    }}
    out_instruction->address = row.address;
    memcpy(out_instruction->bytes, row.bytes, sizeof(out_instruction->bytes));
    memcpy(out_instruction->text, row.instruction, sizeof(out_instruction->text));
    memcpy(out_instruction->symbol, row.symbol, sizeof(out_instruction->symbol));
    out_instruction->has_symbol = row.has_symbol;
    out_instruction->is_current_ip = row.is_current_ip;
    out_instruction->has_breakpoint = row.has_breakpoint;
    out_instruction->branch_target = row.branch_target;
    out_instruction->has_branch_target = row.has_branch_target;
    out_instruction->changed_since_last_step = row.changed_since_last_step;
    return EMU_AUTOMATION_OK;
}}

static emu_automation_result_t {cpu_prefix}_automation_register_count(
    void *context,
    size_t *out_count)
{{
    {cpu_name}AutomationDebugContext *ctx = ({cpu_name}AutomationDebugContext *)context;
    PASMDebugCounts counts;
    if (ctx == NULL || ctx->cpu == NULL || out_count == NULL) return EMU_AUTOMATION_INVALID_ARGUMENT;
    if (pasm_dbg_snapshot_counts(ctx->cpu, &counts) != 0) {{
        return EMU_AUTOMATION_ADAPTER_ERROR;
    }}
    *out_count = (size_t)counts.register_rows;
    return EMU_AUTOMATION_OK;
}}

static emu_automation_result_t {cpu_prefix}_automation_read_registers(
    void *context,
    emu_automation_register_value_t *out_registers,
    size_t register_capacity,
    size_t *out_register_count)
{{
    {cpu_name}AutomationDebugContext *ctx = ({cpu_name}AutomationDebugContext *)context;
    PASMDebugCounts counts;
    PASMDebugSnapshotCore core;
    PASMDebugRegisterRow *rows = NULL;
    size_t count = 0u;
    size_t i;
    if (ctx == NULL || ctx->cpu == NULL || out_register_count == NULL) return EMU_AUTOMATION_INVALID_ARGUMENT;
    if (pasm_dbg_snapshot_counts(ctx->cpu, &counts) != 0) {{
        return EMU_AUTOMATION_ADAPTER_ERROR;
    }}
    count = (size_t)counts.register_rows;
    *out_register_count = count;
    if (count == 0u || register_capacity == 0u) return EMU_AUTOMATION_OK;
    if (out_registers == NULL) return EMU_AUTOMATION_INVALID_ARGUMENT;
    rows = (PASMDebugRegisterRow *)calloc(count, sizeof(*rows));
    if (rows == NULL) return EMU_AUTOMATION_INTERNAL_ERROR;
    if (pasm_dbg_snapshot_fill(
            ctx->cpu,
            &core,
            NULL, 0u,
            rows, count,
            NULL, 0u,
            NULL, 0u,
            NULL, 0u,
            NULL, 0u,
            NULL, 0u,
            NULL, 0u,
            NULL, 0u,
            NULL, 0u,
            NULL, 0u) != 0) {{
        free(rows);
        return EMU_AUTOMATION_ADAPTER_ERROR;
    }}
    if (count > register_capacity) count = register_capacity;
    for (i = 0u; i < count; ++i) {{
        memcpy(out_registers[i].name, rows[i].name, sizeof(out_registers[i].name));
        memcpy(out_registers[i].hex_value, rows[i].hex_value, sizeof(out_registers[i].hex_value));
        memcpy(out_registers[i].dec_value, rows[i].dec_value, sizeof(out_registers[i].dec_value));
        out_registers[i].has_dec = rows[i].has_dec;
        out_registers[i].changed = rows[i].changed;
    }}
    free(rows);
    *out_register_count = count;
    return EMU_AUTOMATION_OK;
}}

static emu_automation_result_t {cpu_prefix}_automation_write_register(
    void *context,
    const char *register_name,
    uint64_t value)
{{
    {cpu_name}AutomationDebugContext *ctx = ({cpu_name}AutomationDebugContext *)context;
    if (ctx == NULL || ctx->cpu == NULL || register_name == NULL || register_name[0] == '\\0') {{
        return EMU_AUTOMATION_INVALID_ARGUMENT;
    }}
    if (pasm_dbg_write_register(ctx->cpu, register_name, value) != 0) {{
        return EMU_AUTOMATION_ADAPTER_ERROR;
    }}
    return EMU_AUTOMATION_OK;
}}

static emu_automation_result_t {cpu_prefix}_automation_set_breakpoint(
    void *context,
    uint64_t address,
    uint8_t enabled)
{{
    {cpu_name}AutomationDebugContext *ctx = ({cpu_name}AutomationDebugContext *)context;
    if (ctx == NULL || ctx->cpu == NULL || enabled > 1u) {{
        return EMU_AUTOMATION_INVALID_ARGUMENT;
    }}
    if (pasm_dbg_set_breakpoint_enabled(ctx->cpu, address, enabled) != 0) {{
        return EMU_AUTOMATION_ADAPTER_ERROR;
    }}
    return EMU_AUTOMATION_OK;
}}
"""


def _generate_text_event_impl(cpu_name: str, cpu_prefix: str) -> str:
    return f"""
static emu_automation_result_t {cpu_prefix}_automation_read_text_view_cells(
    {cpu_name}AutomationDebugContext *ctx,
    const {cpu_name}AutomationTextView *view,
    uint8_t *out_cells)
{{
    if (ctx == NULL || ctx->cpu == NULL || view == NULL || out_cells == NULL) {{
        return EMU_AUTOMATION_INVALID_ARGUMENT;
    }}
    for (uint32_t row = 0u; row < view->rows; ++row) {{
        for (uint32_t col = 0u; col < view->columns; ++col) {{
            size_t index = ((size_t)row * (size_t)view->columns) + (size_t)col;
            uint64_t address = {cpu_prefix}_automation_text_address(view, row, col);
            uint8_t native_code = 0u;
            if (pasm_dbg_read_memory(ctx->cpu, address, &native_code, 1u) != 0) {{
                return EMU_AUTOMATION_ADAPTER_ERROR;
            }}
            out_cells[index] = native_code;
        }}
    }}
    return EMU_AUTOMATION_OK;
}}

static uint64_t {cpu_prefix}_automation_hash_text_cells(
    const uint8_t *cells,
    size_t cell_count)
{{
    uint64_t hash = 1469598103934665603ull;
    if (cells == NULL) return 0ull;
    for (size_t i = 0u; i < cell_count; ++i) {{
        hash ^= (uint64_t)cells[i];
        hash *= 1099511628211ull;
    }}
    return hash;
}}

static void {cpu_prefix}_automation_find_text_change_bounds(
    const {cpu_name}AutomationTextView *view,
    const uint8_t *previous_cells,
    const uint8_t *current_cells,
    uint32_t *out_x,
    uint32_t *out_y,
    uint32_t *out_width,
    uint32_t *out_height,
    uint32_t *out_cell_count)
{{
    uint32_t min_x = view->columns;
    uint32_t min_y = view->rows;
    uint32_t max_x = 0u;
    uint32_t max_y = 0u;
    uint32_t count = 0u;
    uint8_t found = 0u;
    for (uint32_t row = 0u; row < view->rows; ++row) {{
        for (uint32_t col = 0u; col < view->columns; ++col) {{
            size_t index = ((size_t)row * (size_t)view->columns) + (size_t)col;
            if (previous_cells[index] == current_cells[index]) continue;
            count += 1u;
            if (found == 0u) {{
                min_x = col;
                min_y = row;
                max_x = col;
                max_y = row;
                found = 1u;
            }} else {{
                if (col < min_x) min_x = col;
                if (row < min_y) min_y = row;
                if (col > max_x) max_x = col;
                if (row > max_y) max_y = row;
            }}
        }}
    }}
    if (out_x != NULL) *out_x = (found != 0u) ? min_x : 0u;
    if (out_y != NULL) *out_y = (found != 0u) ? min_y : 0u;
    if (out_width != NULL) *out_width = (found != 0u) ? (max_x - min_x + 1u) : 0u;
    if (out_height != NULL) *out_height = (found != 0u) ? (max_y - min_y + 1u) : 0u;
    if (out_cell_count != NULL) *out_cell_count = count;
}}

static {cpu_name}AutomationEventOwned *{cpu_prefix}_automation_build_text_deltas(
    const {cpu_name}AutomationTextView *view,
    const uint8_t *previous_cells,
    const uint8_t *current_cells,
    uint32_t expected_count)
{{
    {cpu_name}AutomationEventOwned *owned;
    size_t write_index = 0u;
    if (view == NULL || previous_cells == NULL || current_cells == NULL || expected_count == 0u) {{
        return NULL;
    }}
    owned = ({cpu_name}AutomationEventOwned *)calloc(1u, sizeof(*owned));
    if (owned == NULL) return NULL;
    owned->text_deltas = (emu_automation_text_delta_t *)calloc(
        (size_t)expected_count,
        sizeof(*owned->text_deltas));
    if (owned->text_deltas == NULL) {{
        free(owned);
        return NULL;
    }}
    for (uint32_t row = 0u; row < view->rows; ++row) {{
        for (uint32_t col = 0u; col < view->columns; ++col) {{
            size_t index = ((size_t)row * (size_t)view->columns) + (size_t)col;
            emu_automation_text_delta_t *delta;
            if (previous_cells[index] == current_cells[index]) continue;
            delta = &owned->text_deltas[write_index++];
            memset(delta, 0, sizeof(*delta));
            delta->struct_size = (uint32_t)sizeof(*delta);
            delta->struct_version = EMU_AUTOMATION_STRUCT_VERSION;
            delta->x = col;
            delta->y = row;
            {cpu_prefix}_automation_fill_text_cell(view, row, col, previous_cells[index], &delta->before);
            {cpu_prefix}_automation_fill_text_cell(view, row, col, current_cells[index], &delta->after);
        }}
    }}
    owned->text_delta_count = write_index;
    return owned;
}}

static emu_automation_result_t {cpu_prefix}_automation_hash_text_view(
    {cpu_name}AutomationDebugContext *ctx,
    const {cpu_name}AutomationTextView *view,
    uint64_t *out_hash)
{{
    size_t cell_count;
    uint8_t *cells;
    emu_automation_result_t result;
    if (view == NULL || out_hash == NULL) return EMU_AUTOMATION_INVALID_ARGUMENT;
    cell_count = (size_t)view->columns * (size_t)view->rows;
    if (cell_count == 0u) return EMU_AUTOMATION_INVALID_ARGUMENT;
    cells = (uint8_t *)calloc(cell_count, sizeof(*cells));
    if (cells == NULL) return EMU_AUTOMATION_INTERNAL_ERROR;
    if ({cpu_prefix}_automation_read_text_view_cells(ctx, view, cells) != EMU_AUTOMATION_OK) {{
        free(cells);
        return EMU_AUTOMATION_ADAPTER_ERROR;
    }}
    *out_hash = {cpu_prefix}_automation_hash_text_cells(
        cells,
        cell_count);
    result = EMU_AUTOMATION_OK;
    free(cells);
    return result;
}}

static void {cpu_prefix}_automation_initialize_text_events(
    {cpu_name}AutomationDebugContext *ctx)
{{
    const {cpu_name}AutomationTextView *view = &{cpu_prefix}_automation_text_views[0];
    if (ctx == NULL || {cpu_prefix}_automation_text_view_count == 0u) {{
        return;
    }}
    if ({cpu_prefix}_automation_read_text_view_cells(
            ctx,
            view,
            ctx->last_text_cells) == EMU_AUTOMATION_OK) {{
        uint64_t hash = {cpu_prefix}_automation_hash_text_cells(
            ctx->last_text_cells,
            (size_t)view->columns * (size_t)view->rows);
        ctx->last_text_hash = hash;
        ctx->last_text_hash_valid = 1u;
        ctx->last_text_cells_valid = 1u;
    }}
}}

static void {cpu_prefix}_automation_emit_screen_events(
    {cpu_name}AutomationDebugContext *ctx)
{{
    const {cpu_name}AutomationTextView *view = &{cpu_prefix}_automation_text_views[0];
    size_t cell_count;
    uint8_t *current_cells;
    {cpu_name}AutomationEventOwned *text_owned = NULL;
    uint64_t hash;
    uint32_t change_x = 0u;
    uint32_t change_y = 0u;
    uint32_t change_width = 0u;
    uint32_t change_height = 0u;
    uint32_t change_cell_count = 0u;
    if (ctx == NULL || {cpu_prefix}_automation_text_view_count == 0u) {{
        return;
    }}
    cell_count = (size_t)view->columns * (size_t)view->rows;
    if (cell_count == 0u) {{
        return;
    }}
    current_cells = (uint8_t *)calloc(cell_count, sizeof(*current_cells));
    if (current_cells == NULL) {{
        return;
    }}
    if ({cpu_prefix}_automation_read_text_view_cells(
            ctx,
            view,
            current_cells) != EMU_AUTOMATION_OK) {{
        free(current_cells);
        return;
    }}
    hash = {cpu_prefix}_automation_hash_text_cells(
        current_cells,
        cell_count);
    if (ctx->last_text_hash_valid == 0u || ctx->last_text_cells_valid == 0u) {{
        ctx->last_text_hash = hash;
        ctx->last_text_hash_valid = 1u;
        memcpy(
            ctx->last_text_cells,
            current_cells,
            cell_count);
        ctx->last_text_cells_valid = 1u;
        free(current_cells);
        return;
    }}
    if (ctx->last_text_hash != hash) {{
        {cpu_prefix}_automation_find_text_change_bounds(
            view,
            ctx->last_text_cells,
            current_cells,
            &change_x,
            &change_y,
            &change_width,
            &change_height,
            &change_cell_count);
        if (change_cell_count > 0u) {{
            text_owned = {cpu_prefix}_automation_build_text_deltas(
                view,
                ctx->last_text_cells,
                current_cells,
                change_cell_count);
        }}
        ctx->last_text_hash = hash;
        memcpy(
            ctx->last_text_cells,
            current_cells,
            cell_count);
        {cpu_prefix}_automation_push_event(
            ctx,
            EMU_AUTOMATION_EVENT_TEXT_CHANGED,
            0,
            0,
            {cpu_prefix}_automation_text_views[0].id,
            change_x,
            change_y,
            change_width,
            change_height,
            change_cell_count,
            text_owned != NULL ? text_owned->text_deltas : NULL,
            text_owned != NULL ? text_owned->text_delta_count : 0u,
            text_owned);
        {cpu_prefix}_automation_push_event(
            ctx,
            EMU_AUTOMATION_EVENT_SCREEN_CHANGED,
            0,
            0,
            {cpu_prefix}_automation_text_views[0].id,
            change_x,
            change_y,
            change_width,
            change_height,
            change_cell_count,
            NULL,
            0u,
            NULL);
    }}
    free(current_cells);
}}
"""
