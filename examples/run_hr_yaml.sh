#!/bin/bash
#SBATCH --job-name=pycmor-hr
#SBATCH --partition=compute
#SBATCH --account=ba0989
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=256G
#SBATCH --time=04:00:00
#SBATCH --output=pycmor_hr_%x_%j.log
#SBATCH --error=pycmor_hr_%x_%j.log

# Generic HR runner: takes an absolute yaml path as $1 and an optional
# output subdir name as $2 (default: derived from the yaml's parent dir).
# All 17 HR production yamls share the same compute-node topology
# (TCo319, 256 GB, 16 cores, 4 h wall); only the yaml + output dir change.

set -euo pipefail

YAML="${1:?usage: sbatch run_hr_yaml.sh <yaml-path> [output-subdir]}"
OUTSUB="${2:-$(basename "$(dirname "$YAML")")}"

source ~/loadconda.sh
conda activate pycmor_py312

cd /work/ab0246/a270092/software/pycmor

PYCMOR_SCRATCH=/scratch/a/a270092/pycmor_tmp/$$
mkdir -p $PYCMOR_SCRATCH/prefect/storage
export PREFECT_HOME=$PYCMOR_SCRATCH/prefect
export PREFECT_LOCAL_STORAGE_PATH=$PYCMOR_SCRATCH/prefect/storage
export TMPDIR=$PYCMOR_SCRATCH
export OMP_NUM_THREADS=1

# Use /scratch for outputs (fast). Setstripe 8 for parallel I/O if lfs exists.
OUTROOT=${OUTROOT:-/scratch/a/a270092/pycmor_hr_out}
OUTDIR=$OUTROOT/$OUTSUB
mkdir -p "$OUTDIR"
command -v lfs >/dev/null && lfs setstripe -c 8 "$OUTDIR" 2>/dev/null || true

# Override yaml: use local dask cluster on this compute node (slurm dispatch
# adds overhead we don't want), 1 worker + blosc internal threads, and write
# to our target output dir.
sed -e 's/dask_cluster: "slurm"/dask_cluster: "local"/' \
    -e 's|output_directory: .*|output_directory: '"$OUTDIR"'|' \
    "$YAML" > $PYCMOR_SCRATCH/hr.yaml

echo "=== yaml: $YAML  ->  out: $OUTDIR ==="
pycmor process $PYCMOR_SCRATCH/hr.yaml
