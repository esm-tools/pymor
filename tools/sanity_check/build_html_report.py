#!/usr/bin/env python3
"""
build_html_report.py
====================

Convert a pycmor sanity-check JSONL plus the literature bounds table into a
static HTML site, split by realm (atm / oce / ice / veg) plus an index page.

Inputs
------
* ``--jsonl``    Path to JSONL produced by ``sanity_check.py``
                 (default ``/tmp/sanity_check_results.jsonl``).
* ``--table``    Markdown table with literature bounds and rationale
                 (default ``doc/sanity_check_ranges.md``).
* ``--out-dir``  Directory to write the HTML report into.
* ``--label``    Label used in titles. Inferred from JSONL paths if omitted.

Outputs
-------
``<out-dir>/{index,atm,oce,ice,veg}.html`` plus a tiny ``assets/`` folder.

Self-contained: no external CDNs, no matplotlib, no images.

Run
---
    python build_html_report.py --jsonl /tmp/sanity_check_results.jsonl \
        --table /work/.../doc/sanity_check_ranges.md \
        --out-dir tools/sanity_check/reports/myrun_html
"""

from __future__ import annotations

import argparse
import html
import json
import math
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


# ---------------------------------------------------------------------------
# Severity classifier (mirrors build_issues_md.py / sanity_summary.py)
# ---------------------------------------------------------------------------

SIGN_BUGS = {"masscello", "thkcello"}

SEVERITY_ORDER = [
    "DATA_INTEGRITY",
    "PHYS_IMPOSSIBLE",
    "UNIT_MISMATCH",
    "SIGN_FLIP",
    "PICONTROL_NONZERO",
    "PHYS_NEG_VALUES",
    "BOUNDS_OR_PEAK",
    "BOUNDS_TIGHT_MINOR",
]
SEVERITY_RANK = {s: i for i, s in enumerate(SEVERITY_ORDER)}

# Status worst-of ordering: FAIL > ERROR > WARN > NOBOUNDS > PASS
STATUS_RANK = {"FAIL": 0, "ERROR": 1, "WARN": 2, "NOBOUNDS": 3, "PASS": 4}


# Keywords in the bounds-table rationale that mark a variable as one whose
# 0 bound is there because of piControl/anthropogenic forcing, NOT because of
# physics. Used to disambiguate "below expected_min 0" violations.
_PICONTROL_RATIONALE_HINTS = (
    "picontrol", "anthropogenic", "luh2", "luc",
    "harvest", "harvested", "fertilis", "fertiliz",
    "no synthetic", "no anthropogenic", "no harvest", "no luc",
    "no land-use", "no land use",
)


def severity_of(var: str, notes: Sequence[str], rationale: str = "") -> str:
    if var in SIGN_BUGS:
        return "PHYS_IMPOSSIBLE"
    text = "; ".join(notes).lower()
    if "non-finite" in text:
        return "DATA_INTEGRITY"
    if "wrong sign" in text:
        return "SIGN_FLIP"
    m = re.search(r"off by ([\d.eE+-]+)x", text)
    if m:
        try:
            f = float(m.group(1))
            if f > 1e3:
                return "UNIT_MISMATCH"
        except Exception:
            pass
    # Hard zero bound violation. Two distinct causes:
    #   * piControl / anthropogenic forcing: variable should be ~0 because the
    #     model isn't run with that forcing on. The bounds-table rationale will
    #     mention piControl, LUH2, anthropogenic, harvest, fertiliser, etc.
    #   * physical lower bound: variable cannot be negative on physical
    #     grounds (precipitation, evaporation, snow melt, etc.). Negative
    #     values are likely numerical noise or a sign bug, NOT forcing leakage.
    # Match a hard zero bound only — "above expected_max 0.0003" does NOT
    # trigger; "above expected_max 0;" or "above expected_max 0$" does.
    has_zero_bound = (re.search(r"above expected_max 0(?:\s|;|,|$)", text)
                      or re.search(r"below expected_min 0(?:\s|;|,|$)", text))
    if has_zero_bound:
        rat = rationale.lower()
        if any(kw in rat for kw in _PICONTROL_RATIONALE_HINTS):
            return "PICONTROL_NONZERO"
        return "PHYS_NEG_VALUES"
    if "slightly" in text:
        return "BOUNDS_TIGHT_MINOR"
    return "BOUNDS_OR_PEAK"


# ---------------------------------------------------------------------------
# Realm bucket assignment
# ---------------------------------------------------------------------------

ATM_REALMS = {"atmos", "atmoschem", "aerosol"}
OCE_REALMS = {"ocean"}
ICE_REALMS = {"seaice", "landice"}
VEG_REALMS = {"land"}


def domain_of(realm: Optional[str], directory: Optional[str]) -> Optional[str]:
    """Return one of {'atm','oce','ice','veg'} or None."""
    r = (realm or "").strip().lower()
    d = (directory or "").strip().lower()

    if r in ATM_REALMS:
        return "atm"
    if r in OCE_REALMS:
        return "oce"
    if r in ICE_REALMS:
        return "ice"
    if r in VEG_REALMS:
        return "veg"

    # Fallbacks based on directory
    if not r:
        if "cap7_aerosol" in d or d.endswith("_atm") or "_atm" in d:
            return "atm"
        if d.endswith("_ocean") or "_ocean" in d:
            return "oce"
        if d.endswith("_seaice") or "_seaice" in d:
            return "ice"
        if d.endswith("_land") or "_land" in d:
            return "veg"
    return None


