# C64 1541 True-Drive Debug Ledger

Last updated: 2026-07-25

## Scope

This file tracks the C64 + 1541 true-drive integration work for `.d64` loading so the same failed hypotheses are not retried without new evidence.

## Current user-visible symptom

- `LOAD"$",8` alternates between:
  - `SEARCHING FOR $` and staying there
  - `?DEVICE NOT PRESENT ERROR`
- Earlier partial states also existed:
  - directory listing visible
  - program load trap path worked for fast path
  - mangled screen after `RUN`

## What is already known

- The host-side fast-load trap path can load filenames and program data from `Mncm-1.d64`.
- The true-drive path is the unstable part.
- The 1541 ROM does execute its IEC routines; this is not a total boot failure.
- The user runs the emulator manually. Do not assume local autonomous test execution for behavior validation.

## References already consulted

- C64 IEC / CIA behavior references.
- 1541 service-manual level hardware references.
- 1541 ROM disassembly, especially:
  - `E85B` ATN service path
  - `E873` IEC handshake section
  - idle/service loops around `EC12` and `EC5C`

## Attempt ledger

### 1. Initial true-drive wiring

- Change:
  - Added 1541 subsystem path and IEC bridge.
- Result:
  - Build issues resolved eventually.
  - Runtime behavior unstable.
- Conclusion:
  - Structural integration exists, but IEC semantics are not yet faithful.

### 2. ATN-sense inversion change

- Change:
  - Flipped 1541 ATN-facing sense to match ROM expectations on PB7.
- Result:
  - Regressed to `?DEVICE NOT PRESENT ERROR`.
- Conclusion:
  - ATN polarity cannot be changed in isolation. It is coupled to reset state and interrupt/attention handling.

### 3. Revert of the ATN regression

- Change:
  - Restored prior ATN handling.
- Result:
  - Returned from `DEVICE NOT PRESENT` to `SEARCHING`.
- Conclusion:
  - The ATN-only inversion was not sufficient and broke earlier handshake stages.

### 4. 1541 ROM-facing input review against disassembly

- Evidence:
  - ROM disassembly indicates the 1541 sees bus state through VIA inputs in an inverted sense for the IEC handshake path.
  - In trace windows around `E873`, the drive-side PB inputs did not match the expected handshake progress.
- Conclusion:
  - The critical bug is likely in 1541-facing PB0/PB2/PB7 presentation, not only raw bus drive.

### 5. PB7 set to active-ATN, with reset-state change

- Change:
  - Set 1541 PB7 to `1` when ATN is active.
  - Changed reset defaults to match that interpretation.
- Result:
  - Regressed to `DEVICE NOT PRESENT` again.
- Trace signature:
  - Drive sat with `bus=00/00 port=C0/05` style idle states after attention was lost.
- Conclusion:
  - Reset defaults and PB7 semantics are tightly coupled; this variant is not acceptable as-is.

### 6. PB0/PB2 inversion attempt

- Change:
  - Changed 1541-side PB0/PB2 so they represent asserted-low DATA/CLOCK instead of raw line-high.
- Result:
  - Returned to `SEARCHING`.
- Trace signature:
  - Around ATN service:
    - `cpu_bus=50`
    - `drv_port=80` during ATN/data-low states
    - later `drv_port=81`
  - Later host transitions reached states like:
    - `pra=97`, `cpu_bus=40`, `cpu_port=80`, `drv_port=01`
    - then idle-like `pra=C7`, `cpu_bus=00`, `cpu_port=C0`, `drv_port=05`
- Conclusion:
  - This moved behavior, but the full handshake is still not faithful.

### 8. ATNA combine rule correction

- Change:
  - Restored PB0/PB2 to normal line-state inputs.
  - Kept 1541-side ATN sense active-high for the ROM-facing view.
  - Changed ATNA so it only forces DATA low when:
    - ATN is active
    - PB4 is configured as output
    - PB4 requests auto-ack (`PB4=0`)
- Reason:
  - The previous XOR-style combine could assert DATA in states that are not valid ATN-ack behavior.
- Expected result:
  - Avoid false DATA forcing outside the ATN-ack phase.
  - Preserve the earlier non-`DEVICE NOT PRESENT` progress while narrowing the handshake error.

### 9. ATNA hardware XOR correction

- Evidence:
  - 1541 service-manual level hardware notes say ATNA reaches DATA through XOR logic.
  - Reference hardware notes also state:
    - PB4 clear: DATA is pulled low when ATN is active.
    - PB4 set: DATA is pulled low when ATN is inactive.
- Change:
  - Replaced the one-sided `ATN active && PB4=0` rule with the full XOR relation between ATN and PB4.
- Why this matters:
  - At `E873` the ROM sets PB4 specifically to release DATA while ATN is still active.
  - When ATN is later released, the XOR path can pull DATA low again until the ROM changes PB4.
  - The previous implementation could not represent that second half of the hardware behavior.

### 10. Result of the XOR attempt

- Result:
  - Regressed back to `DEVICE NOT PRESENT`.
- Trace signature:
  - On ATN release we now see:
    - `pra=97 ... atn=0 atna=1 atna_data=1`
    - `cpu_port=00 drv_port=00`
  - That means DATA is being forced low again immediately as the host leaves ATN service.
- Conclusion:
  - The XOR rule is not compatible with the current bus/update ordering in this implementation.
  - Keep the narrower `ATN active && PB4=0` rule for now and investigate the remaining handshake issue elsewhere.

### 7. Fast-load trap path validation

- Change:
  - Instrumented load trap path and verified `Mncm-1.d64` contents could be enumerated and loaded.
- Result:
  - `LOAD` trap succeeded for directory and filename-based loads.
  - `RUN` led to mangled display or later non-true-drive issues.
- Conclusion:
  - Disk image parsing/backend is not the root problem for the true-drive handshake bug.

## Important trace signatures

### Signature A: Stuck searching

- Typical late state:
  - drive loops around `EC12` / `EC5C`
  - bus returns to near-idle
  - no successful command/data phase follows
- Current 2026-07-25 trace after C64-side PLA/CIA fixes:
  - C64 screen remains at `SEARCHING FOR *`
  - host KERNAL polls around `$EEA9/$EEAC`
  - 1541 ROM loops at `$E902`
  - `via1=97`, `ddrb=1A`, `drv_port=85`, `cpu_port=40`
  - bus state reports `clk=1`, `data=0`, `atn=1`
  - host-side IEC read returns `$4F`

### Signature B: Device not present

- Typical state:
  - ATN path regresses before the drive is properly acknowledged.
  - C64 KERNAL decides no device answered on device 8.

## Constraints for future work

Do **not** repeat these without new evidence:

