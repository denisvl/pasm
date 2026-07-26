# Emulator Automation and Terminal Access Implementation Plan

## 1. Purpose

This document defines an implementation plan for adding automation, terminal access, structured observation, and programmable input to an existing emulator infrastructure.

The design is intentionally:

- **Emulator-architecture agnostic**
- **Compatible with partially or substantially implemented emulators**
- **Non-invasive to existing CPU, memory, video, audio, and input implementations**
- **Suitable for 8-bit computers and consoles**
- **Usable from Python, C, and Rust**
- **Suitable for automated testing, debugging, scripting, AI agents, remote control, and interactive terminal tools**

The automation layer must not require existing emulator systems to be redesigned around it. Instead, it should be introduced as an adapter and service layer over the emulator capabilities that already exist.

---

## 2. Primary Goals

The infrastructure must allow an external or embedded client to:

1. Observe the current emulated machine state.
2. Read text, character graphics, tiles, bitmaps, sprites, and other visible output in structured form.
3. Render machine output in a human-readable terminal representation.
4. Generate keyboard, controller, paddle, mouse, switch, and console input.
5. Control emulator execution.
6. Wait for deterministic emulated conditions.
7. Subscribe to emulator events.
8. Record and replay sessions.
9. Write portable automation scripts.
10. Use the same automation model across multiple emulated systems.
11. Preserve access to machine-specific capabilities.
12. Integrate without coupling the automation system to a particular emulator architecture.

---

## 3. Non-Goals

The first implementation does not need to:

- Replace existing debugger interfaces.
- Replace existing host input systems.
- Replace existing video rendering.
- Require all systems to expose semantic text immediately.
- Interpret arbitrary games or applications at a human semantic level.
- Provide OCR as the primary screen-reading method.
- Standardize every machine-specific feature into one lowest-common-denominator API.
- Require networking.
- Require a specific internal programming language.
- Require an emulator to run in a separate process.

---

## 4. Design Principles

### 4.1 Add adapters instead of rewriting systems

Existing emulator implementations should remain responsible for:

- CPU execution
- Memory access
- Video generation
- Audio generation
- Input emulation
- Timers
- Interrupts
- Media devices
- Save states
- Debugging

The automation layer should consume those capabilities through small adapter interfaces.

### 4.2 Separate observation from control

Observation APIs must not modify machine state.

Control APIs must clearly distinguish:

- Actions available to the original machine user
- Emulator-only operations
- Debugging operations
- Direct state modification

### 4.3 Preserve native information

The automation layer should not discard:

- Native character codes
- Screen memory addresses
- Video modes
- Palette indexes
- Tile identifiers
- Sprite identifiers
- Keyboard matrix locations
- Controller port information
- Device register values

Portable representations should be added alongside native data, not replace it.

### 4.4 Use emulated time

Automation timing, timeouts, input duration, and synchronization should normally use emulated time or frame numbers.

Wall-clock time should only be used for host integration and communication timeouts.

### 4.5 Make transport optional

The core automation API must work:

- In-process
- Through a command-line pipe
- Through sockets
- Through WebSocket
- Through a debugger front end
- Through test frameworks

The data model must not depend on any one transport.

### 4.6 Prefer structured state over image analysis

When the emulator already knows the underlying display state, expose that state directly.

Framebuffer analysis and OCR should be fallback mechanisms.

---

## 5. High-Level Architecture

```text
Existing emulator systems
    |
    | Existing CPU, memory, video, input, media, and execution APIs
    v
Machine Automation Adapter
    |
    v
Canonical Automation Core
    |
    +-- Observation service
    +-- Input service
    +-- Execution control service
    +-- Synchronization service
    +-- Event service
    +-- Recording and replay service
    |
    v
Language and transport bindings
    |
    +-- Python
    +-- C
    +-- Rust
    +-- JSON Lines
    +-- Interactive terminal
    +-- Test frameworks
    +-- Remote clients
```

---

## 6. Core Architectural Layers

## 6.1 Existing Emulator Layer

This is the emulator implementation that already exists.

No common internal design is assumed.

An emulator may use:

- Device objects
- Flat procedural code
- Message passing
- ECS-style components
- Shared memory
- Callbacks
- Polling
- Frame-based execution
- Cycle-based execution
- Instruction-based execution

The automation infrastructure must adapt to these implementations rather than dictate how they work internally.

---

## 6.2 Machine Automation Adapter

Each emulated system implements or registers an adapter.

The adapter translates existing emulator capabilities into the canonical automation model.

Example responsibilities:

- Report machine identity and capabilities.
- Capture current framebuffer output.
- Read native character or tile state.
- Enumerate input devices.
- Translate logical keys to machine-specific key matrix operations.
- Submit joystick or controller input.
- Pause, resume, reset, or step the emulator.
- Read or write memory when supported.
- Subscribe to frame, video, input, and execution events.
- Expose machine-specific properties.

The adapter should be thin. It should not duplicate core emulation logic.

---

## 6.3 Canonical Automation Core

The canonical core provides a machine-independent data and command model.

Recommended major services:

```text
Machine information
Screen observation
Input injection
Execution control
Inspection
Synchronization
Events
Recording and replay
Serialization
Capability discovery
```

The canonical core should be reusable by all language bindings and transports.

