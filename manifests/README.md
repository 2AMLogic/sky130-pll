# `manifests/` — what is stored outside git

`manifests/artifacts/<bench>-<run-id>.manifest.json` is written by
`sim/run_corners.py` and `sim/run_fmax.py` (via `sim/harness/evidence_store.py`)
(and by `layout/bin/run-pll-layout-flow.sh`, via `layout/bin/store_pll_evidence.py`,
as `layout-pll-<run-id>.manifest.json`) for every evidence run minted after
[DR-012](../spec/decision-records/DR-012-evidence-bytes-in-artifact-store.md).
One manifest per run; one entry per stored file:

```json
{
  "schema_version": 1,
  "entries": [
    {
      "sha256": "<64 hex>",
      "size": 1234,
      "kind": "evidence",
      "producer": {"tool": "klt", "version": "...", "loom.repo": "owner/name", "commit": "<sha>"},
      "uri": "artifact:<key>",
      "name": "sim/<bench>/corners/<run-id>/<file>"
    }
  ]
}
```

`name` is the logical path the bytes would have had under `sim/` (or
`layout/pll/reports/` for the PLL layout flow) and the path
the run's record cites. `uri` is `artifact:<key>`, a logical name that only the
artifact broker resolves. **A manifest names no storage location** — no
bucket, endpoint or account — so nothing in this directory identifies where the
bytes live. `git grep -nE 's3://|arn:aws:' -- manifests/` is empty, and
`scripts/check_artifact_manifests.py` rejects any other `uri` scheme.

Manifests are append-only evidence: never edit or delete one. A re-run mints a
new manifest and a new record that names the one it supersedes.

## Checking

- **In CI, offline:** `python3 scripts/check_artifact_manifests.py --tree HEAD`
  (part of `npm run check:ci`) validates the schema and fails if the sha256 of
  any git-tracked file equals a manifest entry (the bytes must not also be
  committed). It uses neither `klt` nor the broker, so a pass means
  "schema-valid", not "bytes verified".
- **Against the store:** `klt artifact verify manifests/artifacts/<name>.manifest.json`
  with `KLT_ARTIFACT_BROKER` set re-hashes every object. Fetch one with
  `klt artifact get <manifest>#<name> -o <out>`.

Records minted before DR-012 keep their raw bytes in git under `sim/`; they have
no manifest.