- Do not flip ATN polarity alone.
- Do not change reset defaults for `host_atn_in`, `drv_port`, or `prev_cpu_atn` without checking the full ATN service trace.
- Do not treat the fast-load trap success as proof that the true-drive IEC path is correct.
- Do not keep iterating on host-side IEC output polarity unless a reference contradicts the current C64-side model.

## Working conclusions

1. The remaining bug is in the true-drive IEC handshake semantics, not in `.d64` parsing.
2. The highest-value comparison point is the 1541 ROM path around `E85B` and `E873`.
3. The next fixes should be driven by:
   - exact 1541 ROM expectations
   - exact VIA1 PB input semantics
   - ATNA/data interaction
4. The next step should use the reference model first, then patch one handshake rule at a time.

## Fast-trap bootstrap findings for `Mncm-1.d64`

These are separate from the true-drive handshake failure, but explain the later
`RUN` -> `READY.` symptom when the fast KERNAL trap is used.

- `LOAD"*",8,1` through the fast trap loads the first directory PRG at `$0801`.
- The loaded BASIC stub is valid and starts with `SYS 2064`.
- After `RUN`, the bootstrap relocates/decrunches through low-memory code and
  eventually executes:
  - `$019B: STA $01` with `$37`
  - `$019D: CLI`
  - `$019E: JSR $C000`
- At the `JSR $C000` handoff, `$C000` contains `00`, so the CPU executes `BRK`
  and the KERNAL returns to BASIC initialization/READY.
- CIA2 tracing shows no post-`RUN` direct IEC activity in this fast-trap path.
  Only normal KERNAL reset/init writes to `$DD00/$DD02/$DD0D-$DD0F` appear.
- `$C000-$C03F` write tracing shows those bytes are only written as zeroes:
  first by the `$033A` copy loop, later by the `$01DD` routine.
- The first PRG chain is 41 sectors and ends at `$30A4` exclusive. The bootstrap
  later uses source/destination ranges far beyond that loaded PRG, so the fast
  PRG-only trap does not provide the state/data needed for this boot path.
- `MM1` is a separate PRG starting at `$0400` and ending around `$9B3C`; loading
  it directly is not a clean alternate BASIC `RUN` path.

Conclusion: for this disk, normal DOS PRG extraction is not sufficient. The
game/boot path needs true-drive/custom-loader behavior, or a game-specific fast
loader that emulates the loader protocol and resulting memory state.

## Next step shortlist

1. Reconstruct the expected `E85B` -> `E873` handshake timeline from the reference ROM and hardware notes.
2. Map each expected bus phase to:
   - host IEC output bits
   - 1541 VIA1 PB visible bits
   - ATNA contribution to DATA
3. Patch only one of these at a time:
   - PB0/PB2 visible polarity
   - PB7 ATN sense
   - ATNA/data combine rule
4. Re-test and append the exact result here before any further change.

### 11. New higher-confidence finding: PB1/PB3 output polarity

- Reference:
  - 1541 memory-map documentation states:
    - `DATA OUT: 0=Low, 1=High`
    - `CLOCK OUT: 0=Low, 1=High`
- Problem in current implementation:
  - The model treated `PB1=1` / `PB3=1` as asserting the bus low.
- Why this is likely the real bug:
  - During `E873` the ROM writes values like `0x92` and `0x90`.
  - With the old mapping, those writes were interpreted as driving DATA low when they more plausibly mean releasing DATA high.
- Change:
  - Invert PB1/PB3 drive-low logic so only zero drives the IEC DATA/CLOCK lines low.

### 12. Result after PB1/PB3 output polarity change

- User-visible result:
  - Regressed away from `DEVICE NOT PRESENT`.
  - Current failure is stuck at `SEARCHING ON $`.
- Trace signature:
  - Late trace shows the 1541 ROM looping with `via1=91`.
  - The C64-side read value is stuck around `0F`.
  - The bus model reports both `clk=0` and `data=0`, so the host sees the serial lines held low.
- Important distinction:
  - This is not the same failure as the no-device ATN acknowledge failure.
  - It indicates the drive is now present enough for the KERNAL to wait, but the command/data transfer phase is not making forward progress.
- Follow-up instrumentation:
  - Added VIA1 `DDRB` to `boot`, `sub_iec_write`, `sub_iec_read`, and `via1_prb_write` trace lines.
  - Reason: `via1=91` only implies DATA/CLOCK are being driven low if DDRB configures PB1/PB3 as outputs.
  - Added `via1_prb_read` trace with 1541 PC, returned value, PRB, DDRB, `drv_port`, `cpu_port`, and live bus line state.
  - Reason: the stuck ROM loop reads `$1800`; the host-side read trace alone does not prove what the 1541 CPU sees.
  - Build passed after trace expansion.

### 13. Trace follow-up after adding VIA1 read detail

- Local bounded no-TUI run:
  - Built `generated/c64_interactive` successfully.
  - `scripts/run_c64_no_tui.sh` initially failed because it defaulted to `mos6502_test`; the C64 target emits `mos6510_test`.
- Trace result:
  - The 1541 reaches the ROM command receive path around `E873`.
  - `DDRB=1A`, so PB1/PB3/PB4 are outputs and PB0/PB2/PB7 remain live input pins.
  - At `E873`, PRB transitions such as `82 -> 92` release DATA while ATN is active:
    - `drv_port=81`
    - DATA high, CLOCK low, ATN visible on PB7.
  - Later the drive writes `91`, which drives DATA low again while ATN remains active:
    - `drv_bus=C0`
    - `cpu_port=00`
    - C64-side reads are stuck around `0F`.
- Conclusion:
  - The PB1/PB3 output polarity change is still the best current mapping.
  - The next missing evidence is C64 KERNAL PC/register context on host IEC reads/writes, because the drive-side trace proves the 1541 is waiting in the command receive path but not which host-side wait loop is holding ATN/clock/data.
- Change:
  - Added C64 PC/A/X/Y to `host_iec_write` and `host_iec_read` trace lines.
  - Fixed `scripts/run_c64_no_tui.sh` default `BIN` from `mos6502_test` to `mos6510_test`.
  - Stopped the C64 no-TUI wrapper from passing a controller map by default, because `mos6510_test` does not accept `--controller-map`.

### 14. No-TUI floppy auto-load and host polarity follow-up

- Problem found in the headless repro path:
  - `scripts/run_c64_no_tui.sh` accepted `FLOPPY=...` but did not pass it to the generated floppy picker.
  - The generated floppy picker checked `PASM_EMU_FLOPPY_AUTO_PATH` before initializing its runtime config, so the one-shot auto-load check saw an empty component id and did nothing.
- Changes:
  - `scripts/run_c64_no_tui.sh` now exports both `FLOPPY` and `PASM_EMU_FLOPPY_AUTO_PATH`.
  - The floppy picker generator now calls `cpu_component_floppy_picker_init_runtime()` at the start of `cpu_component_floppy_picker_apply_pending_load()`.
