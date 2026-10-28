#!/bin/bash
# Telemac calculator script for fz
#
# Runs a Telemac module (telemac2d by default) on the steering file (.cas) given
# by fz, then extracts the results at the points of interest of the *.poi files
# into CSV files (telemac_poi.py, next to this script), read by the fz model.
#
# Telemac is taken, in this order, from:
#   1. TELEMAC_CMD, e.g. "telemac2d.py" or "/opt/telemac/scripts/python3/telemac2d.py"
#      (TELEMAC_PROFILE, if set, is sourced first: e.g. a pysource/telemac.profile file);
#   2. $TELEMAC_MODULE.py on PATH (local installation);
#   3. a container image TELEMAC_IMAGE (default irsn/telemac-mascaret:latest) run with
#      TELEMAC_CONTAINER (docker, podman, apptainer or singularity; default: the
#      first one available, in this order).
#
# Environment (all optional):
#   TELEMAC_MODULE       telemac2d (default), or another module with a 2D result file
#   TELEMAC_NCSIZE       number of MPI processes (default: number of CPUs; reduce it
#                        when fz runs several cases in parallel)
#   TELEMAC_OPTS         extra options of the Telemac launcher (e.g. "-c <config>")
#   TELEMAC_CONTAINER_OPTS  extra options of "docker/podman run" or "apptainer run"
#   TELEMAC_POI_METHOD   linear (default: interpolation in the mesh triangle) or nearest
#   TELEMAC_PYTHON       python with numpy for the POI extraction (default: python3, python)
#
# Input: a case directory, or the case files; the steering file is the *.cas
# file that sets a GEOMETRY FILE (FICHIER DE GEOMETRIE), else the first *.cas.
#
# Exit codes:
#   0 normal end ("My work is done")    1 no steering file      2 usage
#   3 non-ASCII working path (unsupported by Telemac)
#   4 Telemac not found (no TELEMAC_CMD, no local install, no container runtime)
#   5 Telemac failed (non-zero exit; the reason is in the listing, see out.txt/err.txt)
#   6 no result file after the run     7 POI extraction failed

if [ $# -eq 0 ]; then
  echo "Usage: $0 <case.cas ...|case_directory>" >&2
  exit 2
fi
if [ -d "$1" ]; then
  cd "$1" || exit 1
  set -- *
fi

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

CAS=""
for f in "$@"; do
  case "$f" in
    *.cas)
      [ -f "$f" ] || continue
      [ -z "$CAS" ] && CAS="$f"
      if grep -v '^[[:space:]]*/' "$f" | grep -q -i -E '(GEOMETRY FILE|FICHIER DE GEOMETRIE)[[:space:]]*[=:]'; then
        CAS="$f"; break
      fi ;;
  esac
done
if [ -z "$CAS" ]; then
  echo "No Telemac steering file (*.cas) found in: $*" >&2
  exit 1
fi

if pwd -P | LC_ALL=C grep -q '[^ -~]'; then
  echo "Telemac does not support non-ASCII characters in the working path: $(pwd -P)" >&2
  exit 3
fi

MODULE="${TELEMAC_MODULE:-telemac2d}"
NCSIZE="${TELEMAC_NCSIZE:-$(nproc 2>/dev/null || getconf _NPROCESSORS_ONLN 2>/dev/null || echo 1)}"
IMAGE="${TELEMAC_IMAGE:-irsn/telemac-mascaret:latest}"
# shellcheck disable=SC2206
OPTS=(${TELEMAC_OPTS:-})
# shellcheck disable=SC2206
COPTS=(${TELEMAC_CONTAINER_OPTS:-})

if [ -n "${TELEMAC_PROFILE:-}" ]; then
  # shellcheck disable=SC1090
  . "$TELEMAC_PROFILE" || { echo "Cannot source TELEMAC_PROFILE=$TELEMAC_PROFILE" >&2; exit 4; }
fi

if [ -n "${TELEMAC_CMD:-}" ]; then
  # shellcheck disable=SC2206
  CMD=($TELEMAC_CMD)
  command -v "${CMD[0]}" >/dev/null 2>&1 || { echo "Telemac launcher not found: TELEMAC_CMD=$TELEMAC_CMD" >&2; exit 4; }
  RUN=("${CMD[@]}" --ncsize="$NCSIZE" "${OPTS[@]}" "$CAS")
