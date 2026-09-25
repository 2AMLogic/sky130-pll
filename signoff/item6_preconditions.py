#!/usr/bin/env python3
"""Re-derive T1 item 6's preconditions from the repo, instead of asserting them.

`signoff/README.md` § "Why every other row is `unmet`" case **4b** argues why
`signoff/block-manifest.json` does not cite
`sim/pll-lock-mc/analysis/yield-evidence/klt-yield-report.json` for T1 item 6
("Statistical claims carry Monte Carlo evidence"). Item 6's checklist text names
four things a Monte Carlo campaign must carry:

    MC runs need a recorded seed, sample count, a deterministic negative
    control, and results combined with (not instead of) process corners

-- and `signoff/run-signoff.sh`'s guard 3 adds the fifth condition the cited
report's own statistics have to satisfy (a `sample_size.verdict` of
`sufficient`).

Until this script existed, which of those were outstanding lived **only** in
that README's prose, and it went stale: case 4b said "`sim/pll-lock`'s manifest
declares no `measure.jitter` block; that is issue #180" hours after issue #180
landed the block (PR #189). The prose conclusion still held -- the deterministic
axis still has no jitter figure -- but for a different reason than the one
written down, and nothing in the repo noticed.

So this script re-derives every precondition from the committed artifact and
field that actually settles it, and writes `signoff/item6-preconditions.md`.
`--check` runs in `npm run check:ci`, so the day a precondition changes the
generated document drifts and CI says so, rather than a reader having to
re-audit five facts by hand.

It is the `signoff/` counterpart of the `analysis/` convention `sim/README.md`
defines: **it simulates nothing, runs no `klt`, needs no PDK, and introduces no
number that is not already in one of the artifacts it reads.** Every row of the
generated table names its source file and the field inside it.

What it reads, and what each artifact settles:

  * `sim/pll-lock-mc/analysis/yield-evidence/mc-samples.json` -- the sample-set
    document the cited report was computed over; its `provenance.source_record`
    is the authoritative link from the artifact to the campaign record, so the
    record is never guessed from a directory listing.
  * that record (`sim/pll-lock-mc/records/<id>.md`) -- the recorded seeds and
    the drawn sample count (requirements 1 and 2).
  * `sim/pll-lock-mc/testbench/tb.json` -- whether the statistical axis samples
    die-to-die process spread at all (`monte_carlo.process`, requirement 4a).
  * `sim/pll-lock-mc/analysis/yield-evidence/klt-yield-report.json` -- the
    declared negative control (`measurements[].negative_control`, requirement 3)
    and the sample-size verdict (`measurements[].sample_size.verdict`,
    guard 3's second condition). These come from the report rather than from
    prose about which control exists, because the report's own field is what
    `klt signoff` and guard 3 read.
  * `sim/pll-lock/testbench/tb.json` + `sim/pll-lock/records/*.md` -- whether
    the deterministic PVT grid the statistical axis must be combined *with* has
    a period-jitter column declared, and whether any committed record on that
    grid actually carries one (requirement 4b).
  * `signoff/block-manifest.json` -- whether item 6 is cited today, reported so
    the generated document and the manifest cannot disagree.

Usage:

    python3 signoff/item6_preconditions.py            # print to stdout
    python3 signoff/item6_preconditions.py --write    # (re)write the document
    python3 signoff/item6_preconditions.py --check    # fail on any drift

    # optional: assert item 6's checklist text still names the four
    # requirements this script tracks (needs a `klt` install's tiers doc, so it
    # is not part of `--check` and never runs in CI)
    python3 signoff/item6_preconditions.py --tiers-doc <design-evidence-tiers.md>

Standard library only, same convention as `sim/run_corners.py` and
`sim/pll-lock-mc/analysis/yield_evidence.py`.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

#: Repo root, from this file's committed location (`signoff/`).
REPO_ROOT = Path(__file__).resolve().parents[1]

#: Written by `--write`, verified by `--check`.
OUTPUT = Path(__file__).resolve().parent / "item6-preconditions.md"

MC_SAMPLES = "sim/pll-lock-mc/analysis/yield-evidence/mc-samples.json"
MC_REPORT = "sim/pll-lock-mc/analysis/yield-evidence/klt-yield-report.json"
MC_MANIFEST = "sim/pll-lock-mc/testbench/tb.json"
PVT_MANIFEST = "sim/pll-lock/testbench/tb.json"
PVT_RECORDS = "sim/pll-lock/records"
BLOCK_MANIFEST = "signoff/block-manifest.json"

#: The four requirements item 6's checklist text names, in its own order and
#: its own words (`docs/design-evidence-tiers.md` item 6, `klt` 0.6.0). Each
#: entry's value is the phrase `--tiers-doc` asserts is still present.
CHECKLIST_REQUIREMENTS = {
    "1": "a recorded seed",
    "2": "sample count",
    "3": "a deterministic negative control",
    "4": "results combined with (not instead of) process corners",
}

#: The T1 item this document is about.
ITEM = "6"

_TRIALS_RE = re.compile(
    r"^\s*- Trials: (?P<trials>\d+) \(seeds (?P<first>\d+)\.\.(?P<last>\d+),", re.M
)


class PreconditionError(RuntimeError):
    """An input artifact is missing or does not have the shape claimed here."""


def _read_json(rel: str) -> dict:
    path = REPO_ROOT / rel
    try:
        return json.loads(path.read_text())
    except OSError as exc:
        raise PreconditionError(f"{rel}: {exc}") from exc
    except ValueError as exc:
        raise PreconditionError(f"{rel} is not readable JSON: {exc}") from exc


def _read_text(rel: str) -> str:
    path = REPO_ROOT / rel
    try:
        return path.read_text()
    except OSError as exc:
        raise PreconditionError(f"{rel}: {exc}") from exc


def _sole_measurement(report: dict) -> dict:
    measurements = report.get("measurements")
    if not isinstance(measurements, list) or len(measurements) != 1:
        raise PreconditionError(
            f"{MC_REPORT} has "
            f"{len(measurements) if isinstance(measurements, list) else 'no'} "
            "measurements; this document is written for the single-measurement "
            "report this campaign produces -- widen it deliberately rather than "
            "letting it grade only the first"
        )
    measurement = measurements[0]
    if not isinstance(measurement, dict):
        raise PreconditionError(f"{MC_REPORT}: measurement is not an object")
    return measurement


def table_headers(markdown: str) -> list[list[str]]:
    """Every markdown table header row in `markdown`, as lists of cells.

    A header is any pipe-delimited row immediately followed by a separator row
    of only `-`/`:`/`|` -- which is how the result tables in this repo's
    records are written, and the only structure this needs to recognize.
    """
    lines = [line.strip() for line in markdown.splitlines()]
    headers: list[list[str]] = []
    for index, line in enumerate(lines[:-1]):
        if not (line.startswith("|") and line.endswith("|")):
            continue
        following = lines[index + 1]
        if not (following.startswith("|") and following.endswith("|")):
            continue
        if set(following) - set("-:| "):
            continue
        headers.append([cell.strip() for cell in line[1:-1].split("|")])
    return headers


def records_with_a_jitter_column(records_dir: str) -> tuple[list[str], list[str]]:
    """Split a records directory into (carries a jitter column, does not).

    Both lists are returned rather than only the first: "no record carries one"
    is the claim this document makes, and a claim of absence has to name what it
    looked at.
    """
    directory = REPO_ROOT / records_dir
    if not directory.is_dir():
        raise PreconditionError(f"{records_dir} is not a directory")
    carries: list[str] = []
    without: list[str] = []
    for path in sorted(directory.glob("*.md")):
        has = any(
            any("jitter" in cell.lower() for cell in header)
            for header in table_headers(path.read_text())
        )
        (carries if has else without).append(path.name)
    if not carries and not without:
        raise PreconditionError(f"{records_dir} holds no records")
    return carries, without


def collect() -> dict:
    """Every fact the generated document states, each with its own source."""
    samples = _read_json(MC_SAMPLES)
    provenance = samples.get("provenance")
    if not isinstance(provenance, dict):
        raise PreconditionError(f"{MC_SAMPLES} carries no provenance block")
    source_record = provenance.get("source_record")
    if not isinstance(source_record, str) or not source_record:
        raise PreconditionError(f"{MC_SAMPLES}'s provenance names no source_record")

    record_text = _read_text(source_record)
    trials = _TRIALS_RE.search(record_text)
    if trials is None:
        raise PreconditionError(
            f"{source_record} has no `Trials: N (seeds a..b, ...)` line -- the "
            "recorded seed and sample count are read from it, not assumed"
        )

    mc_manifest = _read_json(MC_MANIFEST)
    monte_carlo = mc_manifest.get("monte_carlo")
    if not isinstance(monte_carlo, dict):
        raise PreconditionError(f"{MC_MANIFEST} declares no monte_carlo block")

    report = _read_json(MC_REPORT)
    measurement = _sole_measurement(report)
    sample_size = measurement.get("sample_size")
    if not isinstance(sample_size, dict):
        raise PreconditionError(
            f"{MC_REPORT}: measurement carries no sample_size block -- is this a "
            "`klt yield` report?"
        )

    pvt_manifest = _read_json(PVT_MANIFEST)
    pvt_jitter = (pvt_manifest.get("measure") or {}).get("jitter")
    carries, without = records_with_a_jitter_column(PVT_RECORDS)

    block_manifest = _read_json(BLOCK_MANIFEST)
    evidence = block_manifest.get("evidence")
    cited = isinstance(evidence, dict) and ITEM in evidence

    return {
        "source_record": source_record,
        "record_id": Path(source_record).stem,
        "declared_trials": int(trials.group("trials")),
        "seed_first": int(trials.group("first")),
        "seed_last": int(trials.group("last")),
        "seed_base": monte_carlo.get("seed_base"),
        "manifest_trials": monte_carlo.get("trials"),
        "process_sampling": bool(monte_carlo.get("process")),
        "mismatch_sampling": bool(monte_carlo.get("mismatch")),
        "measurement_name": measurement.get("name"),
        "measurable_n": measurement.get("n"),
        "errored": measurement.get("errored"),
        "failed_unmeasurable": measurement.get("failed_unmeasurable"),
        "negative_control": measurement.get("negative_control"),
        "sample_size_verdict": sample_size.get("verdict"),
        "sample_size_n": sample_size.get("n"),
        "required_n": sample_size.get("required_n"),
        "report_status": report.get("status"),
        "pvt_jitter_declared": isinstance(pvt_jitter, dict),
        "pvt_jitter_max_frac": (pvt_jitter or {}).get("max_frac"),
        "pvt_records_with_jitter": carries,
        "pvt_records_without_jitter": without,
        "item6_cited": cited,
    }


def _verdicts(facts: dict) -> list[dict]:
    """One row per precondition: id, requirement, verdict, source, what closes it.

    `verdict` is `met` / `unmet` only -- there is no third state, because a
    precondition this script cannot settle is a `PreconditionError` in
    `collect()` rather than a shrug in the table.
    """
    seeds_agree = (
        facts["seed_base"] == facts["seed_first"]
        and facts["manifest_trials"] == facts["declared_trials"]
        and facts["seed_last"] == facts["seed_first"] + facts["declared_trials"] - 1
    )
    control = facts["negative_control"]
    control_verdict = control.get("verdict") if isinstance(control, dict) else None

    return [
        {
            "id": "1",
            "requirement": "a recorded seed",
            "met": seeds_agree,
            "source": (
                f"`{facts['source_record']}` -- `Trials: {facts['declared_trials']} "
                f"(seeds {facts['seed_first']}..{facts['seed_last']}, ...)`, "
                f"cross-checked against `{MC_MANIFEST}`'s "
                f"`monte_carlo.seed_base` = {facts['seed_base']}"
            ),
            "closes": (
                "already met -- one `ngspice .options seed=<N>` card per draw, "
                "recorded per trial"
                if seeds_agree
                else "the record's declared seed range and the manifest's "
                "`seed_base`/`trials` disagree; fix whichever drifted"
            ),
        },
        {
            "id": "2",
            "requirement": "sample count",
            "met": isinstance(facts["measurable_n"], int) and facts["measurable_n"] > 0,
            "source": (
                f"`{facts['source_record']}` -- {facts['declared_trials']} draws; "
                f"`{MC_REPORT}` -- `n` = {facts['measurable_n']} measurable, "
                f"`errored` = {facts['errored']}, `failed_unmeasurable` = "
                f"{facts['failed_unmeasurable']}"
            ),
            "closes": (
                "already met -- both the drawn count and the measurable count are "
                "recorded (they differ, and the difference is declared rather "
                "than hidden)"
            ),
        },
        {
            "id": "3",
            "requirement": "a deterministic negative control",
            "met": control_verdict == "detected",
            "source": (
                f"`{MC_REPORT}` -- `measurements[0].negative_control` is "
                f"{'null' if control is None else json.dumps(control)}"
            ),
            "closes": (
                "already met"
                if control_verdict == "detected"
                else "a `negative_control` block in the sample-set document, "
                "populated from a seeded known-bad variant's own draws of "
                f"`{facts['measurement_name']}`, plus a `klt yield` re-run whose "
                "`negative_control.verdict` is `detected` -- or a committed record "
                "arguing that `not_detected` is the honest outcome, which "
                "`run-signoff.sh`'s guard 3 names as its own escape hatch. "
                "`klt yield` is not reachable from this repo's pin "
                "(klayout-tools#2466), so the re-run is gated on that too"
            ),
        },
        {
            "id": "4a",
            "requirement": (
                "results combined with (not instead of) process corners "
                "-- the statistical axis samples process spread"
            ),
            "met": facts["process_sampling"],
            "source": (
                f"`{MC_MANIFEST}` -- `monte_carlo.process` = "
                f"{json.dumps(facts['process_sampling'])}, "
                f"`monte_carlo.mismatch` = {json.dumps(facts['mismatch_sampling'])}"
            ),
            "closes": (
                "already met -- every draw carries die-to-die process spread "
                "(`MC_PR_SWITCH`) on top of local mismatch (`MC_MM_SWITCH`), so "
                "the population is a superset of the local-mismatch one DR-006 "
                "names"
                if facts["process_sampling"]
                else "turn `monte_carlo.process` on, or state why a "
                "mismatch-only population answers this requirement"
            ),
        },
        {
            "id": "4b",
            "requirement": (
                "results combined with (not instead of) process corners "
                "-- the deterministic PVT grid has a period-jitter figure to "
                "combine them with"
            ),
            "met": bool(facts["pvt_records_with_jitter"]),
            "source": (
                f"`{PVT_MANIFEST}` -- `measure.jitter` "
                + (
                    f"declared (`max_frac` = {facts['pvt_jitter_max_frac']})"
                    if facts["pvt_jitter_declared"]
                    else "**not** declared"
                )
                + "; `"
                + PVT_RECORDS
                + "/` -- "
                + (
                    "records carrying a period-jitter column: "
                    + ", ".join(f"`{name}`" for name in facts["pvt_records_with_jitter"])
                    if facts["pvt_records_with_jitter"]
                    else "**no** committed record carries a period-jitter column "
                    "(looked at "
                    + ", ".join(
                        f"`{name}`" for name in facts["pvt_records_without_jitter"]
                    )
                    + ")"
                )
            ),
            "closes": (
                "already met"
                if facts["pvt_records_with_jitter"]
                else "a full-grid `sim/pll-lock` re-run against the current "
                "manifest, which is the first record that will carry the declared "
                "column. The declaration alone does not close this: a column that "
                "has never been run is not a measurement"
            ),
        },
        {
            "id": "5",
            "requirement": (
                "the cited report's estimate is sized "
                "(`run-signoff.sh` guard 3, not item 6's checklist text)"
            ),
            "met": facts["sample_size_verdict"] == "sufficient",
            "source": (
                f"`{MC_REPORT}` -- `measurements[0].sample_size.verdict` = "
                f"{json.dumps(facts['sample_size_verdict'])} "
                f"(`n` = {facts['sample_size_n']}, `required_n` = "
                f"{facts['required_n']})"
            ),
            "closes": (
                "already met"
                if facts["sample_size_verdict"] == "sufficient"
                else f"a widened campaign: {facts['required_n']} measurable draws "
                "against the "
                f"{facts['sample_size_n']} this one has. "
                "`sim/pll-lock-mc/analysis/README.md` § \"The sample-size "
                "question, answered\" argues why that spend is not yet the right "
                "one, and what would change that"
            ),
        },
    ]


def render(facts: dict) -> str:
    rows = _verdicts(facts)
    outstanding = [row for row in rows if not row["met"]]
    lines: list[str] = []
    add = lines.append

    add(f"# T1 item {ITEM}: which preconditions are outstanding")
    add("")
    add(
        "**Generated** by `signoff/item6_preconditions.py` -- do not edit. "
        "`python3 signoff/item6_preconditions.py --check` re-derives every row "
        "below from the artifact it names and fails on any drift; it runs in "
        "`npm run check:ci`, so this document cannot go stale against the repo "
        "while the prose that used to carry these facts could."
    )
    add("")
    add(
        f"T1 item {ITEM} is *Statistical claims carry Monte Carlo evidence*. Its "
        "checklist text names four requirements -- "
        + ", ".join(f"*{phrase}*" for phrase in CHECKLIST_REQUIREMENTS.values())
        + f" -- and `signoff/run-signoff.sh`'s guard 3 adds a fifth the cited "
        "report's own statistics must satisfy. Requirement 4 is split into two "
        "rows because its two halves live in different artifacts and are in "
        "different states."
    )
    add("")
    if outstanding:
        summary = (
            f"**Verdict: {len(outstanding)} of {len(rows)} preconditions "
            f"outstanding** ({', '.join(row['id'] for row in outstanding)}). "
        )
        summary += (
            f"`{BLOCK_MANIFEST}` does not cite item {ITEM}, which is what that "
            "verdict calls for."
            if not facts["item6_cited"]
            else f"`{BLOCK_MANIFEST}` **does** cite item {ITEM} -- the manifest "
            "and this document disagree, and the manifest is the one that is "
            "wrong."
        )
    else:
        summary = (
            f"**Verdict: every one of the {len(rows)} preconditions is met.** "
            f"`{BLOCK_MANIFEST}` "
            + ("cites" if facts["item6_cited"] else "does not yet cite")
            + f" item {ITEM}."
        )
    add(summary)
    add("")
    add(
        f"The campaign under grading is `{facts['source_record']}` "
        f"({facts['declared_trials']} draws, seeds {facts['seed_first']}.."
        f"{facts['seed_last']}), and the report that would be cited is "
        f"`{MC_REPORT}` (`status` "
        f"{json.dumps(facts['report_status'])})."
    )
    add("")
    add("| # | Requirement | Verdict | Derived from | What closes it |")
    add("| --- | --- | --- | --- | --- |")
    for row in rows:
        verdict = "met" if row["met"] else "**unmet**"
        add(
            f"| {row['id']} | {row['requirement']} | {verdict} | "
            f"{row['source']} | {row['closes']} |"
        )
    add("")
    add(
        "Read this beside `signoff/README.md` § \"Why every other row is "
        '`unmet`" case 4b, which argues *why* an unmet precondition is a decline '
        "rather than a technicality, and `sim/pll-lock-mc/analysis/README.md`, "
        "which is the full read on the campaign itself."
    )
    add("")
    return "\n".join(lines)


def assert_checklist_unchanged(tiers_doc: Path) -> list[str]:
    """Phrases `CHECKLIST_REQUIREMENTS` claims item 6's text still uses, missing
    from `tiers_doc`. Empty means the checklist has not drifted under this
    script.
    """
    text = tiers_doc.read_text()
    # Item 6's paragraph runs from its own numbered bullet to the next one.
    match = re.search(r"^6\. \*\*Statistical claims.*?(?=^7\. )", text, re.M | re.S)
    if match is None:
        raise PreconditionError(
            f"{tiers_doc} has no item 6 paragraph starting "
            "`6. **Statistical claims` -- a tiers doc whose item 6 moved is a "
            "tool change to read deliberately, not a repo drift"
        )
    paragraph = " ".join(match.group(0).split())
    return [
        phrase for phrase in CHECKLIST_REQUIREMENTS.values() if phrase not in paragraph
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            f"Re-derive T1 item {ITEM}'s preconditions from the repo and render "
            f"{OUTPUT.name}."
        )
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--write", action="store_true", help=f"write the document to {OUTPUT}"
    )
    mode.add_argument(
        "--check",
        action="store_true",
        help="re-derive the document and fail if the committed copy differs",
    )
    parser.add_argument(
        "--tiers-doc",
        type=Path,
        default=None,
        help=(
            "path to a `klt` install's design-evidence-tiers.md -- asserts item "
            f"{ITEM}'s checklist text still names the four requirements this "
            "script tracks. Not part of --check (it needs a `klt` install)"
        ),
    )
    args = parser.parse_args(argv)

    try:
        if args.tiers_doc is not None:
            missing = assert_checklist_unchanged(args.tiers_doc)
            if missing:
                print(
                    f"error: item {ITEM}'s checklist text in {args.tiers_doc} no "
                    "longer names:",
                    file=sys.stderr,
                )
                for phrase in missing:
                    print(f"  {phrase!r}", file=sys.stderr)
                print(
                    "       This script's requirement list is derived from that "
                    "text. Re-read item 6 and update CHECKLIST_REQUIREMENTS (and "
                    "the rows) deliberately.",
                    file=sys.stderr,
                )
                return 1
            print(f"{args.tiers_doc} still names all four requirements.")
        facts = collect()
        document = render(facts)
    except (PreconditionError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.write:
        OUTPUT.write_text(document)
        print(f"wrote {OUTPUT}")
        return 0

    if args.check:
        try:
            committed = OUTPUT.read_text()
        except OSError as exc:
            print(f"error: {OUTPUT}: {exc}", file=sys.stderr)
            return 1
        if committed != document:
            print(
                f"error: {OUTPUT} no longer matches what the repo derives -- a "
                f"precondition of T1 item {ITEM} changed state.",
                file=sys.stderr,
            )
            print(
                "       Re-render it with `python3 signoff/item6_preconditions.py "
                "--write`, then read signoff/README.md case 4b before updating "
                "any claim it backs.",
                file=sys.stderr,
            )
            return 1
        print(f"{OUTPUT} is current.")
        return 0

    print(document, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
