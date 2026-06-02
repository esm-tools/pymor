#!/usr/bin/env python3
"""Generate a gr-grid variant of a FESOM-ingesting pycmor tier yaml.

Input:  the source-of-truth tier yaml (produces `gn` output).
Output: a derived yaml that, when run by pycmor, produces `gr` (regular
        0.5° lat/lon) cmorized output from the same experiment's
        `<var>.fesom.gr.<year>.nc` XIOS-regridded files.

This is launcher-side preprocessing — there is no parallel `_gr/` source
tree to maintain. The gn yaml is the only file humans edit; this script
deterministically derives the gr counterpart on every run.

Filtering (rule level):
  Kept   — rules whose PRIMARY input pattern references `fesom` (substring).
  Dropped — rules with no inputs (mesh-derived fx), rules whose primary
            input is OIFS/atm-side, etc. They have no gr equivalent
            under this naming scheme.

Pattern rewrites (string level, applied recursively to every str value):
  `\\.fesom\\.\\d{4}\\.nc`  →  `\\.fesom\\.gr\\.\\d{4}\\.nc`

Inherit overrides:
  grid_label          → gr
  grid                → "regular 0.5° lat/lon (XIOS interpolation from FESOM DARS, 720x360)"
  nominal_resolution  → "50km"   (CMIP7 CV-bin for ~44 km area-weighted √mean cell area)
  name                → original + " (gr)"   (for log clarity)

Usage:
    generate_gr_yaml.py <input.yaml> <output.yaml>
"""
import functools
import os
import re
import sys
import yaml
from pathlib import Path

NATIVE_PAT = r"\.fesom\.\d{4}\.nc"
GR_PAT = r"\.fesom\.gr\.\d{4}\.nc"
# Post-repoint patterns have the year already substituted:
#   \.fesom\.1851\.nc  (instead of \.fesom\.\d{4}\.nc)
# This regex matches either placeholder form for the gr rewrite.
NATIVE_PAT_REGEX = re.compile(r"\\\.fesom\\\.(\\d\{4\}|\d{4})\\\.nc")

# Custom-step name fragments that mark a pipeline as
# FESOM-unstructured-mesh-dependent. Rules using such a pipeline
# cannot run against the gr (regular lat/lon) data because the steps
# look up mesh cell_area/coords aligned to the source nod2/elem dims.
# Discovered the hard way in cli46:
#   mass_transport_pipeline      → core_ocean_gr_1/_2 FAILED
#   ice_mass_transport_pipeline  → lrcs_seaice_gr_1/2/3 FAILED
# Add more substrings here as new gr failures surface.
FESOM_MESH_STEP_SUBSTRINGS = (
    # Transport calcs needing FESOM cell_area aligned to nod2/elem
    "compute_mass_transport",
    "compute_ice_mass_transport",
    "compute_salt_transport",
    "compute_heat_transport",
    # MOC / barotropic streamfunctions on FESOM mesh
    "compute_msftbarot",
    "compute_msftmz",
    "compute_msftm_density",
    # Volume / vertical-integration steps needing mesh
    "compute_volcello",
    "vertical_integrate",
    # Basin diagnostics via tripyview (mesh-bound)
    "compute_hfbasin",
    "compute_sltbasin",
    # Bottom extraction by mesh indexer (function: extract_bottom)
    "extract_bottom",
    # Hemispheric integration expects nod2 horizontal dim
    # (function: integrate_over_hemisphere)
    "integrate_over_hemisphere",
    # Steric SSH from FESOM column
    "compute_zostoga",
    # FESOM w on layer interfaces → midpoints
    "average_w_interfaces_to_midpoints",
)

# Some pipelines share step functions with working pipelines (compute_sisnhc
# is used by both the simple sisnhc_pipeline and the mesh-dependent
# sisnhc_from_msnow_pipeline). Substring-match these pipeline NAMES to
# filter the broken variants surgically.
FESOM_MESH_PIPELINE_NAME_SUBSTRINGS = (
    # veg_seaice sisnhc_from_msnow_pipeline: cli47 MemoryError
    # (297708764688000,) from a broken broadcast on gr.
    "sisnhc_from_msnow",
)


