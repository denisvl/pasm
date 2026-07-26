# Cassette Runtime

This document describes the current shared cassette runtime contract in PASM.

## Scope

The cassette stack is split into three layers:

1. system-level configuration in `schemas/system_schema.json`
2. reusable source-type definitions in `schemas/cassette_source_schema.json`
3. shared transport/device implementations under `examples/devices/common/`

This is separate from per-machine electrical integration. Each machine still has
to wire its cassette input, output, and motor lines into its own IC/device YAML.

## Runtime Model

There are two distinct concepts:

- transport/player state:
  play, pause, stop, record, volume, bass, treble, motor, current time
- source selection:
  which backing source supplies the tape signal

The transport contract is machine-agnostic. The machine sees callbacks like
`sample_input`, `set_motor`, and `push_output_sample`. It should not know
whether the source is:

- a tape file backed by a WAV payload
- a live line-in capture stream
- a future format-specific backend

## Source Types

Reusable source types are defined by YAML files validated by
`schemas/cassette_source_schema.json`.

Current shared source definitions:

- `examples/cassette_sources/wav_file.yaml`
- `examples/cassette_sources/cas_file.yaml`
- `examples/cassette_sources/cdt_file.yaml`
- `examples/cassette_sources/line_in.yaml`

These are not per-tape files. They describe a source class.

Example:

```yaml
metadata:
  id: wav_file
  type: cassette_source
  model: common_wav_file_source

source:
  kind: file
  label: Tape File
  source_component: cassette_wav_source
  allowed_extensions: [yaml, wav]
```

Amstrad CPC also has a dedicated CDT source type:

```yaml
metadata:
  id: cdt_file
  type: cassette_source
  model: common_cdt_file_source

source:
  kind: file
  label: CDT Tape
  source_component: cassette_cdt_source
  allowed_extensions: [cdt]
```

Atari 8-bit systems can expose a dedicated CAS source type:

```yaml
metadata:
  id: cas_file
  type: cassette_source
  model: common_cas_file_source

source:
  kind: file
  label: CAS Tape
  source_component: cassette_cas_source
  allowed_extensions: [cas]
```

Current shared source backends:

- `examples/devices/common/cassette_wav_source.yaml`
- `examples/devices/common/cassette_cas_source.yaml`
- `examples/devices/common/cassette_cdt_source.yaml`
- `examples/devices/common/cassette_line_in_source.yaml`

Those backends expose the callback surface used by the transport/runtime split:
source selection, media load/unload, transport state updates, sample input,
playback/output hooks, and query callbacks for timing and decoded edge data.

## System Contract

Systems declare a top-level `cassette` block and may provide `sources`.

```yaml
cassette:
  component: cassette_transport
  directory: examples/cassettes/zx_spectrum48k
  default_media: examples/cassettes/zx_spectrum48k/jet_set_willy.yaml
  allowed_extensions: [yaml, wav]
  sources:
    - source_type: ../../cassette_sources/wav_file.yaml
      component: cassette_transport
    - source_type: ../../cassette_sources/line_in.yaml
      component: cassette_transport
  controls:
    picker_action_id: EMU_CASSETTE_PICKER
    play_action_id: EMU_CASSETTE_PLAY
    pause_action_id: EMU_CASSETTE_PAUSE
    stop_action_id: EMU_CASSETTE_STOP
    record_action_id: EMU_CASSETTE_RECORD
    volume_up_action_id: EMU_CASSETTE_VOL_UP
    volume_down_action_id: EMU_CASSETTE_VOL_DOWN
    bass_up_action_id: EMU_CASSETTE_BASS_UP
    bass_down_action_id: EMU_CASSETTE_BASS_DOWN
    treble_up_action_id: EMU_CASSETTE_TREBLE_UP
    treble_down_action_id: EMU_CASSETTE_TREBLE_DOWN
```

Rules:

- `source_type` is resolved relative to the system YAML file
- source-type defaults are merged first
- inline source fields override the source-type defaults
- `component` identifies the transport/player component
- `source_component` identifies the backing source/backend component contract
- `kind: file` entries participate in extension-based file selection
- `kind: line_in` creates a synthetic picker entry for live capture

When `source_component` names a common device under
`examples/devices/common/`, the loader auto-enrolls that backend device into
composition. System YAML does not need to duplicate it under
`components.devices`.

`components.cassette` still names the cassette component visible to the system
composition.

## Picker Behavior

The cassette picker scans `cassette.directory` and maps each file to a source by
extension. It also injects synthetic entries for non-file sources such as
`Line In`.

At runtime:

- file entries call `load_media(path)`
- line-in entries also call `load_media(path)`, but the active source
  descriptor marks them as `kind: line_in`

That keeps the picker contract uniform while allowing source-specific handling
behind the callback surface. The transport/device decides what backend to open
from the selected source kind and source model, not from a magic filename.

