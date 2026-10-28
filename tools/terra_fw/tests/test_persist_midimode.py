# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Toon Stegen
"""persist-settings: MIDI-mode part (settings byte layout, restore into ctx+0x1E8, active flag, save-on-change)."""
import struct

import pytest

pytest.importorskip("keystone")
pytest.importorskip("unicorn")
from test_persist_pitchdown import MODE, Rig, SMF  # noqa: E402

pytestmark = pytest.mark.skipif(not SMF.exists(), reason="no stock firmware")

MIDI = 0x2000357C        # ctx+0x1E8 word: mode bits 2-3, channel bits 0,1,4,5
PREV = 0x20003580        # ctx+0x1EC
ACTIVE = 0x200039AC      # ctx+0x618


def setup(r, midi_word=0x10, pitch=2):
    r.uc.mem_write(MODE, struct.pack("<If", pitch, 1.0))
    r.uc.mem_write(MIDI, struct.pack("<H", midi_word))
    r.uc.mem_write(ACTIVE, struct.pack("<I", 0))


def word(r, a, fmt="<H"):
    return struct.unpack(fmt, bytes(r.uc.mem_read(a, struct.calcsize(fmt))))[0]


@pytest.mark.parametrize("midi", [0x4, 0x8, 0xC])
def test_saved_midi_mode_restored_keeps_channel_and_activates_output(midi):
    b = 1 | midi                                           # pitch mode 1 + MIDI mode
    r = Rig({0x1A: b, 0x1B: b ^ 0xA5})
    setup(r, midi_word=0x31)                              # stock-restored channel bits + junk low bits
    r.tick()
    assert word(r, MIDI) == (0x31 & ~0xC) | midi          # only bits 2-3 replaced
    assert word(r, PREV) == word(r, MIDI)                 # no spurious "mode changed" later
    assert word(r, ACTIVE, "<I") == 1                     # pump enabled
    assert r.mode() == (1, 0.5) and not r.writes


def test_midi_off_does_not_enable_output():
    r = Rig({0x1A: 2, 0x1B: 2 ^ 0xA5})
    setup(r)
    r.tick()
    assert word(r, ACTIVE, "<I") == 0 and word(r, MIDI) == 0x10


def test_old_pitchdown_only_format_is_compatible():
    r = Rig({0x1A: 0, 0x1B: 0 ^ 0xA5})                    # written by the persist-pitchdown mod
    setup(r, midi_word=0x14)
    r.tick()
    assert r.mode()[0] == 0 and word(r, MIDI) == 0x10 and word(r, ACTIVE, "<I") == 0


def test_blank_or_corrupt_gives_defaults():
    for ee in ({}, {0x1A: 0x0C, 0x1B: 0}, {0x1A: 0x1C, 0x1B: 0x1C ^ 0xA5}, {0x1A: 3, 0x1B: 3 ^ 0xA5}):
        r = Rig(ee)
        setup(r, midi_word=0x10)
        r.tick()
        assert r.mode() == (2, 1.0) and word(r, MIDI) == 0x10 and word(r, ACTIVE, "<I") == 0 and not r.writes


def test_midi_mode_change_saved_with_pitch_bits_preserved():
    r = Rig({0x1A: 1, 0x1B: 1 ^ 0xA5})
    setup(r)
    r.tick()
    r.uc.mem_write(MIDI, struct.pack("<H", 0x10 | 0x8))   # user selects mode 8 (channel unchanged)
    r.tick(); r.tick()
    assert r.writes == [(0x1A, bytes([1 | 8, (1 | 8) ^ 0xA5]))]
    r.uc.mem_write(MIDI, struct.pack("<H", 0x10))         # back to off
    r.tick()
    assert r.writes[-1] == (0x1A, bytes([1, 1 ^ 0xA5])) and len(r.writes) == 2


def test_channel_bits_alone_do_not_trigger_a_save():
    r = Rig({0x1A: 2, 0x1B: 2 ^ 0xA5})
    setup(r)
    r.tick()
    r.uc.mem_write(MIDI, struct.pack("<H", 0x23))         # channel changes: the stock code saves those at EEPROM[0x38]
    r.tick()
    assert not r.writes


def test_power_cycle_round_trip():
    r = Rig({})
    setup(r)
    r.tick()
    r.setmode(0)
    r.uc.mem_write(MIDI, struct.pack("<H", 0x10 | 0xC))
    r.tick()
    r2 = Rig(r.eeprom)
    setup(r2, midi_word=0x10)
    r2.tick()
    assert r2.mode()[0] == 0 and word(r2, MIDI) == 0x1C and word(r2, ACTIVE, "<I") == 1
