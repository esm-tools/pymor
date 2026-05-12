#!/bin/bash
#SBATCH --job-name=pycmor-hr-shard
#SBATCH --partition=compute
#SBATCH --account=ba0989
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=128
#SBATCH --mem=0
#SBATCH --time=03:00:00
#SBATCH --output=pycmor_hr_shard_%x_%A_%a.log
#SBATCH --error=pycmor_hr_shard_%x_%A_%a.log

# Step 2 of PLAN_slurm_shard_isolation.md (Option 2-ish: ran on `shared`
# at first, hit queue contention + worker-memory undersizing; pivoted to
# `compute` per the plan's §0 fallback).
#
# Runs ONE shard yaml (≈16-20 rules) in a single Python process on a
# dedicated `compute` node. Driver memory bounded by N rules, not by 70+.
#
# Why `compute`:
#   - `shared` partition was queue-saturated at 35-array submit;
#     compute has 2931 nodes → no wait.
#   - `compute` is OverSubscribe=EXCLUSIVE: we get the whole 256 GB
#     node anyway. ``--mem=0`` tells SLURM "give me all available
#     memory on the node" — no point being shy.
#   - The 94% CPU waste (8-9 active / 128 allocated) is the price
#     of failure isolation per shard.
#
# Designed to be sbatched as a SLURM array (one task per shard):
#   sbatch --array=1-4 examples/run_hr_shard.sh <shards-dir> <run-root> <year> <output-subdir>
#
# Required positional args:
#   $1  SHARDS_DIR  — dir containing <tier>_shard_NN.yaml files
#                     (produced by examples/shard_tier_yaml.py)
#   $2  RUN_ROOT    — full path to model run root
#   $3  YEAR        — 4-digit year to process
#   $4  OUTSUB      — output sub-directory name (typically <tier>/cmorized/<tier>)
#
# Each array task picks shard `$((SLURM_ARRAY_TASK_ID - 1))` from
# SHARDS_DIR. Shard yamls are sorted by filename so shard_00 → array
# task 1, shard_01 → array task 2, etc.
#
# Optional knobs (env):
#   N_WORKERS               (default 2)
#   TPW                     (default 4)
#   MEM_PER_WORKER          (default 8GB) — 2 × 8 GB = 16 GB worker total
#                                           leaving ~44 GB driver headroom
#   CGROUP_GB               (default 60) — matches the 60 GB SBATCH alloc
#   PYCMOR_PREFECT_COLLAPSE (default 1)
#   OUTROOT                 root for output (default /scratch/$USER/pycmor_hr_shard_out)
#   MEMORY                  pycmor --memory override (optional)

set -euo pipefail

SHARDS_DIR="${1:?usage: run_hr_shard.sh <shards-dir> <run-root> <year> [output-subdir]}"
RUN_ROOT="${2:?usage: run_hr_shard.sh <shards-dir> <run-root> <year> [output-subdir]}"
YEAR="${3:?usage: run_hr_shard.sh <shards-dir> <run-root> <year> [output-subdir]}"
OUTSUB="${4:-shard_out}"

