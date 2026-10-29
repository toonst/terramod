# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Toon Stegen
import json

import pytest

from terra_fw import container, crc, presets


def test_crc_known_vector():
    # well-known STM32 CRC unit result for a single zero word
    assert crc.stm32_crc(b"\x00\x00\x00\x00") == 0xC704DD7B


def test_smp_roundtrip(factory_smp):
    c = container.parse(factory_smp)
    assert c.to_bytes() == factory_smp
    bank = presets.decode(c)
    assert presets.encode(bank, c.field04).to_bytes() == factory_smp
    assert presets.from_json(json.loads(json.dumps(presets.to_json(bank)))) == bank
    assert sum(s is not None for s in bank.slots) == 69


def test_smf_roundtrip(stock_smf):
    assert container.parse(stock_smf).to_bytes() == stock_smf


def test_bad_crc_rejected(factory_smp):
    raw = bytearray(factory_smp)
    raw[0x20] ^= 1
    with pytest.raises(container.ContainerError):
        container.parse(bytes(raw))
