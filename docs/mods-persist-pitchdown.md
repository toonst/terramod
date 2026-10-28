# Mod: persist-pitchdown

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