elif command -v "$MODULE.py" >/dev/null 2>&1; then
  RUN=("$MODULE.py" --ncsize="$NCSIZE" "${OPTS[@]}" "$CAS")
else
  CONTAINER="${TELEMAC_CONTAINER:-}"
  if [ -z "$CONTAINER" ]; then
    for c in docker podman apptainer singularity; do
      command -v "$c" >/dev/null 2>&1 && { CONTAINER="$c"; break; }
    done
  fi
  if [ -z "$CONTAINER" ] || ! command -v "$CONTAINER" >/dev/null 2>&1; then
    echo "Telemac not found: set TELEMAC_CMD, put $MODULE.py on PATH, or install docker/podman/apptainer${CONTAINER:+ ($CONTAINER not found)}" >&2
    exit 4
  fi
  case "$CONTAINER" in
    docker|podman)
      [ "$CONTAINER" = podman ] && COPTS=(--ipc=host "${COPTS[@]}")
      case "$IMAGE" in */*/*) ;; *) [ "$CONTAINER" = podman ] && IMAGE="docker.io/$IMAGE" ;; esac
      RUN=("$CONTAINER" run --rm -e I_MPI_HYDRA_BOOTSTRAP=fork -e I_MPI_ROOT_GTOOL_BYPASS=1 \
           -v "$PWD":/workdir -w /workdir "${COPTS[@]}" "$IMAGE" \
           "$MODULE.py" --ncsize="$NCSIZE" "${OPTS[@]}" "$CAS") ;;
    apptainer|singularity)
      case "$IMAGE" in *://*|/*|./*|*.sif) ;; *) IMAGE="docker://$IMAGE" ;; esac
      RUN=("$CONTAINER" run -B "$PWD":/workdir -H /workdir "${COPTS[@]}" "$IMAGE" \
           "$MODULE.py" --ncsize="$NCSIZE" "${OPTS[@]}" "$CAS") ;;
    *)
      echo "Unsupported TELEMAC_CONTAINER=$CONTAINER (docker, podman, apptainer or singularity)" >&2
      exit 4 ;;
  esac
fi

echo "fz-Telemac: ${RUN[*]}"
"${RUN[@]}" &
PID=$!
echo $PID >> PID
trap 'kill $PID 2>/dev/null' INT TERM
wait $PID
RC=$?
rm -f PID
if [ $RC -ne 0 ]; then
  echo "Telemac failed (exit code $RC): see the listing in out.txt/err.txt" >&2
  exit 5
fi

POIS=()
for f in *.poi; do [ -f "$f" ] && POIS+=("$f"); done

PY="${TELEMAC_PYTHON:-}"
if [ -z "$PY" ]; then
  for p in python3 python; do
    "$p" -c 'import numpy' >/dev/null 2>&1 && { PY="$p"; break; }
  done
fi
if [ -z "$PY" ] || [ ! -f "$HERE/telemac_poi.py" ]; then
  if [ ${#POIS[@]} -gt 0 ]; then
    echo "Cannot extract POI: ${PY:-no python with numpy}, $HERE/telemac_poi.py" >&2
    exit 7
  fi
  exit 0
fi

if [ ${#POIS[@]} -eq 0 ]; then
  # no POI: only check that the result file was written
  RES="$("$PY" -c 'import sys; sys.path.insert(0, sys.argv[1]); import telemac_poi as t; print(t.cas_value(sys.argv[2], t.RESULTS_KEYWORDS) or "")' "$HERE" "$CAS")"
  if [ -n "$RES" ] && [ ! -f "$RES" ]; then
    echo "No result file $RES after the Telemac run" >&2
    exit 6
  fi
  exit 0
fi

"$PY" "$HERE/telemac_poi.py" -c "$CAS" -m "${TELEMAC_POI_METHOD:-linear}" "${POIS[@]}"
case $? in
  0) exit 0 ;;
  2) exit 6 ;;
  *) exit 7 ;;
esac
