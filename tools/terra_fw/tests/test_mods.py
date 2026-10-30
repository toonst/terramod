# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Toon Stegen
"""Check every mods/*/mod.toml without SOMA's firmware: the fields the patcher and --auto-name use, and that every
hook assembles and is placed. The stand-in image has the real image's length, so trampolines land where they will in
a real build, and holds each hook's `expect` bytes; everything else is 0xFF."""
import hashlib
import re

import pytest

pytest.importorskip("keystone")

from terra_fw import container, patcher
from terra_fw.firmware import LOAD_BASE

IMAGE_LEN = {"1.7": 236116}     # payload length of TERRA_V1.7.smf (symbols/terra_v1.7.toml: image_end)
SHA256 = re.compile(r"[0-9a-f]{64}")


def stand_in(*mods):
    payload = bytearray(b"\xff" * IMAGE_LEN[mods[0]["mod"]["fw_version"]])
    for mod in mods:
        for h in mod["hook"]:
            expect = bytes.fromhex(h["expect"])
            payload[h["at"] - LOAD_BASE:h["at"] - LOAD_BASE + len(expect)] = expect
    return container.Container(b"....", bytes(payload)).to_bytes()


def test_fields(mod_path):
    mod = patcher.load_mod(mod_path)
    m = mod["mod"]
    assert m["id"] == mod_path.parent.name
    assert isinstance(m["version"], str)
    assert m["fw_version"] in IMAGE_LEN, "add the image length of this firmware version to IMAGE_LEN"
    assert m["targets"] and all(SHA256.fullmatch(t) for t in m["targets"])
    assert mod["hook"]
    for h in mod["hook"]:
        assert h["at"] % 2 == 0, f"hook {h['at']:#x}: Thumb instructions are halfword-aligned"
        assert len(bytes.fromhex(h["expect"])) >= 4, f"hook {h['at']:#x}: expect must cover the 4 bytes the b.w overwrites"
        assert h["asm"].strip()


def test_builds_against_stand_in(mod_path):
    mod = patcher.load_mod(mod_path)
    smf = stand_in(mod)
    mod["mod"]["targets"] = [hashlib.sha256(smf).hexdigest()]
    out, placed = patcher.apply(smf, [mod])
    assert [p.at for p in placed] == [h["at"] for h in mod["hook"]]
    assert all(p.size > 0 for p in placed)
    container.parse(out)  # CRC valid


def test_all_build_together(mods_dir):
    """`patch --all`: the mods share no hook site and target the same firmware."""
    mods = patcher.all_mods(mods_dir)
    assert len({m["mod"]["fw_version"] for m in mods}) == 1
    smf = stand_in(*mods)
    for m in mods:
        m["mod"]["targets"] = [hashlib.sha256(smf).hexdigest()]
    out, placed = patcher.apply(smf, mods)
    assert [p.at for p in placed] == [h["at"] for m in mods for h in m["hook"]]
    container.parse(out)  # CRC valid
