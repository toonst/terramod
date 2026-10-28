# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Toon Stegen
"""Run the stock firmware's boot-time config loader (`hw_config_and_leds_init`, 0x0803ABA6) in an emulator
against a fake EEPROM and log which EEPROM bytes it reads and writes. Used to check that EEPROM bytes
0x1A/0x1B (the persist-pitchdown mod) are not used by the stock firmware."""
import pathlib

import pytest

unicorn = pytest.importorskip("unicorn")
from unicorn import UC_ARCH_ARM, UC_HOOK_CODE, UC_MODE_MCLASS, UC_MODE_THUMB, Uc
from unicorn.arm_const import UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_SP

from terra_fw import container

ROOT = pathlib.Path(__file__).resolve().parents[3]
SMF = ROOT / "firmware" / "TERRA_V1.7.smf"
pytestmark = pytest.mark.skipif(not SMF.exists(), reason="no stock firmware")

BASE = 0x08020000
FUNC, STOP = 0x0803ABA6, 0x08020100
EE_READ, EE_WRITE = 0x0803AE58, 0x0803AE78
MAGIC = bytes.fromhex("534f4d41")                    # 0x414D4F53 little endian, at EEPROM 0x1C
# every other function the loader calls; return value 1 where the caller needs "success"
STUBS = {0x0803D104: 0, 0x0803A7E8: 0, 0x08032BA8: 0, 0x0803EBD0: 0, 0x0803E780: 1,
         0x0803EC68: 1, 0x0803F0C8: 0, 0x0803F3C2: 0, 0x0803F19C: 0, 0x0803F7E4: 0}


def run(eeprom):
    payload = container.parse(SMF.read_bytes()).payload
    uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
    uc.mem_map(BASE, (len(payload) + 0xFFF) & ~0xFFF)
    uc.mem_write(BASE, payload)
    uc.mem_map(0x20000000, 0x20000)
    uc.mem_map(0x40000000, 0x2000000)
    uc.mem_map(0x58000000, 0x100000)
    log = []

    def hook(uc, addr, size, _):
        if addr in (EE_READ, EE_WRITE):
            a, buf, n = (uc.reg_read(r) for r in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2))
            if addr == EE_READ:
                log.append(("R", a, n))
                uc.mem_write(buf, bytes(eeprom.get(a + i, 0xFF) for i in range(n)))
            else:
                data = bytes(uc.mem_read(buf, n))
                log.append(("W", a, n))
                for i, b in enumerate(data):
                    eeprom[a + i] = b
        elif addr in STUBS:
            uc.reg_write(UC_ARM_REG_R0, STUBS[addr])
        else:
            return
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    uc.hook_add(UC_HOOK_CODE, hook, begin=BASE, end=BASE + len(payload))
    uc.reg_write(UC_ARM_REG_SP, 0x2001CD58)
    uc.reg_write(UC_ARM_REG_LR, STOP | 1)
    uc.emu_start(FUNC | 1, STOP, count=200000)
    return log


def touches(log, lo, hi):
    return [(k, a, n) for k, a, n in log if a < hi and a + n > lo]


def test_valid_config_block_never_touches_0x1a_0x1b_except_whole_block_read():
    ee = {i: 0x32 for i in range(2, 0x1A)}
    ee.update({0x1A: 1, 0x1B: 1 ^ 0xA5})
    ee.update({0x1C + i: b for i, b in enumerate(MAGIC)})
    before = dict(ee)
    log = run(ee)
    assert not [e for e in log if e[0] == "W"]                 # nothing is written when the magic is present
    assert ee[0x1A] == before[0x1A] and ee[0x1B] == before[0x1B]
    # the 0x40-byte block read at 0 is the only access that spans 0x1A/0x1B; its bytes 0x1A/0x1B are never used
    assert touches(log, 0x1A, 0x1C) == [("R", 0, 0x40)]


def test_blank_eeprom_reinitialises_first_32_bytes_and_our_check_fails_safe():
    ee = {}
    log = run(ee)
    assert ("W", 0, 0x20) in log and ("W", 0x20, 0x20) in log
    assert bytes(ee[0x1C + i] for i in range(4)) == MAGIC      # magic now present
    assert (ee[0x1A], ee[0x1B]) == (0, 0)                      # default init leaves 0/0
    assert ee[0x1B] != ee[0x1A] ^ 0xA5                         # -> mod treats it as "no saved value"