---

## 6.4 Language Bindings

The initial priority should be:

1. **Python**
2. **C**
3. **Rust**

All three should operate over the same stable C-compatible application binary interface.

The recommended approach is:

```text
Canonical automation implementation
        |
        v
Stable C ABI
        |
        +-- Direct C use
        +-- Python binding
        +-- Rust binding
```

This avoids maintaining three independent behavioral implementations.

---

## 7. Recommended Language Strategy

## 7.1 C ABI as the interoperability foundation

Even if the core emulator is written in C++, Rust, or another language, expose automation through a stable C ABI.

Advantages:

- Usable directly from C.
- Easy to bind from Python.
- Easy to bind from Rust.
- Avoids C++ ABI instability.
- Compatible with dynamic libraries.
- Compatible with embedded use.
- Compatible with foreign-function interfaces.
- Suitable for versioned structures and opaque handles.

Recommended conventions:

- Opaque handles
- Explicit ownership
- Versioned structures
- Fixed-width integer types
- Length-delimited strings and arrays
- No exceptions crossing the ABI
- Explicit result codes
- Threading rules documented per function
- Callbacks with user-data pointers
- Functions to free all library-owned allocations

Example:

```c
typedef struct emu_automation_machine emu_automation_machine_t;
typedef struct emu_automation_snapshot emu_automation_snapshot_t;

typedef enum emu_automation_result {
    EMU_AUTOMATION_OK = 0,
    EMU_AUTOMATION_UNSUPPORTED = 1,
    EMU_AUTOMATION_INVALID_ARGUMENT = 2,
    EMU_AUTOMATION_NOT_READY = 3,
    EMU_AUTOMATION_TIMEOUT = 4,
    EMU_AUTOMATION_INTERNAL_ERROR = 5
} emu_automation_result_t;
```

---

## 7.2 Python binding

Python should be the primary automation language.

Recommended implementation options:

- `ctypes` for the first proof of concept
- `cffi` for maintainable ABI bindings
- A CPython extension or `pybind11` only if high call volume later requires it

Prefer a Pythonic object layer over the raw C ABI.

Example target API:

```python
machine = automation.attach(emulator)

machine.reset(kind="cold")
machine.wait.screen_contains("READY.", timeout_frames=300)

machine.keyboard.type_text('10 PRINT "HELLO"\n')
machine.keyboard.type_text("RUN\n")

snapshot = machine.screen.snapshot(
    views=["text", "tiles", "framebuffer"]
)

print(snapshot.text.plain)
```

The Python package should support:

- Synchronous API
- Optional asynchronous API
- Context managers
- Type hints
- Dataclasses or immutable models
- Pytest helpers
- Session recording
- Scriptable waits
- JSON serialization

---

## 7.3 C API

The C interface should be complete enough for:

- Native automated tests
- Integration in emulator front ends
- External tools
- Embedded scripting hosts
- Low-overhead automation
- Other language bindings

The C API should not merely expose a command-string interface.

It should expose typed structures and functions.

Example:

```c
emu_automation_input_sequence_t *sequence = NULL;

emu_automation_input_sequence_create(&sequence);
emu_automation_input_sequence_add_text(sequence, "RUN\n", 4);
emu_automation_input_sequence_add_wait_frames(sequence, 2);

emu_automation_machine_submit_input(machine, sequence);
emu_automation_input_sequence_destroy(sequence);
```

---

## 7.4 Rust binding

The Rust API should wrap the C ABI with safe ownership and typed abstractions.

Recommended crate structure:

```text
emu-automation-sys
    Raw generated or handwritten C bindings

emu-automation
    Safe high-level Rust API

emu-automation-protocol
    Shared serializable data structures, where appropriate
```

Example target API:

```rust
let machine = Machine::attach(handle)?;

machine.reset(ResetKind::Cold)?;
machine
    .wait()
    .screen_contains("READY.")
    .timeout_frames(300)
    .run()?;

machine.keyboard().type_text("RUN\n")?;

let snapshot = machine.screen().snapshot(
    SnapshotRequest::new()
        .with_text()
        .with_tiles()
        .with_framebuffer(),
)?;
```

Rust callbacks should be converted into:

- Iterators
- Channels
- Streams
- Closures
- RAII subscription handles

---

## 8. Canonical Data Model

The canonical model should be versioned independently from transports and language bindings.

Initial top-level entities:

```text
MachineDescriptor
MachineCapabilities
ScreenSnapshot
ScreenRegion
TextGrid
TileGrid
Framebuffer
DisplayObject
InputDeviceDescriptor
InputSequence
EmulationCommand
WaitCondition
MachineEvent
NativeProperty
AutomationSession
```

---

## 9. Machine Description and Capability Discovery

Every adapter must expose a machine descriptor.

Suggested information:

```text
Machine identifier
System family
Model
Region
Video standard
CPU types
Configured memory
Available video views
Available input devices
Supported execution controls
Supported inspection features
Supported event types
Supported native property namespaces
Automation adapter version
```

Example:

```json
{
  "machine_id": "instance-1",
  "system": "example-8bit",
  "model": "model-a",
  "capabilities": {
    "screen_views": [
      "framebuffer",
      "text_grid",
      "tile_grid"
    ],
    "execution": [
      "pause",
      "resume",
      "reset",
      "step_instruction",
      "step_frame"
    ],
    "inspection": [
      "memory_read",
      "register_read"
    ]
  }
}
```

