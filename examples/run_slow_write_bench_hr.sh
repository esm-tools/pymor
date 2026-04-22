#!/bin/bash
#SBATCH --job-name=pycmor-slow-write-bench-hr
#SBATCH --partition=compute
#SBATCH --account=ba0989
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=256G
#SBATCH --time=00:30:00
#SBATCH --output=pycmor_slow_write_bench_hr_%j.log
#SBATCH --error=pycmor_slow_write_bench_hr_%j.log

# Isolate the single slowest rule from job 24405290 (tasmax_mon, 632s).
# Everything is instrumented here so we can blame chunking vs. compression
# vs. compute vs. write.

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

# Write to local scratch (fast) so any slow-write symptom is not
# just remote-filesystem stall. Can be overridden to compare.
OUTROOT=${OUTROOT:-/scratch/a/a270092/pycmor_bench}
mkdir -p "$OUTROOT"

sed -e "s|output_directory: .*|output_directory: $OUTROOT/slow_write_bench_hr|" \
    examples/cmip7_slow_write_bench_hr.yaml > $PYCMOR_SCRATCH/bench.yaml

echo "=== Input file ==="
ls -lh /work/bb1469/a270092/runtime/awiesm3-develop/HR_test_01/outdata/oifs/atmos_day_minmax_tasmax_day_minmax_1586-1586.nc
df -h "$OUTROOT"

echo "=== Start pycmor process (time-stamped) ==="
date +%s.%N
/usr/bin/time -v pycmor process $PYCMOR_SCRATCH/bench.yaml
date +%s.%N

echo "=== Output ==="
find "$OUTROOT/slow_write_bench_hr" -type f -printf '%s %p\n' | sort -n
