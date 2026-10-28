# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Toon Stegen
"""Emulate the persist-pitchdown trampoline against the real patched image, with a fake EEPROM."""
import pathlib
import struct

import pytest

pytest.importorskip("keystone")
unicorn = pytest.importorskip("unicorn")
from unicorn import UC_ARCH_ARM, UC_HOOK_CODE, UC_MODE_MCLASS, UC_MODE_THUMB, Uc
from unicorn.arm_const import UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_SP

from terra_fw import container, patcher

ROOT = pathlib.Path(__file__).resolve().parents[3]
SMF = ROOT / "firmware" / "TERRA_V1.7.smf"
MOD = ROOT / "mods" / "persist-pitchdown" / "mod.toml"
pytestmark = pytest.mark.skipif(not SMF.exists(), reason="no stock firmware")

BASE = 0x08020000
HOOK, RET = 0x08035A56, 0x08035A5A
MODE, FLOAT, SHADOW = 0x2000337C, 0x20003380, 0x2001FFF0
MAGIC = 0x7E57AB1E


class Rig:
    def __init__(self, eeprom):
        out, _ = patcher.apply(SMF.read_bytes(), [patcher.load_mod(str(MOD))])
        payload = container.parse(out).payload
        self.eeprom = dict(eeprom)
        self.writes = []
        uc = self.uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
        uc.mem_map(BASE, (len(payload) + 0xFFF) & ~0xFFF)
        uc.mem_write(BASE, payload)
        uc.mem_map(0x20000000, 0x20000)
        uc.hook_add(UC_HOOK_CODE, self._stub, begin=0x0803AE58, end=0x0803AE78 + 2)

    def _stub(self, uc, addr, size, _):
        if addr not in (0x0803AE58, 0x0803AE78):
            return
        a, buf, n = (uc.reg_read(r) for r in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2))
        if addr == 0x0803AE58:
            uc.mem_write(buf, bytes(self.eeprom.get(a + i, 0xFF) for i in range(n)))
        else:
            data = bytes(uc.mem_read(buf, n))
            self.writes.append((a, data))
            for i, b in enumerate(data):
                self.eeprom[a + i] = b
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))   # keep the Thumb bit

    def tick(self):
        uc = self.uc
        uc.reg_write(UC_ARM_REG_SP, 0x2001CD58)
        uc.reg_write(UC_ARM_REG_R0, 0x11111111)
        uc.emu_start(HOOK | 1, RET, count=2000)
        assert uc.reg_read(UC_ARM_REG_SP) == 0x2001CD58
        assert uc.reg_read(UC_ARM_REG_R0) == 0x2001BC0C   # displaced `ldr r0,=huart1` re-done

    def mode(self):
        return struct.unpack("<If", bytes(self.uc.mem_read(MODE, 8)))

    def setmode(self, m):
        self.uc.mem_write(MODE, struct.pack("<I", m))


def test_first_boot_blank_eeprom_keeps_default():
    r = Rig({})
    r.uc.mem_write(MODE, struct.pack("<If", 2, 1.0))
    r.tick()
    assert r.mode() == (2, 1.0) and not r.writes


@pytest.mark.parametrize("m,f", [(0, struct.unpack("<f", struct.pack("<I", 0x3DDF7058))[0]), (1, 0.5), (2, 1.0)])
def test_valid_eeprom_is_loaded(m, f):
    r = Rig({0x1A: m, 0x1B: m ^ 0xA5})
    r.uc.mem_write(MODE, struct.pack("<If", 2, 1.0))
    r.tick()
    assert r.mode() == (m, f) and not r.writes


def test_corrupt_or_out_of_range_eeprom_ignored():
    for ee in ({0x1A: 1, 0x1B: 1}, {0x1A: 7, 0x1B: 7 ^ 0xA5}, {0x1A: 0, 0x1B: 0}):
        r = Rig(ee)
        r.uc.mem_write(MODE, struct.pack("<If", 2, 1.0))
        r.tick()
        assert r.mode() == (2, 1.0) and not r.writes


def test_change_is_saved_once():
    r = Rig({})
    r.uc.mem_write(MODE, struct.pack("<If", 2, 1.0))
    r.tick()
    r.setmode(0)
    r.tick(); r.tick(); r.tick()
    assert r.writes == [(0x1A, bytes([0, 0xA5]))]
    r.setmode(1)
    r.tick()
    assert r.writes[-1] == (0x1A, bytes([1, 1 ^ 0xA5])) and len(r.writes) == 2


def test_invalid_mode_not_saved():
    r = Rig({})
    r.uc.mem_write(MODE, struct.pack("<If", 2, 1.0))
    r.tick()
    r.setmode(9)
    r.tick()
    assert not r.writes


def test_survives_power_cycle():
    r = Rig({})
    r.uc.mem_write(MODE, struct.pack("<If", 2, 1.0))
    r.tick(); r.setmode(1); r.tick()
    r2 = Rig(r.eeprom)                       # fresh RAM, same EEPROM
    r2.uc.mem_write(MODE, struct.pack("<If", 2, 1.0))
    r2.tick()
    assert r2.mode() == (1, 0.5)
