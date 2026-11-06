"""Resolve conflict blocks in a file: resolve.py FILE CHOICE [CHOICE...]
CHOICE per block in order: o (ours), t (theirs), n (none), ot / to (both, in that order),
or @path (replace block with that file's content). Handles diff3 (|||||||) markers too."""
import sys, re
from pathlib import Path
path = Path(sys.argv[1]); choices = sys.argv[2:]
lines = path.read_text().splitlines(keepends=True)
out, i, k = [], 0, 0
while i < len(lines):
    if lines[i].startswith("<<<<<<< "):
        ours, base, theirs, cur = [], [], [], "o"
        i += 1
        while not lines[i].startswith(">>>>>>> "):
            if lines[i].startswith("||||||| "): cur = "b"
            elif lines[i].startswith("======="): cur = "t"
            else: {"o": ours, "b": base, "t": theirs}[cur].append(lines[i])
            i += 1
        c = choices[k]; k += 1
        if c.startswith("@"): out.append(Path(c[1:]).read_text())
        else:
            for ch in c:
                if ch == "o": out += ours
                elif ch == "t": out += theirs
                elif ch == "n": pass
        i += 1; continue
    out.append(lines[i]); i += 1
assert k == len(choices), f"{k} blocks, {len(choices)} choices"
path.write_text("".join(out)); print(f"{path}: {k} blocks resolved")
