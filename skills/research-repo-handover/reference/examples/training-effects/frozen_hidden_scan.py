"""Old vocabulary in the parts of frozen files nobody downstream reads: YAML comments in task sets
and training setups, comments/docstrings in vendored Python, JSON provenance, READMEs."""
import ast, io, re, subprocess, sys, tokenize, collections
root = sys.argv[1]
files = subprocess.run(["git", "-C", root, "ls-files"], capture_output=True, text=True).stdout.split()
pat = re.compile(r"\bD[0-9]{2,3}\b|D20[0-9]{2}-[0-9]{2}-[0-9]{2}_|(?<![\w/])#[0-9]{2,4}\b|\bbatter(y|ies)\b|\bsidecars?\b|\boracle\b|\bE[1-6]\b|CLAUDE\.md|invariant [0-9]|\bdocs/|\bscripts/|\barchive/|external/|\bjrb\b|Jason|Titus|\bviewer\b|Quiver|propensity[_-]prediction|\bpp[_-]|PP_|lint_docs|log\.md|decisions\.md|\bceiling\b", re.I)
out = collections.defaultdict(list)
for f in files:
    p = f"{root}/{f}"
    if re.match(r"benchmarks/.*\.ya?ml$|configs/.*\.ya?ml$", f):
        for i, line in enumerate(open(p, encoding="utf-8"), 1):
            if "#" in line:
                comment = line[line.index("#"):]
                if pat.search(comment): out[f].append(f"{i}: {line.strip()[:140]}")
    elif f.startswith("src/training_effects/training/_vendor/") and f.endswith(".py"):
        src = open(p, encoding="utf-8").read()
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type in (tokenize.COMMENT, tokenize.STRING) and pat.search(tok.string):
                for m in pat.finditer(tok.string):
                    out[f].append(f"{tok.start[0]}: ...{tok.string[max(0,m.start()-50):m.end()+40]!r}")
    elif f.endswith((".json", ".md")) and (f.startswith("src/training_effects/training/_vendor/") or f.startswith("benchmarks/shared/") and not f.startswith("benchmarks/shared/reading/") or f.startswith("benchmarks/shared/reading/index")):
        for i, line in enumerate(open(p, encoding="utf-8"), 1):
            if pat.search(line): out[f].append(f"{i}: {line.strip()[:160]}")
    elif f.startswith("benchmarks/shared/reading/index"):
        pass
n = 0
for f, ls in sorted(out.items()):
    print(f"== {f} ({len(ls)})"); n += len(ls)
    for l in ls[:4]: print("   ", l)
print(n, "hits in", len(out), "files")
