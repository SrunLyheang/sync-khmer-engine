"""Smoke test: proves the test harness runs and the package imports.

This exists only to confirm the project scaffold (step 1.1) is wired up
correctly. Real engine tests arrive with later roadmap steps.
"""

import sing_khmer_engine


def test_package_imports():
    assert sing_khmer_engine.__version__ == "0.0.0"
