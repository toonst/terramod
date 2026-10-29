# Flash test plan

Goal: prove, in small steps, that (a) the Terra accepts a longer image and (b) the patched code works.
The bootloader is never touched, so a bad application image can always be replaced with stock V1.7
(`firmware/TERRA_V1.7.smf`) from the USB stick. Not yet verified: that the bootloader still runs after a *crashing*
application (that is exactly what stage 2 would show, so keep the stock stick ready).

## Before you start
1. Back up memory: with a stick inserted at power-on, hold **S**, press **G** (H blinks), keep holding S+G and press **H**.
   Writes `TERRA___.smp` (all 96 presets + 24 pitch-shifter settings, manual p. 24). Copy it off the stick.
   `tools/terra_fw` can open it: `terra-fw info TERRA___.smp`.
2. Prepare sticks per manual p. 23: FAT32, 1-32 GB, **only one firmware file in the root**, USB 2.0 preferred (see forum notes).
3. Keep a stick with stock `TERRA_V1.7.smf` ready.

## Stages (flash, then update procedure: power on with stick, hold **L E**, then press **H** while holding L)
| Stage | File (build output in `dist/`) | Expected |
|---|---|---|
| 0 | stock `TERRA_V1.7.smf` | updater runs, instrument unchanged. Baseline: confirms your procedure and stick work |
| 1 | `dist/TERRA_V1.7_padtest/TERRA_V1.7_padtest.smf` (stock + 64 bytes of 0xFF) | update succeeds, Terra behaves exactly as stock. Tests: longer image + our CRC |
| 2 | `dist/TERRA_V1.7_holdmidi/TERRA_V1.7_holdmidi.smf` | update succeeds; behaviour as stock except hold test below |
| 3 | `dist/TERRA_V1.7_persistsettings/TERRA_V1.7_persistsettings.smf` | update succeeds; checks in [mods-persist-settings.md](mods-persist-settings.md) ("Not verified on hardware") |

Build stage 1 with `uv run terra-fw padtest firmware/TERRA_V1.7.smf dist/TERRA_V1.7_padtest/TERRA_V1.7_padtest.smf` (create the folder first),
stages 2-3 with `uv run terra-fw patch firmware/TERRA_V1.7.smf dist mods/<id>/mod.toml --auto-name`.

Naming (verified on the Terra): `TERRA_V<version>_<suffix>.smf` is recognised (e.g. `TERRA_V1.7_holdmidi.smf`); a `stage1_` prefix is not. One firmware file per stick root; `terra-fw patch ... --auto-name` builds a folder per image (hyphens in mod ids are dropped from the name).
**If stage 1 fails** (LEDs blink incessantly, or "all six LEDs light"): stop. Re-flash stock and write down what you saw;
the mods then need a different place for their code (dead space inside the image).

## Test for stage 2
1. Enter MIDI control (L + tuning sensor + H) and choose the note mode (A-D as CC, 1-12 as notes) and then MPE mode.
2. Use a MIDI monitor on the Terra's MIDI out. Press a note, press Note Hold (I), release the key.
   Expected: Note On, **no** Note Off. Press Hold again with nothing pressed (or press a new chord in auto-replacement mode):
   Note Off for the old note.
3. Regression: without hold, notes still send Note Off on release; sound unchanged; polyphony; MPE channels.
4. Known gap: poly aftertouch for a held, released key goes to 0.

## Results
Record every device test here (date, build, what happened). Until a row says otherwise, treat a stage as untested.

| Date | Build | Result |
|---|---|---|
| (before 2026-10-29) | file-name check | `TERRA_V<version>_<suffix>.smf` recognised by the updater, `stage1_` prefix not (commit 6a0ae54) |
