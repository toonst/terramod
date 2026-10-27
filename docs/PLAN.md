# SOMA Terra — Firmware Mod System Plan

Goal: be able to **make, combine and load modifications** to the Terra's behaviour
without ever losing the ability to go back to stock firmware.

---

## 1. What we know so far

### Files

| File | Size | What it is |
|---|---|---|
| `TERRA_0.smp` | 4,048 B | **Factory preset bank**, not firmware (SOMA lists it as "factory presets") |
| `TERRA_V1.7.smf` | 236,132 B | **Firmware image**, V1.7 (released 2026‑03‑09) |

### `TERRA_0.smp` (preset bank): format decoded

```
0x000  "SOMA"            magic
0x004  03 00 00 00       format version (3)
0x008  "TERR"            device tag
0x00C  u32 LE            CRC-32 over 0x010..EOF  ← confirmed
0x010  96 × 32-byte preset slots (8 groups × 12), 0xFF-filled = empty slot
0xC10  global tables (pitch-shifter transposition table: 16 combos, signed semitones,
       plus fine-tune rows), rest 0xFF / 0x00
```

- The CRC is the **STM32 hardware CRC unit's default** (poly `0x04C11DB7`, init
  `0xFFFFFFFF`, no reflection, fed as little-endian 32-bit words). That is strong
  evidence the main MCU is an **STM32**, and the same routine is probably used for the
  firmware container.
- The 4,048-byte size and the `0xFF` fill look like a raw dump of a flash page/region.
- Each 32-byte preset slot:
  - bytes 0–11: note of each of the 12 note sensors (MIDI note, bit 7 = per-sensor flag, meaning TBD)
  - bytes 12–23: per-sensor microtuning offset (signed int8, likely 1/125-semitone steps)
  - bytes 24–31: packed synthesis parameters (algorithm, timbre, FX, …), bitfields TBD
- 69 of 96 slots are used in the factory bank.

### `TERRA_V1.7.smf` (firmware): first look

```
0x000  "SOMA"  "...."  "TERR"  + 4-byte check value (likely the same CRC, to confirm)
0x010  plain Cortex-M vector table (initial SP 0x2001CD58, reset → 0x08051CC5)
...    Thumb-2 code, float constants, tables
tail   initialised-data tables (the factory pitch-shifter table is visible there)
```

- **Not encrypted and not compressed** (the code is readable as-is). That's the
  single biggest enabler.
- Vectors point into `0x0805xxxx`. The application is linked **above something
  resident at the bottom of flash**, almost certainly the USB-stick bootloader.
  Because the stock updater only replaces the application, the bootloader should keep
  working when a modded application crashes. **This has to be verified** (Phase 0 gate).
- Large vector table and FPU-style float constants point to an F4/F7-class part.
  The exact part number is still to be confirmed.

### Platform facts (from SOMA docs and forum)

- Updates come from a **FAT-formatted USB stick**, which is finicky: old USB 2.0 /
  FAT16 sticks work best.
- **MIDI SysEx control** exists since V1.5, with a public spec in a SOMA Google Doc.
- Engine: 32 algorithms in 4 groups of 8, drum-kit engine, echo FX, gyroscope
  (relative/absolute), MPE, OmniChord mode, hold logic, pitch shifter (4 sensors →
  16 combos), 125 microtuning steps per semitone, 6-LED triangle UI.
- The release history (1.0 → 1.7) names subsystems that are useful landmarks when
  reverse-engineering, e.g. the "A sensor pitch-down mode" and the Pitch Shifter hold.

---

## 2. Guiding principles

1. **Never brick.** Never touch the bootloader. Every mod build is an ordinary
   application image that the stock updater accepts. Stock 1.7 is always one stick
   away.
2. **Don't redistribute SOMA's binary.** Mods ship as *patches* applied to the
   user's own official `.smf`, identified by SHA-256. The tool refuses unknown inputs.
3. **Target-locked.** Every mod declares the exact firmware hash(es) it supports.
4. **Composable.** Mods declare what they touch (byte ranges, hooks, RAM, flash). The
   tool detects conflicts and does all placement and linking in one place.
