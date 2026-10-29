Local Ghidra project `Terra` lives here (git-ignored). Open `Terra.gpr` in Ghidra.
Import settings: see ../docs/ghidra_import.md

## Scripts (`ghidra/scripts/`)
In Ghidra: Script Manager > "Manage Script Directories" (list icon) > add this folder. Run them after the image base is 0x08020000.
- `LoadSvd.java`: labels every peripheral register from `reference/STM32H743.svd` and the
  vector table entries. Run it and pick the SVD file. Prints a summary line to the console.
- `LoadRamImage.java`: loads the RAM images that `tools/scatter_emu.py` writes to `build/ram`: `itcm.bin` becomes a new
  rwx block "ITCM" at 0x0 (engine and audio-interrupt code), `dtcm.bin` fills the existing RAM block at 0x20000000
  (only below 0x2001B000, to skip stack garbage). Create the RAM block first (see ../docs/ghidra_import.md).
