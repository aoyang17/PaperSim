#!/usr/bin/env bash
#SBATCH --job-name=comsol-case
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=32
#SBATCH --mem=64G
#SBATCH --time=02:00:00
#SBATCH --partition=REPLACE_AFTER_SINFO
#SBATCH --output=../logs/slurm-%j.out
#SBATCH --error=../logs/slurm-%j.err

set -euo pipefail

: "${PROJECT_ROOT:?submit with --export=ALL,PROJECT_ROOT=/absolute/project/path}"
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK}"
export CASE_DIR="$PROJECT_ROOT"
export INPUT_MPH="${INPUT_MPH:-$PROJECT_ROOT/input/model.mph}"
export OUTPUT_MPH="${OUTPUT_MPH:-$PROJECT_ROOT/results/model_solved.mph}"
export BATCH_LOG="${BATCH_LOG:-$PROJECT_ROOT/logs/comsol_batch_${SLURM_JOB_ID}.log}"

bash "$PROJECT_ROOT/slurm/comsol_batch.sh"
test -s "$OUTPUT_MPH"