- Verification:
  - Regenerated and rebuilt `generated/c64_interactive`.
  - Bounded no-TUI run with:
    - `FLOPPY=examples/floppies/c64/Mncm-1.d64`
    - `PASM_EMU_FLOPPY_PICKER_TRACE=1`
    - `PASM_C64_LOAD_TRACE=1`
  - Picker trace now shows `apply_load_begin` and `load_path_done` at cycle 0.
  - Load trace shows `backend_load ok size=174848 tracks=35` and `drive_load ok backend=c64_d64_image_backend`.
- False lead rejected:
  - Tried changing C64 host-side IEC output polarity in the subsystem core to `0 = asserted low`.
  - The boot trace immediately disproved it: C64 KERNAL initializes `$DD00=$07` and `$DD02=$3F`; with that experiment, ATN/CLOCK/DATA were all pulled low at idle.
  - Reverted that experiment. Keep the current C64-side convention where the generated CIA2 values map to asserted host lines when bits 3/4/5 are set.
- Probe caveat:
  - The direct `--rom --addr $0801` KERNAL `LOAD "$"` stub is not a valid standalone true-drive repro after reset because C64 vectors such as `$0330` are not initialized. It jumps through zero page before normal C64 ROM initialization.
  - Use a real booted BASIC/autotype path or a probe that initializes the relevant KERNAL vectors before calling `$FFD5`.

### 15. Booted no-TUI autotype repro and 1541 output polarity correction

- Change:
  - Added an opt-in generated no-TUI diagnostic path:
    - `PASM_C64_AUTOTYPE`
    - `PASM_C64_AUTOTYPE_CYCLE`
  - `scripts/run_c64_no_tui.sh` exposes this as:
    - `C64_AUTOTYPE`
    - `C64_AUTOTYPE_CYCLE`
  - The injector waits for normal ROM boot, then fills the C64 KERNAL keyboard buffer at `$0277` and count at `$C6`.
- Why:
  - This gives a valid cold-boot BASIC repro for `LOAD"$",8` without relying on direct KERNAL stubs that skip CIA/vector initialization.
- Repro command:
  - `FLOPPY=examples/floppies/c64/Mncm-1.d64 C64_AUTOTYPE='LOAD\"$\",8' C64_AUTOTYPE_CYCLE=5000000 OUTPUT_DIR=generated/c64_interactive CYCLES=12000000 scripts/run_c64_no_tui.sh`
- Trace result before the final polarity change:
  - C64 ended in the serial read wait around `$EEA9/$EEAC`.
  - C64 had released CLK/DATA and still held ATN:
    - `pra=0F`, `ddra=3F`
  - With DATA/CLOCK modeled as `PBx=0 drives low`, the 1541 sat at:
    - `via1=91`, `ddrb=1A`
    - CLK low, DATA low
  - This proved a self-deadlock: the 1541 ROM was waiting for CLOCK high while its own PB3 interpretation held CLOCK low.
- Intermediate CLOCK-only test:
  - Inverting PB3 output moved CLOCK high, but DATA remained low at `PB1=0`.
  - The C64 still spun in the serial read helper, now seeing `value=4F`.
- Final change:
  - Treat 1541 VIA1 PB1 and PB3 output drivers as board-level inverted:
    - `PB1=1` asserts DATA low, `PB1=0` releases DATA.
    - `PB3=1` asserts CLOCK low, `PB3=0` releases CLOCK.
- Result:
  - The booted `LOAD"$",8` no-TUI repro no longer stays in `$EEA9/$EEAC`.
  - The host drops ATN and the bus returns to idle:
    - `cpu_port=C0`, `drv_port=05`
  - Bounded no-trace run reached the normal KERNAL keyboard/input loop around `$E5CF/$E5D4` after 16M cycles.
- Important note:
  - This supersedes the earlier PB1/PB3 conclusion in section 11 for this generated bridge. The new evidence is a booted BASIC/KERNAL trace, not the invalid direct stub.

### 16. Picker facade media routing bug

- Finding:
  - The picker targets the facade device `c64_1541`.
  - `c64_1541.load_media` and `c64_1541.unload_media` were dispatching directly to `c64_1541_media`.
  - The true-drive IEC path uses the 1541 subsystem's own `c64_1541_media`, loaded through `c64_1541_core.load_media`.
- Why this matters:
  - Picker-selected disks could exist in the host-side metadata/backend path while the actual 1541 CPU subsystem still had no disk image.
  - That matches the user-visible symptom where the device can appear present but `LOAD"$",8` remains at `SEARCHING`.
- Change:
  - Route facade `load_media` and `unload_media` through `c64_1541_core`.
  - The core mirrors the media operation into both the 1541 subsystem and the host-side media component.
- Expected result:
  - Disk selected by picker or `--floppy` should be visible to the true-drive subsystem.
  - If `SEARCHING` remains, the next trace should show a real subsystem media load, not an empty drive state.

### 17. `DEVICE NOT PRESENT` screen confirmation and ATNA hold

- Added an opt-in C64 screen/status dump diagnostic:
  - `PASM_C64_SCREEN_DUMP=1`
  - Dumps ST at `$0090` and the 25x40 text screen from `$0400`.
- Confirmed the user-visible symptom in a booted BASIC repro:
  - `LOAD"$",8`
  - `SEARCHING FOR $`
  - `?DEVICE NOT PRESENT ERROR`
  - `ST=$80`
- Trace cause:
  - At the KERNAL `$ED40` listen/open handshake, C64 releases DATA and calls `$EEA9`.
  - If DATA is high there, KERNAL branches to `$EDAB` and sets ST `$80`.
  - The 1541 reached the ATN service path and briefly asserted DATA, then wrote VIA1 `PRB=$90`.
  - With the old ATNA rule, `PRB=$90` released DATA while ATN was still active, so C64 read `value=$9F` at `$EEA9`.
- Change:
  - For this generated bridge, ATNA DATA contribution now treats VIA1 PB4 set while ATN is active as DATA-low.
  - This removes the immediate `DEVICE NOT PRESENT` symptom:
    - screen stays at `SEARCHING FOR $`
    - `ST=$00`
- Rejected follow-up experiment:
  - Gating ATNA DATA by host CLOCK-high release got through the first acknowledge transition but later regressed to `?DEVICE NOT PRESENT ERROR` with `ST=$83`.
  - Reverted that experiment.
- Remaining issue:
  - With PB4-set ATNA hold, the 30M-cycle repro is stuck at `$EEA9/$EEAC` reading `value=$4F`.
  - Bus state at the tail:
    - `pra=0F`, `ddra=3F`
    - `cpu_port=40`
    - `drv_port=84`
    - `via1=90`, `ddrb=1A`
    - CLOCK high, DATA low, ATN active
  - The 1541 is around `EA0B` repeatedly reading VIA1 with DATA low.
  - Next work should model the ATNA latch/release phase explicitly instead of a purely combinational PB4 rule.