Clients must query capabilities rather than assume that all systems support every operation.

---

## 10. Screen Observation Model

A screen snapshot may contain several simultaneous representations.

```text
ScreenSnapshot
    |
    +-- Frame metadata
    +-- Video mode metadata
    +-- Framebuffer
    +-- Text regions
    +-- Tile regions
    +-- Bitmap regions
    +-- Display objects
    +-- Cursor
    +-- Native properties
    +-- Optional semantic elements
```

A system may expose one or several screen regions.

This is necessary for machines that mix video modes within one frame.

---

## 11. Framebuffer View

All systems should provide a framebuffer or rendered-frame view when possible.

Required metadata:

- Frame number
- Emulated timestamp
- Width
- Height
- Pixel format
- Visible area
- Pixel aspect ratio
- Video standard
- Interlace or field information
- Palette, when indexed
- Dirty region, when available

The framebuffer view is the universal fallback.

It should not be the only representation when structured state is available.

---

## 12. Text and Character-Cell View

Character-based screens should expose cell data directly.

Suggested cell fields:

```text
Native character code
Portable Unicode approximation
Glyph identifier
Foreground color
Background color
Attribute flags
Character-set identifier
Source memory address
Confidence of text mapping
```

The portable text view must distinguish:

- Exact native code
- Best-effort Unicode mapping
- Unknown or graphical characters

Unknown cells should remain representable.

Do not silently convert unknown graphics to spaces.

---

## 13. Tile and Glyph View

Tile-based and redefinable-character systems should expose:

- Grid dimensions
- Tile identifiers
- Tile attributes
- Pattern data
- Palette data
- Flip and rotation flags, when supported
- Source addresses
- Layer information
- Scroll offsets

A glyph dictionary should allow clients to identify visually identical patterns even when no textual meaning exists.

---

## 14. Bitmap Region View

Bitmap regions should expose:

- Region coordinates
- Native resolution
- Pixel or bitplane format
- Palette references
- Source memory information
- Scaling information
- Priority or layer information

This representation is more useful than only returning the final composited frame.

---

## 15. Display Object View

Expose hardware or emulator-known display objects where meaningful.

Examples:

- Sprites
- Player-missile graphics
- Text layers
- Tile maps
- Bitmap planes
- Cursors
- Borders
- Playfields

Suggested fields:

```text
Object identifier
Object type
Position
Dimensions
Visibility
Priority
Palette or color
Pattern reference
Source memory address
Native register references
```

The automation layer should not assign high-level meanings such as “player” or “enemy” unless supplied by a separate semantic analyzer.

---

## 16. Optional Semantic Observation

A later optional layer may interpret native screen data into semantic elements.

Possible roles:

- Prompt
- Menu
- Menu item
- Input field
- Dialog
- Score
- Status
- Error message
- Cursor
- Selection
- Unknown graphic

Semantic interpretation may be based on:

- Known software profiles
- Screen signatures
- Pattern matching
- User-provided rules
- External machine vision
- Language models

Semantic results must include confidence and provenance.

They must remain separate from factual emulator state.

---

## 17. Human-Readable Terminal Rendering

Provide a terminal renderer over the canonical screen model.

Supported output modes should include:

- Plain text
- ANSI text
- Unicode block graphics
- Character-grid dump
- Tile identifiers
- JSON
- Optional sixel or terminal graphics
- Screenshot export

Example:

```text
┌─ MACHINE · TEXT MODE · 40×25 ───────────────────┐
│READY.                                            │
│█                                                 │
│                                                  │
└──────────────────────────────────────────────────┘
Frame: 18422   State: Running
```

The renderer is a client of the canonical API, not part of the emulator core.

---

## 18. Input Model

Input must be represented as explicit events and sequences.

Supported categories:

- Keyboard keys
- Text typing
- Digital controllers
- Analog controllers
- Paddles
- Mouse
- Light pen
- Console switches
- Front-panel controls
- Media controls
- Emulator control commands

Each event should contain an execution time expressed as one of:

- Immediate at the next safe point
- Emulated timestamp
- Cycle number
- Frame number
- Delay from the previous event

---

## 19. Physical Key Input

Physical keyboard input should represent key down and key up separately.

Example:

```json
{
  "device": "keyboard",
  "action": "key_down",
  "control": "LEFT_SHIFT"
}
```

This must pass through the same machine-facing keyboard logic used by real host input whenever possible.

Use cases:

- Modifier combinations
- Keyboard matrix testing
- Games
- Function keys
- Non-text keys
- Key rollover
- Long key holds
- Keyboard scanning behavior

---

## 20. Logical Text Input

Logical text input is a convenience operation.

The adapter translates text into machine-specific physical key sequences.

Example:

```json
{
  "action": "type_text",
  "text": "RUN\n",
  "options": {
    "key_down_frames": 2,
    "inter_key_frames": 1
  }
}
```

The logical text API should support:

- Configurable key duration
- Configurable delay
- Native character mapping
- Error reporting for unsupported characters
- Optional replacement policy
- Optional clipboard-like fast input, when explicitly enabled