DOMAIN_LABELS = {
    "atm": "Atmosphere",
    "oce": "Ocean",
    "ice": "Sea Ice & Land Ice",
    "veg": "Land & Vegetation",
}


# ---------------------------------------------------------------------------
# JSONL + markdown table parsing
# ---------------------------------------------------------------------------

def _nan_parse_constant(token: str) -> float:
    return float("nan")


def parse_jsonl(path: Path) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line, parse_constant=_nan_parse_constant)
            except json.JSONDecodeError as exc:
                print(f"warn: skipping malformed JSONL line {lineno}: {exc}",
                      file=sys.stderr)
                continue
            records.append(rec)
    return records


def parse_metadata_json(path: Path) -> Dict[str, Dict[str, str]]:
    """Return {out_name: {'long_name','comment','standard_name'}} from CMIP7 metadata JSON.

    The JSON has a top-level "Compound Name" mapping where each value is a
    record describing one (variable, frequency, branding) tuple. Multiple
    records exist per variable; they share long_name/comment, so the first
    one wins.
    """
    metadata_by_var: Dict[str, Dict[str, str]] = {}
    if not path.exists():
        return metadata_by_var
    try:
        with path.open("r", encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"warn: could not read metadata JSON {path}: {exc}",
              file=sys.stderr)
        return metadata_by_var

    compound = raw.get("Compound Name") or {}
    if not isinstance(compound, dict):
        return metadata_by_var

    # Several records may share the same out_name (one per branding/freq).
    # Score them so the most generic global record wins:
    #   * branding ending in "-u" (universal/all-tiles)         > tile-specific
    #   * tavg-* (time-mean)                                    > tmax/tmin/tpt
    #   * region GLB                                            > 30S-90S etc
    def _score(compound_key: str) -> int:
        parts = str(compound_key).split(".")
        branding = parts[2] if len(parts) >= 3 else ""
        region = parts[4] if len(parts) >= 5 else ""
        s = 0
        if branding.endswith("-u"):
            s += 1000
        if branding.startswith("tavg-"):
            s += 500
        if region.upper() == "GLB":
            s += 200
        return s

    best_for: Dict[str, Tuple[int, str, Dict[str, Any]]] = {}
    for compound_key, rec in compound.items():
        if not isinstance(rec, dict):
            continue
        var = rec.get("out_name")
        if not var:
            parts = str(compound_key).split(".")
            if len(parts) >= 2:
                var = parts[1]
        if not var:
            continue
        score = _score(compound_key)
        prev = best_for.get(var)
        if prev is None or score > prev[0]:
            best_for[var] = (score, compound_key, rec)

    for var, (_score_v, _key, rec) in best_for.items():
        metadata_by_var[var] = {
            "long_name": str(rec.get("long_name", "") or ""),
            "comment": str(rec.get("comment", "") or ""),
            "standard_name": str(rec.get("standard_name", "") or ""),
        }
    return metadata_by_var


def parse_bounds_table(path: Path) -> Dict[str, Dict[str, Any]]:
    """Return {var_name: {'realm','units','min','mean','max','source'}}."""
    out: Dict[str, Dict[str, Any]] = {}
    if not path.exists():
        return out

    header_seen = False
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.strip().startswith("|"):
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) < 7:
                continue
            if not header_seen:
                if cells[0].lower() == "variable":
                    header_seen = True
                continue
            # Skip alignment row of dashes
            if all(set(c.replace(":", "")).issubset({"-", " "}) for c in cells):
                continue
            var = cells[0]
            if not var:
                continue
            out[var] = {
                "realm": cells[1],
                "units": cells[2],
                "expected_min": cells[3],
                "expected_mean": cells[4],
                "expected_max": cells[5],
                "source": cells[6],
            }
    return out


# ---------------------------------------------------------------------------
# Numeric coercion helpers
# ---------------------------------------------------------------------------

def to_float(value: Any) -> float:
    """Convert string like '~1.4e5', '~10', '-' to float; '-' / 'varies' -> nan."""
    if value is None:
        return float("nan")
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s:
        return float("nan")
    if s in {"-", "—", "?", "n/a", "N/A"} or "vari" in s.lower() or "pft" in s.lower():
        return float("nan")
    s = s.lstrip("~").replace(",", "")
    try:
        return float(s)
    except ValueError:
        # try first numeric token
        m = re.search(r"-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?", s)
        if m:
            try:
                return float(m.group(0))
            except ValueError:
                pass
        return float("nan")


def is_finite(x: float) -> bool:
    try:
        return math.isfinite(x)
    except TypeError:
        return False


def fmt_num(x: Any, sig: int = 4) -> str:
    """Pretty number for tables."""
    if isinstance(x, str):
        return html.escape(x) if x.strip() else "&mdash;"
    try:
        v = float(x)
    except (TypeError, ValueError):
        return "&mdash;"
    if not is_finite(v):
        return "&mdash;"
    if v == 0:
        return "0"
    av = abs(v)
    if av >= 1e5 or av < 1e-3:
        return f"{v:.{sig - 1}e}"
    if av >= 100:
        return f"{v:.1f}"
    if av >= 1:
        return f"{v:.3f}"
    return f"{v:.{sig}g}"


# ---------------------------------------------------------------------------
# Variable aggregation
# ---------------------------------------------------------------------------

