#!/usr/bin/env bash
set -euo pipefail

: "${CASE_DIR:?set CASE_DIR to the absolute remote case directory}"
: "${INPUT_MPH:?set INPUT_MPH to the absolute input MPH path}"
: "${OUTPUT_MPH:?set OUTPUT_MPH to the absolute output MPH path}"

export LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}"
source "$HOME/yeesuan/envs/comsol64_env.sh"
comsol_bin="$HOME/yeesuan/apps/comsol64/multiphysics/bin/comsol"
batch_log="${BATCH_LOG:-$CASE_DIR/logs/comsol_batch.log}"

test -x "$comsol_bin"
test -s "$INPUT_MPH"
mkdir -p "$CASE_DIR/logs" "$CASE_DIR/results"
test ! -e "$OUTPUT_MPH" || {
  printf 'refusing to overwrite %s\n' "$OUTPUT_MPH" >&2
  exit 2
}

"$comsol_bin" batch \
  -inputfile "$INPUT_MPH" \
  -outputfile "$OUTPUT_MPH" \
  -batchlog "$batch_log"

test -s "$OUTPUT_MPH"
test -s "$batch_log"
