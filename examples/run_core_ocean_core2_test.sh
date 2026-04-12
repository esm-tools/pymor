#!/bin/bash
#SBATCH --job-name=pycmor-core-ocean-core2-test
#SBATCH --partition=compute
#SBATCH --account=bb1469
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=256G
#SBATCH --time=01:00:00
#SBATCH --output=pycmor_core_ocean_core2_test_%j.log
#SBATCH --error=pycmor_core_ocean_core2_test_%j.log

# Run pycmor process entirely on compute node (including Prefect server)
# Rules are processed serially (parallel: False) to avoid HDF5/Prefect issues.

source ~/loadconda.sh
conda activate pycmor_py312

cd /work/ab0246/a270092/software/pycmor

# Move Prefect home to local /tmp to avoid NFS SQLite locking issues
export PREFECT_HOME=/tmp/prefect_$$
mkdir -p $PREFECT_HOME
export TMPDIR=/tmp
export HDF5_USE_FILE_LOCKING=FALSE
export OMP_NUM_THREADS=1

# Use local Dask cluster since we're already on a compute node
sed 's/dask_cluster: "slurm"/dask_cluster: "local"/' \
    examples/cmip7_core_ocean_core2_test.yaml > $PYCMOR_SCRATCH/core_ocean_core2_test_local.yaml

pycmor process $PYCMOR_SCRATCH/core_ocean_core2_test_local.yaml
