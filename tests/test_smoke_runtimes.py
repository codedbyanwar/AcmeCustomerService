"""Task 10 smoke test: both runtime modules import and build their agent.

Verifies the entrypoints wire up (model loader, tools, auth, memory) without
calling Bedrock. Each runtime is loaded in a subprocess so their sibling
`data`/`model`/`memory` packages don't collide in one interpreter.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _build(agent_dir: str) -> subprocess.CompletedProcess:
    code = "import main; main.get_or_create_agent(); print('OK')"
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(ROOT / "app" / agent_dir),
        capture_output=True,
        text=True,
    )


def test_customer_service_runtime_builds():
    res = _build("AcmeCustomerService")
    assert res.returncode == 0, res.stderr
    assert "OK" in res.stdout


def test_sales_runtime_builds():
    res = _build("AcmeSales")
    assert res.returncode == 0, res.stderr
    assert "OK" in res.stdout
