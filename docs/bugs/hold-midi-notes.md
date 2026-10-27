# Bug: Note Keyboard Hold does not hold MIDI notes (V1.7)

## Expected (manual v1.4 p.8 + V1.3/V1.7 addenda)
Note Keyboard Hold snapshots the pressed notes; they keep sounding until the hold memory is cleared or (auto
replacement mode) replaced by a new chord. The manual does not mention MIDI, so the proposed behaviour is:
held voices keep their MIDI Note On (no Note Off on key release); Note Off is sent when the hold releases them.

## Root cause (confirmed in disassembly)
Voice state lives in the synth context at `0x20003394` (`ctx`), indexed by voice slot 0..11:

| Array | Address | Meaning |
|---|---|---|
| `ctx+0x2DC` | `0x20003670` | voice -> sensor index |
| `ctx+0x30C` | `0x200036A0` | voice "key is down" flag |
| `ctx+0x36C` | `0x20003700` | voice **hold** flag |

* Hold press (main loop, `app_main_loop`): `ctx+0x36C[0..11] = ctx+0x30C[0..11]`; clearing hold zeroes it.
* Key release clears `ctx+0x30C[v]` only.
* The synth engine (e.g. `FUN_08029AE0`, `FUN_08028380`, `FUN_08028EA0`, `FUN_08027170`) treats a voice as sounding when
  `ctx+0x30C[v] != 0 || ctx+0x36C[v] != 0`.
* The MIDI generator `midi_out_pump` (0x08039940) tests **only** `ctx+0x30C[v]`, so key release sends Note Off even though the
  voice is held.

## Fix sites (both are "voice is down?" tests in `midi_out_pump`)
Hold flag is always at `+0x60` bytes from the key-down flag (0x36C - 0x30C).

1. Note mode (`ctx+0x1E8 & 0xC == 4`), per-voice loop, pointer in r5:
   ```
   0x080399DA  ldrh r0,[r5]        ; key-down flag
   0x080399DC  ldr.w r2,[pc,#..]   ; ctx
   0x080399E0  cmp r0,#0
   0x080399E2  beq.w 0x08039AFC    ; -> note-off path
   ```
   Need: `r0 = [r5] | [r5+0x60]` (flags set by the OR).
2. MPE mode (`== 0xC`), flag pointer kept at `[sp,#0x10]`:
   ```
   0x08039ED0  ldr r1,[sp,#0x10]
   0x08039ED2  ldrh r0,[r1]
   0x08039ED4  cmp r0,#0
   0x08039ED6  beq.w 0x0803A0A4    ; -> note-off path
   ```
   Need: `r0 = [r1] | [r1+0x60]`.

Neither fits in place (needs ~10 bytes, 8 available), so each is a `b.w` trampoline into new code:
```
site1:  b.w t1                       ; at 0x080399DA (rest of the old instructions is dead)
t1:     ldrh r0,[r5]; ldrh.w r1,[r5,#0x60]; orrs r0,r1
        ldr.w r2,=ctx                ; re-do the displaced literal load
        b.w 0x080399E2               ; flags from orrs feed the existing beq.w
site2:  b.w t2                       ; at 0x08039ED0
t2:     ldr r1,[sp,#0x10]; ldrh r0,[r1]; ldrh.w r1,[r1,#0x60]; orrs r0,r1
        b.w 0x08039ED6
```
Check r1 liveness at both sites before shipping (r1 is reloaded right after at 0x080399E6; at site 2 it is dead after `ldrh r0,[r1]`).

## Side effects to decide
* Poly aftertouch / channel pressure for held voices: with the key released the sensor value is 0, so aftertouch goes to 0.
  The engine uses a constant amplitude for held voices; matching that would mean freezing the aftertouch (not implemented in the sketch).
* A held voice retriggered by a new press: the existing note-on bookkeeping (`ctx+0x684`, `0x200039E0`) already handles it.

## Open risks
* Trampolines need ~40 bytes of new code. Free flash starts at `0x08059A54`; whether the bootloader accepts a longer `.smf`
  payload is untested (Phase 1 test). If not, search the image for dead padding.
* Nothing here has been tested on a device.
