#!/bin/bash
# Step 3 of PLAN_slurm_shard_isolation.md: shard tier yamls and sbatch
# one SLURM array per tier on the `shared` partition.
#
# Usage:
#   submit_hr_year_shards.sh <RUN_NAME_OR_ABSPATH> <YEAR> [WORKDIR]
#
#   e.g.  submit_hr_year_shards.sh Test_06 1587
#         submit_hr_year_shards.sh Test_06 1587 /scratch/$USER/cmorize_Test_06_y1587_shards
#
# Pipeline:
#   1. Repoint tier yamls at <RUN>/<YEAR> via repoint_hr_year.py
#   2. Pre-flight: warm mesh + DReq caches (no-op if already cached)
#   3. For each tier yaml: shard via shard_tier_yaml.py
#   4. sbatch one SLURM array per tier (one task per shard)
#
# Knobs (env):
#   SHARD_SIZE             default 20 (rules per shard upper bound)
#   SHUFFLE_SEED           default 42 (for reproducibility of the shard split)
#   TIER                   single tier name; if set, only that tier's
#                          yaml is submitted (used for smoke tests)
#   WALLTIME               default 01:00:00
#   N_WORKERS, TPW, MEM_PER_WORKER, CGROUP_GB — see run_hr_shard.sh
set -euo pipefail

RUN="${1:?usage: $0 <run_name_or_abspath> <year> [workdir]}"
YEAR="${2:?usage: $0 <run> <year> [workdir]}"
WORKDIR="${3:-/scratch/${USER:0:1}/$USER/pycmor_hr/$(basename "$RUN")_y${YEAR}_shards}"

HERE="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$WORKDIR"

