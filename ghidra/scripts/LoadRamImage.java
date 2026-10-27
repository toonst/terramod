// Load the post-scatter-load RAM images (produced by tools/scatter_emu.py) into the program:
//   itcm.bin -> new initialized block "ITCM" at 0x00000000 (rwx), where the audio/engine code lives
//   dtcm.bin -> bytes of the existing RAM block at 0x20000000 (converted to initialized if needed)
// The DTCM image also contains stack garbage near the top; only addresses below 0x2001B000 are written.
//@category Terra

import java.io.File;
import java.nio.file.Files;

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.mem.MemoryBlock;

public class LoadRamImage extends GhidraScript {

	@Override
	protected void run() throws Exception {
		File dir = askDirectory("Directory with itcm.bin / dtcm.bin (build/ram)", "Load");
		Memory mem = currentProgram.getMemory();

		File itcm = new File(dir, "itcm.bin");
		if (itcm.exists()) {
			byte[] b = Files.readAllBytes(itcm.toPath());
			Address a0 = toAddr(0);
			MemoryBlock blk = mem.getBlock(a0);
			if (blk == null) {
				blk = mem.createInitializedBlock("ITCM", a0, 0x10000, (byte) 0, monitor, false);
				blk.setRead(true);
				blk.setWrite(true);
				blk.setExecute(true);
			}
			mem.setBytes(a0, b);
			println("ITCM: wrote " + b.length + " bytes at 0x0");
		}

		File dtcm = new File(dir, "dtcm.bin");
		if (dtcm.exists()) {
			byte[] b = Files.readAllBytes(dtcm.toPath());
			int n = Math.min(b.length, 0x1B000);
			Address a = toAddr(0x20000000L);
			MemoryBlock blk = mem.getBlock(a);
			if (blk != null && !blk.isInitialized()) {
				mem.convertToInitialized(blk, (byte) 0);
			}
			byte[] part = new byte[n];
			System.arraycopy(b, 0, part, 0, n);
			mem.setBytes(a, part);
			println("DTCM: wrote " + n + " bytes at 0x20000000");
		}
	}
}