Fast text injection must be distinguished from authentic keyboard input.

---

## 21. Controller Input

Controller APIs should support:

- Button down
- Button up
- Button tap
- Axis value
- Direction state
- Timed holds
- Multi-control sequences
- Release all controls

Input descriptors must be machine-defined.

Examples:

```text
joystick_port_1.up
joystick_port_1.fire_1
paddle_0.axis
console.reset
console.select
keyboard.break
```

---

## 22. Emulator Control Plane

Emulator-only controls should be separate from machine-user input.

Initial commands:

- Pause
- Resume
- Cold reset
- Warm reset
- Step instruction
- Step cycle or device tick, when supported
- Step scanline, when supported
- Step frame
- Run for emulated duration
- Run until condition
- Set speed
- Save state
- Load state
- Capture snapshot
- Terminate session

These commands should be explicitly identifiable as emulator controls in logs and replay files.

---

## 23. Inspection and Debug Operations

Inspection should be optional and capability-driven.

Potential operations:

- Read memory
- Write memory
- Read CPU registers
- Write CPU registers
- Read device registers
- Read I/O ports
- Set breakpoints
- Set watchpoints
- Query disassembly
- Query memory maps
- Query interrupt state
- Query current instruction
- Query cycle and frame counters

Direct state modification should be disabled or separated in normal user-level automation modes.

---

## 24. Synchronization and Wait Conditions

Reliable automation requires explicit wait conditions.

Initial wait types:

```text
Wait for frame count
Wait for emulated duration
Wait for screen change
Wait for stable screen
Wait for text
Wait for text disappearance
Wait for tile pattern
Wait for memory value
Wait for program counter
Wait for breakpoint
Wait for event
Wait for machine state
Wait for media activity
```

Example:

```python
machine.wait.screen_contains(
    "READY.",
    timeout_frames=300,
    stable_frames=2
)
```

Timeouts should support:

- Frame count
- Emulated duration
- Cycle count
- Optional wall-clock fail-safe

---

## 25. Stable Screen Detection

A stable screen wait is useful for prompts, menus, and loading transitions.

Possible implementation:

1. Generate a hash of the selected canonical view.
2. Ignore cursor blinking or explicitly excluded fields.
3. Wait until the hash remains unchanged for a configured number of frames.
4. Return the final snapshot.

Selectable hash inputs:

- Full framebuffer
- Visible framebuffer region
- Text cells
- Tile cells
- Display objects
- Combined snapshot

---

## 26. Event System

The automation core should publish events.

Initial event categories:

```text
Machine started
Machine stopped
Machine reset
Machine paused
Machine resumed
Frame completed
Screen mode changed
Screen changed
Text cells changed
Tile cells changed
Cursor changed
Input submitted
Input consumed
Media inserted
Media ejected
Media activity
Breakpoint hit
Watchpoint hit
Error
Capability changed
```

Events should include:

- Event sequence number
- Frame number
- Emulated timestamp
- Event type
- Event-specific payload

Clients should be able to:

- Poll events
- Register callbacks
- Subscribe by type
- Consume events through language-native channels or iterators

---

## 27. Threading and Safe Points

Automation operations must not corrupt emulator state.

Define safe points such as:

- Between CPU instructions
- Between scheduler events
- At frame boundaries
- When paused
- At device-defined synchronization points

Each operation should declare or internally select its required safe point.

Examples:

```text
Input event: next input sampling opportunity
Memory read: next scheduler-safe point
Save state: paused or frame boundary
Frame capture: frame completion
Reset: scheduler-safe point
```

The automation core should queue commands when called from external threads.

---

## 28. Recording and Replay

Automation sessions should be recordable.

A session log may contain:

- Machine descriptor
- Emulator build identifier
- ROM hashes
- Media hashes
- Initial configuration
- Random seeds
- Input events
- Emulator commands
- Wait results
- State hashes
- Optional snapshots
- Errors
- Final result

Replay modes:

1. Input-only replay
2. Deterministic verification replay
3. Debug replay with snapshots
4. Interactive replay

Recommended serialization for the initial implementation:

- JSON Lines for inspectability
- Optional compact binary format later

---

## 29. Determinism Support

Automation should expose determinism-relevant information.

Examples:

- Random seed
- Initial state hash
- ROM and media hashes
- Emulator version
- Machine configuration
- Timing mode
- Input event timestamps
- Frame hashes
- Audio hashes, optionally

A deterministic test should be able to verify:

```text
Same emulator build
Same machine configuration
Same media
Same initial state
Same input sequence
Same resulting checkpoints
```

---

## 30. Transport-Neutral Command Model

Define commands and responses independently from transport.

Every command should have:

- Command identifier
- Command type
- Parameters
- Submission timestamp
- Completion status
- Error code
- Optional result payload

The first external transport should be JSON Lines over standard input and output.

Example request:

```json
{"id":1,"method":"machine.describe"}
{"id":2,"method":"screen.snapshot","params":{"views":["text","framebuffer"]}}
{"id":3,"method":"input.type_text","params":{"text":"RUN\n"}}
{"id":4,"method":"wait.screen_contains","params":{"text":"READY.","timeout_frames":300}}
```

Example response:

```json
{"id":3,"result":{"accepted":true}}
```

Example event:

```json
{"event":"frame.completed","frame":1822}
```