@dataclass
class VarEntry:
    var: str
    files: List[Dict[str, Any]] = field(default_factory=list)
    realm: str = ""
    units_table: str = ""
    units_file: str = ""
    expected_min: Any = None
    expected_mean: Any = None
    expected_max: Any = None
    source: str = ""
    domain: str = ""
    worst_status: str = "PASS"
    worst_severity: Optional[str] = None
    worst_notes: List[str] = field(default_factory=list)
    n_total: int = 0
    obs_min: float = float("nan")
    obs_mean: float = float("nan")
    obs_max: float = float("nan")
    units_in_file: str = ""
    directory: str = ""

    @property
    def severity_rank(self) -> int:
        if self.worst_severity is None:
            return len(SEVERITY_ORDER) + 1
        return SEVERITY_RANK.get(self.worst_severity, len(SEVERITY_ORDER))


def collapse(records: Sequence[Dict[str, Any]],
             bounds_meta: Dict[str, Dict[str, Any]]) -> List[VarEntry]:
    by_var: Dict[str, VarEntry] = {}

    for rec in records:
        var = rec.get("var") or rec.get("primary") or "?"
        ent = by_var.get(var)
        if ent is None:
            ent = VarEntry(var=var)
            by_var[var] = ent

        ent.files.append(rec)
        # Realm / dir / domain — last one wins, all should be consistent.
        if not ent.realm and rec.get("realm"):
            ent.realm = str(rec.get("realm") or "")
        if not ent.directory and rec.get("dir"):
            ent.directory = str(rec.get("dir") or "")

        # Expected values: take from JSONL if present, else table
        for k in ("expected_min", "expected_mean", "expected_max"):
            if getattr(ent, k) in (None, "", float("nan")) and rec.get(k) not in (None, ""):
                setattr(ent, k, rec.get(k))
        if not ent.units_table and rec.get("units"):
            ent.units_table = str(rec.get("units"))
        if not ent.units_in_file and rec.get("units_in_file"):
            ent.units_in_file = str(rec.get("units_in_file") or "")

        # Track worst observation (we want representative numbers).
        # Use the file with the highest STATUS_RANK contribution.
        status = str(rec.get("status") or "PASS").upper()
        rank = STATUS_RANK.get(status, 99)
        cur_rank = STATUS_RANK.get(ent.worst_status, 99)
        if rank < cur_rank:
            ent.worst_status = status
            ent.worst_notes = list(rec.get("notes") or [])
            ent.obs_min = to_float(rec.get("min"))
            ent.obs_mean = to_float(rec.get("mean"))
            ent.obs_max = to_float(rec.get("max"))
            ent.n_total = int(rec.get("n_total") or 0)
        elif rank == cur_rank and not ent.worst_notes:
            ent.worst_notes = list(rec.get("notes") or [])
            if not is_finite(ent.obs_mean):
                ent.obs_min = to_float(rec.get("min"))
                ent.obs_mean = to_float(rec.get("mean"))
                ent.obs_max = to_float(rec.get("max"))
                ent.n_total = int(rec.get("n_total") or 0)

    # Now decorate each entry with bounds-table metadata, severity, domain.
    out: List[VarEntry] = []
    for var, ent in by_var.items():
        meta = bounds_meta.get(var, {})
        if not ent.realm:
            ent.realm = str(meta.get("realm", "") or "")
        if not ent.units_table:
            ent.units_table = str(meta.get("units", "") or "")
        if ent.expected_min in (None, ""):
            ent.expected_min = meta.get("expected_min", "")
        if ent.expected_mean in (None, ""):
            ent.expected_mean = meta.get("expected_mean", "")
        if ent.expected_max in (None, ""):
            ent.expected_max = meta.get("expected_max", "")
        ent.source = str(meta.get("source", "") or "")
        ent.domain = domain_of(ent.realm, ent.directory) or ""

        if ent.worst_status == "FAIL":
            ent.worst_severity = severity_of(var, ent.worst_notes,
                                             rationale=ent.source)
        else:
            ent.worst_severity = None

        out.append(ent)
    return out


# ---------------------------------------------------------------------------
# SVG plot
# ---------------------------------------------------------------------------

