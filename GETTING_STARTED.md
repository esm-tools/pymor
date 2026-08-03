# Running cmorization with pycmor on Levante

A short guide for a colleague running their first cmorization pass on their own model output.

## 1. Environment

```bash
source /work/ab0246/a270092/software/miniforge3/etc/profile.d/conda.sh
conda activate pycmor_py312
```

That points at Jan's shared miniforge install. To build your own env instead, clone `/work/ab0246/a270092/software/pycmor` and run `pixi install`, then `pixi shell -e dev`.

## 2. Rules

The AWI-ESM3-veg-HR rule set lives under `awi-esm3-veg-hr-variables/`, split by tier:

- `core_*` core CMIP7 variables per component (atm, land, ocean, seaice)
- `cap7_*` CMIP7-added variables beyond the core
- `extra_*` optional extras
- `lrcs_*` land / regional CMIP scenario variables
- `veg_*` vegetation-specific

Copy the tiers you need. Each `.yaml` file has a fixed top block plus a list of per-variable rules.

## 3. Point at your data

At the top of each tier yaml, edit the `inherit:` section so every rule inherits your run's data path:

```yaml
inherit:
  data_path: /work/<proj>/<user>/<run>/outdata/<component>
```

Rule-level `input.pattern` regexes stay as-is if your model uses the same output filenames as AWI-ESM3-veg-HR. If not, adjust the patterns to match what your XIOS or component writes.

## 4. Smoke-test one tier locally

Pick one small tier and run it on a login node:

```bash
pycmor process my_tier.yaml
```

Confirm the resulting `.nc` files land under the `output_directory` you set. Open one with `ncdump -h` and check the metadata looks right.

## 5. Full year on SLURM

From the pycmor repo root:

```bash
bash examples/submit_hr_year_shards.sh \
  /work/<proj>/<user>/<run> 1851 \
  /scratch/<init>/<user>/pycmor_hr/mytest_ab0246
```

Arguments:
1. Absolute path to your model run root
2. Year to process
3. Workdir for repointed yamls, shards, and cmorized output

That submits one SLURM array per tier (~17 arrays). Monitor with `squeue --me`. Output lands at `<workdir>/cmorized/MIP-DRS7/CMIP7/...`.

The submit log echoes `drs=on` for every tier. If it says `drs=off`, stop and resubmit with `SHARD_DRS=on`: the flat per-tier layout fails the FILE001, PATH001 and PATH002 checks on every single file, which looks like a catastrophic QC result but is purely a directory-layout artefact.

## 6. Aggregate QC

Every `.nc` gets a sibling `qc_*.json` with wcrp + cf-checker findings. Count HIGH findings and see the top offenders:

```python
import json, glob, collections
c = collections.Counter()
for f in glob.glob('<workdir>/cmorized/**/qc_*.json', recursive=True):
    for ncp in json.load(open(f)).values():
        for sc in ncp.values():
            for it in sc.get('high_priorities', []) or []:
                v = it.get('value')
                if isinstance(v, list) and len(v) == 2 and v[0] < v[1]:
                    c[it.get('name')] += 1
print(sum(c.values()), 'HIGH; top:', c.most_common(10))
```

## 7. Iterate

Typical HIGH-finding fixes:
- `cmor_variable` name mismatch in the rule
- Wrong `cell_methods` for the variable's temporal shape
- Bad `compound_name` (typo or wrong branding suffix)
- Missing `data_request_variable` mapping

Fix the rule, then rerun only the affected tier with:

```bash
sbatch --array=<N> examples/run_hr_shard.sh <shards_dir> <run> <year> <output_subdir>
```

where `<N>` is the shard index within that tier (from the submit log).

## Gotchas

- SLURM account is `ab0246` (project-specific; ask your PI if you need a different one).
- Never single-node for TCo319 grid data. The driver needs multi-node memory on `compute` partition (default `--mem=0` for full-node memory).
- A HIGH finding is not automatically a rule bug. Several classes are checker-side and get fixed upstream in cc-plugin-wcrp; keep the local checkout on a recent `develop` before concluding your data is wrong.
- Findings that hit every file at once usually point at one systematic cause, not hundreds of separate problems. FILE001/PATH001/PATH002 across the whole run means the DRS layout (see step 5), not bad metadata.
- GPG signing on commits uses key `D763C0EA86718612` when unlocked; do not add `--no-gpg-sign`.

## Where to look for help

- `CLAUDE.md` at the repo root has the project overview and dev conventions.
- `examples/` has real working configs (e.g. `submit_hr_year_shards.sh`, `run_hr_shard.sh`).
- `doc/` has the full Sphinx docs (or read on ReadTheDocs at pycmor.readthedocs.io).
- Ping Jan for anything model-specific.
