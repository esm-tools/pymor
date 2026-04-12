#!/bin/bash
#SBATCH --job-name=pycmor-basin-test
#SBATCH --partition=compute
#SBATCH --account=ba0989
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=32G
#SBATCH --time=08:00:00
#SBATCH --output=pycmor_basin_core2_test_%j.log
#SBATCH --error=pycmor_basin_core2_test_%j.log

source ~/loadconda.sh
conda activate pycmor_py312

cd /work/ab0246/a270092/software/pycmor

export HDF5_USE_FILE_LOCKING=FALSE
export OMP_NUM_THREADS=1

pycmor process examples/cmip7_basin_core2_test.yaml
