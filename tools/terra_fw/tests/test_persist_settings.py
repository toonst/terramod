# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Toon Stegen
"""Emulate the persist-settings trampoline against the real patched image, with a fake EEPROM: the pitch-down mode
and the MIDI mode (settings byte layout, restore into ctx+0x1E8, output-active flag, save-on-change)."""
import struct

import pytest

pytest.importorskip("keystone")
pytest.importorskip("unicorn")

from terra_fw import container, patcher
from terra_fw.emu import INITIAL_SP, Emu

HOOK, RET = 0x08035A56, 0x08035A5A
MODE = 0x2000337C        # pitch-down mode index; the engine's float follows at +4
MIDI = 0x2000357C        # ctx+0x1E8 word: mode bits 2-3, channel bits 0,1,4,5
PREV = 0x20003580        # ctx+0x1EC
ACTIVE = 0x200039AC      # ctx+0x618
F_2ST = struct.unpack("<f", struct.pack("<I", 0x3DDF7058))[0]


class Rig(Emu):
    """The patched image with a fake EEPROM and RAM as the stock boot leaves it; tick() runs the hook once."""

    def __init__(self, payload, eeprom, midi=0x10):
        super().__init__(payload, eeprom=eeprom)
        self.write(MODE, "<If", 2, 1.0)
        self.write(MIDI, "<H", midi)
        self.write(ACTIVE, "<I", 0)

    def tick(self):
        self.run(HOOK, RET, count=2000, r0=0x11111111)
        assert self.reg("sp") == INITIAL_SP
        assert self.reg("r0") == 0x2001BC0C   # displaced `ldr r0,=huart1` re-done

    def mode(self):
        return self.read(MODE, "<If")

    def midi(self):
        return self.read(MIDI, "<H")

    def active(self):
        return self.read(ACTIVE, "<I")

    def set_pitch(self, m):
        self.write(MODE, "<I", m)

    def set_midi(self, word):
        self.write(MIDI, "<H", word)


@pytest.fixture
def rig(stock_smf, mods):
    payload = container.parse(patcher.apply(stock_smf, [mods["persist-settings"]])[0]).payload
    return lambda eeprom, **kw: Rig(payload, eeprom, **kw)


@pytest.mark.parametrize("ee", [
    {}, {0x1A: 1, 0x1B: 1}, {0x1A: 0, 0x1B: 0}, {0x1A: 0x0C, 0x1B: 0},
    {0x1A: 3, 0x1B: 3 ^ 0xA5}, {0x1A: 7, 0x1B: 7 ^ 0xA5}, {0x1A: 0x1C, 0x1B: 0x1C ^ 0xA5},
], ids=["blank", "bad-check", "zero", "bad-check-midi", "pitch-3", "pitch-3-midi", "above-0xf"])
def test_blank_or_corrupt_eeprom_gives_defaults(rig, ee):
    r = rig(ee)
    r.tick()
    assert r.mode() == (2, 1.0) and r.midi() == 0x10 and r.active() == 0 and not r.writes


# pitch-down mode

@pytest.mark.parametrize("m,f", [(0, F_2ST), (1, 0.5), (2, 1.0)])
def test_saved_pitch_mode_is_loaded(rig, m, f):
    r = rig({0x1A: m, 0x1B: m ^ 0xA5})
    r.tick()
    assert r.mode() == (m, f) and not r.writes


def test_pitch_change_is_saved_once(rig):
    r = rig({})
    r.tick()
    r.set_pitch(0)
    r.tick(); r.tick(); r.tick()
    assert r.writes == [(0x1A, bytes([0, 0xA5]))]
    r.set_pitch(1)
    r.tick()
    assert r.writes[-1] == (0x1A, bytes([1, 1 ^ 0xA5])) and len(r.writes) == 2


def test_invalid_pitch_mode_not_saved(rig):
    r = rig({})
    r.tick()
    r.set_pitch(9)
    r.tick()
    assert not r.writes


def test_pitch_survives_power_cycle(rig):
    r = rig({})
    r.tick(); r.set_pitch(1); r.tick()
    r2 = rig(r.eeprom)                       # fresh RAM, same EEPROM
    r2.tick()
    assert r2.mode() == (1, 0.5)


# MIDI mode

@pytest.mark.parametrize("midi", [0x4, 0x8, 0xC])
def test_saved_midi_mode_restored_keeps_channel_and_activates_output(rig, midi):
    b = 1 | midi                                           # pitch mode 1 + MIDI mode
    r = rig({0x1A: b, 0x1B: b ^ 0xA5}, midi=0x31)          # stock-restored channel bits + junk low bits
    r.tick()
    assert r.midi() == (0x31 & ~0xC) | midi                # only bits 2-3 replaced
    assert r.read(PREV, "<H") == r.midi()                  # no spurious "mode changed" later
    assert r.active() == 1                                 # pump enabled
    assert r.mode() == (1, 0.5) and not r.writes


def test_midi_off_does_not_enable_output(rig):
    r = rig({0x1A: 2, 0x1B: 2 ^ 0xA5})
    r.tick()
    assert r.active() == 0 and r.midi() == 0x10


def test_old_pitchdown_only_format_is_compatible(rig):
    r = rig({0x1A: 0, 0x1B: 0 ^ 0xA5}, midi=0x14)          # written by the removed persist-pitchdown mod
    r.tick()
    assert r.mode()[0] == 0 and r.midi() == 0x10 and r.active() == 0


def test_midi_mode_change_saved_with_pitch_bits_preserved(rig):
    r = rig({0x1A: 1, 0x1B: 1 ^ 0xA5})
    r.tick()
    r.set_midi(0x10 | 0x8)                                 # user selects mode 8 (channel unchanged)
    r.tick(); r.tick()
    assert r.writes == [(0x1A, bytes([1 | 8, (1 | 8) ^ 0xA5]))]
    r.set_midi(0x10)                                       # back to off
    r.tick()
    assert r.writes[-1] == (0x1A, bytes([1, 1 ^ 0xA5])) and len(r.writes) == 2


def test_channel_bits_alone_do_not_trigger_a_save(rig):
    r = rig({0x1A: 2, 0x1B: 2 ^ 0xA5})
    r.tick()
    r.set_midi(0x23)                                       # channel changes: the stock code saves those at EEPROM[0x38]
    r.tick()
    assert not r.writes


def test_midi_survives_power_cycle(rig):
    r = rig({})
    r.tick()
    r.set_pitch(0)
    r.set_midi(0x10 | 0xC)
    r.tick()
    r2 = rig(r.eeprom)
    r2.tick()
    assert r2.mode()[0] == 0 and r2.midi() == 0x1C and r2.active() == 1
