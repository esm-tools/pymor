"""CLI overrides: apply command-line arguments on top of a loaded YAML config.

This module is CLI-agnostic — no ``click`` import. Errors are raised as
:class:`OverrideError` and translated to ``click.UsageError`` at the CLI
boundary. :func:`apply_overrides` always returns a new cfg dict; do not rely
on object identity.
"""
from __future__ import annotations

import dataclasses
import re
from typing import Any, Optional


class OverrideError(ValueError):
    """Raised when CLI overrides are inconsistent or under-specified."""


# Matches the literal-glob FESOM filename form used in `*_file:` rule
# attributes — e.g. ``.../a_ice.fesom.*.nc``. Audit confirms no OIFS / LPJ
# `*_file:` values use literal globs; future components extending this list
# are responsible for updating the regex.
_FESOM_FILE_RE = re.compile(r"\.fesom\.\*\.nc$")


@dataclasses.dataclass
class CliOverrides:
    data_path: Optional[str] = None
    old_data_path: Optional[str] = None
    year_start: Optional[int] = None
    year_end: Optional[int] = None
    mesh_path: Optional[str] = None
    output_directory: Optional[str] = None
    memory: Optional[str] = None  # SLURM per-job memory, e.g. "512GB"


def apply_overrides(cfg: dict, ov: CliOverrides) -> dict:
    """Return a new cfg with CLI overrides applied.

    Does not mutate the input. Callers should reassign:
    ``cfg = apply_overrides(cfg, ov)``.
    """
    if ov.old_data_path is not None and ov.data_path is None:
        raise OverrideError("--old-data-path requires --data-path")

    # shallow copies of cfg, inherit, and each rule; full recursive copy
    # only when data_path triggers _subst_anchored
    cfg = dict(cfg)
    inherit = dict(cfg.get("inherit", {}))

    if ov.mesh_path is not None:
        inherit["mesh_path"] = ov.mesh_path
    if ov.output_directory is not None:
        inherit["output_directory"] = ov.output_directory

    if ov.memory is not None:
        jobqueue = dict(cfg.get("jobqueue", {}))
        slurm = dict(jobqueue.get("slurm", {}))
        slurm["memory"] = ov.memory
        jobqueue["slurm"] = slurm
        cfg["jobqueue"] = jobqueue

    rules = [dict(r) for r in cfg.get("rules", [])]
    for rule in rules:
        if ov.year_start is not None:
            rule["year_start"] = ov.year_start
        if ov.year_end is not None:
            rule["year_end"] = ov.year_end

    # Expand literal `*` in `*_file:` values when both year flags are set.
    # _expand_year_in_file_keys mutates the dict it receives — safe because
    # we operate on the per-rule and inherit shallow copies created above;
    # the caller's input dict is unaffected.
    if ov.year_start is not None and ov.year_end is not None:
        if ov.year_start == ov.year_end:
            for rule in rules:
                _expand_year_in_file_keys(rule, ov.year_start)
            _expand_year_in_file_keys(inherit, ov.year_start)
        else:
            for rule in rules + [inherit]:
                for k, v in rule.items():
                    if k.endswith("_file") and isinstance(v, str) and "*" in v:
                        new_key_pattern = k.replace("_file", "_pattern")
                        new_key_path = k.replace("_file", "_path")
                        raise OverrideError(
                            f"--year-start != --year-end cannot expand literal "
                            f"'*' in {k}={v!r}. Migrate this entry from "
                            f"`{k}: /path/foo.fesom.*.nc` (literal-path form, "
                            "consumed by xr.open_dataset) to "
                            f"`{new_key_pattern}: foo\\.fesom\\..*\\.nc` plus "
                            f"matching `{new_key_path}: /path` (regex form, "
                            "consumed by _load_secondary_mf which year-filters "
                            "via filter_files_by_year_range)."
                        )

    cfg["inherit"] = inherit
    cfg["rules"] = rules

    if ov.data_path is not None:
        old = ov.old_data_path
        if old is None:
            # Auto-detect: strip ``/outdata/<component>`` suffix from
            # ``inherit.data_path`` to get the run root.
            inherit_dp = inherit.get("data_path")
            if inherit_dp and "/outdata/" in inherit_dp:
                old = inherit_dp.split("/outdata/")[0]
            else:
                raise OverrideError(
                    "--data-path needs --old-data-path when the yaml has no "
                    "inherit.data_path of the form <run_root>/outdata/<component>"
                )
        old_norm = old.rstrip("/")
        new_norm = ov.data_path.rstrip("/")
        if old_norm != new_norm:
            pattern = re.compile(re.escape(old_norm) + r"(?=/|$)")
            cfg = _subst_anchored(cfg, pattern, new_norm)

    return cfg


def _expand_year_in_file_keys(rule_or_inherit: dict, year: int) -> None:
    """In-place: expand ``*`` to ``year`` in FESOM ``*_file:`` literal globs.

    Matches keys ending in ``_file`` whose value ends in ``.fesom.*.nc``.
    Caller is responsible for passing a shallow copy of the dict.
    """
    for k, v in list(rule_or_inherit.items()):
        if isinstance(v, str) and k.endswith("_file") and _FESOM_FILE_RE.search(v):
            rule_or_inherit[k] = _FESOM_FILE_RE.sub(f".fesom.{year}.nc", v)


def _subst_anchored(obj: Any, pattern: "re.Pattern", new: str) -> Any:
    if isinstance(obj, str):
        return pattern.sub(new, obj)
    if isinstance(obj, dict):
        return {k: _subst_anchored(v, pattern, new) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_subst_anchored(v, pattern, new) for v in obj]
    return obj
