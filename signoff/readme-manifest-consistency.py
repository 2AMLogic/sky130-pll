#!/usr/bin/env python3
"""
Verify that README.md's layout record citations match the manifest.

The README.md prose mentions layout records in the item-3 section. This
check ensures those record IDs match what the manifest actually cites.

This is the README<->manifest half of the gap that run-signoff.sh's guard 2
does NOT cover (guard 2 checks manifest<->LATEST only).

Exit codes:
  0  All README record IDs match the manifest
  1  A README record ID does not match the manifest
"""

import json
import pathlib
import re
import sys


def main():
    repo_root = pathlib.Path(__file__).parent.parent
    manifest_path = repo_root / "signoff" / "block-manifest.json"
    readme_path = repo_root / "signoff" / "README.md"

    # Read the manifest to find what record ID is cited for item 3
    try:
        manifest = json.loads(manifest_path.read_text())
    except (OSError, ValueError) as exc:
        print(f"error: cannot read manifest {manifest_path}: {exc}", file=sys.stderr)
        return 1

    # Extract the record ID from item 3's evidence
    item3_evidence = manifest.get("evidence", {}).get("3", {})
    if isinstance(item3_evidence, dict):
        item3_file = item3_evidence.get("file", "")
    else:
        # Might be a string (old format)
        item3_file = item3_evidence if isinstance(item3_evidence, str) else ""

    # Extract the record ID from the file path: layout/pll/reports/<record-id>/...
    pattern = re.compile(r"^layout/[^/]+/reports/([^/]+)/")
    match = pattern.match(item3_file)
    if not match:
        print(
            f"error: cannot extract record ID from manifest item 3 evidence: {item3_file}",
            file=sys.stderr,
        )
        return 1

    manifest_record_id = match.group(1)

    # Read the README and find all layout record IDs mentioned
    try:
        readme_text = readme_path.read_text()
    except OSError as exc:
        print(f"error: cannot read {readme_path}: {exc}", file=sys.stderr)
        return 1

    # Find all patterns like `layout/pll/reports/<record-id>/...`
    # Record IDs are timestamps: YYYYMMDD-HHMMSS-<hex>
    # Pattern matches: layout/pll/reports/<record-id>/
    record_pattern = re.compile(r"`layout/[^/]+/reports/(\d{8}-\d{6}-[a-f0-9]+)/")

    # Extract all record IDs mentioned in the README
    record_ids = []
    for match in record_pattern.finditer(readme_text):
        record_id = match.group(1)
        position = match.start()
        record_ids.append((record_id, position))

    # Check each record ID
    # The historical reference (20260906-195205-4a08c71) should be excluded
    # It appears in a context that explicitly says it's "now-superseded" and
    # "before issue #157's pin bump", so we can check for these contextual markers
    errors = []

    for record_id, position in record_ids:
        # Check if this is the historical reference by examining context
        # Look for "now-superseded" or "before issue #157" in nearby text
        line_start = readme_text.rfind("\n", 0, position) + 1
        line_end = readme_text.find("\n", position)
        if line_end == -1:
            line_end = len(readme_text)

        # Look at a window of context (200 chars on each side).
        #
        # Known limitation: the historical-reference exclusion below keys on
        # literal phrases in the README prose. If the paragraph citing the
        # superseded record is reworded so neither phrase appears within this
        # window, that citation will be flagged as drift (a false positive,
        # not a silent pass). Update the markers here if that prose changes.
        context_start = max(0, position - 200)
        context_end = min(len(readme_text), position + 200)
        context = readme_text[context_start:context_end]

        # If this is the historical record mentioned as "now-superseded", skip it
        if "now-superseded" in context or "before issue #157" in context:
            continue

        # Otherwise, verify it matches the manifest's item 3 record
        if record_id != manifest_record_id:
            errors.append(
                f"README mentions record {record_id}, but manifest item 3 cites {manifest_record_id}"
            )

    if errors:
        print("error: README record IDs do not match the manifest:", file=sys.stderr)
        for line in errors:
            print(f"  {line}", file=sys.stderr)
        print(
            f"\nUpdate README.md to cite {manifest_record_id} instead, or update the manifest.",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
