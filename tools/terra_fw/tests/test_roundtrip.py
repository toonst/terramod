# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Toon Stegen
import json
import pathlib

import pytest

from terra_fw import container, crc, presets

FW = pathlib.Path(__file__).resolve().parents[3] / "firmware"
SMP = FW / "TERRA_0.smp"
SMF = FW / "TERRA_V1.7.smf"


def test_crc_known_vector():
    # well-known STM32 CRC unit result for a single zero word
    assert crc.stm32_crc(b"\x00\x00\x00\x00") == 0xC704DD7B


@pytest.mark.skipif(not SMP.exists(), reason="no .smp")
def test_smp_roundtrip():
    raw = SMP.read_bytes()
    c = container.parse(raw)
    assert c.to_bytes() == raw
    bank = presets.decode(c)
    assert presets.encode(bank, c.field04).to_bytes() == raw
    assert presets.from_json(json.loads(json.dumps(presets.to_json(bank)))) == bank
    assert sum(s is not None for s in bank.slots) == 69


@pytest.mark.skipif(not SMF.exists(), reason="no .smf")
def test_smf_roundtrip():
    raw = SMF.read_bytes()
    c = container.parse(raw)
    assert c.to_bytes() == raw


def test_bad_crc_rejected():
    if not SMP.exists():
        pytest.skip("no .smp")
    raw = bytearray(SMP.read_bytes())
    raw[0x20] ^= 1
    with pytest.raises(container.ContainerError):
        container.parse(bytes(raw))