---

## 31. Interactive Terminal Client

Create a terminal client as an independent executable.

Initial commands:

```text
machine info
machine capabilities
screen
screen text
screen tiles
screen json
screen save
key press <key>
key down <key>
key up <key>
type <text>
controller <device> <control> <action>
pause
resume
reset
step instruction
step frame
run frames <count>
wait text <text>
wait stable
memory read <address> <length>
events watch
record start
record stop
```

The terminal client should connect through:

- In-process mode
- JSON Lines child process mode
- Local socket mode, later

---

## 32. Integration Strategy for Existing Emulator Systems

Existing systems may have different levels of available structured information.

Use an incremental adapter maturity model.

### Level 0: Execution only

Capabilities:

- Pause
- Resume
- Reset
- Step
- Run

### Level 1: Framebuffer and basic input

Capabilities:

- Capture framebuffer
- Submit keyboard events
- Submit controller events
- Frame events

### Level 2: Structured display

Capabilities:

- Text cells
- Tiles
- Sprites
- Cursor
- Video mode metadata

### Level 3: Inspection

Capabilities:

- Memory
- Registers
- Device state
- Breakpoints

### Level 4: Semantic and software-aware access

Capabilities:

- Prompt detection
- Menu detection
- Known application profiles
- Symbolic test helpers

No emulator must implement all levels before becoming usable.

---

## 33. Adapter Integration Patterns

Support several adapter styles.

### 33.1 Direct adapter

The adapter calls existing emulator classes or functions directly.

Best for:

- Emulators under active development
- In-process use
- Native tests

### 33.2 Callback adapter

The emulator registers callbacks for automation services.

Best for:

- C-style systems
- Decoupled modules
- Plugin architectures

### 33.3 Snapshot adapter

The emulator periodically provides state snapshots.

Best for:

- Systems where direct object access is undesirable
- Cross-thread observation
- Remote execution

### 33.4 Message adapter

Automation commands enter the emulator through its existing message queue.

Best for:

- Event-driven emulators
- Multi-threaded front ends
- Remote or sandboxed execution

The canonical API should not expose which integration pattern is used internally.

---

## 34. Screen Adapter Implementation Guidance

Each system-specific adapter should identify the most authoritative screen source.

Priority order:

1. Native video device state
2. Video memory and registers
3. Emulator-generated intermediate display data
4. Final framebuffer
5. OCR or image recognition

Examples of authoritative sources:

- Character RAM
- Color RAM
- Tile maps
- Pattern tables
- Attribute tables
- Display lists
- Sprite registers
- Cursor registers
- Video mode registers

---

## 35. Input Adapter Implementation Guidance

Prefer injecting automation input at the same abstraction level as host input.

Recommended path:

```text
Automation input
    |
    v
Existing host-to-machine input mapping boundary
    |
    v
Keyboard matrix, controller port, or input device
```

Avoid bypassing the emulated input hardware unless explicitly using a fast or debug injection mode.

The adapter should expose whether an input path is:

- Authentic
- Accelerated
- Debug-only
- Direct state modification

---

## 36. Error Model

Use stable machine-readable error codes.

Initial categories:

```text
Unsupported operation
Invalid argument
Invalid state
Machine not running
Machine already running
Timeout
Mapping unavailable
Character unsupported
Device unavailable
Resource unavailable
Transport error
Serialization error
Adapter error
Internal error
```

Errors should include:

- Stable code
- Human-readable message
- Operation
- Optional machine-specific detail
- Optional native error code

---

## 37. Versioning

Version the following independently:

- C ABI
- Canonical data model
- JSON protocol
- Recording format
- Adapter interface
- Language packages

Use explicit size and version fields for ABI structures.

Example:

```c
typedef struct emu_automation_machine_descriptor {
    uint32_t struct_size;
    uint32_t struct_version;
    const char *system_id;
    const char *model_id;
} emu_automation_machine_descriptor_t;
```

New fields should be append-only whenever possible.

---

## 38. Security and Access Modes

Define capability profiles.

Suggested modes:

### User automation

- Screen reading
- Authentic input
- Pause and resume
- Reset
- Save screenshots

### Test automation

- User automation capabilities
- Deterministic stepping
- Save states
- Wait conditions
- Memory reads

### Debug automation

- Test capabilities
- Memory writes
- Register writes
- Breakpoints
- Device inspection

### Restricted remote mode

- Explicitly configured subset
- No direct memory modification by default
- Resource and command limits

---

## 39. Proposed Repository Structure

```text
automation/
    include/
        emu_automation.h
        emu_automation_adapter.h

    core/
        machine_registry
        command_queue
        screen_model
        input_model
        wait_engine
        event_bus
        recorder
        serializer

    protocol/
        json_lines
        schemas

    adapters/
        common
        systems/
            <system_a>
            <system_b>

    clients/
        terminal
        recorder
        replay

    bindings/
        python/
        rust/
        c_examples/

    tests/
        unit/
        integration/
        protocol/
        deterministic/
        adapter_conformance/

    docs/
        architecture.md
        c_api.md
        python_api.md
        rust_api.md
        adapter_guide.md
        protocol.md
```

This is illustrative and may be mapped to the existing repository structure.

---

# 40. Implementation Phases

