"""Shared test helpers.

Both agent packages (AcmeCustomerService, AcmeSales) ship a `data` package.
Importing them by the plain name `data` collides in Python's module cache when
the whole suite runs. `load_module` loads a module by explicit file path under
a unique name so tests stay isolated.
"""

import importlib.util
from pathlib import Path

APP = Path(__file__).resolve().parent.parent / "app"
CS = APP / "AcmeCustomerService"
SALES = APP / "AcmeSales"


import sys


def load_module(path: Path, unique_name: str):
    """Load a Python module from an explicit file path under a unique name.

    The module is registered in sys.modules before execution so features that
    resolve the defining module (e.g. @dataclass) work correctly.
    """
    spec = importlib.util.spec_from_file_location(unique_name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[unique_name] = mod
    spec.loader.exec_module(mod)
    return mod
