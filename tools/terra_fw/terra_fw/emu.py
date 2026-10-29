# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Toon Stegen
"""Run pieces of a TERRA application image in Unicorn, without hardware.

The image is mapped at LOAD_BASE, plus the RAM regions asked for. Calls to the firmware's eeprom_read/eeprom_write
go to a fake EEPROM (a dict; missing bytes read as 0xFF, i.e. blank), and calls to `stubs` return at once with a
fixed r0. Needs the `unicorn` package (a dev dependency). Addresses are V1.7 (symbols/terra_v1.7.toml).
"""
import struct

from unicorn import UC_ARCH_ARM, UC_HOOK_CODE, UC_MODE_MCLASS, UC_MODE_THUMB, Uc, arm_const

from .firmware import LOAD_BASE

INITIAL_SP = 0x2001CD58
EEPROM_READ, EEPROM_WRITE = 0x0803AE58, 0x0803AE78    # (addr, buf, len)
RETURN_ADDR = LOAD_BASE + 0x100                       # inside the vector table, never executed: `call` returns here

# (base, size) of the STM32H7 memories the firmware uses
ITCM = (0x00000000, 0x10000)
DTCM = (0x20000000, 0x20000)
AXI_SRAM = (0x24000000, 0x80000)
SRAM123 = (0x30000000, 0x48000)
SRAM4 = (0x38000000, 0x10000)


def _reg(name: str) -> int:
    return getattr(arm_const, f"UC_ARM_REG_{name.upper()}")


class Emu:
    def __init__(self, payload: bytes, regions=(DTCM,), eeprom=None, stubs=None):
        uc = self.uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
        uc.mem_map(LOAD_BASE, (len(payload) + 0xFFF) & ~0xFFF)
        uc.mem_write(LOAD_BASE, payload)
        for base, size in regions:
            uc.mem_map(base, size)
        self.eeprom = dict(eeprom or {})
        self.reads = []    # (addr, len) of every eeprom_read
        self.writes = []   # (addr, data) of every eeprom_write
        self.stubs = dict(stubs or {})
        for addr in (EEPROM_READ, EEPROM_WRITE, *self.stubs):
            uc.hook_add(UC_HOOK_CODE, self._intercept, begin=addr, end=addr)

    def _intercept(self, uc, addr, size, _):
        if addr in self.stubs:
            uc.reg_write(arm_const.UC_ARM_REG_R0, self.stubs[addr])
        else:
            a, buf, n = (self.reg(r) for r in ("r0", "r1", "r2"))
            if addr == EEPROM_READ:
                self.reads.append((a, n))
                uc.mem_write(buf, bytes(self.eeprom.get(a + i, 0xFF) for i in range(n)))
            else:
                data = bytes(uc.mem_read(buf, n))
                self.writes.append((a, data))
                self.eeprom.update((a + i, b) for i, b in enumerate(data))
        uc.reg_write(arm_const.UC_ARM_REG_PC, self.reg("lr"))   # return to the caller (LR keeps the Thumb bit)

    def run(self, start: int, until: int, *, count: int, sp: int = INITIAL_SP, **regs):
        """Execute from `start` to `until`, after setting SP and any registers given as keywords (r0=...)."""
        self.uc.reg_write(arm_const.UC_ARM_REG_SP, sp)
        for name, value in regs.items():
            self.uc.reg_write(_reg(name), value)
        self.uc.emu_start(start | 1, until, count=count)
        if self.reg("pc") != until:
            raise RuntimeError(f"stopped at {self.reg('pc'):#x} after {count} instructions, before reaching {until:#x}")

    def call(self, func: int, *, count: int = 200_000, **regs):
        """Call the function at `func` and run until it returns."""
        self.run(func, RETURN_ADDR, count=count, lr=RETURN_ADDR | 1, **regs)

    def reg(self, name: str) -> int:
        return self.uc.reg_read(_reg(name))

    def read(self, addr: int, fmt: str):
        """Unpack memory at `addr` with struct format `fmt`; a single field is returned as a plain value."""
        values = struct.unpack(fmt, bytes(self.uc.mem_read(addr, struct.calcsize(fmt))))
        return values[0] if len(values) == 1 else values

    def write(self, addr: int, fmt: str, *values):
        self.uc.mem_write(addr, struct.pack(fmt, *values))