def build_svg(entry: VarEntry,
              width: int = 480,
              height: int = 120) -> Optional[str]:
    """Return an SVG string showing expected band + observed range, or None."""
    em = to_float(entry.expected_min)
    ee = to_float(entry.expected_mean)
    ex = to_float(entry.expected_max)
    am = entry.obs_min
    ae = entry.obs_mean
    ax = entry.obs_max

    candidates = [v for v in (em, ee, ex, am, ae, ax) if is_finite(v)]
    if not candidates:
        return None
    # Need at least observed or expected pair to be meaningful.
    have_expected = is_finite(em) and is_finite(ex)
    have_observed = is_finite(am) and is_finite(ax)
    if not (have_expected or have_observed):
        return None

    vmin = min(candidates)
    vmax = max(candidates)
    if vmin == vmax:
        # Pad
        pad = abs(vmin) * 0.1 if vmin != 0 else 1.0
        vmin -= pad
        vmax += pad

    # Decide log scale
    positive = [abs(v) for v in candidates if v != 0]
    use_log = False
    if positive:
        big = max(abs(v) for v in candidates)
        small = min(positive)
        if small > 0 and big / small > 1000 and vmin > 0:
            use_log = True

    pad_frac = 0.05
    span = vmax - vmin
    plot_min = vmin - span * pad_frac
    plot_max = vmax + span * pad_frac
    if use_log:
        plot_min = max(plot_min, min(positive) * 0.5)
        log_min = math.log10(plot_min)
        log_max = math.log10(plot_max)

    margin_l = 50
    margin_r = 20
    margin_t = 20
    margin_b = 35
    plot_w = width - margin_l - margin_r
    plot_h = height - margin_t - margin_b
    y_band_top = margin_t + 10
    y_band_bot = margin_t + plot_h - 10
    y_obs = margin_t + plot_h / 2

    def x_of(v: float) -> float:
        if use_log:
            if v <= 0:
                return margin_l  # clamp to left edge
            return margin_l + (math.log10(v) - log_min) / (log_max - log_min) * plot_w
        return margin_l + (v - plot_min) / (plot_max - plot_min) * plot_w

    parts: List[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}" role="img" '
        f'aria-label="Range plot for {html.escape(entry.var)}">'
    )

    # Background
    parts.append(
        f'<rect x="{margin_l}" y="{margin_t}" width="{plot_w}" height="{plot_h}" '
        'fill="#fafafa" stroke="#ddd"/>'
    )

    # Expected band
    if have_expected:
        x_em = x_of(em)
        x_ex = x_of(ex)
        if x_em > x_ex:
            x_em, x_ex = x_ex, x_em
        parts.append(
            f'<rect x="{x_em:.1f}" y="{y_band_top:.1f}" '
            f'width="{max(x_ex - x_em, 1):.1f}" height="{y_band_bot - y_band_top:.1f}" '
            'fill="#e7e7e7" stroke="#bbb"/>'
        )
        if is_finite(ee):
            x_ee = x_of(ee)
            parts.append(
                f'<line x1="{x_ee:.1f}" y1="{y_band_top:.1f}" x2="{x_ee:.1f}" '
                f'y2="{y_band_bot:.1f}" stroke="#888" stroke-width="1.2" '
                'stroke-dasharray="3 2"/>'
            )

    # Observed range
    if have_observed:
        x_am = x_of(am)
        x_ax = x_of(ax)
        if x_am > x_ax:
            x_am, x_ax = x_ax, x_am
        color = "#3a3"
        if entry.worst_status in ("FAIL", "ERROR"):
            color = "#c33"
        elif entry.worst_status == "WARN":
            color = "#e80"
        parts.append(
            f'<line x1="{x_am:.1f}" y1="{y_obs:.1f}" x2="{x_ax:.1f}" y2="{y_obs:.1f}" '
            f'stroke="{color}" stroke-width="3" stroke-linecap="round"/>'
        )
        # End caps
        for xp in (x_am, x_ax):
            parts.append(
                f'<line x1="{xp:.1f}" y1="{y_obs - 8:.1f}" x2="{xp:.1f}" '
                f'y2="{y_obs + 8:.1f}" stroke="{color}" stroke-width="2"/>'
            )
        if is_finite(ae):
            x_ae = x_of(ae)
            parts.append(
                f'<line x1="{x_ae:.1f}" y1="{y_obs - 12:.1f}" x2="{x_ae:.1f}" '
                f'y2="{y_obs + 12:.1f}" stroke="{color}" stroke-width="3"/>'
            )

    # Axis
    axis_y = margin_t + plot_h
    parts.append(
        f'<line x1="{margin_l}" y1="{axis_y}" x2="{margin_l + plot_w}" '
        f'y2="{axis_y}" stroke="#444"/>'
    )
    if use_log:
        ticks_log = [log_min, (log_min + log_max) / 2, log_max]
        ticks = [10 ** v for v in ticks_log]
    else:
        ticks = [plot_min, (plot_min + plot_max) / 2, plot_max]
    for t in ticks:
        xt = x_of(t)
        parts.append(
            f'<line x1="{xt:.1f}" y1="{axis_y}" x2="{xt:.1f}" y2="{axis_y + 4}" '
            'stroke="#444"/>'
        )
        parts.append(
            f'<text x="{xt:.1f}" y="{axis_y + 16}" font-size="10" fill="#333" '
            f'text-anchor="middle">{html.escape(fmt_num(t))}</text>'
        )

    # Y label hints
    parts.append(
        f'<text x="6" y="{y_band_top + 4:.1f}" font-size="9" fill="#666">expected</text>'
    )
    parts.append(
        f'<text x="6" y="{y_obs + 3:.1f}" font-size="9" fill="#666">observed</text>'
    )

    # Units (right-bottom)
    units = entry.units_table or entry.units_in_file
    if units:
        parts.append(
            f'<text x="{width - margin_r}" y="{height - 6}" font-size="10" '
            f'fill="#444" text-anchor="end">{html.escape(units)}{" (log)" if use_log else ""}</text>'
        )
    elif use_log:
        parts.append(
            f'<text x="{width - margin_r}" y="{height - 6}" font-size="10" '
            'fill="#444" text-anchor="end">log scale</text>'
        )

    parts.append("</svg>")
    return "".join(parts)


# ---------------------------------------------------------------------------
# Diagnosis text
# ---------------------------------------------------------------------------

