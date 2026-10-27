"""Preset bank (.smp) payload codec.

Payload (after the 16-byte container header, 0xFC0 bytes) is a dump of EEPROM 0x40..0xFFF:
  96 x 32-byte slots (6 banks x 16 sensors A-D,1-12: slot = bank*16 + sensor), then a 960-byte
  tail of global tables.
A slot of all 0xFF is empty. Otherwise:
  [0:12]   note per sensor; bit 7 is a per-sensor flag (meaning unknown)
  [12:24]  signed int8 microtuning per sensor (meaning inferred, unverified)
  [24:32]  packed synth parameters (kept raw until decoded)
The tail is kept raw. Everything is lossless: encode(decode(x)) == x.
"""
from dataclasses import dataclass, field
from typing import List, Optional

from .container import Container, ContainerError

SLOTS = 96
SLOT_LEN = 32
TAIL_LEN = 960


@dataclass
class Preset:
    notes: List[int]
    flags: List[bool]
    tuning: List[int]
    params: bytes

    def to_bytes(self) -> bytes:
        nb = bytes((n & 0x7F) | (0x80 if f else 0) for n, f in zip(self.notes, self.flags))
        tb = bytes(t & 0xFF for t in self.tuning)
        return nb + tb + self.params


@dataclass
class Bank:
    slots: List[Optional[Preset]] = field(default_factory=lambda: [None] * SLOTS)
    tail: bytes = b"\xff" * TAIL_LEN


def decode(c: Container) -> Bank:
    p = c.payload
    if len(p) != SLOTS * SLOT_LEN + TAIL_LEN:
        raise ContainerError(f"unexpected preset payload size {len(p)}")
    bank = Bank(tail=p[SLOTS * SLOT_LEN:])
    for i in range(SLOTS):
        r = p[i * SLOT_LEN:(i + 1) * SLOT_LEN]
        if r == b"\xff" * SLOT_LEN:
            continue
        bank.slots[i] = Preset(
            notes=[b & 0x7F for b in r[:12]],
            flags=[bool(b & 0x80) for b in r[:12]],
            tuning=[b - 256 if b > 127 else b for b in r[12:24]],
            params=bytes(r[24:32]),
        )
    return bank


def encode(bank: Bank, field04: bytes = b"\x03\x00\x00\x00") -> Container:
    out = b"".join(s.to_bytes() if s else b"\xff" * SLOT_LEN for s in bank.slots)
    return Container(field04, out + bank.tail)


def to_json(bank: Bank) -> dict:
    return {
        "slots": [None if s is None else {
            "notes": s.notes, "flags": s.flags, "tuning": s.tuning, "params": s.params.hex(),
        } for s in bank.slots],
        "tail": bank.tail.hex(),
    }


def from_json(d: dict) -> Bank:
    slots = [None if s is None else Preset(
        s["notes"], s["flags"], s["tuning"], bytes.fromhex(s["params"])) for s in d["slots"]]
    return Bank(slots, bytes.fromhex(d["tail"]))
