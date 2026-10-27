# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Toon Stegen
"""Run the Keil scatter loader (0x08051B8C) of TERRA_V1.7 in Unicorn and dump the RAM images.

usage: python scatter_emu.py build/app.bin build/ram
Writes itcm.bin, dtcm.bin, axi.bin, sram123.bin, sram4.bin (only the non-zero extent).
"""
import os
import sys

from unicorn import UC_ARCH_ARM, UC_MODE_MCLASS, UC_MODE_THUMB, Uc
from unicorn.arm_const import UC_ARM_REG_LR, UC_ARM_REG_SP

BASE = 0x08020000
SCATTERLOAD = 0x08051B8C
REGIONS = {
    "itcm": (0x00000000, 0x10000),
    "dtcm": (0x20000000, 0x20000),
    "axi": (0x24000000, 0x80000),
    "sram123": (0x30000000, 0x48000),
    "sram4": (0x38000000, 0x10000),
}


def main(app, outdir):
    data = open(app, "rb").read()
    uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
    flash_len = (len(data) + 0xFFF) & ~0xFFF
    uc.mem_map(BASE, flash_len + 0x1000)
    uc.mem_write(BASE, data)
    for addr, size in REGIONS.values():
        uc.mem_map(addr, size)
    uc.reg_write(UC_ARM_REG_SP, 0x2001CD58)
    stop = BASE + 0x100
    uc.reg_write(UC_ARM_REG_LR, stop | 1)
    uc.emu_start(SCATTERLOAD | 1, stop, count=5_000_000)
    os.makedirs(outdir, exist_ok=True)
    for name, (addr, size) in REGIONS.items():
        img = bytes(uc.mem_read(addr, size))
        end = len(img.rstrip(b"\0"))
        open(os.path.join(outdir, name + ".bin"), "wb").write(img[:end])
        print(f"{name:8} {addr:#010x}  non-zero extent {end:#x}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
