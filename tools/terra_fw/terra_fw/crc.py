"""STM32 hardware CRC unit: CRC-32/MPEG-2 over little-endian 32-bit words
(poly 0x04C11DB7, init 0xFFFFFFFF, no reflection, no final XOR)."""
import struct

_POLY = 0x04C11DB7


def _make_table():
    table = []
    for i in range(256):
        c = i << 24
        for _ in range(8):
            c = ((c << 1) ^ _POLY) & 0xFFFFFFFF if c & 0x80000000 else (c << 1) & 0xFFFFFFFF
        table.append(c)
    return table


_TABLE = _make_table()


def stm32_crc(data: bytes, init: int = 0xFFFFFFFF) -> int:
    """CRC over `data`, which must be a multiple of 4 bytes."""
    if len(data) % 4:
        raise ValueError("stm32_crc input must be a multiple of 4 bytes")
    c = init
    for (w,) in struct.iter_unpack("<I", data):
        c ^= w
        for _ in range(4):
            c = ((c << 8) & 0xFFFFFFFF) ^ _TABLE[c >> 24]
    return c