## Phase 0: Inventory Existing Emulator Capabilities

### Objective

Identify reusable integration points without changing system architecture.

### Tasks

- Catalogue emulator instances and lifecycle management.
- Identify execution control functions.
- Identify framebuffer access.
- Identify frame boundaries.
- Identify host input injection paths.
- Identify keyboard matrix and controller APIs.
- Identify save-state support.
- Identify memory and register inspection support.
- Identify event or callback systems.
- Identify thread ownership and safe points.
- Identify how each machine exposes video state.
- Document differences among systems.
- Select one representative initial system.

### Deliverables

- Emulator capability inventory
- Initial adapter integration map
- Threading and safe-point document
- Selected pilot system
- Gap list

### Exit criteria

- At least one system has identified integration points for execution, video, and input.
- No major emulator rewrite is required for the pilot.

---

## Phase 1: Define the Canonical Model and C ABI

### Objective

Establish a stable minimum automation contract.

### Initial scope

- Machine descriptor
- Capabilities
- Frame metadata
- Framebuffer snapshot
- Input device descriptors
- Key and controller events
- Pause
- Resume
- Reset
- Step frame
- Run frames
- Error model
- Opaque machine handles

### Tasks

- Define ABI conventions.
- Define ownership rules.
- Define result codes.
- Define versioned structures.
- Define command submission behavior.
- Define safe-point behavior.
- Define callback rules.
- Write a minimal adapter interface.
- Create ABI conformance tests.

### Deliverables

- `emu_automation.h`
- `emu_automation_adapter.h`
- ABI specification
- Mock adapter
- Unit tests

### Exit criteria

- A mock machine can be controlled through the C API.
- ABI tests pass from both C and C++ callers.

---

## Phase 2: Integrate the First Existing Emulator

### Objective

Prove that automation can be layered over an existing implemented system.

### Initial features

- Attach or register a running emulator instance.
- Query machine information.
- Pause and resume.
- Reset.
- Step one frame.
- Run a fixed number of frames.
- Read framebuffer.
- Submit one keyboard key.
- Submit one controller action.
- Receive frame-completed events.

### Tasks

- Implement the pilot adapter.
- Add command queuing if the emulator runs on another thread.
- Define safe points.
- Reuse existing host input path.
- Reuse existing framebuffer.
- Add a minimal test application.

### Deliverables

- First system adapter
- C example program
- Integration tests
- Adapter implementation notes

### Exit criteria

- A C program can reset the machine, submit input, run frames, and capture output.
- Existing non-automation emulator behavior remains unchanged.

---

## Phase 3: Python Binding and Test API

### Objective

Make Python the primary automation environment.

### Tasks

- Bind the C ABI.
- Add Pythonic wrappers.
- Add typed snapshots and descriptors.
- Add input sequence helpers.
- Add context-managed subscriptions.
- Add exceptions mapped from result codes.
- Add pytest fixtures.
- Add example scripts.
- Add screenshot export.
- Add session lifecycle helpers.

### Initial Python API

```python
with automation.attach(instance) as machine:
    machine.reset("cold")
    machine.keyboard.tap("RETURN")
    machine.run.frames(10)
    frame = machine.screen.framebuffer()
```

### Deliverables

- Python package
- Type hints
- Pytest plugin or fixtures
- Example automation scripts
- Python API documentation

### Exit criteria

- The pilot emulator can be driven entirely from Python.
- A pytest test can launch or attach to a machine and verify output.

---

## Phase 4: Structured Screen Model

### Objective

Expose machine-readable text, tiles, and display state.

### Tasks

- Define screen regions.
- Define text grids.
- Define tile grids.
- Define glyph dictionaries.
- Define bitmap regions.
- Define display objects.
- Preserve native codes and addresses.
- Add screen snapshot requests.
- Add human-readable text rendering.
- Implement structured views for the pilot system.
- Define fallback behavior for unsupported modes.

### Deliverables

- Canonical screen structures
- Structured screen C API
- Python structured screen API
- Pilot structured video adapter
- Terminal screen renderer
- Conformance tests

### Exit criteria

- At least one native text or tile mode is readable without OCR.
- Unknown graphical cells remain machine-readable.
- A human-readable terminal representation is available.

---

## Phase 5: Input Sequences and Timing

### Objective

Support realistic, deterministic input.

### Tasks

- Define key down and key up events.
- Define controller button and axis events.
- Define relative and absolute timing.
- Define input sequences.
- Add logical text typing.
- Add per-machine character maps.
- Add configurable press and delay durations.
- Add release-all operation.
- Record accepted and applied input timestamps.
- Add deterministic input replay tests.

### Deliverables

- Input sequence API
- Text mapping interface
- Python sequence builder
- Rust sequence builder
- Replayable input logs

### Exit criteria

- Text can be typed through authentic key events.
- Key combinations and timed holds work.
- The same sequence produces the same event schedule.

---

## Phase 6: Wait Engine and Synchronization

### Objective

Make automation reliable without arbitrary sleeps.

### Tasks

- Define wait-condition interface.
- Implement wait for frames.
- Implement wait for emulated duration.
- Implement wait for screen change.
- Implement stable-screen wait.
- Implement text matching.
- Implement event matching.
- Add timeout handling.
- Return diagnostic snapshots on timeout.
- Allow conditions to be composed.

