# Mod: persist-settings (supersedes persist-pitchdown)

**Problem:** the V1.3 "A + tuning" setting (A sensor pitch-down: 2 semitones / 12 semitones / until full stop; the same
selection also changes the pitch-bender variants of two POLYPHONIC algorithms) is lost at power-off. The manual says it is not saved in presets.

**Firmware facts (V1.7)**
| Item | Address / value |
|---|---|
| mode index (0 = 2 st, 1 = 12 st, 2 = full stop) | RAM `0x2000337C`, default 2, written only by the selector code in `app_main_loop` (`0x08036E9E..0x08036ECE`) |
| value used by the engine | float at RAM `0x20003380`: `1 - 2^(-n/12)` = `0x3DDF7058` (2 st), `0.5` (12 st), `1.0` (stop); read by engine code at `0x08025DF4/0x08025E0C` |
| selector | `app_main_loop` block that tests the tuning sensor and three bits of the triangle input port |

**Design:** persist the 0..2 index in two bytes of the config block of the external EEPROM: `0x1A` = mode, `0x1B` = mode ^ 0xA5.
Those bytes lie between the calibration arrays (`0x02..0x19`) and the `"SOMA"` magic (`0x1C`) and nothing reads or writes them in V1.7.
A factory reset (the init code rewrites the block) leaves a non-matching pair, which loads as the default. The EEPROM is not part of the `.smp` dump (that starts at `0x40`), so presets and SysEx dumps are unaffected.

**Mechanism:** `mod_tick` is called from a hook at the head of every main-loop pass (`0x08035A56`, replacing `ldr r0,=huart1`).
First call: read the two bytes, validate, set the index and float (otherwise leave the default). Later calls: if the index differs from the last
loaded/saved value and is 0..2, write both bytes (one ~5 ms EEPROM write per change, same routine the firmware uses for master tune).
Shadow state (magic + last mode) lives at `0x2001FFF0`, the top of DTCM, which nothing in the image references. Registers r0-r3, r12 and lr are preserved.

**Tests:** `tools/terra_fw/tests/test_persist_pitchdown.py` runs the real patched image in an emulator against a fake EEPROM (blank EEPROM, valid values,
corrupt/out-of-range values, saving once per change, power-cycle round trip, stack and register balance).

**Not verified on hardware.** Things to check on the Terra: set each of the three modes with A + tuning, power-cycle, confirm it is restored;
and that A-sensor behaviour and the triangle LEDs are otherwise unchanged. Open assumptions: EEPROM bytes `0x1A/0x1B` really unused; top of DTCM free.

## Added in persist-settings: MIDI mode

**Why the stock firmware forgets it:** the MIDI settings word `ctx+0x1E8` (RAM `0x2000357C`) holds the MIDI *mode* in bits 2-3
(`0` off, `4`, `8`, `0xC` = MPE) and the MIDI *channel* in bits 0, 1, 4, 5. The save routine (main loop, `0x080363CE`) stores only `word & 0x33` to
EEPROM `0x38`, so the channel persists and the mode does not; the manual says the output returns to *off* at power-up. Restoring the bits alone is not
enough: the MIDI pump runs only while `ctx+0x618` (RAM `0x200039AC`) is non-zero, and only the settings UI sets it.

**What the mod does at boot:** replaces bits 2-3 of `ctx+0x1E8` (the channel bits restored by the stock code stay), copies the word to `ctx+0x1EC`
(the previous-value copy, so no spurious "mode changed" panic/all-notes-off), and sets `ctx+0x618 = 1` if the mode is not off. OmniChord stays off at power-up as documented.

**Storage:** one settings byte at EEPROM `0x1A` = `pitch_mode (bits 0-1) | midi_mode (bits 2-3)`, `0x1B` = byte ^ 0xA5. Saved on change only (a channel-only change is
left to the stock code). Bytes written by `persist-pitchdown` stay valid (MIDI mode off). Not combinable with `persist-pitchdown` (same hook site; the patcher refuses).

**Tests:** `test_persist_midimode.py` (restore per mode, channel bits kept, output enabled only when the mode is not off, old format, corrupt/blank EEPROM,
save-on-change with pitch bits preserved, channel-only changes ignored, power-cycle round trip).

**Not verified on hardware:** that each of the three MIDI modes (CC, notes, MPE) comes up transmitting after a power cycle without entering the settings UI, and that the
channel behaves as before. Gotcha found while testing: keystone silently mis-assembles a backward `cbz`; use `cmp`+`beq` for backward branches.
