# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Toon Stegen
"""Shared fixtures. Tests that need SOMA's files skip when they are not in firmware/."""
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[3]
MOD_FILES = sorted((ROOT / "mods").glob("*/mod.toml"))


def _official(name):
    path = ROOT / "firmware" / name
    if not path.exists():
        pytest.skip(f"no {name} in firmware/")
    return path.read_bytes()


@pytest.fixture(scope="session")
def stock_smf() -> bytes:
    """TERRA_V1.7.smf, the firmware every mod targets."""
    return _official("TERRA_V1.7.smf")


@pytest.fixture(scope="session")
def factory_smp() -> bytes:
    return _official("TERRA_0.smp")


@pytest.fixture
def mods() -> dict:
    """Every mod in mods/ by id; a fresh copy per test, so a test may edit it."""
    from terra_fw import patcher
    return {p.parent.name: patcher.load_mod(p) for p in MOD_FILES}


def pytest_generate_tests(metafunc):
    if "mod_path" in metafunc.fixturenames:
        metafunc.parametrize("mod_path", MOD_FILES, ids=[p.parent.name for p in MOD_FILES])