def diagnosis_text(entry: VarEntry) -> str:
    var = entry.var
    units = entry.units_table or entry.units_in_file or ""
    file_units = entry.units_in_file or ""
    n_total = entry.n_total

    am = entry.obs_min
    ae = entry.obs_mean
    ax = entry.obs_max
    em = to_float(entry.expected_min)
    ee = to_float(entry.expected_mean)
    ex = to_float(entry.expected_max)
    notes_text = "; ".join(entry.worst_notes)

    sev = entry.worst_severity

    if entry.worst_status == "PASS":
        return "Within bounds."
    if entry.worst_status == "ERROR":
        msg = notes_text or "(no detail)"
        return f"Read failed: {msg}."
    if entry.worst_status == "NOBOUNDS":
        return "No literature bound available; observed values logged but not validated."
    if entry.worst_status == "WARN":
        msg = notes_text or ""
        return f"Within tolerance of the bound. {msg}".strip()

    # FAIL branches
    if sev == "DATA_INTEGRITY":
        return (
            f"All {n_total} cells are non-finite (NaN/fill-value). "
            "The producing rule emitted a file with no real data — likely "
            "the source field is missing/empty or a divide-by-zero in the "
            f"compute step. Investigate the rule's pipeline in "
            f"`awi-esm3-veg-hr-variables/{entry.directory or '?'}/`."
        )
    if sev == "PHYS_IMPOSSIBLE":
        return (
            f"Output contains physically impossible values "
            f"(min={fmt_num(am)} {html.escape(units)}). For `masscello` "
            "(mass per area) and `thkcello` (cell thickness) any negative "
            "value indicates an upstream sign or differencing bug."
        )
    if sev == "UNIT_MISMATCH":
        factor = "?"
        if is_finite(ae) and is_finite(ee) and ee != 0:
            try:
                factor = fmt_num(ae / ee)
            except Exception:
                factor = "?"
        return (
            f"Observed mean {fmt_num(ae)} is {factor}x the expected mean "
            f"{fmt_num(ee)}. Likely a missing unit conversion: the file "
            f"declares `{html.escape(file_units or '?')}` but the CMIP table "
            f"expects `{html.escape(units or '?')}`. Add `source_units:` "
            "in the rule yaml."
        )
    if sev == "SIGN_FLIP":
        return (
            f"Mean {fmt_num(ae)} has the wrong sign vs the expected "
            f"{fmt_num(ee)}. The rule may be saving an anomaly or has "
            "the wrong source variable."
        )
    if sev == "PICONTROL_NONZERO":
        return (
            "These should be ~0 in piControl (no anthropogenic forcing) "
            f"but the model emits min={fmt_num(am)}, mean={fmt_num(ae)}, "
            f"max={fmt_num(ax)}. Either the LUC forcing dataset isn't "
            "being honoured, or this is documented internal model "
            "behaviour — investigate, don't fix in pycmor."
        )
    if sev == "PHYS_NEG_VALUES":
        # Hard zero bound on a physical quantity that cannot be negative
        # (precipitation, evaporation, snow melt, etc.) — but the file has
        # negative values somewhere. Mean and max are usually fine.
        return (
            f"Negative values found (min={fmt_num(am)}) despite a physical "
            f"lower bound of 0 — {entry.var} cannot physically be negative. "
            f"Mean={fmt_num(ae)} and max={fmt_num(ax)} are within range; "
            "the violation is at the lower end and likely numerical noise "
            "(e.g. flux scheme overshoot, regridding artefact) rather than "
            "a forcing issue. Check whether to clip to 0 in the rule, or "
            "whether the source field has a known sign-error."
        )
    if sev == "BOUNDS_OR_PEAK":
        return (
            f"Grid-cell extremes (min={fmt_num(am)} / max={fmt_num(ax)}) "
            f"overshoot the bound, but the global mean ({fmt_num(ae)}) is "
            "reasonable. The bound was set for global mean at LR resolution; "
            "HR cells legitimately have higher peaks. Loosen the bound "
            "rather than touch the model."
        )
    if sev == "BOUNDS_TIGHT_MINOR":
        return (
            "Marginal overshoot of the literature bound. "
            "The bound likely needs widening."
        )
    return notes_text or "Failed sanity check."


# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------

