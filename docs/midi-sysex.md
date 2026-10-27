# Terra MIDI input, SysEx and OmniChord (firmware V1.7)

Spec reference: SOMA's Terra SysEx document (linked from the V1.5 release notes). Firmware
findings from `symbols/terra_v1.7.toml`.

## Receive path
- USART1 RX, 31250 baud, **circular DMA of a single byte** into `0x30000000` (`HAL_UART_Receive_DMA(huart1, 0x30000000, 1)`
  started from `app_main_loop`). No USART interrupt is used.
- Each received byte raises the DMA1 stream 3 transfer-complete interrupt (vector 30 at `0x08051608`),
  which branches to **`0x0803C478`**: the per-byte MIDI input handler (not a Ghidra function yet;
  define one at `0x0803C478` to decompile it). The byte is cleared (`strb 0,[0x30000000]`) after use.
- A byte arriving while the previous one has not been consumed is simply lost (1-byte buffer).

## SysEx receive state machine (context `0x20019BB4`)
| State | Meaning |
|---|---|
| 0 | idle |
| 1 | `F0` seen, collecting the 8 header bytes into ctx+0x14..0x1B |
| 2 | collecting data: each group of 5 seven-bit bytes becomes one 32-bit word at ctx+0x1C+idx |
| 3 | `F7` received with no partial group: command ready for `sysex_dispatch` (0x0803C25C) |
| 4 | reply ready, success (`sysex_tx_pump` sends it) |
| 5 | error (reply sent with ack = 1) |

- A status byte (>= 0x80) other than `F7` inside a message aborts it with state 5. Real-time bytes (>= 0xF8) are not consumed by the SysEx machine.
- Overflow guard: if the write index reaches 0x1771 (6001 bytes) the state returns to 0.
- Word assembly: the n-th byte of a group is OR'd in at shift `7*(4-n)`, so the first byte carries the top 4 bits.

## Spec vs firmware
| Spec | Firmware | Verdict |
|---|---|---|
| `F0 7E 54 45 52 aa bb cc dd ... F7` | header check: ctx[5]==0x7E, 'T','E','R' at +0x15..0x17, command at +0x18, bank +0x19, preset +0x1A, repeat +0x1B compared with command | matches |
| commands 0x00..0x0B | `sysex_dispatch` switch on 0..11, same grouping (0/2 = full dump, 1 write dump, 3 write all pitchshifters, 4 read one PS, 5 write one PS, 6/8/10 read preset/sound/scale, 7/9/11 write) | matches |
| bank 0..5, `0x7F` = full dump; preset 0..15, `0x7F` = live | write handlers accept bank <= 5 and preset <= 0xF, or preset 0x7F meaning the live preset (applied with FUN_08038AB4 instead of written to EEPROM) | matches |
| 4 data bytes -> 5 bytes, MSB 0, first byte holds the top 4 bits | RX packing as above; TX (`sysex_cmd_dump_all_presets`) emits `>>28, >>21&7F, >>14&7F, >>7&7F, &7F` | matches (endianness of the source word still to verify against a real dump) |
| reply `F0 7E TER aa bb cc dd(0 ok/1 fail) data F7` | `sysex_tx_pump`: `F0`, ctx[0x14..] (header + data), `F7`; ack = (state == 5) | matches |
| data is the `.smp` file | full dump packs 4 header words (SOMA header + CRC computed with the hardware CRC unit) then EEPROM 0x40..0xFFF in 32-byte records = 5060 bytes + `F7` | confirmed: SysEx data == `.smp` file, 4048 bytes |
| error codes | only 0 / 1 | firmware has only states 4 / 5 |

Consequence: `terra_fw.presets` can already produce and parse the payload of every SysEx message, so a
SysEx librarian needs only the 5-byte packing and the MIDI transport.

## Regular (non-SysEx) MIDI input
The same handler then runs a small running-status machine (state at `0x2001C398`):
- **OmniChord flag** `0x2000366C` != 0: only messages on the Terra's MIDI channel (`u16` at `0x20003582`)
  are used. Note On with velocity >= 1 stores `note - 12` into the table `u16[12]` at `0x200035F8`
  (second table at `0x20003610` zeroed), at the position given by the counter `0x2001C3FC`
  (clamped 0..11); existing voices are retriggered through `FUN_08037FB8(sensor)`. Note Off / velocity 0
  decrements the counter. This matches the V1.4 / V1.41 changelog (notes assigned to sensors 1..N,
  not retriggered until played).
- **OmniChord off**: if `0x2001C3B8` != 0 (the "tune a sensor from a MIDI keyboard" mode, V1.2) only Note On
  is accepted and the note is stored for the tuning code (`0x20003378`).
- Channel mode / other messages fall through and update the running status.
