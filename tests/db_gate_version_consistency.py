"""Import shim so tests can exercise db/gate/verify_version_consistency.py.

The gate scripts are standalone executables, not an installed package; this
loads the module by path rather than restructuring them for the tests' benefit.
"""
from __future__ import annotations

import importlib.util
import pathlib

_PATH = (
    pathlib.Path(__file__).resolve().parents[1]
    / "db" / "gate" / "verify_version_consistency.py"
)
_spec = importlib.util.spec_from_file_location("_turab_version_consistency", _PATH)
assert _spec and _spec.loader
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)

Claim = _module.Claim
collect = _module.collect
verify = _module.verify
