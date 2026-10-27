# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Toon Stegen
"""SOMA container shared by .smf (firmware) and .smp (presets).

Layout (all little-endian):
  0x00  b"SOMA"
  0x04  4 bytes  format field (u32 version 3 in .smp, b"...." in .smf) - kept verbatim
  0x08  b"TERR"  device tag
  0x0C  u32      STM32 CRC over bytes 0x10..EOF
  0x10  payload
"""
from dataclasses import dataclass

from .crc import stm32_crc

MAGIC = b"SOMA"
DEVICE = b"TERR"
HEADER_LEN = 0x10


class ContainerError(ValueError):
    pass


@dataclass
class Container:
    field04: bytes  # raw bytes 4..8
    payload: bytes

    @property
    def crc(self) -> int:
        return stm32_crc(self.payload)

    def to_bytes(self) -> bytes:
        return (MAGIC + self.field04 + DEVICE
                + self.crc.to_bytes(4, "little") + self.payload)


def parse(data: bytes, verify: bool = True) -> Container:
    if len(data) < HEADER_LEN:
        raise ContainerError("file too short")
    if data[:4] != MAGIC:
        raise ContainerError("bad magic")
    if data[8:12] != DEVICE:
        raise ContainerError("not a Terra file")
    payload = data[HEADER_LEN:]
    if len(payload) % 4:
        raise ContainerError("payload not word-aligned")
    c = Container(data[4:8], payload)
    stored = int.from_bytes(data[12:16], "little")
    if verify and stored != c.crc:
        raise ContainerError(f"CRC mismatch: stored {stored:#010x}, computed {c.crc:#010x}")
    return c
