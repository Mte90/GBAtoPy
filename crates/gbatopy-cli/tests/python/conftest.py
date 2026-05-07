"""Test fixtures for GBA runtime"""

import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "assets"))

import pytest
from gba_runtime.cpu import CPU
from gba_runtime.memory import Memory
from gba_runtime.rom import ROM


@pytest.fixture
def cpu():
    return CPU()


@pytest.fixture
def memory():
    return Memory()


@pytest.fixture
def rom():
    return ROM()
