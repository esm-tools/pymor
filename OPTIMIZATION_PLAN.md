# pycmor HR optimization — Phase 2 plan

Phase 1 closed with two clean negative results: slab-loop save path
(reverted in `1c7f2d7`) and offline input rechunking (5×5 ensemble
showed source 9 % faster on warm cache, 12× lighter in heap). See
`HANDOFF_memory_pressure.md` for the full record.

This file plans Phase 2: targeted attacks on the bottlenecks we
**actually** measured, ranked by ROI/effort, with parallel-test
groupings called out.

## Confirmed bottlenecks

From the Phase 1 ensemble + parallel agent's runs:

| bottleneck | evidence | plausible mechanism |
|---|---|---|
| Page-cache hit rate dominates single-rule wall | cold 4:54 vs warm 2:45 (1.78×) | first-rule reads from disk, subsequent rules from RAM |
| HDF5 B-tree contention under concurrent reads | parallel agent measured ~1.7 MB/s aggregate at P7 | 8 readers × 5840 small chunks each → metadata seek storm |
| Per-rule pipeline-step orchestration overhead | not directly measured; **Prefect 3.x benchmarks at ~1500 tasks/hour ≈ 2.4 s/task** ([source](https://clankercloud.ai/blog/best-tools-containerized-kubernetes-data-pipelines-2026-benchmark)) | 13 tasks/rule × 52 rules × 2.4 s = ~27 min orchestration overhead per cap7_atm run |
| Many small native HDF5 chunks per file | 5840 chunks/file (6hr) or 8760 (1hr) | structural decision at XIOS (model side); source chunk shape `(1, 2, 421120)` |

Single-rule wall is the critical path (P5 vs P6 verified — adding
workers doesn't help). So every minute saved per heavy rule turns
into a minute saved on cap7_atm wall.

## Variants under consideration

### A — HDF5 chunk cache + h5netcdf engine

**What**: switch `pycmor.core.gather_inputs.load_mfdataset` from the
default `netcdf4` engine to `h5netcdf`, and pass `rdcc_nbytes=256_000_000`
(256 MB) via h5py file kwargs.

**Why**:

1. HDF5's per-dataset chunk cache default is **1 MiB** ([HDF Group](https://forum.hdfgroup.org/t/why-increasing-rdcc-nbytes-and-rdcc-nslots-will-result-in-a-decrease-in-indexing-performance/9062))
   — 1 chunk fits in cache. Our chunks are ~1.5 MB each, so 0.6
   chunks fit. Every read walks the B-tree + decompresses. Bumping
   to 256 MB holds ~170 chunks, so chunks reused across pipeline
   steps (timeavg, set_global, set_variable, set_coordinates,
   map_dimensions, etc.) become cache hits.
2. [xarray docs](https://docs.xarray.dev/en/stable/user-guide/io.html)
   say `engine="h5netcdf"` is "often faster" for `open_mfdataset`.
   One reported workflow saw 4×.

**Implementation**: ~5–10 LOC in `gather_inputs.load_mfdataset`. Pass
`engine="h5netcdf"`, then construct an `h5netcdf` kwarg dict for the
`rdcc_nbytes` value. Optionally make both configurable via the
`pycmor` config block.

**Expected impact**: largest on cold-cache. Warm-cache may also
improve by avoiding HDF5 metadata re-walks within a rule's pipeline.

**Risk**: low. h5netcdf is in pycmor's deps (1.8.1 confirmed). Worst
case it's slower and we revert.

### B — `inline_array=True` for dask graphs

**What**: pass `inline_array=True` to `xr.open_mfdataset(...)` in
`load_mfdataset`.

**Why**: with 5840 chunks per file, the dask task graph has 5840
separate task nodes. `inline_array=True` collapses the graph
representation (chunks become inline values rather than separate task
references). [xarray docs](https://docs.xarray.dev/en/stable/generated/xarray.open_dataset.html)
mention this option specifically for the many-chunks scenario.

**Implementation**: 1-line change.

**Expected impact**: reduces Python overhead in dask graph
evaluation. May be 5–15 % wall for compute-heavy steps. Independent
of A; can layer.

**Risk**: low — flag is a standard xarray kwarg.

### C — Prefect task collapse

**What**: refactor pycmor's pipeline runner so multiple metadata-only
steps (`set_global`, `set_variable`, `set_coordinates`,
`map_dimensions`, attribute touches) are batched into a single
Prefect task. Heavy steps (`load_mfdataset`, `timeavg`,
`save_dataset`) stay as their own tasks.

**Why**: Prefect 3.x ≈ **2.4 s/task** scheduler latency
([benchmark](https://clankercloud.ai/blog/best-tools-containerized-kubernetes-data-pipelines-2026-benchmark)).
13 tasks/rule × 52 rules = 676 task invocations × 2.4 s = **~27 min
of pure orchestration overhead** in the cap7_atm 2:57 baseline.
Collapsing to ~5 tasks/rule (load + apply_metadata + timeavg +
unit_conv + save) would save ~17 min.

**Implementation**: more invasive. Touches `pycmor/core/pipeline.py`
and the cmorizer's task wiring. ~1–2 days. Risk of breaking
Prefect's caching / hashing invariants for task results.

**Expected impact**: ~15 % reduction on cap7_atm wall. Independent
of A and B; layers cleanly.

**Risk**: medium. Behavior change in pycmor's core. Need a careful
test against the existing test suite plus a validation cap7_atm run.

### D — Shared input loading across rules

**What**: when N rules read the same input file, load it once and
dispatch the dataset to each rule instead of re-loading per rule.

**Why**: cap7_atm has many rules reading the same XIOS streams (e.g.
multiple variables from `atmos_1h_pt_*.nc`). The parallel agent's
"1.7 MB/s aggregate" diagnosis at P7 was likely concurrent rules
contending on shared files. Sharing the load step could give 2-4×
I/O reduction on those shared inputs.

**Implementation**: architectural. Touches scheduling (`cmorizer.py`)
and the pipeline runner. ~1 week.

**Expected impact**: significant on heavy-tail rules that share
inputs. Conservative estimate: 15-30 % off cap7_atm wall on top of
A-C. But unverified.

**Risk**: high — biggest behavioral change. Defer until after
A-C measured.

### E — Cache prewarming

**What**: explicit `cat input.nc > /dev/null` on each rule's input
files in parallel before starting that rule's pipeline.

**Why**: production runs are usually cold-cache (year N's data was
just written). Prewarming lets the I/O happen overlapped with any
prior rule's compute, instead of stalling at the start of the new
rule.

**Implementation**: shell wrapper or pycmor-side `&` background read.
Simple in concept, fiddly in practice (need to know which files
the rule will read).

**Expected impact**: limited unless cap7_atm has long compute phases
that overlap. Probably not worth pursuing alone.

**Risk**: low.

### F — Lustre input striping (`lfs migrate -c 8`)

**What**: re-stripe input files across 8 OSTs (currently default,
likely 1 OST per file).

**Why**: with 8 concurrent rules reading the same OST, throughput is
serialized. Striping across 8 OSTs gives parallel disk reads.

**Implementation**: `lfs migrate -c 8 file.nc`. ~minutes per file,
one-time per simulation year.

**Expected impact**: helps under contention. Less under serial /
warm-cache.

**Risk**: low. Reversible.

## Parallel test groupings

Variants split into two independent axes that can be tested in
parallel:

```
Axis 1 (load-step optimizations, share load_mfdataset implementation):
  A:  h5netcdf + rdcc_nbytes
  B:  inline_array=True
  AB: combine A+B in one yaml

Axis 2 (orchestration / scheduler):
  C:  Prefect task collapse

Axis 3 (architectural — defer):
  D:  shared input loading
  E:  cache prewarming
  F:  Lustre input striping
```

Test plan:

1. **Round 1 (load-step axis)**: A, B, AB in parallel. 3 variants ×
   5-member ensemble × ~5 min/run on warm cache = ~75 min wall total
   when batched. Compare to the existing source-input ensemble
   (24694882 + 24695049/51/53/55, mean 2:45 warm-cache).

2. **Round 2 (orchestration)**: C alone, after A/B/AB winner is
   picked. The Prefect collapse is independent of which load-step
   variant we use; we'll layer it on top of the round-1 winner.

3. **Round 3 (validation at scale)**: take the best combo from rounds
   1+2 and run cap7_atm with the parallel agent. Compare to baseline
   (2:57 / 48/52). Expectation: 2:00–2:15 / 48/52.

## What I need

- **Approval to modify `src/pycmor/core/gather_inputs.py`** (axis 1).
  Small change behind opt-in env var or config key; default behavior
  unchanged when the new key isn't set.
- **A clean test rule for round 1**. Use `ua_6hr_pl7h` (already has
  the bench yaml + runscript). Same as Phase 1 source-input ensemble
  — apples-to-apples comparison.
- **5-member ensembles** for each variant in round 1. Compute is
  cheap (~5 min/run × 5 = 25 min wall per variant, fully parallel).
- **No drop_caches between runs needed**. Phase 1 showed ensemble
  variance is dominated by cold-vs-warm-cache; first run cold, rest
  warm. The same pattern across A/B/AB will cancel out as long as
  ensembles are submitted in the same order.

Optional but useful:

- **A second test rule** like `uas_1hr` (8760-timestep, different
  shape, more chunks). Lets us see whether axis-1 wins generalize
  across rule shapes.
- **memray or py-spy on one A/AB run** — confirms whether HDF5
  `_read_chunk` time actually drops with the bigger cache, or
  whether some other cost dominates.

## Decision tree

```
Round 1 (A / B / AB on ua_6hr_pl7h):

  AB wall ≤ 2:30 (≥10% off baseline)
    → ship AB; queue Round 2 (C on top of AB)
  
  AB wall ~2:40-2:45 (no measurable win)
    → check warm-vs-cold split; cold-cache win may exist
    → if no cold-cache win either, drop axis 1; do C standalone
  
  AB wall > 2:45 (regression)
    → diagnose; engine swap rarely regresses but possible
    → revert and only try C
```

## Round 1 result: regression on both variants

5×5 ensemble, ua_6hr_pl7h. Source baseline: ~2:45 warm-cache, ~5:02
cold-cache.

| variant | wall mean | save step | verdict |
|---|---|---|---|
| baseline (netcdf4, default) | 2:45 (warm) / 5:02 (cold) | ~1:46 | reference |
| B (inline_array=True) | 5:30 | n/a | **2× slower** |
| A (h5netcdf engine) — first attempt | 2:35 (failed at save) | crash | save errored on `compression='unknown'` |
| A (h5netcdf engine) — after `_strip_unportable_encoding` fix | **10:42** uniform across 5 runs | **5:00** | **3.9× wall, 2.8× save regression** |

**Why h5netcdf is slower for our case**: it wins on file-open
(measured 0.03 s vs 15 s for source) but loses 2.8× on the chunked
data read during save. xarray docs say "h5netcdf is often faster" for
`open_mfdataset` with many files, where file-open dominates. Our
pattern is 1 large file with many small chunks, where the
per-chunk-read path matters far more than the file-open cost.

**Why inline_array=True is slower**: with our 17 GB array spread
across 5840 chunks, inlining each chunk reference into the dask task
graph makes the graph much larger to evaluate. The intended use case
is small arrays where the graph indirection dominates.

**Patches kept** (small, opt-in, default off):
- `src/pycmor/core/gather_inputs.py`: `xarray_open_mfdataset_engine_override`
  + `xarray_open_mfdataset_inline_array` rule attrs / config keys.
  Default behavior unchanged.
- `src/pycmor/std_lib/files.py`: `_strip_unportable_encoding` —
  drops `compression="unknown"` from coord encoding before save.
  Defensive cleanup; would prevent breakage if anyone explicitly
  opts into the h5netcdf engine in the future.

**Round 1 axis closed.** Load-step optimizations researched online
don't apply to our pattern.

---

## Round 2: Prefect task collapse

Background and motivation in OPTIMIZATION_PLAN.md "Variants under
consideration / variant C". Prefect 3.x at ~2.4 s/task × 676
invocations ≈ 27 min orchestration overhead per cap7_atm run (~15 %
of the 2:57 baseline).

Plan:
1. Map the current 13-task pipeline. Identify which tasks are
   metadata-only (no dataset compute, just attribute touches): likely
   `set_global`, `set_variable`, `set_coordinates`, `map_dimensions`,
   `manual_checkpoint`, `show_data`, possibly the trigger_compute
   no-op when `lazy_write=true`.
2. Collapse those into a single Prefect task `apply_metadata`.
3. Heavy tasks stay separate: `load_mfdataset`, `timeavg`,
   `handle_unit_conversion`, `save_dataset`.
4. Goal: 13 → ~5 tasks/rule, saves ~17 min/run on cap7_atm.

Risk: Prefect's task hashing / caching may rely on per-step
invocation. Need to preserve cache key behavior or document the
break.

Implementation plan to be filled in once the pipeline runner code
is read.

## Files to add / modify

```
src/pycmor/core/gather_inputs.py     # axis 1: engine + rdcc_nbytes + inline_array
src/pycmor/core/config.py            # optional: knobs in pycmor block
src/pycmor/core/pipeline.py          # axis 2: Prefect task collapse
examples/cmip7_bench_hr_ua_6hr_h5nc.yaml      # axis 1, variant A
examples/cmip7_bench_hr_ua_6hr_inline.yaml    # axis 1, variant B
examples/cmip7_bench_hr_ua_6hr_h5nc_inline.yaml  # axis 1, variant AB
examples/run_bench_hr_ua_6hr_h5nc.sh
examples/run_bench_hr_ua_6hr_inline.sh
examples/run_bench_hr_ua_6hr_h5nc_inline.sh
OPTIMIZATION_PLAN.md                 # this file
```

## Sources

- [HDF5 chunk cache — HDF Group forum](https://forum.hdfgroup.org/t/why-increasing-rdcc-nbytes-and-rdcc-nslots-will-result-in-a-decrease-in-indexing-performance/9062)
- [Improve HDF5 performance using caching — HDF Group](https://www.hdfgroup.org/2022/10/17/improve-hdf5-performance-using-caching/)
- [h5py File Objects (rdcc_nbytes API)](https://docs.h5py.org/en/stable/high/file.html)
- [xarray reading and writing files](https://docs.xarray.dev/en/stable/user-guide/io.html)
- [xarray.open_dataset (inline_array)](https://docs.xarray.dev/en/stable/generated/xarray.open_dataset.html)
- [xarray Dask user guide](https://docs.xarray.dev/en/stable/user-guide/dask.html)
- [Cloud-Performant NetCDF4/HDF5 reading via Zarr lib (Pangeo)](https://medium.com/pangeo/cloud-performant-reading-of-netcdf4-hdf5-data-using-the-zarr-library-1a95c5c92314)
- [h5netcdf documentation](https://h5netcdf.org/index.html)
- [Parallel I/O Characterization and Optimization (arXiv)](https://arxiv.org/html/2501.00203v1)
- [Lustre concurrent I/O handling — HPC SRE](https://hpcadmin.com/2023/03/25/lustres-approach-to-handling-concurrent-read-and-write-operations-efficiently/)
- [Prefect data pipeline benchmark — Clanker Cloud (May 2026)](https://clankercloud.ai/blog/best-tools-containerized-kubernetes-data-pipelines-2026-benchmark)
- [pycmor (esm-tools) — GitHub](https://github.com/esm-tools/pycmor)
