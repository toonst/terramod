# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Toon Stegen
import pytest

pytest.importorskip("keystone")

from terra_fw import cli, container, patcher


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


def test_shared_hook_site_refused(stock_smf, mods):
    with pytest.raises(patcher.PatchError, match="overlaps"):
        patcher.apply(stock_smf, [mods["hold-midi"], mods["hold-midi"]])


def test_cli_patch_all(stock_smf, mods, mods_dir, tmp_path, monkeypatch):
    smf = tmp_path / "TERRA_V1.7.smf"
    smf.write_bytes(stock_smf)
    monkeypatch.chdir(mods_dir.parent)
    cli.main(["patch", str(smf), str(tmp_path / "dist"), "--all", "--auto-name"])
    (out,) = (tmp_path / "dist").glob("*/*.smf")
    assert out.name == "TERRA_V1.7_" + "+".join(i.replace("-", "") for i in mods) + ".smf"
    container.parse(out.read_bytes())  # CRC valid


@pytest.mark.parametrize("args", [[], ["--all", "mods/hold-midi/mod.toml"]])
def test_cli_patch_needs_mods_or_all(args):
    with pytest.raises(SystemExit):
        cli.main(["patch", "in.smf", "out.smf", *args])