5. **Reproducible.** Unpacking and repacking stock firmware must give byte-identical
   output. Builds are deterministic.
6. **If the bootloader turns out to verify a signature, stop at Tier 0** (see §3) and
   talk to SOMA. Do not try to defeat it.

---

## 3. Mod tiers (in increasing power and risk)

| Tier | What changes | Examples | Risk |
|---|---|---|---|
| **0: Data** | Preset banks, SysEx, no firmware change | Preset/scale editor, Scala `.scl/.kbm` import, bank librarian, SysEx remote | None |
| **1: Constant/table patches** | Bytes in the image (tables, limits, defaults) | Different pitch-shifter table, default modes, LED timing, parameter ranges, velocity curves | Low |
| **2: Code hooks** | Redirect selected functions to new C code in free flash | New hold behaviour, custom sensor mappings, MIDI tweaks, new gyroscope modes | Medium |
| **3: Mod runtime** | A resident "modkit" with a stable hook API that other mods plug into | Insert effects on the audio block, replacement algorithms, mod settings over SysEx | Medium (built once, then safer per mod) |

Each tier builds on the one before, and you get usable results from Tier 0 onward.

---

## 4. Architecture

```
  official TERRA_V1.7.smf ─┐
  (user-supplied, hashed)  │
                           ▼
  mods/*.toml + *.c ──► terra-mod build
                         1. verify container + SHA-256 against supported list
                         2. unpack → app.bin @ load address
                         3. apply Tier-1 byte patches (with "expect" check)
                         4. compile + link Tier-2/3 code against symbol map,
                            place in free flash / reserved RAM
                         5. patch hook sites (BL retarget / trampolines)
                         6. repack + recompute header CRC
                           │
                           ▼
                    TERRA_V1.7+mods.smf ──► USB stick ──► stock bootloader ──► Terra
```

### Mod package format (proposal)

```toml
[mod]
id = "pitchshift-tables"
version = "0.1.0"
targets = ["70db296e2db1f553f8378db35eb14aebccc3810a83065b058f47a6f45a8a3572"]  # V1.7
conflicts = []
requires = []          # e.g. ["modkit>=1.0"] for Tier 3 mods

[[patch]]              # Tier 1
symbol = "pitch_shift_table"         # resolved via the per-version symbol map
expect = "00e8f4f90cdc02ed..."        # refuse if the original bytes differ
replace = "..."

[[hook]]               # Tier 2
target = "hold_handle_press"          # function in the symbol map
kind   = "replace" | "wrap"           # wrap = call original from the mod
impl   = "src/hold.c:my_hold_handle_press"

[resources]
flash = 2048           # bytes requested in the free-flash pool
ram   = 256
```

### Symbol maps (the "SDK")

`symbols/terra_v1.7.toml`: function and data names, addresses, C prototypes, and
notes on calling context (ISR / audio / main loop). This is the most valuable
artifact of the reverse-engineering work. Mods use names, never raw addresses, so
porting to V1.8 means porting the map, not every mod.

### Suggested repo layout

```
terra_firmware/
  docs/                  # PLAN.md, ghidra_import.md
  tools/terra_fw/        # Python: container, CRC, .smp codec, CLI, tests
  symbols/               # per-firmware-version symbol maps
  firmware/              # official *.smf / *.smp (git-ignored) + KNOWN.md hashes
  reference/             # STM32H743.svd, RM0433 (pdf ignored), README
  third_party/STM32CubeH7/   # git submodule (HAL source for matching decompiled code)
  build/                 # generated (app.bin, decompiler dumps), git-ignored
  sdk/ mods/ modkit/     # planned (Phases 3-5)
```

---

## 5. Phased roadmap

### Phase 0: Groundwork & safety gate

- [ ] Init git repo. `.gitignore` all `*.smf`/`*.smp`. Record SHA-256 of every
      official file in `firmware/KNOWN.md`.
