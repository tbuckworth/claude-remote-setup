"""Delete `_COMMANDS` entries in cli.py whose command module is absent; drop groups left empty.

Usage: python3 trim_cli.py REPO. Pure deletion of the entries' exact source lines (via ast).
"""

import ast
import sys
from pathlib import Path

repo = Path(sys.argv[1])
cli = repo / "src/propensity_prediction/cli.py"
text = cli.read_text()
lines = text.split("\n")
tree = ast.parse(text)
assign = next(n for n in tree.body if isinstance(n, ast.Assign) and n.targets[0].id == "_COMMANDS")
drop: set[int] = set()
removed = []
for gkey, gval in zip(assign.value.keys, assign.value.values, strict=True):
    kept_any = False
    for ckey, cval in zip(gval.keys, gval.values, strict=True):
        owner, module = cval.elts[0].value, cval.elts[1].value
        path = repo / f"src/propensity_prediction/{owner}/commands/{module}.py"
        if path.is_file():
            kept_any = True
            continue
        removed.append(f"{gkey.value} {ckey.value}")
        drop.update(range(ckey.lineno - 1, cval.end_lineno))
    if not kept_any:
        removed.append(f"[group] {gkey.value}")
        drop.update(range(gkey.lineno - 1, gval.end_lineno))
cli.write_text("\n".join(line for i, line in enumerate(lines) if i not in drop))
print("removed:", ", ".join(removed))
