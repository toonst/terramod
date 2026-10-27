// Label STM32 peripheral registers and interrupt vectors from a CMSIS-SVD file.
// Creates a label and a sized data item (byte/word/dword) at every register address
// that already lies in program memory, plus labels on the vector table entries.
// Safe to re-run: existing user labels with the same name are left alone.
//@category Terra

import java.io.File;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import javax.xml.parsers.DocumentBuilderFactory;

import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.Node;
import org.w3c.dom.NodeList;

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.data.ByteDataType;
import ghidra.program.model.data.DWordDataType;
import ghidra.program.model.data.DataType;
import ghidra.program.model.data.WordDataType;
import ghidra.program.model.listing.CommentType;
import ghidra.program.model.symbol.SourceType;
import ghidra.program.model.symbol.Symbol;

public class LoadSvd extends GhidraScript {

	private static class Reg {
		String name;
		String desc;
		long offset;
		int bits;
	}

	private static class Periph {
		String name;
		long base;
		List<Reg> regs = new ArrayList<>();
		Element el;
	}

	// first direct child element with the given tag, or null
	private static Element child(Element e, String tag) {
		for (Node n = e.getFirstChild(); n != null; n = n.getNextSibling()) {
			if (n instanceof Element && ((Element) n).getTagName().equals(tag)) {
				return (Element) n;
			}
		}
		return null;
	}

	private static String text(Element e, String tag) {
		Element c = child(e, tag);
		return c == null ? null : c.getTextContent().trim();
	}

	private static long num(String s) {
		s = s.trim();
		if (s.startsWith("0x") || s.startsWith("0X")) {
			return Long.parseUnsignedLong(s.substring(2), 16);
		}
		if (s.startsWith("#")) {
			return Long.parseUnsignedLong(s.substring(1), 2);
		}
		return Long.parseLong(s);
	}

	private List<Reg> readRegs(Element periph, int defaultBits) {
		List<Reg> out = new ArrayList<>();
		Element regs = child(periph, "registers");
		if (regs == null) {
			return out;
		}
		for (Node n = regs.getFirstChild(); n != null; n = n.getNextSibling()) {
			if (!(n instanceof Element) || !((Element) n).getTagName().equals("register")) {
				continue; // clusters are not present in the STM32H743 SVD
			}
			Element r = (Element) n;
			Reg reg = new Reg();
			reg.name = text(r, "name");
			reg.desc = text(r, "description");
			reg.offset = num(text(r, "addressOffset"));
			String size = text(r, "size");
			reg.bits = size == null ? defaultBits : (int) num(size);
			out.add(reg);
		}
		return out;
	}

	private DataType typeFor(int bits) {
		switch (bits) {
			case 8:
				return ByteDataType.dataType;
			case 16:
				return WordDataType.dataType;
			default:
				return DWordDataType.dataType;
		}
	}

	private boolean label(Address a, String name, String comment) {
		try {
			for (Symbol s : currentProgram.getSymbolTable().getSymbols(a)) {
				if (s.getName().equals(name)) {
					return true;
				}
			}
			currentProgram.getSymbolTable().createLabel(a, name, SourceType.USER_DEFINED)
					.setPrimary();
			if (comment != null && !comment.isEmpty()) {
				currentProgram.getListing().setComment(a, CommentType.EOL,
					comment.replaceAll("\\s+", " "));
			}
			return true;
		}
		catch (Exception e) {
			return false;
		}
	}

	@Override
	protected void run() throws Exception {
		File svd = askFile("CMSIS-SVD file", "Load");
		Document doc = DocumentBuilderFactory.newInstance().newDocumentBuilder().parse(svd);
		Element device = doc.getDocumentElement();

		int defaultBits = 32;
		String ds = text(device, "size");
		if (ds != null) {
			defaultBits = (int) num(ds);
		}

		// pass 1: collect peripherals
		Map<String, Periph> byName = new HashMap<>();
		List<Periph> order = new ArrayList<>();
		Element peripherals = child(device, "peripherals");
		for (Node n = peripherals.getFirstChild(); n != null; n = n.getNextSibling()) {
			if (!(n instanceof Element) || !((Element) n).getTagName().equals("peripheral")) {
				continue;
			}
			Element e = (Element) n;
			Periph p = new Periph();
			p.el = e;
			p.name = text(e, "name");
			p.base = num(text(e, "baseAddress"));
			p.regs = readRegs(e, defaultBits);
			byName.put(p.name, p);
			order.add(p);
		}
		// pass 2: peripherals with derivedFrom inherit registers
		for (Periph p : order) {
			String from = p.el.getAttribute("derivedFrom");
			if (!from.isEmpty() && p.regs.isEmpty() && byName.containsKey(from)) {
				p.regs = byName.get(from).regs;
			}
		}

		int labelled = 0;
		int outside = 0;
		int failed = 0;
		for (Periph p : order) {
			Address base = toAddr(p.base);
			if (currentProgram.getMemory().contains(base)) {
				label(base, p.name, null);
			}
			for (Reg r : p.regs) {
				Address a = toAddr(p.base + r.offset);
				if (!currentProgram.getMemory().contains(a)) {
					outside++;
					continue;
				}
				if (!label(a, p.name + "_" + r.name, r.desc)) {
					failed++;
					continue;
				}
				try {
					if (currentProgram.getListing().getInstructionAt(a) == null) {
						currentProgram.getListing().clearCodeUnits(a,
							a.add(r.bits / 8 - 1), false);
						currentProgram.getListing().createData(a, typeFor(r.bits));
					}
				}
				catch (Exception e) {
					// overlapping registers (unions) - the label is enough
				}
				labelled++;
			}
		}

		// interrupt vector table: label word (16 + IRQn) at the image base
		int vecs = 0;
		Address table = currentProgram.getImageBase();
		for (Periph p : order) {
			for (Node n = p.el.getFirstChild(); n != null; n = n.getNextSibling()) {
				if (!(n instanceof Element) || !((Element) n).getTagName().equals("interrupt")) {
					continue;
				}
				Element irq = (Element) n;
				long value = num(text(irq, "value"));
				Address a = table.add(4 * (16 + value));
				if (currentProgram.getMemory().contains(a) &&
					label(a, "vec_" + text(irq, "name"), text(irq, "description") + " (IRQ " + value + ")")) {
					vecs++;
				}
			}
		}

		println("SVD " + text(device, "name") + ": " + labelled + " registers labelled, " + outside +
			" outside program memory, " + failed + " failed, " + vecs + " vector labels.");
	}
}
