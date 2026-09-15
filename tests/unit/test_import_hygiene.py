"""Import hygiene: importing ``marginkit`` must not drag in banned dependencies.

CLAUDE.md hard constraint 1 forbids any GPU, ML-framework, or plotting dependency, at any
time, for any reason. The only way to check that honestly is to import the real package in a
fresh interpreter and inspect ``sys.modules`` there — asserting against ``sys.modules`` inside
the running pytest process is worthless, since pytest and unrelated test modules have already
imported arbitrary things by the time any test body runs.
"""

from __future__ import annotations

import subprocess
import sys

# Visible in one place so later phases can extend it as new forbidden dependencies are named.
# `pandas` is deliberately absent: `statsmodels` requires pandas, so its presence in
# `sys.modules` after importing `marginkit` is unavoidable and is not a constraint violation.
# Do not "tighten" this test by adding it.
FORBIDDEN_MODULES: tuple[str, ...] = ("torch", "tensorflow", "jax", "matplotlib")

_SUBPROCESS_SCRIPT = """
import sys

import marginkit  # noqa: F401

forbidden = {forbidden!r}
leaked = sorted(name for name in forbidden if name in sys.modules)
print(",".join(leaked))
"""


def _run_import_in_subprocess() -> tuple[int, str, str]:
    """Import ``marginkit`` in a fresh interpreter and report which forbidden modules leaked.

    Returns
    -------
    tuple[int, str, str]
        The subprocess return code, its stdout, and its stderr.
    """
    script = _SUBPROCESS_SCRIPT.format(forbidden=FORBIDDEN_MODULES)
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=60,
    )
    return result.returncode, result.stdout, result.stderr


def test_importing_marginkit_does_not_load_forbidden_modules() -> None:
    """A plain ``import marginkit`` must never pull torch, tensorflow, jax, or matplotlib."""
    returncode, stdout, stderr = _run_import_in_subprocess()
    assert returncode == 0, f"subprocess failed to import marginkit: {stderr}"

    leaked = [name for name in stdout.strip().split(",") if name]
    assert not leaked, (
        f"forbidden module(s) leaked into sys.modules on import of marginkit: {leaked}"
    )


def test_marginkit_version_is_a_nonempty_string() -> None:
    """``marginkit.__version__`` must exist and be a non-empty string.

    The exact value is not asserted: it changes every phase, and pinning it here would make
    this test a maintenance tax rather than a hygiene check.
    """
    import marginkit

    assert isinstance(marginkit.__version__, str)
    assert marginkit.__version__ != ""


# Phase 3 addition (plan section 7 Phase 3 "Tests"): marginkit.report and marginkit.testing are
# importable submodules, not re-exported from marginkit/__init__.py (plan section 4's layout --
# `report.py`, `testing.py`). Neither may pull in a dev-only dependency merely by being imported --
# jsonschema is a dev extra used by marginkit.testing's *own* test suite and by consumers'
# validators, not by loading the module itself; hypothesis and pytest belong to marginkit's own
# test suite. A production install of a consumer that only imports these modules must not need
# any of the three.
_DEV_ONLY_MODULES: tuple[str, ...] = ("jsonschema", "hypothesis", "pytest")

_REPORT_AND_TESTING_SUBPROCESS_SCRIPT = """
import sys

import marginkit  # noqa: F401
import marginkit.report  # noqa: F401
import marginkit.testing  # noqa: F401

forbidden = {forbidden!r}
leaked = sorted(name for name in forbidden if name in sys.modules)
print(",".join(leaked))
"""


def test_importing_report_and_testing_does_not_load_dev_only_modules() -> None:
    """A fresh-interpreter import of ``marginkit``, ``marginkit.report`` and
    ``marginkit.testing`` together must never pull in ``jsonschema``, ``hypothesis`` or
    ``pytest``."""
    script = _REPORT_AND_TESTING_SUBPROCESS_SCRIPT.format(forbidden=_DEV_ONLY_MODULES)
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, f"subprocess failed to import marginkit: {result.stderr}"

    leaked = [name for name in result.stdout.strip().split(",") if name]
    assert not leaked, (
        f"dev-only module(s) leaked into sys.modules on import of marginkit/report/testing: "
        f"{leaked}"
    )