## Media Model

Cassette media sidecars are still validated by `schemas/cassette_schema.json`.

Current supported payload path:

- YAML sidecar pointing at a WAV file
- direct WAV file selection
- direct CAS file selection for Atari-style cassette images
- direct CDT file selection for CPC-style TZX/CDT tape images

Recording currently targets WAV output as well.

Current shared source models:

- `common_wav_file_source`
- `common_cas_file_source`
- `common_cdt_file_source`
- `common_line_in_source`

The common cassette transports reject unsupported source models at load time.
That is intentional: new source types should add a new backend path instead of
accidentally falling through an implicit local implementation.

## Host Integration

Live line-in capture currently depends on the SDL host-audio path.

Relevant behavior:

- SDL builds now allow capture-device open requests
- the shared line-in path requests mono signed 16-bit capture
- Linux and Windows are both expected to use the SDL audio backend here

The GLFW and stub backends are not the reference path for capture.

## Transport Contract

The shared cassette callbacks remain:

- `load_media`
- `unload_media`
- `set_transport_mode`
- `set_motor`
- `set_volume`
- `set_bass`
- `set_treble`
- `set_playhead_fp`
- `sample_input`
- `push_output_sample`
- `query_selected_source_kind`
- `query_selected_source_model`

Per-system adapters should call these callbacks. They should not own picker UI,
file-extension dispatch, or live-input device management.

The selected-source queries let adapters make backend-specific decisions
without inferring source identity from file extensions or synthetic paths.

The `select_source` callback now carries:

1. source kind
2. source index
3. source model
4. source component id

That lets the transport/device path know which backend component is meant to
own the source, even before file parsing is delegated.

The backend IDs are now active runtime ownership points. In normal configured
systems:

- `cassette_wav_source` owns WAV media load/unload, timing queries, and WAV
  `sample_input`
- `cassette_cas_source` owns CAS media presence, transport state, and playhead
  timing for machine adapters that decode CAS themselves
- `cassette_cdt_source` owns CDT media load/unload, block decoding, timing
  queries, and CDT `sample_input`
- `cassette_line_in_source` owns line-in open/close, timing/state queries, and
  line-in `sample_input`
- the shared cassette transports own picker/overlay control flow, transport
  actions, signal emission, and recorder plumbing

The shared transports now delegate source-backed operations to the selected
backend component:

- `select_source`
- `load_media`
- `unload_media`
- `set_transport_mode`
- `set_motor`
- `set_volume`
- `set_bass`
- `set_treble`
- `set_playhead_fp`

The shared transports also perform backend-first delegation for media-derived
queries:

- `query_transport_state`
- `query_edge_count`
- `query_edge_initial_level`
- `query_edge_fp`
- `query_sample_rate`
- `query_playhead_samples`
- `query_leader_start_sample`
- `query_leader_start_index`
- `query_leader_end_sample`
- `query_leader_end_index`
- `query_playback_level`
- `query_volume_percent`

If the selected source backend is nonlocal, the transport treats it as the real
owner for those callbacks.

Backend ownership is now mandatory for cassette media handling in the shared
transport path. The common transports no longer implement a local WAV or
line-in fallback.

## What Is Still Machine-Specific

The following remains per-system work:

1. expose tape input, tape output, and motor lines in the machine IC/device YAML
2. connect those lines to the cassette component used by the system
3. choose control mappings that do not conflict with machine-visible keys
4. decide whether motor control is hardware-driven for that machine

## Current Limitation

Machine-specific cassette adapters can still do additional machine-local
decoding after the shared source backend provides signal/media state. That is
separate from the shared transport/runtime split.

Notable examples:

- `examples/devices/c64/c64_datasette.yaml`
  still owns datasette-specific pulse/decoder behavior
- `examples/devices/atari800xl/atari800xl_cassette_adapter.yaml`
  still owns Atari-specific cassette decoding behavior

Those are machine adapters, not shared transport fallbacks.
  still performs Atari-specific higher-level FSK decode after transport load

The following adapters are now only transport clients, not backend owners:

- Apple II
- BBC Micro
- CoCo 1
- CPC 464
- MSX 1
- ZX Spectrum 48K

That means the next extraction step should target the shared transport pair
first, then C64 datasette, then Atari 800XL.

TODO

- ZX Spectrum 48K WAV turbo-loader compatibility:
  the current generic WAV-to-EAR path is good enough for standard ROM-style
  loads, but not yet faithful enough for custom fast loaders such as
  `Pyjamarama`. Real hardware did not need game-specific handling here; the
  emulator needs a more accurate general tape input model so both ROM loaders
  and custom loaders can read the same analog-derived EAR signal. The next pass
  should focus on signal-faithfulness, not per-game special cases.
