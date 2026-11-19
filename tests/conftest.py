import json
import os
import sys
import tempfile
import time

import pytest

TMP = tempfile.mkdtemp(prefix="smartir_test_")
os.environ["SMARTIR_DB"] = os.path.join(TMP, "test.db")
os.environ["SMARTIR_UPLOADS"] = os.path.join(TMP, "files")
os.environ["SMARTIR_SECRET"] = "test-secret"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import seed  # noqa: E402

sys.argv = ["seed.py"]
seed.main()

RESULTS = []


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    if rep.when == "call":
        doc = (item.function.__doc__ or "").strip().splitlines()
        RESULTS.append({
            "id": item.name.split("_")[1].upper(),
            "requirement": getattr(item.function, "req", ""),
            "description": doc[0] if doc else item.name,
            "expected": doc[1].strip() if len(doc) > 1 else "",
            "result": "Pass" if rep.passed else "Fail",
            "duration_ms": round(rep.duration * 1000, 1),
        })


def pytest_sessionfinish(session, exitstatus):
    out = os.path.join(os.path.dirname(__file__), "results", "functional_results.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as fh:
        json.dump({"run_at": time.strftime("%Y-%m-%d %H:%M:%S"), "results": RESULTS}, fh, indent=1)
