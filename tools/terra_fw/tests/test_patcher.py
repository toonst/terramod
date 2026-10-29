# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Toon Stegen
import pytest

pytest.importorskip("keystone")

from terra_fw import container, patcher


def test_hold_midi_only_touches_hook_sites_and_appends(stock_smf, mods):
    out, placed = patcher.apply(stock_smf, [mods["hold-midi"]])
    a, b = container.parse(stock_smf).payload, container.parse(out).payload
    changed = {patcher.LOAD_BASE + i for i in range(len(a)) if a[i] != b[i]}
    assert changed <= {h.at + k for h in placed for k in range(4)}
    assert len(b) > len(a) and len(b) % 4 == 0
    container.parse(out)  # CRC valid


def test_wrong_firmware_refused(stock_smf, mods):
    c = container.parse(stock_smf)
    other = container.Container(c.field04, c.payload[:-4] + b"\0\0\0\0").to_bytes()
    with pytest.raises(patcher.PatchError):
        patcher.apply(other, [mods["hold-midi"]])


def test_expect_mismatch_refused(stock_smf, mods):
    mod = mods["hold-midi"]
    mod["hook"][0]["expect"] = "00000000"
    with pytest.raises(patcher.PatchError):
        patcher.apply(stock_smf, [mod])


def test_persist_mods_share_a_hook_site_and_cannot_be_combined(stock_smf, mods):
    old, new = mods["persist-pitchdown"], mods["persist-settings"]
    patcher.apply(stock_smf, [old])
    patcher.apply(stock_smf, [new])
    with pytest.raises(patcher.PatchError):
        patcher.apply(stock_smf, [old, new])
