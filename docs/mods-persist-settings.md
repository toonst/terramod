# Mod: persist-settings

Keeps two settings across power cycles that the stock V1.7 firmware forgets:
1. the V1.3 "A + tuning" setting (A sensor pitch-down: 2 semitones / 12 semitones / until full stop; the same selection also changes
   the pitch-bender variants of two POLYPHONIC algorithms). The manual says it is not saved in presets.
2. the MIDI output mode (off / CC + notes variants / MPE). The manual says the output returns to *off* at power-up.

It replaces the earlier `persist-pitchdown` mod (pitch-down only, removed; see git history). Values saved by `persist-pitchdown` load
correctly (as "MIDI off"), and its pitch-down behaviour is unchanged (compared by emulating both mods side by side).

## Firmware facts (V1.7)
Symbols are in `symbols/terra_v1.7.toml`.

| Item | Address / value |
|---|---|
| pitch-down mode index (0 = 2 st, 1 = 12 st, 2 = full stop) | RAM `0x2000337C`, default 2, only touched by the selector block in `app_main_loop` (`0x08036E9E..0x08036ED4`) |
| value used by the engine | float at RAM `0x20003380`: `1 - 2^(-n/12)` = `0x3DDF7058` (2 st), `0.5` (12 st), `1.0` (stop); read by engine code at `0x08025DF4/0x08025E0C` |
| MIDI settings word | `ctx+0x1E8` (RAM `0x2000357C`): mode in bits 2-3 (`0` off, `4`, `8`, `0xC` = MPE), channel in bits 0, 1, 4, 5 |
| MIDI save | main loop `0x080363C8`: stores only `word & 0x33` to EEPROM `0x38`, so the channel persists and the mode does not |
| previous-value copy | `ctx+0x1EC` (RAM `0x20003580`): a difference from `ctx+0x1E8` sends all-notes-off and updates the copy |
| MIDI output active | `ctx+0x618` (RAM `0x200039AC`): `midi_out_pump` only runs while it is non-zero |

Restoring the mode bits alone is not enough: at boot `ctx+0x618` is 0, so the MIDI pump would not run. The stock code sets it when the mode
bits are non-zero in the change-check block at `0x080363F0`; when that block runs (every pass or only in the settings UI) has not been
checked, so the mod sets the flag itself.

## Design
**Storage:** one settings byte in the config block of the external EEPROM: `0x1A` = `pitch_mode (bits 0-1) | midi_mode (bits 2-3)`,
`0x1B` = byte ^ 0xA5 (validity check). These bytes lie between the calibration arrays (`0x02..0x19`) and the `"SOMA"` magic (`0x1C`);
[eeprom-map.md](eeprom-map.md) shows (statically and by emulating the config loader) that the stock firmware never uses them.
A factory reset rewrites the block and leaves a non-matching pair, which loads as the defaults (pitch = full stop, MIDI off).
The EEPROM is not part of the `.smp` dump (that starts at `0x40`), so presets and SysEx dumps are unaffected.

**Mechanism:** `mod_tick` is called from a hook at the head of every main-loop pass (`0x08035A56`, replacing `ldr r0,=huart1`, which the
trampoline redoes). Registers r0-r3, r12 and lr are preserved. Shadow state (magic + last saved byte) lives at `0x2001FFF0`, the top of
DTCM, which nothing in the image references.
* First call: read the two bytes; if valid, set the pitch-down index and float, replace bits 2-3 of `ctx+0x1E8` (the channel bits restored by
  the stock code stay), copy the word to `ctx+0x1EC` (so there is no spurious "mode changed" all-notes-off), and set `ctx+0x618 = 1` if the
  MIDI mode is not off. OmniChord stays off at power-up as documented.
* Later calls: if the combined byte differs from the last loaded/saved one (and the pitch index is 0..2), write both bytes: one ~5 ms
  EEPROM write per change, the same routine the firmware uses for master tune. A channel-only change is left to the stock code.

## Tests
`tools/terra_fw/tests/test_persist_settings.py` runs the real patched image in an emulator against a fake EEPROM: blank EEPROM, each valid
value, corrupt and out-of-range values, saving once per change, the old `persist-pitchdown` format, MIDI restore per mode with the channel
bits kept, output enabled only when the mode is not off, channel-only changes ignored, power-cycle round trips, stack and register balance.

## Not verified on hardware
* Set each of the three pitch-down modes with A + tuning, power-cycle, confirm it is restored; A-sensor behaviour and the triangle LEDs are
  otherwise unchanged.
* Each of the three MIDI modes (CC, notes, MPE) comes up transmitting after a power cycle without entering the settings UI, and the channel
  behaves as before.
* Open assumption: the top of DTCM (`0x2001FFF0..0x2001FFF7`) is free at run time (nothing in the image references it; the stack starts at
  `0x2001CD58` and grows down).

Gotcha found while testing: keystone silently mis-assembles a backward `cbz`; use `cmp`+`beq` for backward branches.
