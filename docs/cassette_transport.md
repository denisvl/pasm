# Cassette Transport Layer

This document defines the first-pass shared cassette contract for PASM systems.

## Scope

This layer is intentionally split from per-machine integration. It provides:

- a shared cassette media schema: `schemas/cassette_schema.json`
- a shared transport device: `examples/devices/common/cassette_transport.yaml`
- a system-level cassette contract in `schemas/system_schema.json`
- host UI schema support for cassette picker font sizing in `schemas/host_schema.json`

It does not yet wire cassette read/write/motor lines for each machine. That work should be done per system on top of this transport.

## Media Model

Cassette media is described by a YAML sidecar validated by `cassette_schema.json`.

First-pass constraints:

- waveform container: `wav`
- load path: cassette media YAML points to a WAV or supported structured tape file
- load path: cassette media YAML points to a WAV file
- save path: recording also targets WAV
- normalized transport controls: play, pause, stop, record, volume, bass, treble

The cassette YAML is the durable metadata/configuration layer. The WAV file is the audio payload.

## Shared Device

`cassette_transport.yaml` is the common transport abstraction. It owns:

- transport mode
- motor state
- volume/bass/treble controls
- current input/output level
- currently loaded media path

Callbacks are intentionally generic:

- `load_media`
- `unload_media`
- `set_transport_mode`
- `set_motor`
- `set_volume`
- `set_bass`
- `set_treble`
- `sample_input`
- `push_output_sample`

Per-system cassette adapters should call into this device rather than directly handling host file UI.

## System Contract

Systems can declare a top-level `cassette` block:

```yaml
cassette:
  component: cassette_transport
  directory: examples/cassettes/zx_spectrum48k
  default_media: examples/cassettes/zx_spectrum48k/jet_set_willy.yaml
  allowed_extensions: [yaml, wav]
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

`components.cassette` should name the cassette component used by the system composition.

## Integration Guidance

Per-system follow-up work should stay thin:

1. expose machine tape input, tape output, and motor control in the relevant IC/device YAML
2. connect those lines to the shared `cassette_transport`
3. add host key/controller mappings for the `controls.*_action_id` actions from the subset actually supported by the active backend runtime, while avoiding machine-visible keys already claimed by the system keyboard map; do not force defaults for every action when the keyboard surface is weak
4. keep native file-format handling outside the shared transport
5. convert native format to/from normalized mono PCM around the adapter boundary

## First Systems To Wire

The existing codebase already has partial cassette-related hooks in:

- `trs80_model4`
- `cpc464`
- `zx_spectrum48k`

Those are the safest first targets for the next phase.
