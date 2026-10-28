# Notes for AI agents (and anyone decompiling)

You do not need any of this to build or install mods; see [README.md](README.md). This is for reverse-engineering and writing new mods.

## Optional reference material (not needed for normal use)

**SOMA's documents** (copyright SOMA Laboratory, therefore not in git): download the Terra manual and the "Additional functions" PDF from
<https://somasynths.com/firmware_terra/> into `reference/`. They are git-ignored there and describe the intended behaviour of every
control (read them before fixing a "bug"). `pdftotext -layout` makes them greppable.

**ST HAL source** (large): `third_party/STM32CubeH7` is a submodule of ST's whole STM32CubeH7 repository (about 1.9 GB, slow to fetch).
The firmware's init and driver code is ST HAL code, so the sources help to name functions and struct fields in the decompiler output.
Fetch only the useful parts:

```bash
git submodule update --init --depth 1 third_party/STM32CubeH7
git -C third_party/STM32CubeH7 submodule update --init --depth 1 \
    Drivers/STM32H7xx_HAL_Driver Drivers/CMSIS/Device/ST/STM32H7xx
```

(The shallow flags are untested; `git submodule update --init --recursive` works but downloads everything.)

## Working method
* Start with [symbols/terra_v1.7.toml](symbols/terra_v1.7.toml) (addresses, structs, confirmed vs inferred), then [docs/midi-sysex.md](docs/midi-sysex.md)
  and the worked example [docs/bugs/hold-midi-notes.md](docs/bugs/hold-midi-notes.md).
* Ghidra setup: [docs/ghidra_import.md](docs/ghidra_import.md) (base `0x08020000`; scripts in `ghidra/scripts/`). The Ghidra MCP plugin only reads,
  renames and comments; it cannot create functions or run analyzers, so ask the user to do those in the GUI.
* Engine code runs from ITCM RAM and is not in the flash image as such; recover it with `uv run python tools/scatter_emu.py build/app.bin build/ram`.
* Record every finding in the symbol map with its status (`confirmed` / `inferred` / `guess`) and say how it was verified.
* Use `uv run` for everything (`uv run terra-fw …`, `uv run pytest`).

## Rules
* **Never commit SOMA firmware, presets, manuals or anything extracted from them** (`firmware/`, `build/`, `dist/`, `ghidra/Terra.*` are git-ignored). Mods are patches only.
* **Never touch the bootloader** (below `0x08020000`); every build must be an ordinary application image the stock updater accepts.
* Mods are locked to the SHA-256 of the firmware they were written for and check the original bytes at each hook (`expect`).
* Do not flash anything yourself or claim a mod works until the user has tested it on a Terra; say what was and wasn't verified.
* Licence: GPL-2.0-or-later, with an SPDX header on every source file.