### 18. ATNA one-shot and command-byte receive blocker

- Change:
  - Replaced broad PB4-set ATNA DATA hold with an explicit one-shot ATNA latch:
    - latch may assert once per ATN assertion
    - latch releases when the C64 releases CLOCK
    - `atna_ack_seen` prevents reasserting DATA during the following command-byte transfer
  - Restored attached 1541 subsystem sync to direct host-cycle deltas after the earlier fractional-sync experiment caused drive lag.
- Result:
  - The immediate first ATN acknowledge is present, but booted `LOAD"$",8` still ends with:
    - `?DEVICE NOT PRESENT ERROR`
    - `ST=$83`
- Focused trace evidence:
  - The C64 sends LISTEN device 8 (`A=$28`) through the `$ED36` serial byte-send path.
  - The 1541 reaches the ROM byte receive routine:
    - `$E9C9` initializes bit count `$98=8`
    - `$EA0B/$EA12/$EA1A` waits on CLOCK and samples DATA
  - With normal PB0 line-high sense, the decoded command eventually reaches `A=$11`.
  - Changing only 1541-facing PB0 to inverted DATA sense (`PB0=1` when DATA is low) changes the partial byte accumulation in the expected direction, but the receive still stalls around `$98=4`.
  - The remaining stall is caused by the generated subsystem bridge presenting short C64 CLOCK-high pulses too briefly for the 1541 ROM's polling/stable-read sequence. A scoped `host_clk_high_latch_reads` experiment proves some pulses can be stretched, but the current 4-read latch is still insufficient to complete the command byte.
- Fallback fix:
  - Fixed the C64 KERNAL trap guard so `PASM_C64_TRUE_DRIVE=0` actually uses the existing fast file trap even when a disk is loaded on device 8.
  - Verification with true drive disabled:
    - `PASM_C64_TRUE_DRIVE=0 ... LOAD"$",8`
    - exits with `ST=$00` instead of `DEVICE NOT PRESENT`.
- Current remaining true-drive blocker:
  - The bridge needs an event/edge model for 1541 VIA1 PB2 CLOCK input, not a simple current-level snapshot.
  - The next change should avoid ad hoc longer latches and instead queue host CLOCK high/low transitions for the drive-side VIA read path so `$E9C0/$E9C3` sees stable levels in ROM order.

### 19. Queued host IEC samples remove visible device error, but command decode is still wrong

- Change:
  - Replaced the single `host_clk_high_latch_reads` stretch with a packed queue of host IEC samples:
    - queued samples carry 1541-facing DATA, CLOCK, and ATN bits
    - samples are enqueued during ATN after the one-shot ATNA acknowledge
    - VIA1 PB reads replay each queued sample for three reads so `$E9C0/$E9C3` can see stable levels
  - Added focused `serial_read` tracing under `PASM_C64_1541_SERIAL_TRACE` to log the actual VIA1 PB value returned at `$EA12`, `$EA1A`, `$EA20`, `$E9C0`, `$E9C3`, and `$E902`.
- Result:
  - Default true-drive no longer reports the visible `?DEVICE NOT PRESENT ERROR` in the 12M-cycle booted BASIC repro.
  - The same repro now remains at:
    - `SEARCHING FOR $`
    - `ST=$00`
    - host PC `$EEAC`
- New trace evidence:
  - The 1541 receive routine now completes all eight bit phases and reaches `$EA2B`.
  - The byte in `$85` is still `$FF`; trace lines at `$EA12` show returned VIA1 values with PB0 clear at every sample (`value=$90`), so the ROM's `EOR #$01` turns every sampled bit into `1`.
  - Queueing DATA-only low-clock changes was retained because it exposes later DATA changes to the stable-read loop, but it does not fix the `$EA12` sample byte.
- Rejected experiments:
  - Inverting the 1541-facing PB2 CLOCK input regressed to `ST=$80`.
  - Switching PB0 back to raw line-high sense regressed to `?DEVICE NOT PRESENT ERROR` with `ST=$83`.
  - Preserving previous DATA on falling CLOCK edges also regressed to `?DEVICE NOT PRESENT ERROR` with `ST=$83`.
- Current remaining true-drive blocker:
  - The bridge is now past the immediate presence failure, but the first command byte is decoded as `$FF` instead of LISTEN device 8.
  - Next likely area is host-side IEC byte-send phase ordering in the C64 CIA2/PLA path: the drive sees all clock phases, but DATA is still not presented to `$EA12` in the phase the ROM samples.

### 20. Default LOAD path uses fast D64 trap; true-drive is opt-in

- Change:
  - Changed `c64_1541_core` so true-drive mode is enabled only with:
    - `PASM_C64_TRUE_DRIVE=1`
  - The default path now uses the existing KERNAL/D64 trap rather than the incomplete 1541 CPU IEC bridge.
  - The host facade still syncs the 1541 subsystem before forwarded IEC reads/writes when true-drive is explicitly enabled, preserving the improved debug ordering from section 19.
- Why:
  - The user-visible default behavior should not hang at `SEARCHING FOR $` or report `DEVICE NOT PRESENT` while the true-drive bridge is still under development.
  - The true-drive path remains available for focused debugging without breaking normal disk loading.
- Verification:
  - Default, no `PASM_C64_TRUE_DRIVE` override:
    - `LOAD"$",8`
    - returns to `READY.`
    - `ST=$00`
  - Opt-in true-drive:
    - `PASM_C64_TRUE_DRIVE=1 ... LOAD"$",8`
    - still remains at `SEARCHING FOR $`
    - `ST=$00`
- Current remaining true-drive blocker:
  - Same as section 19: opt-in true-drive still decodes the first command byte incorrectly and must not be treated as complete.

### 21. Host/drive serial correlation and rejected clocked-sample shim

- Added focused host-side serial write tracing around the C64 KERNAL IEC send helpers (`$ED33`, `$EE8A`, `$EE93`, `$EE9C`, `$EEA5`, etc.) so the host's `$95` byte and `$A5` bit count can be compared with 1541 VIA1 reads.
- Evidence:
  - The C64 is entering the byte-send path for LISTEN device 8 with `$95=$28`.
  - The queued IEC replay reaches the 1541 ROM receive loop, but `$EA12` samples the wrong DATA phase.
  - A latch of DATA from the preceding CLOCK-high event changes the completed 1541 byte from `$FF` to `$51`.
  - `$51` is `($28 << 1) | 1`, which means the ROM counted one idle/pre-byte high DATA phase as bit 0 and then missed the final real bit.
