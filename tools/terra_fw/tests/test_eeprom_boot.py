# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Toon Stegen
"""Run the stock firmware's boot-time config loader (`hw_config_and_leds_init`, 0x0803ABA6) in an emulator
against a fake EEPROM and log which EEPROM bytes it reads and writes. Used to check that EEPROM bytes
0x1A/0x1B (the persist-settings mod) are not used by the stock firmware."""
import pytest

pytest.importorskip("unicorn")

from terra_fw import container
from terra_fw.emu import DTCM, Emu

FUNC = 0x0803ABA6
MAGIC = bytes.fromhex("534f4d41")                    # 0x414D4F53 little endian, at EEPROM 0x1C
PERIPHERALS = [(0x40000000, 0x2000000), (0x58000000, 0x100000)]
# every other function the loader calls; return value 1 where the caller needs "success"
STUBS = {0x0803D104: 0, 0x0803A7E8: 0, 0x08032BA8: 0, 0x0803EBD0: 0, 0x0803E780: 1,
         0x0803EC68: 1, 0x0803F0C8: 0, 0x0803F3C2: 0, 0x0803F19C: 0, 0x0803F7E4: 0}


def run(smf, eeprom):
    emu = Emu(container.parse(smf).payload, regions=[DTCM, *PERIPHERALS], eeprom=eeprom, stubs=STUBS)
    emu.call(FUNC)
    return emu


def touches(accesses, lo, hi):
    return [(a, n) for a, n in accesses if a < hi and a + n > lo]


def test_valid_config_block_never_touches_0x1a_0x1b_except_whole_block_read(stock_smf):
    ee = {i: 0x32 for i in range(2, 0x1A)}
    ee.update({0x1A: 1, 0x1B: 1 ^ 0xA5})
    ee.update({0x1C + i: b for i, b in enumerate(MAGIC)})
    emu = run(stock_smf, ee)
    assert not emu.writes                                       # nothing is written when the magic is present
    # the 0x40-byte block read at 0 is the only access that spans 0x1A/0x1B; its bytes 0x1A/0x1B are never used
    assert touches(emu.reads, 0x1A, 0x1C) == [(0, 0x40)]


def test_blank_eeprom_reinitialises_first_32_bytes_and_our_check_fails_safe(stock_smf):
    emu = run(stock_smf, {})
    ee = emu.eeprom
    assert {(0, 0x20), (0x20, 0x20)} <= {(a, len(d)) for a, d in emu.writes}
    assert bytes(ee[0x1C + i] for i in range(4)) == MAGIC      # magic now present
    assert (ee[0x1A], ee[0x1B]) == (0, 0)                      # default init leaves 0/0
    assert ee[0x1B] != ee[0x1A] ^ 0xA5                         # -> mod treats it as "no saved value"
