#!/usr/bin/env bash
set -euo pipefail

top=$(git rev-parse --show-toplevel 2>/dev/null) || { echo "guard install: run this inside the project's repository" >&2; exit 1; }
src="$top/doctrine/guard"
name=$(basename "$top")
dest="${DOCTRINE_GUARD_HOME:-$HOME/.doctrine-guard}/$name"

[ -f "$src/claude-hook.sh" ] || { echo "guard install: $src/claude-hook.sh is missing" >&2; exit 1; }

rm -rf "$dest"
mkdir -p "$dest/project" "$dest/githooks"
( cd "$src" && find . -type f ! -path './fixtures/*' ) | while IFS= read -r file; do
  mkdir -p "$dest/project/$(dirname "$file")"
  tr -d '\r' < "$src/$file" > "$dest/project/$file"
done

if [ -d "$src/githooks" ]; then
  for hook in "$src"/githooks/*; do
    [ -f "$hook" ] || continue
    hookname=$(basename "$hook")
    if [ "$hookname" = "pre-push" ]; then
      cat > "$dest/githooks/$hookname" <<EOF
#!/bin/sh
input=\$(cat)
printf '%s\n' "\$input" | sh "$dest/project/githooks/$hookname" "\$@" || exit 1
top=\$(git rev-parse --show-toplevel)
if [ -f "\$top/.githooks/$hookname" ]; then
  printf '%s\n' "\$input" | sh "\$top/.githooks/$hookname" "\$@" || exit 1
fi
exit 0
EOF
    else
      cat > "$dest/githooks/$hookname" <<EOF
#!/bin/sh
sh "$dest/project/githooks/$hookname" "\$@" || exit 1
top=\$(git rev-parse --show-toplevel)
if [ -f "\$top/.githooks/$hookname" ]; then
  sh "\$top/.githooks/$hookname" "\$@" || exit 1
fi
exit 0
EOF
    fi
    chmod +x "$dest/githooks/$hookname"
  done
fi
echo "guard install: copied to $dest"

hooks="$dest/githooks"
if command -v cygpath >/dev/null 2>&1; then hooks=$(cygpath -m "$hooks"); fi
git -C "$top" config core.hooksPath "$hooks"
echo "guard install: core.hooksPath is $(git -C "$top" config --get core.hooksPath)"

matcher="Bash|PowerShell|Edit|Write|NotebookEdit"
if [ -f "$src/matcher" ]; then matcher=$(tr -d '\r\n' < "$src/matcher"); fi
hookpath="$dest/project/claude-hook.sh"
if command -v cygpath >/dev/null 2>&1; then hookpath=$(cygpath -m "$hookpath"); fi

python - "$top/.claude/settings.local.json" "$matcher" "$hookpath" <<'PY'
import json
import sys
from pathlib import Path

path, matcher, hook = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
command = (
    f"bash -c 'h=\"{hook}\"; [ -f \"$h\" ] || {{ echo \"doctrine guard missing: $h\" >&2; exit 2; }}; "
    f"bash \"$h\"; rc=$?; [ $rc -eq 0 ] && exit 0; exit 2'"
)
settings = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
entries = settings.setdefault("hooks", {}).setdefault("PreToolUse", [])
entries[:] = [
    e for e in entries
    if not any(hook in h.get("command", "") or ".doctrine-guard" in h.get("command", "") for h in e.get("hooks", []))
]
entries.append({"matcher": matcher, "hooks": [{"type": "command", "command": command, "timeout": 15}]})
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
print(f"guard install: {path} registers the hook for {matcher}")
PY

if ! git -C "$top" check-ignore -q .claude/settings.local.json; then
  echo "guard install: warning: .claude/settings.local.json is not ignored in $top; it must never be committed" >&2
fi
echo "guard install: done"
