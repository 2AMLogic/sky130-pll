#!/usr/bin/env bash
# Fixture tests for scripts/audit-headless.sh using fake uv/npm/node/python.
# Nothing is downloaded and nothing outside a mktemp dir is touched.
set -u
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
src="$here/../audit-headless.sh"
unset AUDIT_HEADLESS_ACTIVE AUDIT_HEADLESS_RECREATE

T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
fails=0; n=0
ok()  { n=$((n+1)); echo "ok $n - $1"; }
bad() { n=$((n+1)); fails=$((fails+1)); echo "not ok $n - $1"; }
expect() { # desc cond-exit
  if [ "$2" -eq 0 ]; then ok "$1"; else bad "$1"; fi
}

# System utilities the wrapper needs, symlinked so PATH can exclude real uv/npm.
sysbin="$T/sysbin"; mkdir "$sysbin"
for t in bash dirname mkdir rm cat git env sh ln chmod; do
  p="$(command -v "$t")" && ln -s "$p" "$sysbin/$t"
done

fakebin="$T/fakebin"; mkdir "$fakebin"
cat > "$fakebin/node" <<'X'
#!/bin/sh
echo v0.0-fake
X
cat > "$fakebin/npm" <<'X'
#!/bin/sh
[ "$1" = "--version" ] && { echo 0.0-fake; exit 0; }
echo "npm $* cwd=$PWD python=$(command -v python3) klt=$(command -v klt)" >> "$FAKE_LOG"
exit "${FAKE_NPM_RC:-0}"
X
cat > "$fakebin/uv" <<'X'
#!/bin/sh
case "$1" in
  --version) echo "uv 0.0-fake";;
  venv)
    echo "uv $*" >> "$FAKE_LOG"
    [ -n "${FAKE_UV_FAIL:-}" ] && exit 9
    d="$4"; mkdir -p "$d/bin"
    echo "${FAKE_PYVER:-3.11.9}" > "$d/pyver"
    cat > "$d/bin/python" <<'P'
#!/bin/sh
d="$(dirname "$0")/.."
case "$2" in
  *version_info*) cat "$d/pyver";;
  *metadata*) cat "$d/kltver";;
esac
P
    printf '#!/bin/sh\necho klt\n' > "$d/bin/klt"
    ln -s python "$d/bin/python3"
    chmod +x "$d/bin/python" "$d/bin/klt";;
  pip)
    echo "uv $*" >> "$FAKE_LOG"
    [ -n "${FAKE_PIP_FAIL:-}" ] && exit 8
    d="$(dirname "$(dirname "$4")")"
    echo "${FAKE_KLTVER:-0.7.0}" > "$d/kltver";;
esac
X
chmod +x "$fakebin"/*

# Fake repository: wrapper copied in, so its repo root is the fake one.
repo="$T/fake repo"; mkdir -p "$repo/scripts" "$repo/signoff"
cp "$src" "$repo/scripts/audit-headless.sh"
cat > "$repo/signoff/run-signoff.sh" <<'X'
#!/usr/bin/env bash
echo "signoff $* cwd=$PWD python=$(command -v python3) klt=$(command -v klt)" >> "$FAKE_LOG"
exit "${FAKE_SIGNOFF_RC:-0}"
X
export FAKE_LOG="$T/log"
cache="$T/cache dir with spaces"
run() { : > "$FAKE_LOG"; ( cd "$T" && PATH="$fakebin:$sysbin" AUDIT_HEADLESS_CACHE="$cache" "$@" bash "$repo/scripts/audit-headless.sh" ) > "$T/out" 2>&1; }

# 1. happy path from outside the repo, cache path with spaces
rm -rf "$cache"; run env
rc=$?
expect "happy path exits 0" $rc
grep -q "npm run check:ci cwd=$repo python=$cache/venv-py3.11-klt0.7.0/bin/python3 klt=$cache/venv-py3.11-klt0.7.0/bin/klt" "$FAKE_LOG"
expect "npm check runs from repo root with env python/klt first on PATH" $?
grep -q "signoff --check cwd=$repo python=$cache/.*bin/python3" "$FAKE_LOG"
expect "signoff check runs after, from repo root, with env on PATH" $?
grep -q "^commit:" "$T/out" && grep -q "python:  *3.11.9" "$T/out" && grep -q "klayout-tools:  *0.7.0" "$T/out"
expect "summary records commit and tool versions" $?

# 2. reuse
run env; rc=$?
expect "second run exits 0" $rc
! grep -q "^uv " "$FAKE_LOG"; expect "second run does not re-provision" $?
grep -q "reusing" "$T/out"; expect "second run says it reused the env" $?

# 3. incompatible env
echo 3.12.1 > "$cache/venv-py3.11-klt0.7.0/pyver"
run env; rc=$?
[ $rc -eq 1 ]; expect "incompatible env stops with exit 1" $?
grep -q "incompatible" "$T/out" && ! grep -q "^npm " "$FAKE_LOG"; expect "incompatible env is reported and no check runs" $?
run env AUDIT_HEADLESS_RECREATE=1; rc=$?
expect "RECREATE=1 rebuilds and passes" $rc
grep -q "^uv venv" "$FAKE_LOG"; expect "RECREATE=1 re-provisions" $?

# 4. missing prerequisite
mv "$fakebin/uv" "$T/uv.off"; run env; rc=$?
[ $rc -eq 2 ] && grep -q "missing prerequisite 'uv'" "$T/out"; expect "missing uv -> exit 2 with message" $?
mv "$T/uv.off" "$fakebin/uv"
mv "$fakebin/npm" "$T/npm.off"; run env; rc=$?
[ $rc -eq 2 ] && grep -q "missing prerequisite 'npm'" "$T/out"; expect "missing npm -> exit 2 with message" $?
mv "$T/npm.off" "$fakebin/npm"

# 5. provisioning failure
rm -rf "$cache"; run env FAKE_UV_FAIL=1; rc=$?
[ $rc -eq 3 ] && ! grep -q "^npm " "$FAKE_LOG"; expect "uv venv failure -> exit 3, no checks" $?
rm -rf "$cache"; run env FAKE_PIP_FAIL=1; rc=$?
[ $rc -eq 3 ] && [ ! -e "$cache/venv-py3.11-klt0.7.0" ]; expect "install failure -> exit 3, partial env removed" $?

# 6. check failures
rm -rf "$cache"; run env FAKE_NPM_RC=7; rc=$?
[ $rc -ne 0 ] && ! grep -q "^signoff " "$FAKE_LOG" && grep -q "skipped" "$T/out"; expect "first-check failure fails and skips signoff" $?
run env FAKE_SIGNOFF_RC=5; rc=$?
[ $rc -ne 0 ] && grep -q "^signoff " "$FAKE_LOG" && grep -q "exit 5" "$T/out"; expect "signoff failure propagates nonzero" $?

# 7. recursion guard
run env AUDIT_HEADLESS_ACTIVE=1; rc=$?
[ $rc -eq 4 ]; expect "recursive invocation refused" $?

# 8. default path never touches PDK/sim flags
! grep -Eq "require-pdk|ngspice|volare" "$FAKE_LOG"; expect "no PDK/simulation commands invoked" $?

echo "1..$n"; [ $fails -eq 0 ]
