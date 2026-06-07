# Schema Editor Tool — Development Plan

## Overview

A C++ Dear ImGui + SDL2 desktop application that dynamically generates YAML editing forms from the JSON schemas in `schemas/`. Users can browse, edit, and save YAML files found under `examples/` with a schema-driven form interface. C code fields get a specialized multiline editor with clang-format prettification.

## Project Location

`tools/schema_editor/`

## Cross-Platform Targets

- **Linux** (primary, same build pattern as existing tools)
- **Windows** (via vcpkg or FetchContent)

## Dependencies

| Dependency | Acquisition | Purpose |
|---|---|---|
| SDL2 + SDL2_image | `pkg-config` (Linux) / `find_package` (Windows) | Window, input, rendering |
| Dear ImGui v1.91+ | Vendored at `third_party/imgui/` | UI framework |
| yaml-cpp 0.8.0 | `FetchContent` | YAML parsing & serialization |
| nlohmann/json 3.11.3 | `FetchContent` | JSON Schema parsing |
| clang-format | External binary (optional) | C code prettification |

## File Structure

```
tools/schema_editor/
├── CMakeLists.txt
└── src/
    ├── main.cpp               # Entry point, SDL2 + ImGui init, main loop
    ├── app.h / app.cpp        # App orchestrator: panels, state, layout
    ├── file_browser.h/.cpp    # Tree view + filter tabs for examples/
    ├── schema_parser.h/.cpp   # JSON Schema → SchemaField tree
    ├── yaml_loader.h/.cpp     # YAML load/save via yaml-cpp
    ├── form_renderer.h/.cpp   # Schema-driven ImGui widget generation
    ├── c_code_editor.h/.cpp   # Multiline C editor + clang-format integration
    └── schema_registry.h/.cpp # Path→schema matching (by convention)
```

## Architecture

### Data Flow

```
File Browser → select .yaml file
       ↓
Schema Registry → determine which JSON schema applies
       ↓
Schema Parser → parse JSON Schema → SchemaField tree
  (also: YAML Loader → parse YAML → YamlNode data tree)
       ↓
Form Renderer → emit ImGui widgets guided by SchemaField tree,
                read/write YamlNode values
       ↓
C Code Editor → for C fields: multiline editor + Prettify button
       ↓
Save → yaml-cpp serializes YamlNode → .yaml file
```

### Schema Field Structure

```cpp
struct SchemaField {
    std::string name;
    std::string type;          // "string", "integer", "number", "boolean", "array", "object"
    bool required = false;
    std::string description;
    std::string pattern;
    double minimum, maximum;
    int minLength, maxLength, minItems, maxItems;
    std::vector<std::string> enumValues;
    std::shared_ptr<SchemaField> items;            // array element type
    std::vector<SchemaField> properties;           // object fields
    std::vector<std::vector<SchemaField>> oneOfVariants;
    bool isCCodeField = false;
    // For additionalProperties: { "type": "string" }
    bool hasAdditionalProperties = false;
    SchemaField additionalPropertiesSchema;
};
```

### Widget Mapping

| Schema Type | ImGui Widget |
|---|---|
| `"string"` + not C code | `InputText` (single line) |
| `"string"` + C code field | `InputTextMultiline` + Prettify button |
| `"string"` + `enum` | `Combo` dropdown |
| `"string"` + `pattern` (regex) | `InputText` with validation indicator |
| `"integer"` | `InputInt` / `SliderInt` |
| `"number"` | `InputFloat` / `SliderFloat` |
| `"boolean"` | `Checkbox` |
| `"array"` | Collapsible list with add/remove/reorder |
| `"object"` | Collapsible tree node with children |
| `oneOf` / `anyOf` | Radio selector to pick variant |
| `additionalProperties` | Dynamic key-value table editor |

## UI Layout

```
┌──────────────────────────────────────────────────────┐
│ Menu:  File | View | Help                            │
├──────────────────┬───────────────────────────────────┤
│ File Browser     │  Form Editor                      │
│                  │                                   │
│ [All] [Proc]     │  [Collapsible sections per schema] │
│ [Syst] [ICs]     │  ┌─ metadata ───────────────────┐ │
│ [Dev] [Host]     │  │ name:    [____________]     │ │
│ [Cart] [Key]     │  │ bits: [___]  endian: [v]    │ │
│ [Ctrl]           │  └──────────────────────────────┘ │
│                  │  ┌─ registers ───────────────────┐ │
│ examples/        │  │ [+] Add register             │ │
│ ├─ processors/   │  │ ├─ r0: type=[v] bits=[_]    │ │
│ │  └ mc6809      │  │ └─ r1: type=[v] bits=[_]    │ │
│ ├─ systems/      │  └──────────────────────────────┘ │
│ │  └ apple2/     │  ┌─ instructions ────────────────┐ │
│ ...              │  │ behavior: [C code..........]  │ │
│                  │  │           [Prettify]          │ │
│                  │  └──────────────────────────────┘ │
├──────────────────┴───────────────────────────────────┤
│ Status: examples/processors/mc6809.yaml | Dirty       │
└──────────────────────────────────────────────────────┘
```

