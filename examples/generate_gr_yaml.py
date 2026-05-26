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
import sys
import yaml
from pathlib import Path

NATIVE_PAT = r"\.fesom\.\d{4}\.nc"
GR_PAT = r"\.fesom\.gr\.\d{4}\.nc"

# Custom-step name fragments that mark a pipeline as
# FESOM-unstructured-mesh-dependent. Rules using such a pipeline
# cannot run against the gr (regular lat/lon) data because the steps
# look up mesh cell_area/coords aligned to the source nod2/elem dims.
# Discovered the hard way in cli46:
#   mass_transport_pipeline      → core_ocean_gr_1/_2 FAILED
#   ice_mass_transport_pipeline  → lrcs_seaice_gr_1/2/3 FAILED
# Add more substrings here as new gr failures surface.
FESOM_MESH_STEP_SUBSTRINGS = (
    "compute_mass_transport",
    "compute_ice_mass_transport",
    "compute_hfbasin",
    "compute_sltbasin",
    "compute_msftbarot",
    "compute_zostoga",
    "average_w_interfaces_to_midpoints",
)


def is_fesom_primary(rule):
    inputs = rule.get("inputs") or []
    if not inputs:
        return False
    pattern = inputs[0].get("pattern", "")
    return "fesom" in pattern


def pipeline_needs_fesom_mesh(pl_def):
    for step in pl_def.get("steps", []) or []:
        if not isinstance(step, str):
            continue
        if any(needle in step for needle in FESOM_MESH_STEP_SUBSTRINGS):
            return True
    return False


def rule_uses_fesom_mesh(rule, mesh_pipeline_names):
    pls = rule.get("pipelines") or []
    return any(p in mesh_pipeline_names for p in pls)


def rewrite_patterns(obj):
    if isinstance(obj, str):
        return obj.replace(NATIVE_PAT, GR_PAT)
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
    kept = [
        r
        for r in rules
        if is_fesom_primary(r) and not rule_uses_fesom_mesh(r, mesh_pls)
    ]
    d["rules"] = rewrite_patterns(kept)
    n_mesh_dropped = sum(
        1 for r in rules if is_fesom_primary(r) and rule_uses_fesom_mesh(r, mesh_pls)
    )

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
        f"({n_mesh_dropped} fesom-mesh-only dropped)",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
