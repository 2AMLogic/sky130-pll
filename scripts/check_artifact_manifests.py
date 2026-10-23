#!/usr/bin/env python3
"""Stored-evidence manifests: schema guard and no-committed-bytes check (issue #370).

Provenance: adapted from 2AMLogic/sg13g2-comparator,
``scripts/check_artifact_manifests.py`` at
b46d54afe3d87d619f20a94b44ceece3a29ada1b. Changes: ``artifact:<key>`` URIs
only (no ``s3://``), no broker ``verify`` subcommand (use ``klt artifact
verify``), and the "bytes must not also be committed" test compares sha256
digests of tracked files rather than paths.

New simulation evidence bytes go to the fleet artifact store through
``klt artifact put`` (``sim/harness/evidence_store.py``); git keeps a manifest
per run under ``manifests/artifacts/<bench>-<run-id>.manifest.json`` plus the
run's Markdown summary. This script is the git-side check of that contract.

    check_artifact_manifests.py [--repo DIR] [--tree REV]

Reads every manifest committed in ``REV`` (default ``HEAD``; blob contents via
git, so a sparse working tree does not matter) and fails if one is malformed
(wrong schema, unknown or missing field, a ``uri`` that is not
``artifact:<key>`` ending in the entry's sha256, a ``name`` that is not a
canonical ``sim/...`` path, a duplicate name), or if the sha256 of any
git-tracked file equals a manifest entry: the point of a manifest is that the
bytes are *not* committed.

This never contacts the broker and says so: schema-valid is not
hash-verified. Run ``klt artifact verify <manifest>`` for that.

Exit codes: 0 ok; 1 a manifest is invalid or a stored object is committed;
2 usage or git error. Stdlib only; needs ``git`` on PATH.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import posixpath
import re
import subprocess
import sys

MANIFEST_DIR = "manifests/artifacts/"
MANIFEST_RE = re.compile(r"^manifests/artifacts/[A-Za-z0-9][A-Za-z0-9._-]*\.manifest\.json$")
DIR_FILES_ALLOWED = {"manifests/artifacts/README.md"}

SCHEMA_VERSION = 1
KIND = "evidence"
REQUIRED = ("sha256", "size", "kind", "producer", "uri")
OPTIONAL = ("name", "media_type")
PRODUCER_FIELDS = ("tool", "version", "loom.repo", "commit")

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
URI_RE = re.compile(r"^artifact:([^/\s]\S*)$")

EXIT_OK, EXIT_INVALID, EXIT_ERROR = 0, 1, 2


class ToolError(Exception):
    """Git failure: exit 2, fail closed."""


def canonical_name(name) -> bool:
    return (isinstance(name, str) and name.startswith("sim/")
            and "\\" not in name and "\0" not in name
            and posixpath.normpath(name) == name
            and not {"", ".", ".."} & set(name.split("/")))


def entry_problems(entry) -> list[str]:
    if not isinstance(entry, dict):
        return ["entry is not an object"]
    problems = []
    missing = [f for f in REQUIRED if f not in entry]
    extra = sorted(set(entry) - set(REQUIRED) - set(OPTIONAL))
    if missing:
        problems.append(f"missing {', '.join(missing)}")
    if extra:
        problems.append(f"unknown field(s) {', '.join(extra)}")
    sha = entry.get("sha256")
    if not isinstance(sha, str) or not SHA256_RE.match(sha):
        problems.append("sha256 must be 64 lowercase hex digits")
    size = entry.get("size")
    if not isinstance(size, int) or isinstance(size, bool) or size < 1:
        problems.append("size must be a positive integer")
    if entry.get("kind") != KIND:
        problems.append(f"kind must be {KIND!r}")
    producer = entry.get("producer")
    if not isinstance(producer, dict) or set(producer) != set(PRODUCER_FIELDS):
        problems.append(f"producer must carry exactly {', '.join(PRODUCER_FIELDS)}")
    else:
        for f in ("tool", "version", "loom.repo"):
            if not isinstance(producer.get(f), str) or not producer[f]:
                problems.append(f"producer.{f} must be a non-empty string")
        if producer.get("commit") is not None and not isinstance(producer["commit"], str):
            problems.append("producer.commit must be a string or null")
    uri = entry.get("uri")
    m = URI_RE.match(uri) if isinstance(uri, str) else None
    if m is None:
        problems.append("uri must be artifact:<key> (no storage location in a manifest)")
    elif m.group(1).rsplit("/", 1)[-1] != sha:
        problems.append("uri key does not end in the entry's sha256")
    if "name" not in entry:
        problems.append("name is required here (the logical sim/ path of the bytes)")
    elif not canonical_name(entry["name"]):
        problems.append("name must be a canonical relative sim/... path")
    if "media_type" in entry and not isinstance(entry["media_type"], str):
        problems.append("media_type must be a string")
    return problems


def manifest_problems(manifest) -> list[str]:
    if not isinstance(manifest, dict) or set(manifest) != {"schema_version", "entries"} \
            or manifest.get("schema_version") != SCHEMA_VERSION \
            or not isinstance(manifest.get("entries"), list):
        return [f"not {{schema_version: {SCHEMA_VERSION}, entries: [...]}}"]
    if not manifest["entries"]:
        return ["has no entries"]
    problems = []
    seen = set()
    for i, entry in enumerate(manifest["entries"]):
        for p in entry_problems(entry):
            problems.append(f"entry {i}: {p}")
        name = entry.get("name") if isinstance(entry, dict) else None
        if isinstance(name, str):
            if name in seen:
                problems.append(f"entry {i}: duplicate name {name!r}")
            seen.add(name)
    return problems


def git(repo: str, *args: str) -> bytes:
    try:
        p = subprocess.run(["git", "-C", repo, *args], stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, check=False,
                           env={**os.environ, "GIT_NO_LAZY_FETCH": "1"})
    except OSError as exc:
        raise ToolError(f"cannot run git: {exc}") from exc
    if p.returncode != 0:
        raise ToolError(f"git {' '.join(args)} failed: "
                        f"{p.stderr.decode('utf-8', 'replace').strip()}")
    return p.stdout


def tracked_blobs(repo: str, tree: str) -> dict[str, tuple[str, str, int]]:
    """``{path: (mode, object_id, size)}`` of every blob in ``tree``."""
    out = {}
    for rec in git(repo, "ls-tree", "-r", "-l", "-z", tree).split(b"\0"):
        if not rec:
            continue
        meta, _, name = rec.partition(b"\t")
        mode, typ, oid, size = meta.decode().split()
        if typ == "blob":
            out[name.decode("utf-8", "surrogateescape")] = (mode, oid, int(size))
    return out


def check(repo: str, rev: str) -> int:
    if rev.startswith("-"):
        raise ToolError(f"invalid revision {rev!r}")
    tree = git(repo, "rev-parse", "--verify", "--quiet", "--end-of-options",
               f"{rev}^{{tree}}").decode().strip()
    if not tree:
        raise ToolError(f"revision {rev!r} is unavailable")
    blobs = tracked_blobs(repo, tree)
    errors: list[str] = []
    stored: dict[tuple[str, int], str] = {}  # (sha256, size) -> manifest path
    manifests = entries = 0
    for path in sorted(p for p in blobs if p.startswith(MANIFEST_DIR)):
        mode = blobs[path][0]
        if path in DIR_FILES_ALLOWED:
            continue
        if not MANIFEST_RE.match(path) or mode == "120000":
            errors.append(f"{path}: only <bench>-<run-id>.manifest.json files (and "
                          "README.md) belong in manifests/artifacts/")
            continue
        try:
            manifest = json.loads(git(repo, "show", f"{tree}:{path}").decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            errors.append(f"{path}: not valid JSON: {exc}")
            continue
        problems = manifest_problems(manifest)
        errors += [f"{path}: {p}" for p in problems]
        if problems:
            continue
        manifests += 1
        for entry in manifest["entries"]:
            entries += 1
            stored.setdefault((entry["sha256"], entry["size"]), path)
    # A tracked file whose bytes equal a stored object is the blob fallback this
    # repo forbids. Only files of a matching size can match, so hash just those.
    sizes = {size for _, size in stored}
    for path, (_, oid, size) in sorted(blobs.items()):
        if size not in sizes:
            continue
        sha = hashlib.sha256(git(repo, "cat-file", "blob", oid)).hexdigest()
        if (sha, size) in stored:
            errors.append(f"{stored[(sha, size)]}: sha256 {sha} is also committed as "
                          f"{path}; stored evidence bytes must not be committed")
    if errors:
        print(f"FAIL: {len(errors)} stored-evidence manifest problem(s) in {rev}:",
              file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        return EXIT_INVALID
    print(f"OK: {manifests} manifest(s), {entries} entr{'y' if entries == 1 else 'ies'} "
          f"in {MANIFEST_DIR} of {rev}: schema valid, no stored bytes committed. "
          "Bytes NOT hash-verified here (no broker contact); run "
          "`klt artifact verify <manifest>` with $KLT_ARTIFACT_BROKER set.")
    return EXIT_OK


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tree", default="HEAD", help="commit or tree (default HEAD)")
    ap.add_argument("--repo", default=".", help="repository path (default .)")
    args = ap.parse_args(argv)
    try:
        return check(args.repo, args.tree)
    except ToolError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
