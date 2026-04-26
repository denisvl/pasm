# PASM Keyboard Mapper UI

Desktop editor for keymapper/image overlays and runtime host keyboard bindings.

## Run (Default - C++/ImGui)

```bash
scripts/run_keymapper_ui.sh
```

Explicit full C++/ImGui UI:

```bash
scripts/run_keymapper_ui_cpp.sh
```

Per-system presets:

```bash
scripts/run_keymapper_ui_cpc64_cpp.sh
scripts/run_keymapper_ui_apple2_cpp.sh
scripts/run_keymapper_ui_atari800xl_cpp.sh
```

Current C++/ImGui app status:
- Real right-side UI panel (not title-only)
- Scancode-first key diagnostics (`SDL scancode` + name + mapped target)
- Canvas/image + bbox rendering, selection, multi-select toggle, drag move, zoom/pan
- Primary selected resize handle (bottom-right)
- Resize cursor feedback on handle hover
- Auto-scroll canvas while dragging/resizing near edges
- Eyedropper from image pixels (`Pick Color From Image`) with cursor feedback
- Explicit zoom controls in canvas (`Fit`, `-`, `+`, slider) + mouse wheel zoom
- Per-field X/Y/W/H and R/G/B propagation to all selected keys
- Key ID rename flow (`Rename Key ID`) with host-map `mapper_key_id` propagation
- Host bindings list + bindings-for-selected list
- Binding target editor (`mapper` / `system` / `emulator`) for selected host binding
- System keys panel (add/update/remove, visual feedback flag)
- System keys panel can create/remove system-key bbox directly
- Selecting a system key auto-selects its bbox when present
- Map selected host binding directly to selected system key
- System alias capture path (press host key to map to selected system key)
- Context menu on right-click (align/size/distribute)
- Undo/redo (`Ctrl+Z` / `Ctrl+Y`)
- Alias capture flow (Add Host Alias, Esc to cancel, Remove Selected Alias)
- Save mapper + save host map + reload
- Dirty close flow (`Ctrl+Q` or window close): save mapper -> save host map -> final confirm
- Transform shortcuts: `Ctrl+L/R/T/B`, `Ctrl+W/H/E`, `Ctrl+Shift+H/V`
- View shortcut: `Ctrl+0` (reset zoom/pan)
- Box creation/duplication shortcuts: `Ctrl+N`, `Ctrl+D`
- Mapper save persists create/update/delete of bboxes (deletions remove key blocks from YAML)

Defaults:
- Mapper: `examples/hosts/cpc464/cpc_keyboard_mapper.yaml`
- Host map: `examples/hosts/cpc464/host_keyboard_cpc.yaml`
- Device: `examples/devices/cpc464/cpc_keyboard.yaml`

## Run (Legacy PyQt)

```bash
scripts/run_keymapper_ui_legacy.sh
```

Canvas-only implementation path (generated host-HAL scaffold runtime):

```bash
scripts/run_keymapper_ui_host_hal_new.sh
```

Also available as:

```bash
scripts/run_keymapper_ui_native.sh
```

Override keyboard map used by the scaffold:

```bash
KEYBOARD_MAP=examples/hosts/apple2/host_keyboard_apple2.yaml \
  scripts/run_keymapper_ui_host_hal_new.sh
```

Override mapper file used for bbox loading/rendering in scaffold:

```bash
MAPPER=examples/hosts/apple2/apple2_keyboard_mapper.yaml \
  scripts/run_keymapper_ui_host_hal_new.sh
```

Current host-HAL scaffold controls:
- Mapper `image.file` background is rendered in this scaffold track (`png/jpg/jpeg/bmp/webp` via SDL_image, with extension fallback by stem).
- Key `overlay_color` from mapper YAML is respected for non-selected bbox fills.
- `Left click`: select bbox
- `Ctrl+click` / `Shift+click`: toggle bbox in multi-selection
- `Right click`: set primary selected bbox (anchor for align/size/distribute)
- `F2`: rename primary selected key id (`Enter` apply, `Esc` cancel)
- `Drag`: move all selected bboxes as a group
- `Mouse wheel`: zoom in/out (around cursor)
- `Middle mouse drag`: pan viewport
- `Ctrl + 0`: fit view to image/bboxes
- `Bottom-right handle` on primary selection: resize `W/H`
- `Drag near window edge`: auto-scroll viewport
- `Arrow keys`: nudge selection in move mode by 1 px
- `Shift + Arrow`: nudge by 10 px
- `X` / `Y` / `W` / `H`: switch per-field edit mode
- `R` / `G` / `B`: switch overlay-color component edit mode (keys with `overlay_color`)
- `Esc`: return to move mode
- `Ctrl + S`: save bbox `x/y/width/height` back to mapper YAML
- `Ctrl + Q`: quit (shows confirmation if there are unsaved edits)
- `Ctrl + N`: create a new bbox at mouse position
- `Ctrl + D`: duplicate selected bbox(es) with offset and unique ids
- `Ctrl + I`: sample image pixel under mouse and apply as `overlay_color` to selection
- `Delete`/`Backspace`: remove selected bbox(es)
- Multi-select transforms (anchor = primary selected bbox):
- `Ctrl + L/R/T/B`: align left/right/top/bottom
- `Ctrl + W/H`: match width/height
- `Ctrl + E`: match size (width + height)
- `Ctrl + Shift + H/V`: distribute selected keys horizontally/vertically (endpoints fixed)
- Unsaved close prompt: `Ctrl + S` save+quit, `Enter`/`Q` discard+quit, `Esc` cancel
- `Ctrl + Z` / `Ctrl + Y`: undo / redo geometry edits
- Save scope now includes existing-key updates, key removals, and appending newly created keys with default metadata skeleton.

System presets for native app:

```bash
scripts/run_keymapper_ui_cpc64_native.sh
scripts/run_keymapper_ui_apple2_native.sh
scripts/run_keymapper_ui_atari800xl_native.sh
```

You can override with env vars:

```bash
MAPPER=... HOST_MAP=... DEVICE=... scripts/run_keymapper_ui_new.sh
```

## Migration helper

Inject `mapper_key_id` into host bindings from keymapper legends/combos:

```bash
uv run python -m tools.keymapper_ui.migrate_mapper_key_ids \
  --host-map examples/hosts/cpc464/host_keyboard_cpc.yaml \
  --mapper examples/hosts/cpc464/cpc_keyboard_mapper.yaml
```
