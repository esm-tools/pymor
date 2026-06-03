"""
Per-shard compliance-checker step.

Runs ``cchecker.py`` against every NetCDF file the current rule wrote into
``rule.output_directory`` and stores a JSON sidecar summary alongside them.

Opt-in: set ``qc_enabled: true`` on the rule (or in ``inherit:``). Off by
default so existing configs are unchanged.

Rule attributes consumed (all optional):

- ``qc_enabled`` (bool, default False) — master switch
- ``qc_tests`` (list[str], default ``["cf"]``) — checker suites; ``cf``,
  ``acdd``, ``wcrp_cmip7`` if the plugin is installed.
- ``qc_criteria`` (str, default ``"normal"``) — lenient | normal | strict
- ``qc_fail_on_mandatory`` (bool, default False) — raise on any Mandatory
  finding instead of just logging.
- ``qc_binary`` (str, default ``"cchecker.py"``) — override path.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Iterable

from ..core.logging import logger


class QCFailure(RuntimeError):
    """Raised when ``qc_fail_on_mandatory`` is True and the run had Mandatory findings."""


def _rule_files(rule) -> list[Path]:
    out_dir = getattr(rule, "output_directory", None)
    if not out_dir or not os.path.isdir(out_dir):
        return []
    cmor_var = getattr(rule, "cmor_variable", None) or getattr(rule, "name", None)
    table_id = getattr(rule, "table_id", None)
    if not cmor_var:
        return []
    prefix = f"{cmor_var}_{table_id}_" if table_id else f"{cmor_var}_"
    return sorted(
        Path(out_dir) / name
        for name in os.listdir(out_dir)
        if name.endswith(".nc") and name.startswith(prefix)
    )


def _count_findings(entries) -> int:
    n = 0
    for f in entries or []:
        if f.get("msgs"):
            n += 1
        n += _count_findings(f.get("children"))
    return n


def _suite_counts(suite_result: dict) -> dict:
    """Prefer cchecker's pre-tallied counts; fall back to recursing priorities."""
    if all(k in suite_result for k in ("high_count", "medium_count", "low_count")):
        return {
            "high": int(suite_result["high_count"]),
            "medium": int(suite_result["medium_count"]),
            "low": int(suite_result["low_count"]),
        }
    return {
        "high": _count_findings(suite_result.get("high_priorities")),
        "medium": _count_findings(suite_result.get("medium_priorities")),
        "low": _count_findings(suite_result.get("low_priorities")),
    }


def _summarize(report: dict) -> dict:
    totals = {"high": 0, "medium": 0, "low": 0}
    by_file: dict[str, dict] = {}
    for file_path, suites in report.items():
        file_counts: dict[str, dict] = {}
        for suite_name, suite_result in (suites or {}).items():
            c = _suite_counts(suite_result or {})
            file_counts[suite_name] = c
            for k, v in c.items():
                totals[k] += v
        by_file[file_path] = file_counts
    return {"totals": totals, "by_file": by_file}


def _run_cchecker(binary: str, tests: Iterable[str], criteria: str,
                  out_json: Path, files: list[Path]) -> tuple[int, str]:
    cmd = [binary, "-f", "json_new", "-o", str(out_json), "-c", criteria]
    for t in tests:
        cmd += ["-t", t]
    cmd += [str(p) for p in files]
    logger.info(f"qc: running {' '.join(cmd)}")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return proc.returncode, (proc.stderr or proc.stdout or "")


def run_compliance_checker(data, rule):
    """Pipeline step: run ``cchecker.py`` against this rule's output files.

    Returns ``data`` unchanged so it can be appended after ``save_dataset``
    without altering the pipeline contract.
    """
    if not getattr(rule, "qc_enabled", False):
        return data

    binary = getattr(rule, "qc_binary", None) or "cchecker.py"
    if not shutil.which(binary):
        logger.warning(f"qc: {binary} not on PATH — skipping compliance check")
        return data

    files = _rule_files(rule)
    if not files:
        logger.warning(
            f"qc: no output files found for rule "
            f"{getattr(rule, 'cmor_variable', '?')} in "
            f"{getattr(rule, 'output_directory', '?')} — skipping"
        )
        return data

    tests = list(getattr(rule, "qc_tests", None) or ["cf"])
    criteria = getattr(rule, "qc_criteria", None) or "normal"
    cmor_var = getattr(rule, "cmor_variable", "var")
    table_id = getattr(rule, "table_id", "tab")
    out_json = Path(rule.output_directory) / f"qc_{cmor_var}_{table_id}.json"

    rc, err = _run_cchecker(binary, tests, criteria, out_json, files)
    if not out_json.exists():
        logger.error(f"qc: cchecker.py rc={rc}; no JSON produced. stderr:\n{err}")
        if getattr(rule, "qc_fail_on_mandatory", False):
            raise QCFailure(f"qc: cchecker.py produced no report for {cmor_var}")
        return data

    try:
        report = json.loads(out_json.read_text())
    except json.JSONDecodeError as exc:
        logger.error(f"qc: failed to parse {out_json}: {exc}")
        return data

    summary = _summarize(report)
    totals = summary["totals"]
    logger.info(
        f"qc[{cmor_var}/{table_id}]: {len(files)} file(s); "
        f"high={totals['high']} medium={totals['medium']} low={totals['low']}; "
        f"report={out_json}"
    )
    for fp, suite_counts in summary["by_file"].items():
        for suite, fc in suite_counts.items():
            if any(fc.values()):
                logger.warning(
                    f"qc[{cmor_var}]: {Path(fp).name} {suite} "
                    f"high={fc['high']} medium={fc['medium']} low={fc['low']}"
                )

    if totals["high"] and getattr(rule, "qc_fail_on_mandatory", False):
        raise QCFailure(
            f"qc[{cmor_var}]: {totals['high']} Mandatory finding(s) — see {out_json}"
        )

    return data
