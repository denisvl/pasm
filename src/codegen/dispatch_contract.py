"""Shared dispatch contract declarations for split core/system ownership."""


def generate_dispatch_contract_decls() -> str:
    """Generate declarations shared between cpu core and system glue split units."""
    return """typedef struct {
    const char *from_component;
    const char *from_kind;
    const char *from_name;
    const char *to_component;
    const char *to_kind;
    const char *to_name;
    uint64_t from_component_hash;
    uint64_t from_name_hash;
    uint64_t to_component_hash;
    uint64_t to_name_hash;
    uint8_t from_kind_id;
    uint8_t to_kind_id;
} ComponentConnection;

extern const ComponentConnection g_component_connections[];
extern const size_t g_component_connections_count;

uint64_t cpu_component_call(
    CPUState *cpu,
    const char *source_component,
    const char *callback_name,
    const uint64_t *args,
    uint8_t argc
);

void cpu_component_emit_signal(
    CPUState *cpu,
    const char *source_component,
    const char *signal_name,
    const uint64_t *args,
    uint8_t argc
);

uint64_t cpu_component_dispatch_callback(
    CPUState *cpu,
    const char *component_id,
    const char *callback_name,
    const uint64_t *args,
    uint8_t argc
);

void cpu_component_dispatch_handler(
    CPUState *cpu,
    const char *component_id,
    const char *handler_name,
    const uint64_t *args,
    uint8_t argc
);

uint8_t cpu_components_bus_read(
    CPUState *cpu,
    uint16_t addr,
    uint8_t *handled
);

uint8_t cpu_components_bus_write(
    CPUState *cpu,
    uint16_t addr,
    uint8_t value,
    uint8_t *handled
);

uint8_t cpu_components_port_read(
    CPUState *cpu,
    uint16_t port,
    uint8_t *handled
);

void cpu_components_port_write(
    CPUState *cpu,
    uint16_t port,
    uint8_t value,
    uint8_t *handled
);"""