CSS = """
:root {
  --fg: #222;
  --muted: #666;
  --bg: #fff;
  --bg2: #fafafa;
  --border: #d4d4d4;
  --pill-fail: #c33;
  --pill-warn: #e80;
  --pill-pass: #3a3;
  --pill-nobounds: #888;
}
* { box-sizing: border-box; }
html, body {
  margin: 0;
  padding: 0;
  background: var(--bg);
  color: var(--fg);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
               Oxygen, Ubuntu, Cantarell, "Helvetica Neue", Arial, sans-serif;
  font-size: 14px;
  line-height: 1.45;
}
nav.top {
  position: sticky;
  top: 0;
  z-index: 10;
  background: #f3f3f3;
  border-bottom: 1px solid var(--border);
  padding: 8px 16px;
}
nav.top a {
  margin-right: 14px;
  color: #134;
  text-decoration: none;
  font-weight: 500;
}
nav.top a.active {
  text-decoration: underline;
}
main {
  max-width: 1500px;
  margin: 0 auto;
  padding: 18px 24px 80px;
}
h1 { font-size: 22px; margin: 14px 0 6px; }
h2 { font-size: 18px; margin: 28px 0 10px; border-bottom: 1px solid var(--border); padding-bottom: 4px; }
h3 { font-size: 15px; margin: 0; }
.subtle { color: var(--muted); font-size: 12px; }
.pill {
  display: inline-block;
  padding: 1px 8px;
  border-radius: 10px;
  color: white;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.3px;
  vertical-align: middle;
}
.pill.fail, .pill.error { background: var(--pill-fail); }
.pill.warn { background: var(--pill-warn); }
.pill.pass { background: var(--pill-pass); }
.pill.nobounds { background: var(--pill-nobounds); }
.sev-tag {
  display: inline-block;
  font-size: 10px;
  background: #222;
  color: #fff;
  padding: 1px 6px;
  border-radius: 3px;
  margin-left: 4px;
  letter-spacing: 0.5px;
}
.var-card {
  border: 1px solid var(--border);
  background: var(--bg);
  border-radius: 6px;
  padding: 12px 14px;
  margin: 10px 0;
}
.var-card.compact {
  padding: 6px 10px;
  background: var(--bg2);
}
.var-card .header {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}
.var-card .header .name {
  font-weight: 600;
  font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
  font-size: 14px;
}
.var-card .meta {
  margin-left: auto;
  color: var(--muted);
  font-size: 12px;
}
.var-card svg { margin: 8px 0; display: block; }
p.longname {
  margin: 6px 0 2px 0;
  font-size: 1.05em;
  color: #222;
}
p.stdname {
  margin: 0 0 4px 0;
  font-size: 0.85em;
  color: #555;
}
p.description {
  margin: 0 0 10px 0;
  font-size: 0.9em;
  color: #333;
  max-width: 800px;
  line-height: 1.4;
}
img.varmap {
  display: block;
  max-width: 1400px;
  width: 100%;
  height: auto;
  margin: 8px 0;
  border: 1px solid #ddd;
  background: #fafafa;
}
table.numbers {
  border-collapse: collapse;
  margin: 8px 0;
  font-size: 13px;
}
table.numbers th, table.numbers td {
  border: 1px solid var(--border);
  padding: 3px 8px;
  text-align: right;
  font-variant-numeric: tabular-nums;
}
table.numbers th { background: var(--bg2); text-align: center; }
table.numbers td.label { text-align: left; font-weight: 500; }
.diagnosis {
  background: #fff8e8;
  border-left: 3px solid #e80;
  padding: 6px 10px;
  margin-top: 6px;
  font-size: 13px;
}
.var-card.fail .diagnosis,
.var-card.error .diagnosis {
  background: #fdecea;
  border-left-color: #c33;
}
.source {
  color: var(--muted);
  font-size: 12px;
  margin-top: 4px;
}
details.files {
  margin-top: 6px;
  font-size: 12px;
  color: var(--muted);
}
details.files summary {
  cursor: pointer;
  color: #134;
}
details.files ul { margin: 4px 0 4px 18px; padding: 0; }
table.summary {
  border-collapse: collapse;
  width: 100%;
  margin: 12px 0;
}
table.summary th, table.summary td {
  border: 1px solid var(--border);
  padding: 6px 10px;
  text-align: left;
}
table.summary th { background: var(--bg2); }
.callout {
  background: #fdecea;
  border: 1px solid #c33;
  border-radius: 6px;
  padding: 10px 14px;
  margin: 16px 0;
}
.callout h2 {
  margin-top: 0;
  border: none;
  color: #c33;
}
.callout ul { margin: 4px 0; padding-left: 22px; }
"""


def _pill(status: str) -> str:
    s = status.upper()
    cls = {
        "FAIL": "fail",
        "ERROR": "error",
        "WARN": "warn",
        "PASS": "pass",
        "NOBOUNDS": "nobounds",
    }.get(s, "nobounds")
    return f'<span class="pill {cls}">{html.escape(s)}</span>'


def _nav(active: str, label: str) -> str:
    items = [
        ("index", "Summary"),
        ("atm", "Atmosphere"),
        ("oce", "Ocean"),
        ("ice", "Ice"),
        ("veg", "Land/Veg"),
    ]
    out = ['<nav class="top">']
    out.append(f'<strong>{html.escape(label)}</strong> &middot; ')
    for key, lbl in items:
        cls = ' class="active"' if key == active else ""
        href = f"{key}.html"
        out.append(f'<a href="{href}"{cls}>{html.escape(lbl)}</a>')
    out.append("</nav>")
    return "".join(out)


def _page_shell(title: str, label: str, active: str, body: str) -> str:
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en"><head>'
        '<meta charset="utf-8"/>'
        f'<title>{html.escape(title)}</title>'
        '<link rel="stylesheet" href="assets/style.css"/>'
        "</head><body>"
        + _nav(active, label)
        + "<main>"
        + body
        + "</main>"
        "</body></html>\n"
    )


