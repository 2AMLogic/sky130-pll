#!/usr/bin/env bash
# Opt-in headless audit bootstrap: provision Python 3.11 + klayout-tools
# 0.7.0 in a dedicated virtual environment outside the checkout, then run the
# two PDK-free repository checks CI runs, in order:
#
#   1. npm run check:ci
#   2. bash signoff/run-signoff.sh --check
#
# Usage:   bash scripts/audit-headless.sh        (from any directory)
#
# Prerequisites (never installed by this script): bash, node, npm, uv.
# Install uv per https://docs.astral.sh/uv/ -- no sudo or system package
# manager is used or required here.
#
# Environment (all optional):
#   AUDIT_HEADLESS_CACHE     parent directory for the audit venv
#                            (default: ${XDG_CACHE_HOME:-$HOME/.cache}/sky130-pll-audit-headless)
#   AUDIT_HEADLESS_RECREATE  1 = delete and rebuild an incompatible existing venv
#                            (default: stop and explain)
#
# This is the default PDK-free path only: no simulation, no PDK install, no
# --require-pdk, no heavy validation, no signoff regeneration. The klt pin
# below is for the audit environment only; signoff/run-signoff.sh keeps its
# own KLT_PIN and layout/requirements.txt is deliberately not used.
#
# Exit codes: 0 both checks passed; 1 a check failed (or the environment is
# incompatible); 2 missing prerequisite; 3 provisioning failure; 4 recursion.

set -uo pipefail

PY_VERSION="3.11"
KLT_VERSION="0.7.0"

die() { local code=$1; shift; echo "audit-headless: $*" >&2; exit "$code"; }

if [ -n "${AUDIT_HEADLESS_ACTIVE:-}" ]; then
  die 4 "refusing recursive invocation (called from inside an audit run)"
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)" || die 1 "cannot resolve script directory"
repo_root="$(cd "$script_dir/.." && pwd)" || die 1 "cannot resolve repository root"

for tool in bash node npm uv; do
  command -v "$tool" >/dev/null 2>&1 || die 2 "missing prerequisite '$tool'. Install it first (uv: https://docs.astral.sh/uv/getting-started/installation/); this script does not install host tools."
done

cache_parent="${AUDIT_HEADLESS_CACHE:-${XDG_CACHE_HOME:-$HOME/.cache}/sky130-pll-audit-headless}"
venv="$cache_parent/venv-py${PY_VERSION}-klt${KLT_VERSION}"
case "$venv" in
  "$repo_root"|"$repo_root"/*) die 1 "audit environment must live outside the checkout (got: $venv)";;
esac

py_actual() { "$venv/bin/python" -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])' 2>/dev/null; }
klt_actual() { "$venv/bin/python" -c 'import importlib.metadata as m; print(m.version("klayout-tools"))' 2>/dev/null; }

env_state() {  # prints: ok | absent | incompatible
  [ -e "$venv" ] || { echo absent; return; }
  local p k
  p="$(py_actual)" || { echo incompatible; return; }
  k="$(klt_actual)" || { echo incompatible; return; }
  case "$p" in "$PY_VERSION".*) ;; *) echo incompatible; return;; esac
  [ "$k" = "$KLT_VERSION" ] && [ -x "$venv/bin/klt" ] && echo ok || echo incompatible
}

state="$(env_state)"
if [ "$state" = incompatible ]; then
  if [ "${AUDIT_HEADLESS_RECREATE:-0}" = 1 ]; then
    echo "audit-headless: rebuilding incompatible environment: $venv" >&2
    rm -rf -- "$venv" || die 3 "cannot remove $venv"
    state=absent
  else
    die 1 "existing environment is incompatible (want python ${PY_VERSION}.x + klayout-tools ${KLT_VERSION}; have python '$(py_actual)' klayout-tools '$(klt_actual)'): $venv
Re-run with AUDIT_HEADLESS_RECREATE=1 to rebuild it, or remove that directory."
  fi
fi

if [ "$state" = absent ]; then
  echo "audit-headless: provisioning $venv" >&2
  mkdir -p -- "$cache_parent" || die 3 "cannot create $cache_parent"
  uv venv --python "$PY_VERSION" "$venv" \
    || die 3 "uv could not create a Python ${PY_VERSION} environment (network or interpreter download failure?)"
  uv pip install --python "$venv/bin/python" "klayout-tools==${KLT_VERSION}" \
    || { rm -rf -- "$venv"; die 3 "uv could not install klayout-tools==${KLT_VERSION} (network failure?)"; }
  [ "$(env_state)" = ok ] || die 3 "environment failed verification after provisioning: $venv"
else
  echo "audit-headless: reusing compatible environment: $venv" >&2
fi

export AUDIT_HEADLESS_ACTIVE=1
export PATH="$venv/bin:$PATH"
cd "$repo_root" || die 1 "cannot cd to $repo_root"

commit="$(git rev-parse HEAD 2>/dev/null || echo unknown)"
status_ci="not-run"; status_signoff="not-run"

report() {
  echo "---- audit-headless summary ----"
  echo "commit:            $commit"
  echo "python:            $(py_actual)"
  echo "klayout-tools:     $(klt_actual)"
  echo "node:              $(node --version 2>&1)"
  echo "npm:               $(npm --version 2>&1)"
  echo "uv:                $(uv --version 2>&1)"
  echo "environment:       $venv"
  echo "npm run check:ci:                          $status_ci"
  echo "bash signoff/run-signoff.sh --check:       $status_signoff"
  echo "Note: provisioning success alone does not show the audited revision passes."
}

npm run check:ci
rc=$?
status_ci="exit $rc"
if [ "$rc" -ne 0 ]; then
  status_signoff="skipped (first check failed)"
  report
  echo "audit-headless: FAILED: npm run check:ci exited $rc" >&2
  exit 1
fi

bash signoff/run-signoff.sh --check
rc=$?
status_signoff="exit $rc"
report
if [ "$rc" -ne 0 ]; then
  echo "audit-headless: FAILED: signoff --check exited $rc" >&2
  exit 1
fi
echo "audit-headless: both checks passed"
