#!/bin/bash
#SBATCH --job-name=pycmor-bench-hr-fluxnumpy
#SBATCH --partition=compute
#SBATCH --account=ba0989
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=256G
#SBATCH --time=00:30:00
#SBATCH --output=pycmor_bench_hr_fluxnumpy_%j.log
#SBATCH --error=pycmor_bench_hr_fluxnumpy_%j.log

# Same workload as run_slow_write_bench_hr.sh but with flox_engine="numpy"
# on the rule, bypassing flox's numbagg JIT path inside resample().mean().

source ~/loadconda.sh
conda activate pycmor_py312

cd /work/ab0246/a270092/software/pycmor

PYCMOR_SCRATCH=/scratch/a/a270092/pycmor_tmp/$$
mkdir -p $PYCMOR_SCRATCH/prefect/storage
export PREFECT_HOME=$PYCMOR_SCRATCH/prefect
export PREFECT_LOCAL_STORAGE_PATH=$PYCMOR_SCRATCH/prefect/storage
export TMPDIR=$PYCMOR_SCRATCH
export HDF5_USE_FILE_LOCKING=FALSE
export OMP_NUM_THREADS=1

OUTROOT=${OUTROOT:-/scratch/a/a270092/pycmor_bench_numpy}
mkdir -p "$OUTROOT"

# Patch the bench yaml: inject flox_engine: numpy into the single rule.
sed -e "s|output_directory: .*|output_directory: $OUTROOT/slow_write_bench_hr|" \
    -e "s|  - name: tasmax_mon|  - name: tasmax_mon\n    flox_engine: numpy|" \
    examples/cmip7_slow_write_bench_hr.yaml > $PYCMOR_SCRATCH/bench.yaml

echo "=== Patched rule ==="
grep -nE "tasmax_mon|flox_engine" $PYCMOR_SCRATCH/bench.yaml

echo "=== Start pycmor process ==="
date +%s.%N
/usr/bin/time -v pycmor process $PYCMOR_SCRATCH/bench.yaml
date +%s.%N

echo "=== Output ==="
find "$OUTROOT/slow_write_bench_hr" -type f -printf '%s %p\n' | sort -n