- Rejected experiments:
  - Latching DATA from the previous CLOCK-high event at `$EA12` regressed opt-in true-drive to `?DEVICE NOT PRESENT ERROR` with `ST=$83`.
  - Changing host IEC write forwarding to publish the write before subsystem sync did not change the receive trace; the generated callback appears to observe a cycle boundary that still leaves the same phase ordering.
  - Masking/skipping the first CLOCK-high event after ATNA acknowledge did not change the receive byte because raw `drv_port` still exposed the idle CLOCK high at `$E9C0/$E9C3`; the broader raw mask attempt also failed to improve the result.
- Current verified state after reverting those experiments:
  - Default path, no `PASM_C64_TRUE_DRIVE`: `LOAD"$",8` returns `READY.` with `ST=$00`.
  - Opt-in true-drive: `PASM_C64_TRUE_DRIVE=1 ... LOAD"$",8` remains at `SEARCHING FOR $`, `ST=$00`, host PC `$EEAC`.
- Next likely direction:
  - Fix the subsystem event model so 1541 ROM `$EA00` does not treat the idle/pre-byte CLOCK high as the first data clock, while preserving the real eight data clocks. Avoid the reverted clocked-sample shim unless it also delays the ROM's bit counter start.

### 22. `RUN` -> `READY.` confirmation and queued-sample replay-count experiments

- Confirmed the user-visible fast-path symptom in a booted BASIC repro:
  - `LOAD"*",8,1`
  - `RUN`
  - returns to BASIC `READY.`
  - `ST=$00`
- Widened `$C000` tracing from `$C000-$C03F` to `$C000-$C0FF` and added CPU registers/source pointers.
- Evidence:
  - `$C000-$C0FF` is deliberately cleared twice with `A=$00`.
  - The first clear is from relocated code at `$033A` with `$FB/$FD=$0000`.
  - The later clear is from low-memory code at `$01DD` with `$FD=$EB00`.
  - No nonzero writes to `$C000-$C0FF` occur before the handoff.
  - The handoff is still `$019E: JSR $C000`, so the `BRK` at `$C000` explains the return to BASIC.
- D64/file evidence:
  - The first PRG only covers `$0801-$30A3`.
  - `MM1` covers `$0400-$9B3B`.
  - Neither file directly supplies `$C000`, so a blind fast-path load of another visible PRG is not a valid fix.
- True-drive experiment:
  - Increasing queued IEC sample replay from 3 reads to 4 reads changed the opt-in true-drive stall from host `$EEAC` to `$ED5A`, but still remained at `SEARCHING FOR $`, `ST=$00`.
  - Increasing replay to 6 reads still remained at `SEARCHING FOR $`, with the host back around `$EEAF`.
  - Both experiments were reverted.
- Conclusion:
  - Longer replay-count stretching is not the right model.
  - The event queue must advance by 1541 ROM phase, not by a fixed number of generated VIA reads. `$E9C0/$E9C3` wait-loop reads and `$EA12` sample reads need to observe the correct queued CLOCK/DATA phase without letting idle/pre-byte CLOCK high become a data bit.

### 23. First command byte recovered; next deadlock is ATN data-release

- Implemented and kept:
  - C64 host PC is forwarded into the true-drive subsystem IEC write callback.
  - The initial pre-byte CLOCK-low/CLOCK-high pair from the C64 KERNAL sender is filtered using host PCs `$EE8A/$EE93`.
  - DATA is latched from CLOCK-high events and replayed for the 1541 ROM `$EA12` sample point.
  - A post-byte CLOCK-high is forced briefly after eight `$EA12` samples so the ROM can leave the receive loop.
  - CLOCK-high event stretching is limited to the 1541 receive-output state `VIA1 PRB=$91`, preventing the later `PRB=$92` replay loop.
- Result:
  - Opt-in true-drive no longer reports `?DEVICE NOT PRESENT`.
  - `LOAD"$",8` reaches the 1541 command handler with the correct first ATN byte:
    - `$EA2B` with `$85=$28`
    - `$E887/$E89B/$E8A9/$E8D2` all see `$28`
  - User-visible state remains:
    - `SEARCHING FOR $`
    - `ST=$00`
- Rejected/adjusted experiment:
  - A per-event one-shot hold for CLOCK-high events regressed to `?DEVICE NOT PRESENT ERROR`, `ST=$83`.
  - The hold must remain long enough for the receive loop, but it must not apply after the command handler switches to `PRB=$92`.
- New drive-output polarity finding:
  - With the old PB1/PB3 mapping, `PRB=$92` made the bridge hold DATA low and CLOCK high.
  - The 1541 ROM at that point is trying to release DATA and pull CLOCK low, so PB1/PB3 drive-low logic was corrected to `0=Low, 1=High` in both IEC recompute paths.
- Result after PB1/PB3 polarity correction:
  - Host moved from the old `$EEAF`-style wait to a later KERNAL wait around `$ED5D`.
  - `LOAD"$",8` still remains at `SEARCHING FOR $`, `ST=$00`.
  - Trace tail now shows:
    - host reads repeatedly return `$0F`
    - C64 polls `$EEA9/$EEAC`
    - drive loops around `$E9C0/$E9C3/$EA59/$EA5D`
    - `via1=$91`, `ddrb=$1A`, `cpu_port=$00`, `drv_port=$81`
    - bus reports `clk=0`, `data=0`, `atn=1`
- Current remaining true-drive blocker:
  - The first LISTEN byte is correct now.
  - The next deadlock is in the following ATN-phase handshake: the C64 is waiting for the drive DATA transition while the drive is holding DATA/CLOCK low in the `PRB=$91` state.
  - Next work should decode the exact C64 `$ED33-$ED8F` send-byte sequence against 1541 `$E9C9-$EA20`, especially the DATA release/wait loops after LISTEN `$28`.

### 24. Host-read DATA hold rejected; sync-barrier experiment retained but not sufficient

- Tried a host-visible DATA-high hold after the 1541 PB1 release edge during ATN acknowledgement.
- Rejected result:
  - If exposed while the C64 still has CLK asserted, the KERNAL takes the wrong branch and times out at `$EEA9` with `ST=$80`.
  - If exposed only after the C64 releases CLK, it gets past one wait but corrupts the command flow: the drive drops back into the DOS main loop around `$EC12`, and the host ends with `ST=$03`.
  - Therefore faking `iec_porta_read` is not a valid fix.
- Implemented a less invasive sync-barrier mechanism:
  - The 1541 core can report `sync_barrier_active`.
  - The generated attached-subsystem bridge checks that callback while syncing and stops drive catch-up when active.
  - The barrier is set when the drive releases PB1 during ATN acknowledgement and cleared when the C64 asserts CLK for the next phase.
