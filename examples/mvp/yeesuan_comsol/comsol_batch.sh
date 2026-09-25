#!/usr/bin/env bash
set -euo pipefail

: "${COMSOL_ENV_SCRIPT:?set COMSOL_ENV_SCRIPT to the user's environment script}"
: "${COMSOL_BIN:?set COMSOL_BIN to the user's COMSOL executable}"
: "${CASE_DIR:?set CASE_DIR to the absolute remote case directory}"
: "${INPUT_MPH:?set INPUT_MPH to the absolute input MPH path}"
: "${OUTPUT_MPH:?set OUTPUT_MPH to the absolute output MPH path}"

export LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}"
source "$COMSOL_ENV_SCRIPT"
batch_log="${BATCH_LOG:-$CASE_DIR/logs/comsol_batch.log}"

test -x "$COMSOL_BIN"
test -s "$INPUT_MPH"
mkdir -p "$CASE_DIR/logs" "$CASE_DIR/results"
test ! -e "$OUTPUT_MPH" || {
  printf 'refusing to overwrite %s\n' "$OUTPUT_MPH" >&2
  exit 2
}

"$COMSOL_BIN" batch \
  -inputfile "$INPUT_MPH" \
  -outputfile "$OUTPUT_MPH" \
  -batchlog "$batch_log"

test -s "$OUTPUT_MPH"
test -s "$batch_log"