### Example composition

```python
machine.wait.any(
    machine.conditions.screen_contains("READY."),
    machine.conditions.screen_contains("ERROR")
).timeout_frames(300).run()
```

### Deliverables

- Wait engine
- Initial condition set
- Python fluent API
- Timeout diagnostics
- Unit and integration tests

### Exit criteria

- Automation tests no longer require fixed wall-clock sleeps.
- Failed waits provide enough state to diagnose the failure.

---

## Phase 7: Event System

### Objective

Allow clients to react to emulator activity.

### Tasks

- Define event envelope.
- Implement event sequence numbers.
- Implement frame events.
- Implement reset and execution-state events.
- Implement screen-change events.
- Implement input events.
- Add polling API.
- Add callback API.
- Add Python iterator and async iterator.
- Add Rust channel or stream wrapper.
- Document callback thread rules.

### Deliverables

- Event bus
- C event API
- Python event API
- Rust event API
- Event tracing tool

### Exit criteria

- Clients can observe frame and state changes without polling full snapshots.
- Event order is deterministic within an emulator session.

---

## Phase 8: JSON Lines Protocol and Terminal Client

### Objective

Enable external process automation and interactive use.

### Tasks

- Define JSON protocol version.
- Map canonical commands to protocol methods.
- Map events to protocol messages.
- Implement standard input/output transport.
- Implement request identifiers.
- Implement error responses.
- Implement terminal client.
- Add JSON schema or protocol documentation.
- Add protocol test suite.

### Deliverables

- JSON Lines server
- Terminal client
- Protocol specification
- Example shell and Python clients
- Golden protocol tests

### Exit criteria

- An emulator can be controlled from another process.
- The terminal client can show screen output and submit input.

---

## Phase 9: Rust Binding

### Objective

Provide a safe native Rust automation API.

### Tasks

- Create raw FFI crate.
- Generate or maintain bindings.
- Create safe handle wrappers.
- Implement ownership and lifetime rules.
- Wrap snapshots and descriptors.
- Wrap event subscriptions.
- Implement input sequence builders.
- Add serde support where appropriate.
- Add examples and tests.

### Deliverables

- `emu-automation-sys`
- `emu-automation`
- Rust examples
- Rust API documentation

### Exit criteria

- Rust clients can perform all capabilities available through the C ABI.
- No unsafe operations are required in normal client code.

---

## Phase 10: Recording, Replay, and Determinism

### Objective

Support reproducible test execution and debugging.

### Tasks

- Define recording format.
- Record machine configuration.
- Record ROM and media hashes.
- Record input events.
- Record emulator commands.
- Record wait outcomes.
- Add checkpoint hashes.
- Implement replay.
- Implement verification mode.
- Add divergence diagnostics.
- Add optional snapshot capture on divergence.

### Deliverables

- Recorder
- Replay engine
- Determinism verifier
- Session inspection tool
- Regression tests

### Exit criteria

- A recorded session can be replayed.
- Deterministic divergence is detected and reported at a useful checkpoint.

---

## Phase 11: Inspection and Debug Access

### Objective

Expose optional low-level diagnostics without contaminating normal automation.

### Tasks

- Add memory read and write interfaces.
- Add register access.
- Add device property access.
- Add breakpoint and watchpoint APIs.
- Define machine-specific namespaces.
- Add access profiles.
- Add debug event types.
- Integrate with existing debugger infrastructure.

### Deliverables

- Inspection API
- Debug capability profile
- Native namespace conventions
- Python and Rust debug wrappers

### Exit criteria

- Existing debugger functionality can be accessed through the automation layer where appropriate.
- User-level automation can run without debug permissions.

---

## Phase 12: Multi-System Expansion

### Objective

Add adapters without changing the canonical core for every machine.

### Tasks per system

- Implement descriptor and capabilities.
- Implement execution controls.
- Implement framebuffer access.
- Implement input devices.
- Implement structured screen views where feasible.
- Implement native properties.
- Add adapter conformance tests.
- Add one smoke automation scenario.
- Document unsupported features.

### Recommended validation systems

Select systems with different video and input architectures, such as:

- A machine with native text mode
- A machine with bitmap-only display
- A machine with tile and sprite hardware
- A machine with mixed display-list modes
- A console with controllers but no keyboard

### Exit criteria

- At least three substantially different systems use the same automation core.
- No system-specific logic has leaked into the generic language bindings.

---

## Phase 13: Optional Semantic Layer

### Objective

Add higher-level interpretation without modifying factual screen observation.

### Tasks

- Define semantic element schema.
- Define confidence and provenance.
- Add rule-based recognizers.
- Add screen signature support.
- Add software profiles.
- Add optional external analyzer interface.
- Add semantic wait conditions.
- Add profile packaging and versioning.

### Deliverables

- Semantic analyzer API
- Initial recognizer framework
- Example software profile
- Semantic wait support

### Exit criteria

- Semantic data can be enabled or disabled independently.
- Native snapshots remain available as the source of truth.

---

# 41. Testing Strategy

## 41.1 Unit tests

Test:

- Data structure validation
- ABI ownership
- Serialization
- Input sequence scheduling
- Wait conditions
- Event ordering
- Error mapping
- Hashing
- Replay parsing

