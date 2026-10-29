# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Toon Stegen
"""Apply code-hook mods to a TERRA .smf.

A mod is a TOML file:

  [mod]
  id = "hold-midi"
  targets = ["<sha256 of the stock .smf>"]

  [[hook]]
  at     = 0x080399DA      # address of the first instruction that is replaced by `b.w <trampoline>`
  expect = "2888dff8"      # the 4 original bytes at `at` (refused if they differ)
  asm    = "..."           # trampoline code (Thumb-2, keystone syntax); `{base}` is not needed, jumps use absolute targets

Trampolines are appended to the end of the application image (4-byte aligned).
Only the 4 bytes at `at` are modified; any remaining halves of displaced instructions stay in place and are never executed.
"""
import hashlib
import tomllib
from dataclasses import dataclass
from typing import List

from keystone import KS_ARCH_ARM, KS_MODE_THUMB, Ks

from .container import Container, parse
from .firmware import LOAD_BASE


class PatchError(RuntimeError):
    pass


@dataclass
class Placed:
    at: int
    tramp: int
    size: int


def _asm(ks: Ks, code: str, addr: int) -> bytes:
    enc, _ = ks.asm(code, addr)
    if enc is None:
        raise PatchError(f"assembly failed at {addr:#x}")
    return bytes(enc)


def load_mod(path: str) -> dict:
    with open(path, "rb") as f:
        return tomllib.load(f)


def apply(smf: bytes, mods: List[dict]) -> (bytes, List[Placed]):
    sha = hashlib.sha256(smf).hexdigest()
    c = parse(smf)
    payload = bytearray(c.payload)
    ks = Ks(KS_ARCH_ARM, KS_MODE_THUMB)
    placed: List[Placed] = []
    touched = []  # (start, end) of rewritten ranges, for overlap detection
    for mod in mods:
        if sha not in mod["mod"]["targets"]:
            raise PatchError(f"mod {mod['mod']['id']} does not target this firmware ({sha})")
        for h in mod["hook"]:
            at = h["at"]
            off = at - LOAD_BASE
            if not 0 <= off <= len(payload) - 4:
                raise PatchError(f"hook {at:#x} outside the image")
            if any(s < at + 4 and at < e for s, e in touched):
                raise PatchError(f"hook {at:#x} overlaps another patch")
            expect = bytes.fromhex(h["expect"])
            if bytes(payload[off:off + len(expect)]) != expect:
                raise PatchError(f"hook {at:#x}: original bytes are {bytes(payload[off:off+len(expect)]).hex()}, "
                                 f"expected {expect.hex()}")
            while len(payload) % 4:
                payload.append(0xFF)
            tramp = LOAD_BASE + len(payload)
            code = _asm(ks, h["asm"], tramp)
            payload += code
            while len(payload) % 4:
                payload.append(0xFF)
            payload[off:off + 4] = _asm(ks, f"b.w #{tramp:#x}", at)
            touched.append((at, at + 4))
            placed.append(Placed(at, tramp, len(code)))
    return Container(c.field04, bytes(payload)).to_bytes(), placed


def pad_test(smf: bytes, n: int = 64) -> bytes:
    """Stock firmware plus `n` bytes of 0xFF appended: tests that the updater accepts a longer image."""
    c = parse(smf)
    return Container(c.field04, c.payload + b"\xff" * n).to_bytes()
