# External EEPROM map (firmware V1.7)

I2C EEPROM, device address `0xA0`, 16-bit memory addresses, all access through `eeprom_read` (0x0803AE58) / `eeprom_write` (0x0803AE78)
(write-protect pin GPIOD 11 is dropped only inside `eeprom_write`). The only other users of `i2c_mem_read/write` talk to the touch controllers (address `0xB4`).
Size is not known; the firmware uses `0x0000..0x0FFF`.

Derived from all 28 `eeprom_*` call sites (static) plus an emulated run of the boot loader (`tools/terra_fw/tests/test_eeprom_boot.py`).

| Address | Size | Content | Written by |
|---|---|---|---|
| `0x00` | 1 | last used preset index | `FUN_08038808` (preset save), config init |
| `0x01` | 1 | master tune (signed) | main loop (`0x08036588`), config init |
| `0x02..0x19` | 24 | sensor calibration (2 x 12 bytes, default `0x32`) | calibration routine `FUN_080330b4` (`0x080338E2`), config init |
| `0x1A..0x1B` | 2 | **unused in V1.7** (zero after config init); used by the `persist-pitchdown` mod | config init only (writes 0/0) |
| `0x1C..0x1F` | 4 | magic `"SOMA"` (`0x414D4F53`), checked at boot; if wrong the block is re-initialised | config init |
| `0x20..0x3F` | 32 | 16 x u16 thresholds (default 400) | calibration routine (`0x080338D0`), config init |
| `0x38` | 1 | MIDI output mode/channel bits (`ctx+0x1E8 & 0x33`); written by the main loop (`0x080363E0`). It overlaps the threshold array: a firmware quirk, not ours | main loop |
| `0x40..0xBFF` | 96 x 32 | presets (`0x40 + (bank*16 + slot)*0x20`; +0x18 holds the 8 parameter bytes) | preset save, SysEx 7/9/11/1 |
| `0xC40..0xFFF` | 24 x 32 | pitch-shifter tunings (`0xC40 + n*0x20`) | pitch-shifter tuning, SysEx 5/3 |

## Is `0x1A/0x1B` free?
* **Writes:** every write that can cover them is the config-init path (`hw_config_and_leds_init`, 0x0803AC62: `write(0, 0x20)`), which runs only when the
  magic at `0x1C` is missing. All other writes are `[0]`, `[1]`, `[2..0x19]`, `[0x20..0x3F]`, `[0x38]`, or `>= 0x40`. SysEx writes are bounded to `0x40..0xFFF`.
* **Reads:** the only read spanning them is the 0x40-byte read of the whole block at boot; the firmware then uses bytes `[0]`, `[1]`, `[2..0x19]`, `[0x1C]` and `[0x20..]` only.
* **Emulation:** with a valid block the boot loader performs no writes and leaves the bytes untouched; with a blank EEPROM it re-initialises bytes `0..0x1F`
  (so `0x1A/0x1B` become 0/0), which the mod's `mode ^ 0xA5` check treats as "nothing saved".
* **Side effect to know:** a factory re-initialisation (or a corrupt magic) forgets the saved pitch-down mode. Normal operation, SysEx and preset
  load/save never touch these bytes.
