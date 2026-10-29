# Loading the V1.7 firmware in Ghidra

1. Extract the application image and recover the RAM-resident code:
   ```bash
   uv run terra-fw unpack firmware/TERRA_V1.7.smf build/app.bin
   uv run python tools/scatter_emu.py build/app.bin build/ram     # itcm.bin, dtcm.bin, axi.bin, sram123.bin, sram4.bin
   ```
2. Ghidra: File > Import File > `build/app.bin`
   - Format: **Raw Binary**
   - Language: **ARM:LE:32:Cortex** (Thumb)
   - Options: Base Address **0x08020000**
3. Add memory blocks (Window > Memory Map):
   - RAM (DTCM) `0x20000000`, size `0x20000`, rw, uninitialised
   - AXI SRAM `0x24000000`, size `0x80000`, rw, uninitialised
   - SRAM1-3 `0x30000000`, size `0x48000`, rw, uninitialised (MIDI RX byte at `0x30000000`, audio frame at `0x30000074`)
   - Peripherals `0x40000000`, size `0x20000000`, rw, volatile (covers the H7's D3 domain at `0x58000000`, e.g. RCC)
   - System `0xE0000000`, size `0x100000`, rw, volatile
4. Create function at `0x08051CC4` (Reset_Handler), disassemble in Thumb mode, then auto-analyze.
   Vector table words at `0x08020000` should be defined as pointers.
5. Run the scripts in `ghidra/scripts/` (see [ghidra/README.md](../ghidra/README.md)): `LoadSvd.java` (register and vector labels), then
   `LoadRamImage.java` with `build/ram` (creates the ITCM block at `0x0` with the engine code and fills DTCM with its initial values).
   Disassemble the TIM3 audio interrupt at `0x9730` afterwards.
6. Start GhidraMCP (plugin listens on 127.0.0.1:8080) so the `mcp__ghidra__*` tools can reach it.
