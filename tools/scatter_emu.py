# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Toon Stegen
"""Run the Keil scatter loader (0x08051B8C) of TERRA_V1.7 in Unicorn and dump the RAM images.

usage: uv run python tools/scatter_emu.py build/app.bin build/ram
Writes itcm.bin, dtcm.bin, axi.bin, sram123.bin, sram4.bin (only the non-zero extent).
"""
import os
import sys

from terra_fw.emu import AXI_SRAM, DTCM, ITCM, SRAM4, SRAM123, Emu

SCATTERLOAD = 0x08051B8C
REGIONS = {"itcm": ITCM, "dtcm": DTCM, "axi": AXI_SRAM, "sram123": SRAM123, "sram4": SRAM4}


def main(app, outdir):
    with open(app, "rb") as f:
        emu = Emu(f.read(), regions=REGIONS.values())
    emu.call(SCATTERLOAD, count=5_000_000)
    os.makedirs(outdir, exist_ok=True)
    for name, (addr, size) in REGIONS.items():
        img = bytes(emu.uc.mem_read(addr, size))
        end = len(img.rstrip(b"\0"))
        with open(os.path.join(outdir, name + ".bin"), "wb") as f:
            f.write(img[:end])
        print(f"{name:8} {addr:#010x}  non-zero extent {end:#x}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