def render_var_card(entry: VarEntry,
                    out_dir: Optional[Path] = None,
                    metadata_by_var: Optional[Dict[str, Dict[str, str]]] = None) -> str:
    status = entry.worst_status
    status_cls = status.lower()

    # Every card gets the full layout — including PASS — so each variable
    # has a map plot regardless of status.
    sev_tag = ""
    if entry.worst_severity:
        sev_tag = f'<span class="sev-tag">{html.escape(entry.worst_severity)}</span>'

    units_table = entry.units_table or "?"
    units_file = entry.units_in_file or "?"

    parts: List[str] = []
    parts.append(
        f'<div class="var-card {status_cls}" id="var-{html.escape(entry.var)}">'
    )
    parts.append('<div class="header">')
    parts.append(f'<span class="name">{html.escape(entry.var)}</span>')
    parts.append(_pill(status))
    parts.append(sev_tag)
    parts.append(
        f'<span class="meta">realm={html.escape(entry.realm or "?")} '
        f"&middot; units(file)={html.escape(units_file)} "
        f"&middot; units(table)={html.escape(units_table)}"
        "</span>"
    )
    parts.append("</div>")

    # CMIP7 long_name / standard_name / description block.
    meta = (metadata_by_var or {}).get(entry.var, {})
    long_name = (meta.get("long_name") or "").strip()
    description = (meta.get("comment") or "").strip()
    standard_name = (meta.get("standard_name") or "").strip()
    if long_name:
        parts.append(
            f'<p class="longname"><strong>{html.escape(long_name)}</strong></p>'
        )
    if standard_name:
        parts.append(
            f'<p class="stdname">CF: <em>{html.escape(standard_name)}</em></p>'
        )
    if description:
        parts.append(
            f'<p class="description">{html.escape(description)}</p>'
        )

    svg = build_svg(entry)
    if svg:
        parts.append(svg)

    # Optional time-mean map image, if present alongside the report.
    if out_dir is not None:
        map_path = out_dir / "assets" / "maps" / f"{entry.var}.png"
        if map_path.exists():
            parts.append(
                f'<img class="varmap" src="assets/maps/{html.escape(entry.var)}.png" '
                f'alt="time-mean map of {html.escape(entry.var)}" loading="lazy"/>'
            )

    # Numbers table
    parts.append(
        '<table class="numbers">'
        "<thead><tr><th>Quantity</th><th>Expected</th><th>Observed</th></tr></thead>"
        "<tbody>"
        f'<tr><td class="label">min</td><td>{fmt_num(entry.expected_min)}</td>'
        f"<td>{fmt_num(entry.obs_min)}</td></tr>"
        f'<tr><td class="label">mean</td><td>{fmt_num(entry.expected_mean)}</td>'
        f"<td>{fmt_num(entry.obs_mean)}</td></tr>"
        f'<tr><td class="label">max</td><td>{fmt_num(entry.expected_max)}</td>'
        f"<td>{fmt_num(entry.obs_max)}</td></tr>"
        "</tbody></table>"
    )

    if entry.source:
        parts.append(
            f'<div class="source"><strong>Source / rationale:</strong> '
            f"{html.escape(entry.source)}</div>"
        )

    diag = diagnosis_text(entry)
    if diag:
        parts.append(f'<div class="diagnosis">{html.escape(diag)}</div>')

    if entry.files:
        basenames = sorted({os.path.basename(f.get("file", "")) for f in entry.files})
        items = "".join(f"<li>{html.escape(b)}</li>" for b in basenames if b)
        parts.append(
            "<details class=\"files\">"
            f"<summary>Affected files ({len(basenames)})</summary>"
            f"<ul>{items}</ul>"
            "</details>"
        )

    parts.append("</div>")
    return "".join(parts)


def sort_key(entry: VarEntry) -> Tuple[int, int, str]:
    status = entry.worst_status
    if status == "FAIL":
        return (0, entry.severity_rank, entry.var.lower())
    if status == "WARN":
        return (1, 0, entry.var.lower())
    if status == "PASS":
        return (2, 0, entry.var.lower())
    # ERROR / NOBOUNDS at the bottom
    return (3, 0, entry.var.lower())


def render_domain_page(domain: str,
                       entries: Sequence[VarEntry],
                       label: str,
                       out_dir: Optional[Path] = None,
                       metadata_by_var: Optional[Dict[str, Dict[str, str]]] = None) -> str:
    title = f"{label} — {DOMAIN_LABELS[domain]}"
    sorted_entries = sorted(entries, key=sort_key)

    fails = [e for e in sorted_entries if e.worst_status == "FAIL"]
    warns = [e for e in sorted_entries if e.worst_status == "WARN"]
    passes = [e for e in sorted_entries if e.worst_status == "PASS"]
    others = [e for e in sorted_entries if e.worst_status in ("ERROR", "NOBOUNDS")]

    body: List[str] = []
    body.append(f"<h1>{html.escape(title)}</h1>")
    body.append(
        f'<p class="subtle">{len(sorted_entries)} variable(s): '
        f"{len(fails)} FAIL, {len(warns)} WARN, {len(passes)} PASS, "
        f"{len(others)} other.</p>"
    )

    if fails:
        body.append("<h2>FAIL</h2>")
        body.extend(render_var_card(e, out_dir, metadata_by_var) for e in fails)
    if warns:
        body.append("<h2>WARN</h2>")
        body.extend(render_var_card(e, out_dir, metadata_by_var) for e in warns)
    if passes:
        body.append("<h2>PASS</h2>")
        body.extend(render_var_card(e, out_dir, metadata_by_var) for e in passes)
    if others:
        body.append("<h2>Other (ERROR / NOBOUNDS)</h2>")
        body.extend(render_var_card(e, out_dir, metadata_by_var) for e in others)

    if not sorted_entries:
        body.append("<p>No variables in this domain.</p>")

    return _page_shell(title, label, domain, "".join(body))