# Pick the shard yaml that corresponds to this array task.
# SLURM_ARRAY_TASK_ID is 1-based; shard files are 0-based.
task_idx=${SLURM_ARRAY_TASK_ID:-1}
shard_idx=$((task_idx - 1))
shard_yaml=$(ls -1 "$SHARDS_DIR"/*.yaml | sort | sed -n "$((shard_idx + 1))p")
if [ -z "${shard_yaml:-}" ]; then
  echo "ABORT: shard index $shard_idx not found in $SHARDS_DIR"
  exit 2
fi
shard_basename=$(basename "$shard_yaml" .yaml)

source ~/loadconda.sh
conda activate pycmor_py312

cd /work/ab0246/a270092/software/pycmor
export PYCMOR_HOME=/work/ab0246/a270092/software/pycmor

N_WORKERS=${N_WORKERS:-4}
TPW=${TPW:-4}
# 48 GB per worker (was 32 GB in cli22): hourly OIFS rules like tas
# (8760 timesteps × 421k cells × float32 ≈ 14 GiB raw) spike past 30 GB
# during regrid+aggregate; one worker OOM = whole shard dies (cli22
# cap7_land_05). 4 × 48 = 192 GB workers, ~30 GB driver, headroom OK
# on the 256 GB cgroup.
MEM_PER_WORKER=${MEM_PER_WORKER:-48GB}
CGROUP_GB=${CGROUP_GB:-256}
# Smaller tmpfs budget than the per-tier runner: at N=16-20 rules per
# process, peak concurrent staged writes is bounded by N_WORKERS.
TMPFS_BUDGET_GB=${PYCMOR_TMPFS_BUDGET_GB:-$(( N_WORKERS * 1 ))}

# Budget check — same shape as run_hr_yaml_cli.sh. The 75% factor leaves
# headroom for Python, xarray caches, etc.
mem_gb=${MEM_PER_WORKER%GB}
mem_gb=${mem_gb%gb}
worker_gb=$(( N_WORKERS * mem_gb ))
total_gb=$(( worker_gb + TMPFS_BUDGET_GB ))
budget_gb=$(( CGROUP_GB * 85 / 100 ))
if [ "$total_gb" -gt "$budget_gb" ]; then
  echo "ABORT: N_W*MEM_PER_W + tmpfs = ${worker_gb}+${TMPFS_BUDGET_GB} = ${total_gb} GB exceeds budget ${budget_gb} GB"
  echo "       (85% of CGROUP_GB=${CGROUP_GB}). Lower N_WORKERS or MEM_PER_WORKER."
  exit 2
fi
echo "=== shard: $shard_basename (array task $task_idx) ==="
echo "=== budget: ${worker_gb} GB dask + ${TMPFS_BUDGET_GB} GB tmpfs / ${budget_gb} GB allowed (${CGROUP_GB} GB cgroup) ==="

# Dask spill thresholds (fractions of MEM_PER_WORKER).
export DASK_DISTRIBUTED__WORKER__MEMORY__TARGET=0.50
export DASK_DISTRIBUTED__WORKER__MEMORY__SPILL=0.60
export DASK_DISTRIBUTED__WORKER__MEMORY__PAUSE=0.75
export DASK_DISTRIBUTED__WORKER__MEMORY__TERMINATE=0.90

PYCMOR_SCRATCH=/scratch/a/a270092/pycmor_tmp/${SLURM_JOB_ID:-$$}_${task_idx}
mkdir -p "$PYCMOR_SCRATCH/prefect/storage"
PREFECT_NODELOCAL=/tmp/pycmor_prefect_${SLURM_JOB_ID:-$$}_${task_idx}
mkdir -p "$PREFECT_NODELOCAL/storage"
export PREFECT_HOME="$PREFECT_NODELOCAL"
export PREFECT_LOCAL_STORAGE_PATH="$PREFECT_NODELOCAL/storage"
trap "rm -rf $PREFECT_NODELOCAL" EXIT
export TMPDIR="$PYCMOR_SCRATCH"
export HDF5_USE_FILE_LOCKING=FALSE
export OMP_NUM_THREADS=1
export PYCMOR_PREFECT_COLLAPSE=${PYCMOR_PREFECT_COLLAPSE:-1}
# Concurrency: rely on default n_workers×tpw (=16 here). cli22's
# PYCMOR_MAX_IN_FLIGHT=2 was a misdiagnosis — cli7 (May 9) ran the full
# 77-rule core_atm tier in 1h25 with N_WORKERS=4×16GB and no global
# throttle. The actual failure mode in cli21/cli22 was worker OOM on
# heavy single rules, which throttling can't fix. Per-pipeline
# throttle_group annotations in the yamls (for sea-ice OIFS-regrid)
# remain in effect via cmorizer.py's _make_batches logic.

OUTROOT=${OUTROOT:-/scratch/a/a270092/pycmor_hr_shard_out}
OUTDIR="$OUTROOT/$OUTSUB"
mkdir -p "$OUTDIR"
command -v lfs >/dev/null && lfs setstripe -c 8 "$OUTDIR" 2>/dev/null || true

# Inject runtime parallel knobs into a copy of the shard yaml.
python3 - <<PY
import yaml
y = yaml.safe_load(open("$shard_yaml"))
y.setdefault("pycmor", {})
y["pycmor"]["parallel"] = True
y["pycmor"]["pipeline_orchestrator"] = "dask"
y["pycmor"]["dask_cluster"] = "local"
y["pycmor"]["dask_n_workers"] = ${N_WORKERS}
y["pycmor"]["dask_threads_per_worker"] = ${TPW}
y["pycmor"]["dask_memory_limit"] = "${MEM_PER_WORKER}"
yaml.safe_dump(y, open("$PYCMOR_SCRATCH/par.yaml", "w"), sort_keys=False)
PY

CLI_ARGS=(
  --data-path "${RUN_ROOT}"
  --year-start "${YEAR}"
  --year-end "${YEAR}"
  --output-directory "${OUTDIR}"
)
if [ -n "${MEMORY:-}" ]; then
  CLI_ARGS+=(--memory "${MEMORY}")
fi

echo "=== shard yaml: $shard_yaml  ->  $OUTDIR ==="
echo "=== --data-path ${RUN_ROOT}  --year ${YEAR}  --memory ${MEMORY:-<unset>} ==="
echo "=== config: parallel=True orchestrator=dask N_WORKERS=${N_WORKERS} TPW=${TPW} MEM_PER_WORKER=${MEM_PER_WORKER} ==="
echo "=== node $(hostname), $(nproc) cores allocated, $(free -g | awk '/^Mem:/{print $2}') GB visible ==="
date +%s.%N
/usr/bin/time -v pycmor process "$PYCMOR_SCRATCH/par.yaml" "${CLI_ARGS[@]}"
date +%s.%N

echo "=== Output files for this shard ==="
# Don't dump the entire OUTDIR — other shards write here too. Print only
# files modified since this script started.
find "$OUTDIR" -type f -newer "$PYCMOR_SCRATCH" -printf '%s %p\n' | sort -n