- [ ] Read the main manual (update procedure, p. 23), the *Additional Functions*
      manual, and the SysEx spec doc. Note how presets are exported and backed up.
- [ ] **Back up your own presets** (export to stick, or SysEx dump if the spec allows).
- [ ] Prepare 2 known-good sticks (small, FAT16), one permanently holding stock V1.7.
- [ ] **Recovery gate:** find out how the bootloader is entered (always at power-up
      when a stick is present? or a button combo?) and whether it runs *before* the
      application. Use the manual/forum, or ask SOMA directly. Do not ship any
      Tier 1+ build to the device until this is answered.
- [ ] Optional: photograph the PCB to confirm the MCU part number. This fixes flash
      size, sector map and RAM. Opening the case may affect warranty.

**Done when:** recovery path is known and documented, and backups exist.

### Phase 1: Container & preset tooling (`terra_fw`, Tier 0)

- [ ] `terra_fw.container`: parse and validate `.smf`/`.smp` headers, STM32-CRC
      implementation, `unpack` (→ `app.bin` + metadata JSON), `pack`.
- [ ] Confirm the `.smf` check value uses the same CRC as `.smp` (or identify it).
- [ ] Round-trip test: `pack(unpack(x)) == x` for every official file.
- [ ] `terra_fw.presets`: full `.smp` codec ↔ JSON/YAML, decoding the packed
      parameter bits by diffing presets saved on the device with one parameter changed.
- [ ] Scala `.scl` + `.kbm` → 12 sensors + microtuning offsets (with the
      125-steps/semitone quantisation).
- [ ] SysEx client (Python `mido`, later WebMIDI) per SOMA's spec.
- [ ] **First device test:** flash a repacked *unmodified* image (byte-identical,
      so it only validates the workflow). Then one harmless Tier-1 change (e.g. a
      value in the pitch-shifter default table) to prove the device accepts modified
      images. If it rejects them → signature present → stay Tier 0 (principle 6).

**Done when:** presets and scales are editable from the computer, and a modified
image is accepted (or a hard "no" is established).

### Phase 2: Understand the firmware (interoperability RE)

- [ ] Load `app.bin` in Ghidra at the right base address with the MCU's SVD file
      for peripheral names (Ghidra MCP is already available here).
- [ ] Landmark subsystems: reset → `main`, audio DMA interrupt and block render,
      codec setup, sensor scanning/calibration, pots, LED triangle, preset
      load/save + flash layout, SysEx parser, MIDI in/out, USB-host/updater handoff.
- [ ] Map **resources**: free flash after the image end (and erase-sector
      boundaries), spare RAM between `.bss` end and the stack, audio-callback CPU
      headroom.
- [ ] Write `symbols/terra_v1.7.toml` as you go.
- [ ] Get older official images (1.5/1.6) if SOMA still hosts them. Diffing releases
      (Ghidra Version Tracking / BinDiff) pinpoints features named in the changelog
      and rehearses porting symbols to future versions.

**Done when:** the symbol map covers the audio path, sensor input, presets, MIDI,
and the free-resource map is written down.

### Phase 3: Patch engine (Tier 1)

- [ ] Implement the mod manifest, `expect`/`replace` patches by symbol, conflict
      detection (overlapping ranges), build report (what changed where).
- [ ] `terra-mod build --fw TERRA_V1.7.smf mods/a mods/b -o out.smf`.
- [ ] 2–3 real Tier-1 mods (alternate transposition tables, default "A sensor"
      mode, a parameter range).

**Done when:** two independent Tier-1 mods combine into one image that runs on the
device.

### Phase 4: Code mods (Tier 2)

- [ ] Toolchain: `arm-none-eabi-gcc`, matching CPU/FPU flags, `-ffreestanding`, no libc
      heap. The linker script places code in the free-flash pool and data in the
      reserved RAM pool, and imports firmware symbols (`--just-symbols` generated from
      the map).
- [ ] Hook mechanisms, implemented by the builder, not by hand:
      - **call-site retarget**: rewrite selected `BL` instructions to the mod function
      - **entry trampoline**: overwrite a function's first instructions with a branch;
        relocate the overwritten prologue so `wrap` mods can call the original
