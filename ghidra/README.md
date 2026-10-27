Local Ghidra project `Terra` lives here (git-ignored). Open `Terra.gpr` in Ghidra.
Import settings: see ../docs/ghidra_import.md

## Scripts (`ghidra/scripts/`)
- `LoadSvd.java`: labels every peripheral register from `reference/STM32H743.svd` and the
  vector table entries. In Ghidra: Script Manager > "Manage Script Directories" (list icon) >
  add this folder, run `LoadSvd.java`, pick the SVD file. Run it after the image base is
  0x08020000. Prints a summary line to the console.
