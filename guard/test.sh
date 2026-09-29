#!/usr/bin/env bash
set -u -o pipefail

top=$(git rev-parse --show-toplevel 2>/dev/null) || { echo "guard test: run this inside the project's repository" >&2; exit 1; }
src="$top/doctrine/guard"
plugin=$(cd "$(dirname "$0")/.." && pwd)
pass=0
fail=0

for fixture in "$src"/fixtures/*.json; do
  [ -f "$fixture" ] || continue
  name=$(basename "$fixture" .json)
  case $name in
    refuse-*) want=2 ;;
    allow-*) want=0 ;;
    *) fail=$((fail + 1)); echo "FAIL  $name: a fixture name starts with refuse- or allow-"; continue ;;
  esac
  reason=$(tr -d '\r' < "$fixture" | bash "$src/claude-hook.sh" 2>&1 >/dev/null)
  got=$?
  if [ "$got" = "$want" ]; then
    pass=$((pass + 1)); echo "ok    $name (exit $got)"
  else
    fail=$((fail + 1)); echo "FAIL  $name (expected exit $want, got $got) ${reason}"
  fi
done

if [ -f "$src/test-githooks.sh" ]; then
  if GUARD_PLUGIN="$plugin" bash "$src/test-githooks.sh"; then
    pass=$((pass + 1)); echo "ok    test-githooks.sh"
  else
    fail=$((fail + 1)); echo "FAIL  test-githooks.sh"
  fi
fi

echo "guard test: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
