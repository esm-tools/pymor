#!/usr/bin/env python3
"""
Repoint the 17 HR pycmor tier yamls at a different model run + year.

Reads each `awi-esm3-veg-hr-variables/<tier>/cmip7_awiesm3-veg-hr*.yaml`,
swaps the hard-coded HR_test_01 paths to the requested run, and adds a
year filter to the input regex `pattern:` entries:

  - FESOM patterns          \\.fesom\\..*\\.nc      ->  \\.fesom\\.<YEAR>\\.nc
  - OIFS  patterns          atm[...]_.*\\.nc        ->  atm[...]_<YEAR>-<YEAR>\\.nc
  - LPJ-GUESS patterns      */run1/*.out            ->  unchanged (per-var file
                                                       contains all years)

Outputs the modified yamls into <workdir>, leaving the source tree clean.

Usage:
  repoint_hr_year.py <RUN_NAME_OR_ABSPATH> <YEAR> <WORKDIR>

Examples:
  repoint_hr_year.py Test_16n 1587 /scratch/$USER/cmorize_Test_16n_y1587
  repoint_hr_year.py /work/bb1469/.../runtime/awiesm3-develop/Test_16n 1587 ./out
"""
from __future__ import annotations

import pathlib
import re
import sys

SRC_DIR = pathlib.Path(__file__).resolve().parent.parent / "awi-esm3-veg-hr-variables"
OLD_RUN_TOKEN = "HR_test_01"
RUNTIME_ROOT = "/work/bb1469/a270092/runtime/awiesm3-develop"


def resolve_run_dir(arg: str) -> str:
    return arg if arg.startswith("/") else f"{RUNTIME_ROOT}/{arg}"


def add_year_to_pattern(pat: str, year: str) -> str:
    """Apply year filter to a single pattern string (regex form, as written in YAML)."""
    # FESOM convention: <var>.fesom.<year>.nc — pattern ends in `\..*\.nc`
    if r"\.fesom\." in pat:
        return re.sub(r"\\\.\.\*\\\.nc$", rf"\\.{year}\\.nc", pat)
    # OIFS convention: atm[os|_remapped]_..._<year>-<year>.nc
    if pat.startswith("atmos_") or pat.startswith("atm_remapped_"):
        return re.sub(r"_\.\*\\\.nc$", rf"_{year}-{year}\\.nc", pat)
    # LPJ-GUESS .out files contain all years inline
    return pat


def repoint_yaml(src: pathlib.Path, run_dir: str, year: str) -> str:
    text = src.read_text()
    # Path swap: any HR_test_01 path -> the requested run dir
    text = re.sub(
        rf"{re.escape(RUNTIME_ROOT)}/{OLD_RUN_TOKEN}",
        run_dir,
        text,
    )

    # Year filter on `pattern:` and `second_input_pattern:` lines
    def _repl(m: re.Match) -> str:
        prefix, pat = m.group(1), m.group(2)
        return f"{prefix}{add_year_to_pattern(pat, year)}"

    text = re.sub(
        r"(^\s*(?:pattern|second_input_pattern|hnode_pattern):\s*)(\S+)",
        _repl,
        text,
        flags=re.M,
    )

    # Year filter on absolute file specs (salt_file, mice_file, second_input_file, ...)
    # These look like "*_file: /abs/path/<var>\\.fesom\\..*\\.nc" — same FESOM rule.
    def _repl_file(m: re.Match) -> str:
        prefix, val = m.group(1), m.group(2)
        return f"{prefix}{add_year_to_pattern(val, year)}"

    text = re.sub(
        r"(^\s*[a-z_]+_file:\s*)(\S+)",
        _repl_file,
        text,
        flags=re.M,
    )

    # Inject `year:` into the inherit block so year-aware steps
    # (e.g. cap7_aerosol's select_year on centennial GHG forcing files)
    # know which run-year to slice. LPJ-GUESS / OIFS / FESOM patterns
    # already filter by year via the regex; this is for steps that
    # operate on data that the regex couldn't filter.
    text = re.sub(
        r"(^inherit:\s*\n)",
        rf"\1  year: {year}\n",
        text,
        count=1,
        flags=re.M,
    )

    return text


def main() -> int:
    if len(sys.argv) != 4:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    run_arg, year, workdir_arg = sys.argv[1], sys.argv[2], sys.argv[3]
    run_dir = resolve_run_dir(run_arg)
    workdir = pathlib.Path(workdir_arg).resolve()

    if not pathlib.Path(run_dir).is_dir():
        print(f"ERROR: run dir not found: {run_dir}", file=sys.stderr)
        return 1
    if not re.fullmatch(r"\d{4}", year):
        print(f"ERROR: year must be 4 digits, got {year!r}", file=sys.stderr)
        return 1

    workdir.mkdir(parents=True, exist_ok=True)

    yamls = sorted(SRC_DIR.glob("*/cmip7_awiesm3-veg-hr*.yaml"))
    if not yamls:
        print(f"ERROR: no HR yamls under {SRC_DIR}", file=sys.stderr)
        return 1

    for src in yamls:
        tier = src.parent.name
        dest = workdir / f"{tier}.yaml"
        dest.write_text(repoint_yaml(src, run_dir, year))
        print(f"  {tier:<14}  ->  {dest}")

    print(f"\nWrote {len(yamls)} repointed yamls into {workdir}")
    print(f"  source run: {run_dir}")
    print(f"  year filter: {year}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