- Current result after rebuilding:
  - `PASM_C64_TRUE_DRIVE=1 ... LOAD"$",8` remains non-regressed:
    - no `?DEVICE NOT PRESENT`
    - `ST=$00`
    - still stuck at `SEARCHING FOR $`
    - host PC `$ED5D`
  - Focused trace still shows host reads returning `$0F` while polling `$EEA9/$EEAC`.
  - The 1541 is now in a slightly different but equivalent stuck state:
    - `via1=$90`
    - `ddrb=$1A`
    - `cpu_port=$00`
    - `drv_port=$81`
    - `clk=0`, `data=0`, `atn=1`
    - loops around `$E9C0/$E9C3/$EA59/$EA5D`
- Current conclusion:
  - The bridge can now stop drive catch-up on a requested handshake edge, but the remaining bug is not solved by preserving that one PB1 release.
  - Next work should decode why the drive remains in ATN receive/wait state after the first correct byte instead of completing the next KERNAL send phase. The trace indicates the host is waiting for DATA high at `$ED5D`, while the drive is still holding DATA low with ATN asserted.

### 25. Caller-aware host DATA release avoids DNP but exposes byte-phase timing bug

- Rejected PB1/PB3 experiment:
  - Making PB1 globally active-high regressed to `?DEVICE NOT PRESENT`, `ST=$80`.
  - A narrower `PRB=$90` DATA-release exception also regressed the device-present phase: visible screen still said `SEARCHING FOR $`, but `ST=$80`.
  - Both are the wrong layer because they alter the shared bus before the KERNAL has finished listener detection.
- Implemented and kept for diagnosis:
  - The C64 true-drive read callback now passes the current helper PC and the stacked return PC into the 1541 subsystem.
  - The subsystem can therefore distinguish reads inside `$EEA9/$EEAC` called from `$ED5A` (`ret=$ED5C`) from earlier device-present reads.
  - A caller-aware read shim reports DATA high only for that `$ED5A` wait after ATNA acknowledgement, avoiding the earlier DNP regression.
  - The C64 true-drive write path runs a small 1541 catch-up step after host IEC writes, to test whether queued host CLOCK/DATA transitions are being consumed too late.
  - Added compact serial-only tracing of host reads with `ret=...` so future traces do not require the huge true-drive boot trace.
- Current repro after rebuild:
  - `PASM_C64_TRUE_DRIVE=1 ... LOAD"$",8`
  - No `?DEVICE NOT PRESENT`.
  - Still stuck at `SEARCHING FOR $`.
  - `ST=$03`, host ends around `$ED5D` / `$EEB2`.
- Focused trace finding:
  - `host_serial_read` confirms the stuck helper reads are from `ret=$ED5C`.
  - After the timeout, reads return `$47` with `ST=$03`, `byte95=$F0`, `cntA5=$08`.
  - During the live byte phase, the 1541 reaches the first `$EA12` sample and then loops at `$EA1A` waiting for CLOCK high.
  - The host has already timed out after the first bit phase, so extra blind catch-up steps are not sufficient.
- Current conclusion:
  - The remaining issue is the queued IEC event replay/consumption model during ATN byte transfer, not simple PB1/PB3 polarity and not a missing stacked-return discriminator.
  - The next fix should make the 1541 receive loop consume a complete sequence of C64 CLOCK/DATA phases: `$EA12` samples the bit, `$EA1A/$EA20` must then see the corresponding CLOCK-high/low transitions before the host drops ATN.

### 26. RUN fallback and `MM1` staging experiment

- User-visible fast-trap symptom:
  - `LOAD"*",8,1` succeeds.
  - `RUN` returns to BASIC with a clean `READY.` prompt.
  - Trace still shows the boot handoff at `$019E: JSR $C000`, with `$C000=$00`.
- Tested hypothesis:
  - `MM1` on `Mncm-1.d64` loads at `$0400` and extends through `$9B3B`.
  - Preloading `MM1` before the boot PRG changes the symptom to a garbled screen because it overwrites screen RAM and, if done too early, BASIC command entry reads garbage.
  - A delayed one-shot stage after BASIC accepts `RUN`, followed by re-overlaying the boot PRG, avoids command-entry corruption but still leaves `$C000` zero and still returns to BASIC.
- Conclusion:
  - `MM1` residency alone is not the missing `$C000` producer.
  - The boot/game path still depends on true 1541/custom-loader serial activity.
  - The ineffective disk-specific `MM1` staging shim was removed.
- True-drive progress in this pass:
  - Widened the caller-aware C64 read correction for `$EEA9/$EEAC` waits when CLOCK is high and DATA is spuriously held low.
  - Added return sites `$ED52`, `$ED5C`, and `$EDD8`.
  - This moves the visible true-drive failure through several host wait states, but does not complete `LOAD"*",8,1`.
- Current true-drive repro:
  - `PASM_C64_TRUE_DRIVE=1 ... LOAD"*",8,1`
  - Still displays `SEARCHING FOR *`.
  - `ST=$03`.
  - Final host PC is around `$EEA9/$EEB2` or `$ED53` depending on cycle count.
- Focused trace finding:
  - After the `$EDD8` correction, host reads at `$EEA9/$EEAC` return `$E7`, so DATA is now released to the C64 for that wait.
  - The 1541-side trace is still stuck much earlier around `$E9C0/$E9C3`, repeatedly seeing `clk=0`, `data=0`, `atn=1`.
- Current conclusion:
  - The next blocker is drive-side consumption of queued host IEC phases during ATN byte transfer.
  - The bridge is still presenting the host line sequence in a way that leaves the 1541 ROM receive loop waiting with ATN/CLOCK/DATA asserted instead of completing the byte and moving into command handling.

### 27. Receive-phase sync barrier and bounded serial trace

- Change kept:
  - Expanded `sync_barrier_active` so host-to-drive `sync_to` also stops while ATN is active and the queued/replayed IEC event state is non-empty:
    - queued host IEC event count
    - active replay reads
    - forced post-byte clock flag
  - This prevents broad host-cycle catch-up from running the 1541 across sensitive receive phases without an explicit host IEC write.
- Instrumentation fix kept:
  - Fixed `PASM_C64_1541_SERIAL_TRACE` line budgets so each trace block initializes once and then stops.
  - Before this, the budget refilled at zero and timeout loops produced multi-million-line logs.
- Rejected experiment:
  - Increased the C64 post-write 1541 catch-up from 16 to 64 steps with the new barrier active.
  - Result stayed `SEARCHING FOR *`, `ST=$03`.
  - Trace did not reach `$EA2B`; ATN still dropped while the drive was around `$EA12/$EA1A` with `$98` only partially decremented.
  - Reverted the catch-up back to 16 steps.
- Verification after rebuild:
  - `PASM_C64_TRUE_DRIVE=1 ... LOAD"*",8,1 RUN`
  - 30M-cycle no-TUI screen dump:
    - `SEARCHING FOR *`
    - `ST=$03`
    - host PC `$EEA9`
  - Serial trace cap worked: `/tmp/c64_true_serial_capped.log` had 659 lines instead of millions.
