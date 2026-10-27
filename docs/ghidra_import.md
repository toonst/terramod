# Loading the V1.7 firmware in Ghidra

1. `cd tools/terra_fw && PYTHONPATH=. python3 -m terra_fw.cli unpack ../../firmware/TERRA_V1.7.smf ../../build/app.bin`
2. Ghidra: File > Import File > `build/app.bin`
   - Format: **Raw Binary**
   - Language: **ARM:LE:32:Cortex** (Thumb)
   - Options: Base Address **0x08020000**
3. Add memory blocks (Window > Memory Map):
   - RAM `0x20000000`, size `0x20000`, rw, uninitialised
   - Peripherals `0x40000000`, size `0x20000000`, rw, volatile
   - System `0xE0000000`, size `0x100000`, rw, volatile
4. Create function at `0x08051CC4` (Reset_Handler), disassemble in Thumb mode, then auto-analyze.
   Vector table words at `0x08020000` should be defined as pointers.
5. Start GhidraMCP (plugin listens on 127.0.0.1:8080) so the `mcp__ghidra__*` tools can reach it.