## Schema → File Matching (Convention-Based)

| File Pattern | JSON Schema |
|---|---|
| `examples/processors/*.yaml` | `processor_schema.json` |
| `examples/systems/**/*.yaml` | `system_schema.json` |
| `examples/ics/**/*.yaml` | `ic_schema.json` |
| `examples/devices/**/*.yaml` | `device_schema.json` |
| `examples/cartridges/**/*.yaml` | `cartridge_schema.json` |
| `examples/hosts/**/*hal*.yaml`, `*stub*.yaml`, `*_interactive*.yaml` | `host_schema.json` |
| `examples/hosts/**/host_keyboard_*.yaml`, `host_console_*.yaml` | `runtime_keyboard_map_schema.json` |
| `examples/hosts/**/host_controller_*.yaml` | `runtime_controller_map_schema.json` |
| `examples/hosts/**/*_keyboard_mapper*.yaml`, `*_console_mapper*.yaml` | `keyboard-keymapper.schema.json` |
| `examples/hosts/**/*_controller_mapper*.yaml` | `controller-mapper.schema.json` |

Any unmatched `.yaml` file triggers a "Schema not found" warning.

## C Code Field Detection

Fields whose name matches any of these are flagged as C code and get the specialized editor:

- `behavior` (instruction behavior, snippet bodies)
- `snippets` → values inside the map are C code
- `callback_handlers` → values are C code
- `handler_bodies` → values are C code
- `api_declarations` → C declarations
- `reset`, `reset_post` → C reset code
- `api_impl` → C implementation
- `initial` → C initializer expressions
- `args`, `returns` → C type names
- `type` (in state fields) → C type names

## C Code Prettify

1. User clicks "Prettify" button
2. Text is passed to `clang-format` via subprocess (`popen`)
3. Style: `{BasedOnStyle: LLVM, IndentWidth: 4, ColumnLimit: 100}`
4. Formatted text replaces editor content
5. If `clang-format` is not found: show warning, disable button

## Implementation Phases

### Phase 1 — Foundation
- `CMakeLists.txt` with FetchContent for yaml-cpp + nlohmann-json
- `src/main.cpp`: SDL2 + ImGui window, main loop, menu bar
- `src/app.h/.cpp`: App class, panel layout skeleton

### Phase 2 — Schema Registry + File Browser
- `src/schema_registry.h/.cpp`: Map YAML paths → schemas
- `src/file_browser.h/.cpp`: Tree widget with filter tabs
- Missing schema detection

### Phase 3 — Schema Parser
- `src/schema_parser.h/.cpp`: Parse all 10 JSON schemas
- Build `SchemaField` trees with C code detection

### Phase 4 — YAML Loader/Saver
- `src/yaml_loader.h/.cpp`: Load/save YAML via yaml-cpp
- Dirty state tracking, error handling

### Phase 5 — Form Renderer
- `src/form_renderer.h/.cpp`: Dynamic ImGui widget generation
- All type mappings, array add/remove, oneOf, additionalProperties

### Phase 6 — C Code Editor
- `src/c_code_editor.h/.cpp`: Multiline editor + clang-format
- Fallback for missing clang-format

### Phase 7 — Integration & Polish
- Save/save-as dialogs
- Dirty state indicator in status bar
- Validation feedback
- Cross-platform testing
- Error handling polish

## Edge Cases

- **No schema found**: Show error panel, offer raw text editing
- **YAML parse failure**: Show error with line number, raw text fallback
- **clang-format not found**: Warning, disable prettify button
- **File changed on disk**: Warn before overwrite
- **Deep nesting**: Scrollable regions, collapse/expand
- **Large arrays**: Lazy rendering, pagination for 50+ items
- **Read-only files**: Lock icon, disable save
- **Empty YAML files**: Show empty form
- **Unknown schema fields**: Show with warning indicator

## Tasks (Execution Tracking)

1. Create `tools/schema_editor/CMakeLists.txt` with FetchContent deps
2. Create `src/main.cpp` — SDL2 + ImGui boilerplate
3. Create `src/app.h/.cpp` — app state, panel orchestration
4. Create `src/schema_registry.h/.cpp` — file→schema mapping
5. Create `src/file_browser.h/.cpp` — tree + filter tabs
6. Create `src/schema_parser.h/.cpp` — JSON Schema → SchemaField tree
7. Create `src/yaml_loader.h/.cpp` — YAML read/write via yaml-cpp
8. Create `src/form_renderer.h/.cpp` — dynamic ImGui widget generation
9. Create `src/c_code_editor.h/.cpp` — multiline editor + clang-format
10. Integration wiring + final polish
