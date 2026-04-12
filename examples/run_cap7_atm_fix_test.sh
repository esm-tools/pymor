#!/bin/bash
#SBATCH --job-name=pycmor-fix-test
#SBATCH --partition=compute
#SBATCH --account=ba0989
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
#SBATCH --time=00:30:00
#SBATCH --output=pycmor_cap7_atm_fix_test_%j.log
#SBATCH --error=pycmor_cap7_atm_fix_test_%j.log

source ~/loadconda.sh
conda activate pycmor_py312

cd /work/ab0246/a270092/software/pycmor

export HDF5_USE_FILE_LOCKING=FALSE
export OMP_NUM_THREADS=1

pycmor process examples/cmip7_cap7_atm_fix_test.yaml
