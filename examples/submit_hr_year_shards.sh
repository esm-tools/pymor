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

  # Run the splitter; capture how many shards it produced.
  python3 "$HERE/shard_tier_yaml.py" "$yaml" \
      shard --shard-size "$SHARD_SIZE" \
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
  case "$short_tier" in
    lrcs_seaice)
      MEM_FLAG="--mem=512G"
      tier_cgroup=512
      ;;
    *)
      MEM_FLAG="--mem=0"
      tier_cgroup=256
      ;;
  esac

  # Per-tier Fix #3 (PYCMOR_WORKER_COMPUTE) selection. Default OFF.
  # Heavy 3D pressure-level atmos pipelines (zg/va/hus/ta/wap monthly)
  # have *small* output (~380 MB) despite reading 280 GB of hourly input.
  # The lazy graph for the aggregation is wide (many time-chunks) but
  # shallow — exactly the shape Fix #3 handles well with worker-side
  # parallel reads. cli30's cap7_atm_1 took 25+ min on synchronous I/O;
  # Fix #3 should bring that to 2-5 min (cli7 baseline).
  # Tiers without 3D-plev-monthly rules stay OFF — they don't benefit
  # and Fix #3 ON re-introduces big-graph OOMs for OIFS-regrid families.
  case "$short_tier" in
    cap7_atm|core_atm|extra_atm|veg_atm)
      FIX3="auto"
      ;;
    *)
      FIX3="off"
      ;;
  esac

  jid=$(sbatch --parsable \
        --array=1-"$num_shards" \
        -J "$jobname" \
        --time="$WALLTIME" \
        $MEM_FLAG \
        --export=ALL,CGROUP_GB=$tier_cgroup,SHARD_FIX3=$FIX3 \
        "$HERE/run_hr_shard.sh" \
        "$shards_dir" "$RUN_ABS" "$YEAR" "${short_tier}/cmorized" 2>&1) \
    || { echo "sbatch failed for $short_tier"; continue; }
  submitted+=("$jid:$short_tier[$num_shards shards, $MEM_FLAG, fix3=$FIX3]")
  echo "  submitted $jobname  jid=$jid  shards=$num_shards  $MEM_FLAG  fix3=$FIX3"
done

echo
echo "Submitted ${#submitted[@]} tiers (each as a SLURM array)."
echo "Outputs: $OUTROOT"
echo "Watch:   squeue -u \$USER -n pycmor-hr"
echo "Each array task logs to: pycmor_hr_shard_<jobname>_<jobid>_<arrayidx>.log"