## 41.2 Mock machine tests

Create a deterministic mock machine with:

- Character display
- Frame counter
- Keyboard input
- Controller input
- Memory
- Scripted state transitions

Use it to test the automation core without a full emulator.

## 41.3 Adapter conformance tests

Every adapter should pass a common suite.

Example checks:

- Descriptor is valid.
- Capability claims match behavior.
- Frame number is monotonic.
- Pause stops execution.
- Step frame advances exactly one frame.
- Input descriptors use unique identifiers.
- Unsupported operations return the correct result.
- Snapshots remain valid for their documented lifetime.
- Events are ordered.

## 41.4 Integration tests

Test complete flows:

```text
Reset
Wait for boot screen
Type command
Wait for output
Capture snapshot
Verify expected state
```

## 41.5 Deterministic tests

Repeat the same test multiple times and compare:

- Frame hashes
- Screen hashes
- Memory checkpoints
- Event sequences
- Final state

## 41.6 Cross-language tests

Run equivalent scenarios from:

- C
- Python
- Rust
- JSON Lines

Verify that they produce equivalent canonical commands and outcomes.

---

# 42. Documentation Plan

Create the following documentation:

```text
Architecture overview
Adapter implementation guide
C ABI reference
Python user guide
Rust user guide
JSON protocol reference
Terminal client guide
Screen model guide
Input timing guide
Wait-condition guide
Recording and replay guide
Adapter conformance guide
Machine-specific capability notes
```

Include complete examples for:

- Boot and wait
- Type text
- Press a key combination
- Move a joystick
- Capture a structured screen
- Wait for screen text
- Step execution
- Record and replay
- Read memory in debug mode

---

# 43. Initial Minimum Viable Product

The first usable release should include:

1. Stable C ABI
2. One existing emulator adapter
3. Machine capability discovery
4. Pause, resume, reset, and frame stepping
5. Framebuffer capture
6. Keyboard key down and key up
7. Controller button input
8. Python binding
9. Wait for frames
10. Frame-completed events
11. JSON Lines transport
12. Minimal terminal client
13. Adapter conformance tests

Structured text and tile reading should follow immediately after this minimum foundation.

---

# 44. Recommended First Automation Scenario

Use a simple scenario that exercises the whole vertical path.

```text
Attach to machine
Cold reset
Run until first stable screen
Capture framebuffer
Read text or tile view, if supported
Press one key
Run a fixed number of frames
Capture another snapshot
Verify that output changed
Record the session
Replay the session
```

The scenario should be implemented in:

- C
- Python
- Rust
- JSON Lines

This becomes the initial cross-language reference test.

---

# 45. Recommended Priority Order

## Priority 1: Foundation

- Canonical model
- C ABI
- Pilot adapter
- Framebuffer
- Authentic key and controller input
- Execution control
- Safe-point command queue

## Priority 2: Python automation

- Python package
- Pytest integration
- Input helpers
- Snapshot helpers
- Basic waits

## Priority 3: Structured observation

- Text grids
- Tile grids
- Glyphs
- Display objects
- Human-readable terminal renderer

## Priority 4: Reliable synchronization

- Screen matching
- Stable-screen waits
- Event waits
- Timeout diagnostics

## Priority 5: External automation

- JSON Lines
- Terminal client
- Remote process control

## Priority 6: Rust support

- Raw FFI crate
- Safe wrapper
- Event and sequence APIs

## Priority 7: Reproducibility and debugging

- Recording
- Replay
- State hashes
- Inspection APIs
- Breakpoints

## Priority 8: Semantic interpretation

- Profiles
- Recognizers
- AI integrations

---

# 46. Key Risks and Mitigations

## Risk: Automation becomes coupled to one emulator architecture

**Mitigation:** Keep the adapter interface small and capability-based.

## Risk: The common model becomes a lowest common denominator

**Mitigation:** Preserve native fields and machine-specific namespaces.

## Risk: Input bypasses authentic hardware behavior

**Mitigation:** Route default automation input through existing host-to-machine input paths.

## Risk: Tests depend on wall-clock timing

**Mitigation:** Use emulated time, frames, events, and conditions.

## Risk: Screen extraction relies on OCR

**Mitigation:** Prefer video memory, registers, tiles, glyphs, and native device state.

## Risk: Language bindings diverge

**Mitigation:** Make the stable C ABI the single behavioral foundation.

## Risk: Threading causes race conditions

**Mitigation:** Queue external commands and execute them at documented emulator safe points.

## Risk: Initial scope becomes too large

**Mitigation:** Start with framebuffer, input, execution control, Python, and one adapter.

## Risk: Existing systems require intrusive modifications

**Mitigation:** Allow direct, callback, snapshot, and message-based adapter patterns.

---

# 47. Completion Criteria

The infrastructure can be considered mature when:

- Multiple emulator systems use the same automation core.
- Python, C, and Rust clients have equivalent functional access.
- Automation can read structured display state where the emulator knows it.
- Automation can submit authentic machine input.
- Tests synchronize without arbitrary sleeps.
- External process control is supported.
- Sessions can be recorded and replayed.
- Deterministic divergence can be detected.
- Existing emulator functionality remains usable without the automation layer.
- New systems can implement adapters without modifying the canonical core.
