"""Load a maintenance script from backend/api/scripts by path, as a module."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"


def load_script(relative: str) -> ModuleType:
    """Import a script that is not part of an installed package.

    Args:
        relative: path of the script under backend/api/scripts, e.g. "eval_recall.py".

    Returns:
        ModuleType: the executed module, also registered in sys.modules under its stem.
    """
    path = SCRIPTS_DIR / relative
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = module
    spec.loader.exec_module(module)
    return module