- [ ] Rules: respect the audio deadline, never block in ISRs, preserve FPU state
      conventions, no flash writes from mods (until Phase 5 provides a safe API).
- [ ] A **debug channel** mod: emit trace values as MIDI SysEx or CC so you can
      observe internals without a debugger.

**Done when:** a C mod changes a real behaviour (e.g. a new hold mode) and a `wrap`
hook can call the original.

### Phase 5: Mod runtime: "modkit" (Tier 3)

- [ ] A Tier-2 mod that installs a fixed set of hooks once and exposes
      `terra_api.h` (versioned):
      `on_boot`, `on_note_on/off`, `on_sensor(id, pressure)`, `on_pot`,
      `on_gyro`, `on_midi_in`, `on_sysex(mod-namespace)`, `on_audio_block(buf, n)`
      (post-processing insert), `get/set_param`, `led_*`.
- [ ] Mod table and dispatcher: several mods coexist, ordering is well-defined.
- [ ] Mod settings: configuration over a **mod-specific SysEx namespace** (no UI
      collisions), plus optional sensor-combo + LED feedback.
- [ ] Persistent mod settings only in a flash area proven unused in Phase 2, with
      wear-aware writes. Never in the preset region.
- [ ] Per-firmware-version adapter, so the API stays stable when SOMA ships V1.8.

**Done when:** an audio insert effect and a MIDI mod run together through modkit.

### Phase 6: Loading & distribution

- [ ] **Primary path:** build-time composition → one `.smf` → stock USB updater.
      Simple, and it uses the path SOMA already tests.
- [ ] Desktop/web "mod workbench": the user drops in their official `.smf`, picks
      mods, downloads the result. Use WebMIDI for preset/SysEx/mod configuration. It
      never hosts SOMA binaries.
- [ ] *Later / optional:* runtime loading of mod blobs from the USB stick by modkit
      at boot. This reuses firmware USB/FAT code and is far riskier. Consider it only
      once Phase 5 is stable.

### Phase 7: Testing & quality (runs alongside the other phases)

- Unit tests for container, CRC, preset codec, patcher.
- Offline emulation (Unicorn engine) of *pure* firmware functions (DSP blocks,
  preset decode) to compare stock vs. modded output without hardware.
- On-device checklist per release: boot, all 32 algorithms, presets load/save, MIDI
  in/out, SysEx, **updater still reachable and stock re-flash still works**.
- CI: build every mod against every supported firmware hash.

---

## 6. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Bricked unit | Bootloader never touched; Phase 0 recovery gate; stock stick always at hand |
| Image rejected / signed | Detected in Phase 1 with a harmless change; fall back to Tier 0 and ask SOMA |
| Preset loss | Back up first; mods never write the preset region |
| Audio dropouts | Measure callback headroom in Phase 2; budget per mod |
| New SOMA firmware | Hash-locked mods; symbol maps ported by binary diffing; modkit adapter layer |
| Flaky USB sticks | Small FAT16 sticks, known-good set |
| Legal / warranty | Personal-use modification of your own device; distribute patches only, no SOMA binaries; consider contacting SOMA (they opened SysEx and announced PC software, so they may be willing to share symbols or a hook API) |

---

## 7. Open questions

1. How exactly does the bootloader start, and does it run independently of the app?
2. Does the `.smf` check value use the same CRC as `.smp`, and is anything else verified?
3. Exact MCU part (flash/RAM size, sector map)?
4. Where in flash do user presets live, and is it the region `.smp` mirrors?
5. Meaning of the note-byte bit 7 flag and the 8 packed parameter bytes.
6. Can the device export a full preset bank to stick (for backup/round-trip tests)?

## 8. Immediate next steps

1. Phase 0 checklist (docs, backups, recovery question; possibly email SOMA).
2. Build `tools/terra_fw` container + `.smp` codec with round-trip tests.
3. Confirm the `.smf` checksum, then load the image in Ghidra at its base address.
