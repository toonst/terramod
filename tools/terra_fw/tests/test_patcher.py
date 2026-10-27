import pathlib

import pytest

pytest.importorskip("keystone")

from terra_fw import container, patcher

ROOT = pathlib.Path(__file__).resolve().parents[3]
SMF = ROOT / "firmware" / "TERRA_V1.7.smf"
MOD = ROOT / "mods" / "hold-midi" / "mod.toml"
pytestmark = pytest.mark.skipif(not SMF.exists(), reason="no stock firmware")


def test_hold_midi_only_touches_hook_sites_and_appends():
    raw = SMF.read_bytes()
    out, placed = patcher.apply(raw, [patcher.load_mod(str(MOD))])
    a, b = container.parse(raw).payload, container.parse(out).payload
    changed = {patcher.LOAD_BASE + i for i in range(len(a)) if a[i] != b[i]}
    assert changed <= {h.at + k for h in placed for k in range(4)}
    assert len(b) > len(a) and len(b) % 4 == 0
    container.parse(out)  # CRC valid


def test_wrong_firmware_refused():
    raw = bytearray(SMF.read_bytes())
    c = container.parse(bytes(raw))
    other = container.Container(c.field04, c.payload[:-4] + b"\0\0\0\0").to_bytes()
    with pytest.raises(patcher.PatchError):
        patcher.apply(other, [patcher.load_mod(str(MOD))])


def test_expect_mismatch_refused(tmp_path):
    mod = patcher.load_mod(str(MOD))
    mod["hook"][0]["expect"] = "00000000"
    with pytest.raises(patcher.PatchError):
        patcher.apply(SMF.read_bytes(), [mod])