def is_fesom_primary(rule):
    inputs = rule.get("inputs") or []
    if not inputs:
        return False
    pattern = inputs[0].get("pattern", "")
    return "fesom" in pattern


def pipeline_needs_fesom_mesh(pl_def):
    # First: pipeline-name match (catches variants whose step function is
    # shared with a working pipeline)
    name = pl_def.get("name", "")
    if any(needle in name for needle in FESOM_MESH_PIPELINE_NAME_SUBSTRINGS):
        return True
    # Then: step-substring match
    for step in pl_def.get("steps", []) or []:
        if not isinstance(step, str):
            continue
        if any(needle in step for needle in FESOM_MESH_STEP_SUBSTRINGS):
            return True
    return False


def rule_uses_fesom_mesh(rule, mesh_pipeline_names):
    pls = rule.get("pipelines") or []
    return any(p in mesh_pipeline_names for p in pls)


@functools.lru_cache(maxsize=16)
def _listdir(path):
    try:
        return tuple(os.listdir(path))
    except OSError:
        return ()


def gr_input_files_exist(rule):
    """Return True if at least one file in the rule's primary input path
    matches the (already gr-rewritten) pattern.

    cli47 surfaced a separate failure class: rules whose primary input
    variable is in the FESOM gn set but not in Patrick's XIOS regrid set
    (Test_v342_1y_01: 87 gn vs 78 gr variables = 9 variable gap). Those
    rules fail with `OSError('no files to open')`. Drop them here so the
    gr derivative only contains rules with actual source data.
    """
    inputs = rule.get("inputs") or []
    if not inputs:
        return True
    inp = inputs[0]
    data_path = inp.get("path", "")
    pattern_re = inp.get("pattern", "")
    if not data_path or not pattern_re:
        return True
    try:
        regex = re.compile(pattern_re)
    except re.error:
        return True
    return any(regex.fullmatch(fn) for fn in _listdir(data_path))


def rewrite_patterns(obj):
    if isinstance(obj, str):
        # Insert `gr\.` between `\.fesom\.` and the year token (which may
        # be the placeholder `\d{4}` or a literal 4-digit year if repoint
        # has already substituted it).
        return NATIVE_PAT_REGEX.sub(r"\.fesom\.gr\.\1\.nc", obj)
    if isinstance(obj, dict):
        return {k: rewrite_patterns(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [rewrite_patterns(x) for x in obj]
    return obj


def main():
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        sys.exit(2)
    src, dst = sys.argv[1], sys.argv[2]
    d = yaml.safe_load(Path(src).read_text())

    pipelines = d.get("pipelines", []) or []
    mesh_pls = {
        p["name"]
        for p in pipelines
        if "name" in p and pipeline_needs_fesom_mesh(p)
    }

    rules = d.get("rules", []) or []
    after_fesom = [r for r in rules if is_fesom_primary(r)]
    after_mesh = [r for r in after_fesom if not rule_uses_fesom_mesh(r, mesh_pls)]
    # Pattern rewrite happens BEFORE file-existence check so the gr-prefixed
    # filenames are what we look for on disk.
    after_mesh = rewrite_patterns(after_mesh)
    after_files = [r for r in after_mesh if gr_input_files_exist(r)]

    d["rules"] = after_files
    n_mesh_dropped = len(after_fesom) - len(after_mesh)
    n_missing_dropped = len(after_mesh) - len(after_files)
    kept = after_files

    inh = d.setdefault("inherit", {})
    inh["grid_label"] = "gr"
    inh["grid"] = (
        "regular 0.5° lat/lon (XIOS interpolation from FESOM DARS, 720x360 cells)"
    )
    inh["nominal_resolution"] = "50km"

    gen = d.setdefault("general", {})
    base_name = gen.get("name", "")
    if base_name and not base_name.endswith(" (gr)"):
        gen["name"] = f"{base_name} (gr)"

    Path(dst).write_text(
        yaml.safe_dump(
            d,
            default_flow_style=False,
            sort_keys=False,
            width=200,
            allow_unicode=True,
        )
    )
    print(
        f"  {Path(src).name} -> {Path(dst).name}: "
        f"{len(kept)}/{len(rules)} rules kept "
        f"({n_mesh_dropped} fesom-mesh-only, "
        f"{n_missing_dropped} no-gr-input dropped)",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
