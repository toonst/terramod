"""Firmware (.smf) payload: a Cortex-M application image."""
import struct
from dataclasses import dataclass

from .container import Container, parse


@dataclass
class FirmwareInfo:
    size: int
    initial_sp: int
    reset_vector: int  # with thumb bit
    vector_min: int
    vector_max: int


def info(c: Container) -> FirmwareInfo:
    sp, reset = struct.unpack_from("<II", c.payload, 0)
    n = min(len(c.payload) // 4, 0x200 // 4)
    vecs = [v for v in struct.unpack_from(f"<{n}I", c.payload, 0)[2:]
            if 0x08000000 <= v < 0x09000000]
    return FirmwareInfo(len(c.payload), sp, reset, min(vecs), max(vecs))


def load(path: str) -> Container:
    with open(path, "rb") as f:
        return parse(f.read())