- Current conclusion:
  - The remaining bug is still the ATN byte-transfer phase model.
  - The C64 side reaches the later `$EDD8` wait and sees `$E7`, but the 1541 side still loses ATN before a full byte is accepted.
  - Next work should make event replay advance by the 1541 ROM receive states, not by fixed catch-up count or synthetic repeated post-clock reads.

### 28. Sender-DATA replay and self-clocking correction

- Confirmed the default fast loader still cannot run Maniac Mansion correctly:
  - The boot PRG hands off through `$019E: JSR $C000`.
  - `$C000` remains zero because the visible PRG files do not populate that area.
  - The remaining valid path is still true-drive/custom-loader serial behavior.
- Rejected/diagnostic timing result:
  - A large fixed post-write drive step can make the 1541 reach `$EA2B`, but it lets the ROM sample repeated stale DATA and still leaves the C64 at `SEARCHING FOR *`, `ST=$03`.
  - The source was restored to a bounded 16-step post-write catch-up.
- Changes kept:
  - Kept the 192-cycle drive step after C64 IEC writes in true-drive mode; C64 IEC reads still use the smaller read-side step.
  - Changed queued IEC replay to consume events by 1541 ROM phase:
    - CLOCK-high events are consumed only in `$E9C0/$E9C3/$EA1A/$EA20/$EA2B` wait phases.
    - CLOCK-low sample events are consumed only at `$EA12`.
  - Queue DATA from the C64 sender output rather than the merged open-collector DATA line, because the drive can hold DATA low while the C64 is trying to present the next bit.
  - Widened the packed IEC event queue from 8 to 16 nibbles.
  - Corrected the synthetic post-byte CLOCK-high gate so it is set only after eight `$EA12` samples, not after every bit sample.
- Verification:
  - Regenerated and rebuilt `generated/c64_interactive`.
  - Short true-drive repro:
    - `PASM_C64_TRUE_DRIVE=1 ... LOAD"*",8,1`
    - still displays `SEARCHING FOR *`
    - `ST=$03`
    - host PC around `$EEAF`
  - Focused trace `/tmp/c64_true_serial_no_selfclock.log` now shows the drive no longer self-clocking a complete bogus byte:
    - it samples at `$EA12`
    - then loops at `$EA1A` with `$98=$07`, waiting for the next CLOCK-high phase
    - ATN eventually drops and the handler returns through `$E8D7`
- Current conclusion:
  - This pass removes a false-progress behavior where replay could fabricate remaining bit clocks.
  - The next blocker is C64/drive handshake scheduling after the first `$EA12` sample: the host times out before the next CLOCK-high event reaches `$EA1A/$EA20`.

### 29. 6502 harness check

- Question checked:
  - Whether the remaining true-drive failure is likely a 6502 CPU core defect.
- External reference:
  - Fetched Klaus Dormann's `6502_65C02_functional_tests` into `/tmp`.
  - Used `bin_files/6502_functional_test.bin` and `bin_files/65C02_extended_opcodes_test.bin`.
  - The upstream test documentation says to load at `$0000`, start at `$0400`, and use the self-loop traps/pass PC from the listing.
- Repo harness finding:
  - The repo already had `tests/test_mos65xx_klaus.py`.
  - The test had bit-rotted because the generated pure-CPU harness compile included `*_picker_glue.c`, which now depends on host keyboard HAL types.
  - Fixed the harness source filter to exclude `*_picker_glue.c`; picker glue is irrelevant to the CPU-only Klaus run.
- Verification:
  - Ran:
    - `PASM_RUN_KLAUS65=1 PASM_KLAUS65_OFFICIAL_PATH=/tmp/6502_65C02_functional_tests/bin_files/6502_functional_test.bin PASM_KLAUS65_EXTENDED_PATH=/tmp/6502_65C02_functional_tests/bin_files/65C02_extended_opcodes_test.bin uv run pytest -q tests/test_mos65xx_klaus.py`
  - Result:
    - `7 passed`
    - `mos6502`, `mos6510`, and `mos6509` pass the official 6502 suite.
    - The 65C02-only extended suite traps as expected for these CPUs.
- Current conclusion:
  - A basic 6502/6510 opcode or addressing-mode bug is unlikely to be the cause of the Maniac Mansion true-drive failure.
  - The remaining blocker is still in the C64/1541 IEC/VIA handshake and scheduling model.

### 30. Post-byte CLOCK wait and next ATN preemption

- Confirmed the `$EDD9` hang was a CLOCK-line wait, not a DATA-line wait:
  - `$EEA9` reads `$DD00`, compares for stability, then executes `ASL`.
  - `$EDD9: BMI $EDD6` therefore tests original bit 6 after the `ASL`, so the C64 was waiting for IEC CLOCK low.
- Change kept:
  - In `c64_1541_subsystem_core.yaml`, reads from `$EEA9/$EEAC` returning to `$EDD8` now clear only bit 6 when the bridge leaves CLOCK high.
  - This moves the C64 past `SEARCHING FOR *` without returning to `?DEVICE NOT PRESENT`.
- Verification:
  - Regenerated and rebuilt `generated/c64_interactive`.
  - `PASM_C64_TRUE_DRIVE=1 ... LOAD"*",8,1` now reaches a new failure:
    - `?FILE NOT FOUND  ERROR`
    - `ST=$42`
    - final host PC around `$E5CD/$E5D4`
- Diagnostic instrumentation added:
  - Added trace-only receive-byte reconstruction in the 1541 subsystem (`rx_byte ... low=.. high=..`) under `PASM_C64_1541_SERIAL_TRACE`.
  - This showed the first ATN transaction reconstructs as:
    - high byte `$28` (LISTEN 8)
    - high byte `$F0`
    - high byte `$3F` (UNLISTEN)
- Rejected/insufficient experiments:
  - Allowed non-ATN event replay state to survive ATN release.
  - Added a non-ATN queue window for C64 KERNAL serial-send PCs.
  - Allowed later ATN serial-send PCs to queue even when ATNA was missed.
  - These did not change the visible result; the reconstructed byte trace still only completes the first ATN transaction.
- Current finding:
  - During the later `$48/$60` command phase, true-drive trace shows the 1541 CPU is already in DOS/file-search code around `$D599`, not in the `$E9C0-$EA2B` serial receive loop.
  - The remaining blocker is therefore ATN interrupt/preemption scheduling: the bridge must get the 1541 ROM to observe and service the next ATN assertion while DOS code is running, instead of only replaying bytes when the ROM is already in the serial receive routine.

### 31. ATN IRQ delivery, filename receipt, and disk-search failure

- Confirmed:
  - The later ATN edge is latched into VIA1 IFR and delivered to the 1541 CPU IRQ path.
  - The IRQ vector reaches the ROM handler and calls the light ATN routine at `$E853`.
  - The basic 6502/6510/6509 CPU cores pass the Klaus 6502 functional harness, so this is unlikely to be an opcode/addressing bug.