# Resolve the run argument to a full path (matches repoint_hr_year.py's
# resolve_run_dir logic). Relative names resolve under RUNTIME_ROOT.
RUNTIME_ROOT=/work/bb1469/a270092/runtime/awiesm3-develop
case "$RUN" in
  /*) RUN_ABS="$RUN" ;;
  *)  RUN_ABS="$RUNTIME_ROOT/$RUN" ;;
esac
if [ ! -d "$RUN_ABS" ]; then
  echo "ABORT: run root $RUN_ABS does not exist"
  exit 2
fi

# Step 1: repoint yamls into WORKDIR/yamls/
YAMLS_DIR="$WORKDIR/yamls"
mkdir -p "$YAMLS_DIR"
python3 "$HERE/repoint_hr_year.py" "$RUN" "$YEAR" "$YAMLS_DIR"

# Optional single-tier filter
if [ -n "${TIER:-}" ]; then
  echo "TIER=$TIER set; restricting to that one tier."
  # repoint_hr_year.py names yamls by tier dir; match with a glob.
  matches=( "$YAMLS_DIR"/*"$TIER"*.yaml )
  if [ ${#matches[@]} -eq 0 ] || [ ! -f "${matches[0]}" ]; then
    echo "ABORT: no yaml in $YAMLS_DIR matches '*$TIER*.yaml'"
    exit 2
  fi
  # Keep only the matched yaml(s); remove the others from this run.
  for y in "$YAMLS_DIR"/*.yaml; do
    keep=0
    for m in "${matches[@]}"; do [ "$y" = "$m" ] && keep=1 && break; done
    [ "$keep" -eq 0 ] && rm -f "$y"
  done
fi

# Step 2: pre-flight — warm caches sequentially.
# Currently a stub. The mesh cache (MESH_cache/) is populated by setgrid
# steps on first use; CV/DReq metadata.json is already cached at
# ~/.cache/pycmor/cmip7_metadata/. If either is missing on a fresh node,
# the first shard pays the load cost; subsequent shards read from cache.
# Full sequential pre-warm to be added when smoke tests show contention.
echo "=== pre-flight (no-op for v1; relying on existing caches) ==="

# Step 3+4: shard each tier and sbatch as array.
SHARD_SIZE="${SHARD_SIZE:-20}"
SHUFFLE_SEED="${SHUFFLE_SEED:-42}"
WALLTIME="${WALLTIME:-03:00:00}"  # benchmark target: 1 year in 3h, zero failures (was 01:00:00 in cli21)
OUTROOT="$WORKDIR/cmorized"
mkdir -p "$OUTROOT"
export OUTROOT
export N_WORKERS=${N_WORKERS:-4}
export TPW=${TPW:-4}
export MEM_PER_WORKER=${MEM_PER_WORKER:-48GB}  # bumped from 32GB after cli22 cap7_land_05 OOM'd on hourly OIFS tas
export CGROUP_GB=${CGROUP_GB:-256}
export PYCMOR_PREFECT_COLLAPSE=${PYCMOR_PREFECT_COLLAPSE:-1}
# SHARD_DRS=on enables the CMIP DRS sub-tree under each shard's OUTDIR
# (pycmor.enable_output_subdirs). When on, the per-tier "<tier>/cmorized"
# OUTSUB prefix is dropped so all tiers land in one shared DRS root.
# Off by default; downstream tools that consume per-tier flat layouts
# can keep using the historical structure.
SHARD_DRS=${SHARD_DRS:-off}
export SHARD_DRS
# No global PYCMOR_MAX_IN_FLIGHT — cli7 (May 9) ran 77-rule core_atm
# clean in 1h25 with the default (n_workers × tpw). cli22's throttle=2
# was an 8× throughput regression and didn't fix the actual root cause
# (per-rule worker OOM, addressed by MEM_PER_WORKER bump). Per-pipeline
# throttle_group still applies via the yaml-level annotation.

submitted=()
for yaml in "$YAMLS_DIR"/*.yaml; do
  tier="$(basename "$yaml" .yaml)"
  # Strip the cmip7_awiesm3-veg-hr_ prefix for the job name brevity.
  short_tier="${tier#cmip7_awiesm3-veg-hr_}"

  shards_dir="$WORKDIR/shards/$short_tier"
  mkdir -p "$shards_dir"
  rm -f "$shards_dir"/*.yaml  # in case of re-run

  # Per-tier SHARD_SIZE override.
  # extra_land has 4 long-pole rules (tas_1hr_south30, orog_south30,
  # mrsow_day, dslw_day) whose synchronous netcdf saves contend in
  # parallel — cli39 wedged 3h walltime with all four stuck at
  # heartbeat #16. Splitting to ~5 rules per shard distributes the
  # contention across ~4 shards, well inside 3h each.
  case "$short_tier" in
    extra_land) tier_shard_size=5 ;;
    *)          tier_shard_size="$SHARD_SIZE" ;;
  esac

  # Run the splitter; capture how many shards it produced.
  python3 "$HERE/shard_tier_yaml.py" "$yaml" \
      shard --shard-size "$tier_shard_size" \
      --seed "$SHUFFLE_SEED" \
      --out-dir "$shards_dir" >/dev/null
  num_shards=$(ls -1 "$shards_dir"/*.yaml | wc -l)
  if [ "$num_shards" -lt 1 ]; then
    echo "WARN: $short_tier produced no shards; skipping."
    continue
  fi

  jobname="pycmor-hr-${short_tier}-y${YEAR}-sh"

  # Per-tier memory override. Tiers with rules that genuinely need a
  # 512+ GB cgroup get --mem=512G (smaller pool of ~282 nodes, slower
  # to dispatch but doesn't OOM). All others default to --mem=0 (any
  # compute node, ~2931 nodes, fast dispatch).
  #
  # Empirical justification — cli26 sacct MaxRSS observations:
  #   lrcs_seaice: 235 GiB on 256 GiB cgroup (Pattern A OOM)
  #   core_land:     2.6 GiB (Pattern B scheduler wedge — memory irrelevant)
  #   veg_land:     12 GiB (Pattern B — memory irrelevant)
  # Only Pattern A benefits from a bigger cgroup.
  # extra_atm joins lrcs_seaice on 512G:
  # sacct history (May 1-15) — every reliable extra_atm completion
  # used 512G memory:
  #   24733123 mem512  1:51:28   24733545 (whole-tier) 1:11:17
  #   24743470 cli3    2:07:45   24748551 cli5         2:34:58
  #   24784803 cli9    1:22:15   24813316 cli17        1:10:25
  # Since switching to sharded --mem=0 (~256G default):
  #   cli28 OOM, cli29 timeout, cli30 OOM (1:30 MaxRSS=235G),
  #   cli33 OOM, cli34 OOM, cli35 OOM, cli36 OOM (MaxRSS=167G,
  #   MaxVMSize=458G — fragmentation past cgroup limit).
  # 6 completions on 512G vs 0 reliable on 256G — proven config.
  # Trade: +1 task on the scarcer ~282-node 512G pool; brings the
  # 512G footprint to 5/35 tasks (14%), still minor pool pressure.
  case "$short_tier" in
    lrcs_seaice|extra_atm)
      MEM_FLAG="--mem=512G"
      tier_cgroup=512
      ;;
    *)
      MEM_FLAG="--mem=0"
      tier_cgroup=256
      ;;
  esac

  # All tiers run on the global WALLTIME (default 3h).
  # lrcs_seaice was previously 6h because cli30 lrcs_seaice_3 TIMEOUTed at
  # 3h — but that was pre-jemalloc when fragmentation drove the slow path.
  # Since cli35+ (jemalloc on), the slowest lrcs_seaice shard runs:
  #   cli35 _2: 1:08:52   cli36 _2: 1:12:04   (well under 3h)
  # No tier-specific override needed.
  tier_walltime="$WALLTIME"

  # Per-tier dask worker count. All tiers use the global N_WORKERS (4).
  # The earlier extra_atm=3 override was a fix for the Fix #3 eager-
  # gather driver-pileup OOM, but cli35 flipped extra_atm to fix3=off,
  # which removes that pile-up entirely. No need for the override now.
  tier_workers="$N_WORKERS"

  # Malloc allocator: jemalloc on all tiers.
  #
  # cli34 lrcs_seaice_2/_3 hit signal-6 SIGABRT at MaxVMSize=557 GiB /
  # RSS=232 GiB on a 512 GiB cgroup — the classic glibc malloc arena-
  # fragmentation footprint (lots of mmap-backed VM space, less actual
  # RSS), abort() firing when malloc bookkeeping can't satisfy an alloc
  # despite cgroup headroom. cli34+jem rescued 2 of 3 failing shards;
  # the 3rd stopped abort()-ing but wedged on slow synchronous compute
  # (a separate issue).
  #
  # cli34 extra_atm OOM'd at MaxRSS=215 GiB / MaxVMSize=281 GiB — the
  # same fragmentation footprint. N_WORKERS=3 hotfix only delayed it,
  # didn't fix it; jemalloc is the actual lever.
  #
  # Initially opted-in per-tier (lrcs_seaice only) because allocator
  # swaps can regress unrelated workloads, but the cli34 evidence
  # is that the fragmentation pattern shows up in every tier with
  # heavy long-running shards. Risk of regression < risk of OOM.
  # /lib64/libjemalloc.so.2 ships on Levante.
  tier_jemalloc=on

  # Per-tier Fix #3 (PYCMOR_WORKER_COMPUTE) selection. Default OFF.
  # Heavy 3D pressure-level atmos pipelines (zg/va/hus/ta/wap monthly)
  # have *small* output (~380 MB) despite reading 280 GB of hourly input.
  # The lazy graph for the aggregation is wide (many time-chunks) but
  # shallow — Fix #3 handles single rules of this shape well with
  # worker-side parallel reads.
  #
  # cap7_atm SPECIFICALLY removed from this list: cli34 shards 1/2/3
  # all TIMEOUT at 3h with 7-13 of their 17-18 rules saved. Logs show
  # 8 concurrent saves wedged at heartbeat #30 (t=1801s) with no I/O
  # progress on the heavy 3D rules (zg/va/ua/hus_6hr_pl7h, ta_mon_ml,
  # pfull_mon). cli9 (May 9) ran the WHOLE 52-rule cap7_atm tier in
  # 1:41:08 — pre-Fix #3 commit (3604c53). The regression hypothesis:
  # Fix #3 client.compute(sync=True) eager-gathers each rule's lazy
  # graph through the LocalCluster scheduler. Single rule = fast.
  # 8 concurrent heavy 3D rules = scheduler saturation + driver-side
  # eager Dataset pileup → wedge.
  # cli35 confirmed extra_atm follows the cap7_atm pattern: wedged on
  # 3D pressure-level rules (cl, pfull) at heartbeat #47+ with fix3=
  # auto, TIMEOUT at 3h. Same hypothesis: 8+ concurrent eager-gather
  # via client.compute(sync=True) saturates the LocalCluster scheduler.
  # Flip extra_atm to fix3=off like cap7_atm.
  # core_atm/veg_atm kept auto — they completed cleanly in cli34/cli35.
  case "$short_tier" in
    core_atm|veg_atm)
      FIX3="auto"
      ;;
    *)
      FIX3="off"
      ;;
  esac

  # Per-tier throttle caps (env-var path; the yaml-side `throttle_caps`
  # key gets dropped by the Everett PycmorConfig schema, only declared
  # Options survive). Format: `group:N,...`.
  # lrcs_seaice and veg_land tiers force strict serial (cap=1) on their
  # respective save-throttle groups so the HDF5 global write lock can't
  # wedge 9+ parallel saves the way it did in cli40/cli41 lrcs_seaice_3.
  case "$short_tier" in
    lrcs_seaice) tier_throttle_caps="lrcs_seaice_serial:1" ;;
    veg_land)    tier_throttle_caps="veg_land_serial:1" ;;
    *)           tier_throttle_caps="" ;;
  esac

  # OUTSUB is the per-tier subdir under OUTROOT. With SHARD_DRS=on the
  # pycmor DRS sub-tree is appended inside the saver, so we collapse the
  # tier prefix and write everything into one shared DRS root.
  if [ "$SHARD_DRS" = "on" ]; then
    tier_outsub="."
  else
    tier_outsub="${short_tier}/cmorized"
  fi

  jid=$(sbatch --parsable \
        --array=1-"$num_shards" \
        -J "$jobname" \
        --time="$tier_walltime" \
        $MEM_FLAG \
        --export=ALL,CGROUP_GB=$tier_cgroup,SHARD_FIX3=$FIX3,N_WORKERS=$tier_workers,SHARD_JEMALLOC=$tier_jemalloc,SHARD_DRS=$SHARD_DRS,PYCMOR_THROTTLE_CAPS=$tier_throttle_caps \
        "$HERE/run_hr_shard.sh" \
        "$shards_dir" "$RUN_ABS" "$YEAR" "$tier_outsub" 2>&1) \
    || { echo "sbatch failed for $short_tier"; continue; }
  submitted+=("$jid:$short_tier[$num_shards shards, $MEM_FLAG, fix3=$FIX3, t=$tier_walltime, n_w=$tier_workers, jem=$tier_jemalloc, drs=$SHARD_DRS]")
  echo "  submitted $jobname  jid=$jid  shards=$num_shards  $MEM_FLAG  fix3=$FIX3  t=$tier_walltime  n_w=$tier_workers  jem=$tier_jemalloc  drs=$SHARD_DRS"
done

echo
echo "Submitted ${#submitted[@]} tiers (each as a SLURM array)."
echo "Outputs: $OUTROOT"
echo "Watch:   squeue -u \$USER -n pycmor-hr"
echo "Each array task logs to: pycmor_hr_shard_<jobname>_<jobid>_<arrayidx>.log"
