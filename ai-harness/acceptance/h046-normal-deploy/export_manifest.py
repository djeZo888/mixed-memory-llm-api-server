#!/usr/bin/env python3
"""Export sealed local bytes only. This tool never grants live qualification or GO.

Run after the final source commit and local builds. Archives contain regular files
rooted at ai-harness/, with no dependencies, credentials or retained runtime state.
The release directory is a proposed immutable Linux path, not a path to mutate.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import tarfile


PROFILES = ("ordinary", "technical", "generation", "technical-generation")
IMPORT = re.compile(r'''(?:from\s*|import\s*\()?['"](\.\.?/[^'"]+\.js)['"]''')
FORBIDDEN_PARTS = {"node_modules", ".git", ".cache", "__pycache__", "secrets",
                   "credentials", "histories", "history", "logs", "uploads",
                   "artifacts", "downloads", "codex-home", "workspaces"}
FORBIDDEN_SUFFIXES = {".key", ".pem", ".p12", ".pfx", ".sqlite", ".sqlite3",
                      ".db", ".log", ".jsonl", ".bin", ".so", ".dylib"}


class Refused(ValueError):
    pass


def require(value, reason):
    if not value:
        raise Refused(reason)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sha(value):
    return hashlib.sha256(value).hexdigest()


def git(repo, *args):
    p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=False)
    require(p.returncode == 0, "git failed: " + p.stderr.decode(errors="replace"))
    return p.stdout


def safe_relative(value):
    p = PurePosixPath(value)
    require(not p.is_absolute() and str(p) == value and p.parts[0] == "ai-harness"
            and not any(x in (".", "..", "") for x in p.parts), "Unsafe archive/source path")
    require(not any(x.lower() in FORBIDDEN_PARTS for x in p.parts), "Runtime/dependency path forbidden")
    require(p.suffix.lower() not in FORBIDDEN_SUFFIXES and not p.name.startswith(".env")
            and p.name not in ("auth.json", "id_ed25519"), "Private/binary/log file forbidden")
    return p


def read_regular(path):
    p = Path(path)
    require(p.is_absolute() and p.resolve() == p, "Moving local source alias")
    before = p.lstat()
    require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1,
            "Only single-link regular source/build files may be exported")
    with p.open("rb") as f:
        raw = f.read()
    after = p.lstat()
    identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    require(identity(before) == identity(after) and len(raw) == before.st_size,
            "Source/build bytes changed during read")
    return raw


def sealed_source(repo, expected=None):
    repo = Path(repo).resolve()
    commit = git(repo, "rev-parse", "HEAD").decode().strip()
    require(re.fullmatch(r"[a-f0-9]{40}", commit) and (expected is None or expected == commit),
            "Final sourceCommit must equal actual HEAD")
    require(not git(repo, "status", "--porcelain=v1", "--untracked-files=all"),
            "Seal all source edits/untracked files before export; HEAD must be clean")
    files, modes = {}, {}
    for entry in git(repo, "ls-files", "--stage", "-z", "--", "ai-harness").split(b"\0"):
        if not entry:
            continue
        meta, name = entry.decode().split("\t", 1)
        mode, blob, stage = meta.split()
        require(stage == "0" and mode in ("100644", "100755"), "Unmerged/symlink source forbidden")
        safe_relative(name)
        raw = read_regular(repo / name)
        require(raw == git(repo, "cat-file", "blob", blob), "Tracked bytes differ from sealed commit")
        files[name] = raw
        modes[name] = 0o755 if mode == "100755" else 0o644
    require(files, "No sealed ai-harness source")
    return commit, files, modes


def compiled_files(repo):
    files = {}
    for relative in ("ai-harness/server/dist", "ai-harness/web/dist"):
        root = repo / relative
        require(root.is_dir() and root.resolve() == root, "Missing canonical local build directory")
        for p in sorted(root.rglob("*")):
            require(not p.is_symlink(), "Symlink inside build forbidden")
            if p.is_dir():
                continue
            name = p.relative_to(repo).as_posix()
            safe_relative(name)
            files[name] = read_regular(p)
    for entry in ("ai-harness/server/dist/main.js", "ai-harness/server/dist/codex-preview-main.js",
                  "ai-harness/web/dist/index.html"):
        require(entry in files and files[entry], "Missing final compiled entry")
    return files


def string_array(raw, symbol, spread=None):
    match = re.search(r"export const " + re.escape(symbol) + r"\s*=\s*\[([^\]]*)\]\s*as const", raw)
    require(match, "Missing authoritative source array " + symbol)
    body = match[1].strip()
    if spread:
        require(body.startswith("..." + spread + ","), "Unexpected receipt array spread")
        body = body[len(spread) + 4:].strip()
    require(re.fullmatch(r'''(?:['"][^'"]+['"]\s*,?\s*)+''', body), "Unsupported authoritative array syntax")
    values = re.findall(r'''['"]([^'"]+)['"]''', body)
    require(len(values) == len(set(values)), "Duplicate authoritative path")
    return values


def authoritative_graphs(source):
    vision = string_array(source["ai-harness/server/src/technical-vision-qualification.ts"].decode(),
                          "TECHNICAL_VISION_SOURCE_GRAPH")
    require(len(vision) == 18, "Vision exact18 graph schema changed")
    receipts = source["ai-harness/server/src/codex-receipts.ts"].decode()
    base = string_array(receipts, "CODEX_RECEIPT_SOURCES")
    technical = base + string_array(receipts, "CODEX_TECHNICAL_RECEIPT_SOURCES", "CODEX_RECEIPT_SOURCES")
    generation = base + string_array(receipts, "CODEX_GENERATION_RECEIPT_SOURCES", "CODEX_RECEIPT_SOURCES")
    require(len(base) == 8 and len(technical) == 10 and len(generation) == 12, "Receipt profile schema changed")
    specialist = source["ai-harness/server/src/codex-specialist-qualification.ts"].decode()
    match = re.search(r'''return kind==="frontier"\s*\?\s*(.*?)\s*:\s*(.*?);\s*\n}''', specialist, re.S)
    require(match, "Missing authoritative specialist source function")
    def specialist_paths(expr):
        modules = re.search(r'''\[\.\.\.\[([^\]]+)\]\.map\(name=>join\(server,name\+'\.js'\)\),''', expr)
        require(modules, "Unsupported specialist module graph syntax")
        names = re.findall(r"'([^']+)'", modules[1])
        tail = expr[modules.end():]
        paths = ["ai-harness/server/dist/" + n + ".js" for n in names]
        matches = list(re.finditer(r"(?:join|resolve)\(deploy,'([^']+)'\)", tail))
        require(re.sub(r"(?:join|resolve)\(deploy,'[^']+'\)", "", tail).strip(",] \n") == "",
                "Unsupported specialist deploy graph syntax")
        for m in matches:
            paths.append(os.path.normpath("ai-harness/deploy/" + m[1]))
        require(len(paths) == len(set(paths)), "Duplicate specialist graph path")
        return paths
    frontier = specialist_paths(match[1])
    generation_paths = specialist_paths(match[2])
    require(len(frontier) == 14 and len(generation_paths) == 30, "Specialist exact graph schema changed")
    return vision, {"ordinary": base, "technical": technical, "generation": generation,
                    "technical-generation": generation + [p for p in technical if p not in base]}, generation_paths, frontier


def absolute_map(files, release):
    return {str(release / name): sha(raw) for name, raw in sorted(files.items())}


def ordinary_files(all_files, profile_sources):
    required = set()
    def walk(name):
        if name in required:
            return
        require(name.startswith("ai-harness/server/"), "Ordinary executable import escapes server release")
        require(name in all_files, "Missing ordinary executable dependency: " + name)
        required.add(name)
        for match in IMPORT.finditer(all_files[name].decode()):
            dependency = os.path.normpath(str(PurePosixPath(name).parent / match[1]))
            walk(dependency)
    walk("ai-harness/server/dist/main.js")
    walk("ai-harness/server/dist/codex-preview-main.js")
    for name in list(required):
        required.add(name.replace("/dist/", "/src/")[:-3] + ".ts")
    required.add("ai-harness/server/package-lock.json")
    for name in profile_sources:
        required.add(os.path.normpath("ai-harness/deploy/" + name))
    required.add("ai-harness/deploy/engine/validate-image-overlays.py")
    require(8 <= len(required) <= 512, "Ordinary current graph exceeds loader bound")
    require(required.issubset(all_files), "Missing paired source/current helper in ordinary graph")
    return {name: all_files[name] for name in sorted(required)}


def release_path(value, commit):
    p = PurePosixPath(value)
    require(p.is_absolute() and str(p) == value and not any(x in (".", "..") for x in p.parts)
            and re.fullmatch(r"/[A-Za-z0-9_./-]+", value) and p.name.startswith(commit + "-"),
            "Release must be an absolute immutable path named by final sourceCommit")
    return p


def make_graphs(source, compiled, release, commit):
    all_files = {**source, **compiled}
    vision_names, profiles, generation, frontier = authoritative_graphs(source)
    def exact(paths):
        require(all(p in all_files for p in paths), "Missing required specialist build/helper")
        return {str(release / p): sha(all_files[p]) for p in paths}
    bindings = {n: sha(compiled["ai-harness/server/dist/" + n + ".js"]) for n in vision_names}
    vision = {"schema": "h046-technical-vision-source-export-v1", "sourceCommit": commit,
              "status": "SOURCE_ONLY_NOT_LIVE_QUALIFICATION", "orderedModules": vision_names,
              "sourceBindings": bindings,
              "sourceGraphSha256": sha(json.dumps(bindings, separators=(",", ":"), ensure_ascii=False).encode()),
              "files": exact(["ai-harness/server/dist/" + n + ".js" for n in vision_names])}
    ordinary = {}
    for profile, names in profiles.items():
        current = ordinary_files(all_files, names)
        receipts = {n: sha(all_files[os.path.normpath("ai-harness/deploy/" + n)]) for n in names}
        ordinary[profile] = {"files": absolute_map(current, release), "fileCount": len(current),
                             "receiptSources": receipts, "receiptSourcesSha256": sha(canonical(receipts))}
    return vision, {"sourceCommit": commit, "status": "SOURCE_ONLY_NOT_GLOBAL_GENERATION_APPROVAL",
                    "requiredCount": 30, "requiredSources": list(exact(generation)),
                    "sourceClosure": exact(generation)}, {
        "sourceCommit": commit, "status": "SOURCE_ONLY_NOT_CURRENT_FRONTIER_QUALIFICATION",
        "requiredSources": list(exact(frontier)), "sourceClosure": exact(frontier)}, {
        "schema": "h046-ordinary-current-source-graphs-v1", "sourceCommit": commit,
        "status": "UNSIGNED_SOURCE_GRAPHS_NOT_NATIVE_PASS", "serverDir": str(release / "ai-harness/server"),
        "deploymentDir": str(release / "ai-harness/deploy"), "profiles": ordinary}


def write_archive(output, files, modes):
    with output.open("xb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
            with tarfile.open(fileobj=zipped, mode="w", format=tarfile.PAX_FORMAT) as archive:
                for name, data in sorted(files.items()):
                    safe_relative(name)
                    info = tarfile.TarInfo(name)
                    info.mode, info.size, info.mtime = modes.get(name, 0o644), len(data), 0
                    info.uid = info.gid = 0
                    info.uname = info.gname = ""
                    archive.addfile(info, io.BytesIO(data))
    return {"path": output.name, "sha256": sha(read_regular(output)), "bytes": output.stat().st_size,
            "fileCount": len(files), "memberSha256": {n: sha(b) for n, b in sorted(files.items())}}


def export(repo, output, release_dir, expected=None, build_receipts=(), path_status="PROPOSED_ROOT_REVIEW_REQUIRED"):
    repo, output = Path(repo).resolve(), Path(output).absolute()
    require(output.resolve() == output and not output.exists() and not output.is_relative_to(repo),
            "Export output must be a new canonical directory outside source checkout")
    commit, source, modes = sealed_source(repo, expected)
    release = release_path(release_dir, commit)
    compiled = compiled_files(repo)
    vision, generation, frontier, ordinary = make_graphs(source, compiled, release, commit)
    receipt_map = {str(Path(p).resolve()): sha(read_regular(Path(p).resolve())) for p in build_receipts}
    source_map = {n: sha(b) for n, b in sorted(source.items())}
    compiled_map = {n: sha(b) for n, b in sorted(compiled.items())}
    helpers = {n: b for n, b in source.items() if n.startswith(("ai-harness/deploy/", "ai-harness/tools/",
                                                                "ai-harness/acceptance/h046-normal-deploy/"))}
    configs = {n: b for n, b in source.items() if n.endswith(("package.json", "package-lock.json", "tsconfig.json"))
               or n.startswith(("ai-harness/deploy/codex/", "ai-harness/deploy/security/", "ai-harness/deploy/systemd/"))}
    ui = {"sourceCommit": commit, "source": {n: d for n, d in source_map.items() if n.startswith("ai-harness/web/")},
          "dist": {n: d for n, d in compiled_map.items() if n.startswith("ai-harness/web/dist/")}}
    require(git(repo, "rev-parse", "HEAD").decode().strip() == commit
            and not git(repo, "status", "--porcelain=v1", "--untracked-files=all"),
            "Source changed before archive export")
    output.mkdir(mode=0o700, parents=False)
    graphs = {"VISION-18JS.json": vision, "GENERATION-30-SOURCES.json": generation,
              "CURRENT-FRONTIER-SOURCES.json": frontier, "ORDINARY-CURRENT-SOURCES.json": ordinary,
              "UI-SHA256.json": ui}
    for name, body in graphs.items():
        (output / name).write_text(json.dumps(body, indent=2, ensure_ascii=False) + "\n")
    metadata = {"ai-harness/source-commit.txt": (commit + "\n").encode()}
    archives = {"source": write_archive(output / "source.tar.gz", {**source, **metadata}, modes),
                "compiled": write_archive(output / "compiled.tar.gz", compiled, {}),
                "release": write_archive(output / "release.tar.gz", {**source, **compiled, **metadata}, modes)}
    manifest = {"schema": "h046-normal-deploy-release-manifest-v1", "sourceCommit": commit,
                "sourceTree": git(repo, "rev-parse", "HEAD^{tree}").decode().strip(),
                "status": "UNAPPROVED_SOURCE_AND_BUILD_EXPORT", "releasePathStatus": path_status,
                "releaseDir": str(release), "serverDir": str(release / "ai-harness/server"),
                "deploymentDir": str(release / "ai-harness/deploy"), "source": source_map,
                "compiled": compiled_map, "generatedMetadata": {n: sha(b) for n, b in metadata.items()},
                "releaseFiles": absolute_map({**source, **compiled, **metadata}, release),
                "config": absolute_map(configs, release), "startupAndHelpers": absolute_map(helpers, release),
                "ordinaryGraphExcludesUnimportedHelpers": True, "buildReceiptSha256": receipt_map,
                "archives": archives, "graphSha256": {n: sha(read_regular(output / n)) for n in graphs},
                "dependencyHandling": "NO_DEPENDENCIES_ARCHIVED_NO_INSTALL_OR_MUTATION; ROOT_VERIFY_EXISTING_IMMUTABLE_LINUX_DEPS",
                "nativeRuntime": {"version": "0.158.0", "upstream": "064c6b8c737f5b41d171fdda80bd9ef10ad06eb3",
                                  "context": 480000, "autoCompact": 400000, "output": 65536},
                "liveAcceptance": {k: "NOT_TESTED" for k in ("native", "UI", "research", "MiMo", "image",
                                                               "manualcompact", "auto400K", "liveActivation")}}
    (output / "RELEASE-MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
    # A changing output/source is a failed export, never silently a valid release.
    require(git(repo, "rev-parse", "HEAD").decode().strip() == commit
            and not git(repo, "status", "--porcelain=v1", "--untracked-files=all"), "Source changed during export")
    for n, raw in {**source, **compiled}.items():
        require(read_regular(repo / n) == raw, "Source/build changed during export: " + n)
    (output / "EXPORT-COMPLETE.json").write_text(json.dumps({"sourceCommit": commit,
        "manifestSha256": sha(read_regular(output / "RELEASE-MANIFEST.json")),
        "status": "STRUCTURAL_EXPORT_COMPLETE_NO_LIVE_AUTHORITY"}, indent=2) + "\n")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--release-dir", required=True)
    parser.add_argument("--source-commit")
    parser.add_argument("--build-receipt", action="append", default=[])
    parser.add_argument("--release-path-status", choices=("PROPOSED_ROOT_REVIEW_REQUIRED", "ROOT_CHOSEN_PATH_NO_GO"),
                        default="PROPOSED_ROOT_REVIEW_REQUIRED")
    args = parser.parse_args()
    manifest = export(args.repo, args.output, args.release_dir, args.source_commit,
                      args.build_receipt, args.release_path_status)
    print(json.dumps({"sourceCommit": manifest["sourceCommit"], "releaseDir": manifest["releaseDir"],
                      "manifest": str(args.output / "RELEASE-MANIFEST.json"),
                      "status": "UNAPPROVED_SOURCE_AND_BUILD_EXPORT"}))


if __name__ == "__main__":
    main()