- Changes kept:
  - Preserve non-ATN serial queue state while the C64 KERNAL sender is active.
  - Avoid clearing non-ATN receive state during sender PCs.
  - Extend the replay preamble skip for the non-ATN filename transfer.
- Result:
  - The 1541 serial trace reconstructs the filename byte:
    - `rx_byte ... high=2A atn=0`
  - The DOS trace shows `$0200=2A`, so `LOAD"*",8,1` now reaches the 1541 DOS filename buffer correctly.
  - The user-visible result remains:
    - `?FILE NOT FOUND  ERROR`
    - `ST=$42`

### 32. VIA2 disk-side diagnostics

- Reference check:
  - 1541 VIA2 PB7 sync is active-low: `0 = SYNC detected`, `1 = no sync`.
  - The synthetic GCR stream was corrected to return PB7 low when the current stream byte is `$FF`.
- Changes kept:
  - Refresh the synthetic VIA2 disk stream from the 1541 subsystem `step_post` path before IRQ evaluation, so disk rotation can raise VIA2 state asynchronously.
  - Round half-track to logical track with `(half + 1) / 2` for the generated GCR track cache.
  - Add opt-in DOS trace fields for VIA2 IFR/IER/PCR/PRB, motor state, byte-ready state, GCR byte, half-track, and stream position.
- Verification:
  - Regenerated and rebuilt `generated/c64_interactive`.
  - `PASM_C64_TRUE_DRIVE=1 ... LOAD"*",8,1` still returns `?FILE NOT FOUND  ERROR`, `ST=$42`.
- Trace finding:
  - The ROM does hit `$F2B0`, but mostly from VIA2 Timer 1 IRQ state (`v2ier=40`, `v2ifr=C0`), not from disk byte-ready data flow.
  - During the failing file-search loop:
    - `v2prb=F0`
    - `motor=0`
    - `gcr=55`
    - `pos=0`
    - `trk=35`
  - Therefore the failure is not “rotating on the right track but bad GCR decode”; the drive DOS reaches file-search state without an active disk read/motor job.

### 33. Immediate file-search loop cause

- ROM bytes around `$D599` show:
  - `$D599` calls `$D50E`, then `$D5A6`, then loops while carry is set.
  - `$D5A6` starts with `LDA $00,X`; in this repro `X=04`.
- New trace fields show:
  - `z00=00 00 00 00 B0 00 00 00`
  - So zero-page `$04` is already `$B0` when `$D5A6` runs.
- Conclusion:
  - `$D5A6` sees a negative channel/job status at `$00,X` and returns carry set.
  - `$D599` loops through the failure path and the host receives `FILE NOT FOUND`.
  - The next fix should target the earlier 1541 command/job setup that sets `$04=$B0`, not C64 CPU correctness, not PB7 sync polarity, and not raw stream timing after the search loop has already failed.

### 34. Job-table completion mirror and D64 layout check

- Added a targeted bridge in `c64_1541_subsystem_core.yaml` for the ROM disk-controller completion path:
  - When execution reaches `$F96E` after `STA $0000,Y`, mirror the completed zero-page job status into `$025B+Y` if the table entry is still negative.
  - This prevents `$D6B4-D6B9` from recopying stale `$B0` back over `$04`.
- Verification:
  - Regenerated and rebuilt `generated/c64_interactive`.
  - Trace confirms the bridge fires:
    - `pc=F96E ... cur=03 ... 025b=00 00 00 00 03`
  - User-visible result still remains `?FILE NOT FOUND  ERROR`, `ST=$42`.
- Added a latched sync flag for the synthetic GCR stream:
  - `via2_refresh_stream` now records when a consumed stream byte is `$FF`.
  - `via2_prb_read` uses that latch for active-low PB7 sync instead of checking only the next cache byte after stream advancement.
  - This did not change the visible result.
- Stepper trace correction:
  - The trace field labeled `trk` is the half-track, not the logical track.
  - Values around `35` mean logical track 18 after `(half + 1) / 2`, so the earlier "track 35" suspicion was a label interpretation error.
  - A temporary direction flip was tested and reverted because it moved the half-track to `37` and did not improve loading.
- Disk image finding:
  - `examples/floppies/c64/Mncm-1.d64` has the expected 174848-byte size but does not have a normal D64 BAM/directory pointer at track 18 sector 0.
  - The first bytes look GCR/protection-like rather than sector-ordered directory data, while `strings` still shows Maniac Mansion content.
  - This makes a plain ROM `LOAD "*",8,1` path suspect for this image; it may require the original custom bootstrap/loader rather than normal wildcard directory lookup.

### 35. No-TUI startup floppy and remaining true-drive load failure

- Found and fixed a no-TUI harness problem:
  - The C64-specific generated `main.c` did not accept `--floppy`.
  - `scripts/run_c64_no_tui.sh` exported `PASM_EMU_FLOPPY_AUTO_PATH`, but the generated C64 binary never loaded it.
  - This invalidated earlier no-TUI `FILE NOT FOUND` runs because the virtual drive was empty.
- Changes kept:
  - `src/generator.py` C64 main template now accepts `--floppy` and falls back to `PASM_EMU_FLOPPY_AUTO_PATH`.
  - `scripts/run_generated_no_tui.sh` passes `FLOPPY` as `--floppy` when the binary supports it.
- Verification:
  - Rebuilt `generated/c64_interactive`.
  - Load trace now confirms startup media insertion:
    - `Loaded floppy image: /tmp/pasm_test_normal.d64`
    - backend reports `size=174848 tracks=35`.
- New controlled repro:
  - A normal temporary D64 at `/tmp/pasm_test_normal.d64` has a valid directory chain:
    - BAM points to track 18 sector 1.
    - sector 18/1 contains PRG entry `HELLO`.
  - Even this normal D64 still returns:
    - `?FILE NOT FOUND  ERROR`
    - `ST=$42`
- Drive-side corrections/finding:
  - VIA2 motor decode was changed to active-low for this ROM path.
  - Stepper direction was flipped after the motor fix; the directory search now remains on half-track 35/logical track 18 instead of drifting to logical track 19.
  - The synthetic GCR stream is populated and rotating on logical track 18, and byte-ready IRQs occur during the early ROM read path.
- Remaining blocker:
  - The 1541 DOS search still reaches `$D599/$D5A6` with job slot 4 status `$B0`.
  - A narrow bridge can force `$04/$025F` to `$03`, but the user-visible result remains `FILE NOT FOUND`, which means the directory-sector buffer/search state is still not what DOS expects.
  - Next work should instrument or correct the 1541 buffer mapping for job slot 4 rather than revisiting host-side media insertion or 6502 opcode correctness.