def render_index(all_entries: Sequence[VarEntry], label: str) -> str:
    title = f"{label} — Sanity Check Summary"

    # Aggregate counts
    counts: Dict[str, int] = defaultdict(int)
    for e in all_entries:
        counts[e.worst_status] += 1
    total = sum(counts.values())

    def pct(n: int) -> str:
        if total == 0:
            return "—"
        return f"{(100.0 * n / total):.1f}%"

    # Per-realm breakdown
    by_dom: Dict[str, List[VarEntry]] = defaultdict(list)
    for e in all_entries:
        if e.domain:
            by_dom[e.domain].append(e)

    body: List[str] = []
    body.append(f"<h1>{html.escape(title)}</h1>")
    body.append(
        f'<p class="subtle">{total} unique variables across all realms.</p>'
    )

    # Totals table
    body.append('<table class="summary"><thead><tr>'
                "<th>Status</th><th>Count</th><th>Percent</th>"
                "</tr></thead><tbody>")
    for status in ("FAIL", "WARN", "PASS", "ERROR", "NOBOUNDS"):
        n = counts.get(status, 0)
        body.append(
            f"<tr><td>{_pill(status)}</td><td>{n}</td><td>{pct(n)}</td></tr>"
        )
    body.append("</tbody></table>")

    # Per-realm
    body.append("<h2>By realm</h2>")
    body.append('<table class="summary"><thead><tr>'
                "<th>Domain</th><th>Total</th><th>FAIL</th><th>WARN</th>"
                "<th>PASS</th><th>Other</th><th>Link</th>"
                "</tr></thead><tbody>")
    for dom in ("atm", "oce", "ice", "veg"):
        ents = by_dom.get(dom, [])
        d_fail = sum(1 for e in ents if e.worst_status == "FAIL")
        d_warn = sum(1 for e in ents if e.worst_status == "WARN")
        d_pass = sum(1 for e in ents if e.worst_status == "PASS")
        d_other = sum(1 for e in ents
                      if e.worst_status in ("ERROR", "NOBOUNDS"))
        body.append(
            f"<tr><td>{html.escape(DOMAIN_LABELS[dom])}</td>"
            f"<td>{len(ents)}</td><td>{d_fail}</td><td>{d_warn}</td>"
            f"<td>{d_pass}</td><td>{d_other}</td>"
            f'<td><a href="{dom}.html">{dom}.html</a></td></tr>'
        )
    body.append("</tbody></table>")

    # Critical issues callout
    critical_sevs = {"DATA_INTEGRITY", "PHYS_IMPOSSIBLE",
                     "UNIT_MISMATCH", "SIGN_FLIP"}
    critical = [
        e for e in all_entries
        if e.worst_status == "FAIL" and e.worst_severity in critical_sevs
    ]
    critical.sort(key=sort_key)
    if critical:
        body.append('<div class="callout">')
        body.append(f"<h2>Critical issues ({len(critical)})</h2>")
        body.append("<ul>")
        for e in critical:
            dom = e.domain or "?"
            href = f"{dom}.html#var-{e.var}"
            body.append(
                f'<li><a href="{html.escape(href)}"><code>{html.escape(e.var)}</code></a> '
                f'<span class="sev-tag">{html.escape(e.worst_severity or "")}</span> '
                f'<span class="subtle">({html.escape(DOMAIN_LABELS.get(dom, dom))})</span></li>'
            )
        body.append("</ul></div>")

    body.append("<h2>Pages</h2><ul>")
    for dom in ("atm", "oce", "ice", "veg"):
        body.append(
            f'<li><a href="{dom}.html">{html.escape(DOMAIN_LABELS[dom])}</a></li>'
        )
    body.append("</ul>")

    return _page_shell(title, label, "index", "".join(body))


# ---------------------------------------------------------------------------
# Label inference
# ---------------------------------------------------------------------------

def infer_label(records: Sequence[Dict[str, Any]]) -> str:
    """Look at file paths; the parent of /cmorized/ is the label."""
    for rec in records:
        path = rec.get("file")
        if not path:
            continue
        m = re.search(r"/([^/]+)/cmorized/", path)
        if m:
            return m.group(1)
    return "sanity-check"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--jsonl", default="/tmp/sanity_check_results.jsonl",
                   help="Sanity-check JSONL output")
    p.add_argument("--table",
                   default=str(Path(__file__).resolve().parents[2]
                               / "doc" / "sanity_check_ranges.md"),
                   help="Bounds-table markdown file")
    p.add_argument("--out-dir", default=None,
                   help="Output directory (default: tools/sanity_check/reports/<label>_html)")
    p.add_argument("--label", default=None,
                   help="Experiment label (default: infer from JSONL paths)")
    p.add_argument("--metadata",
                   default="/home/a/a270092/.cache/pycmor/cmip7_metadata/v1.2.2.2/metadata.json",
                   help="CMIP7 metadata JSON for long names + descriptions")
    args = p.parse_args(argv)

    jsonl_path = Path(args.jsonl)
    table_path = Path(args.table)
    metadata_path = Path(args.metadata)

    if not jsonl_path.exists():
        print(f"error: jsonl not found: {jsonl_path}", file=sys.stderr)
        return 2

    records = parse_jsonl(jsonl_path)
    bounds_meta = parse_bounds_table(table_path)
    metadata_by_var = parse_metadata_json(metadata_path)
    label = args.label or infer_label(records)

    if args.out_dir:
        out_dir = Path(args.out_dir)
    else:
        out_dir = (Path(__file__).resolve().parent / "reports"
                   / f"{label}_html")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "assets").mkdir(parents=True, exist_ok=True)

    # Write CSS
    (out_dir / "assets" / "style.css").write_text(CSS, encoding="utf-8")

    # Collapse to per-variable entries
    entries = collapse(records, bounds_meta)

    # Bucket by domain
    by_dom: Dict[str, List[VarEntry]] = {"atm": [], "oce": [], "ice": [], "veg": []}
    for e in entries:
        if e.domain in by_dom:
            by_dom[e.domain].append(e)
        # entries without a domain are still in `entries` for the index totals,
        # but won't appear on any domain page

    # Index
    (out_dir / "index.html").write_text(
        render_index(entries, label), encoding="utf-8"
    )

    # Per-domain
    for dom in ("atm", "oce", "ice", "veg"):
        page = render_domain_page(dom, by_dom[dom], label, out_dir,
                                  metadata_by_var)
        (out_dir / f"{dom}.html").write_text(page, encoding="utf-8")

    print(f"wrote {out_dir}/index.html and {len(by_dom)} domain pages")
    print(f"variables: {len(entries)} total; "
          f"atm={len(by_dom['atm'])} oce={len(by_dom['oce'])} "
          f"ice={len(by_dom['ice'])} veg={len(by_dom['veg'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
