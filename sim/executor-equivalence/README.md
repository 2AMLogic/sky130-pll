# Executor equivalence: `--executor local` vs. `--executor remote`

Issue #146 added an execution-backend seam to the harness
(`sim/harness/executor.py`, documented in `sim/harness/README.md` →
"Where a unit runs"). The seam's whole claim is that **it changes only where
`ngspice -b` runs** — the patched netlist, the pass/fail judge, the
measurement reducer, and the evidence-record format are the same code for
every backend.

That claim is checkable, and this directory is where the check lives: one
slug run both ways, records committed side by side, measurements compared
within the harness's own tolerance.

## Status

| Side | Record | State |
|---|---|---|
| `local` | [`sim/divider-n5/records/20260919-023351-32f268f.md`](../divider-n5/records/20260919-023351-32f268f.md) | **committed** |
| `remote` | — | **empty — not yet runnable on any host** |

**The remote slot is deliberately empty.** No host in the fleet has a scoped
EC2 launch identity yet — that is tracked privately as **2AMLogic/2am#934**
(a scoped launch profile plus the matching private key on the fleet hosts).
Until it lands, `--executor remote` falls back to `local` everywhere, which
is the documented contract, not a defect. Nothing in this directory
simulates, estimates, or otherwise stands in for a remote run: an unmeasured
number is not evidence, and `sim/README.md`'s append-only evidence rule
applies to this fixture exactly as it does to every other record.

## The chosen slug

`sim/divider-n5` at its single cheapest lock-capable point — `tt`, 27 °C,
nominal 1.80 V supply. It is the right fixture because:

- it exercises the **full** judge, not just the plumbing check: the manifest
  carries a `measure` block with `require_lock`, so a unit only PASSes if
  ngspice completed cleanly *and* the reducer found a clean, held N:1
  division in the waveform dump the run produced. A backend that lost or
  mis-collected a waveform dump could not fake that;
- `N=5`'s short output period makes one point cheap (a 260 ns transient), so
  the remote half will cost one small Spot instance for a couple of minutes
  rather than a fleet-hour;
- it has an existing local campaign to cross-read against
  (`sim/divider-n5/records/`).

## The local half (committed)

Produced by a real run of the shipped code path:

```sh
python3 sim/run_corners.py divider-n5 --executor local \
  --corners tt --temps 27 --supply-tol 0 \
  --subset-reason "executor-equivalence fixture for issue #146: ..."
```

Result: `tt / 27 °C / 1.80 V` → **PASS**, locked at 12.52 ns, post-lock
f_out 50 MHz, duty 39.9 %.

Note what that record does **not** say: it carries no `**Execution**` bullet
at all. That absence is itself an acceptance criterion — a plain
`--executor local` run is byte-for-byte the record it was before this seam
existed, so `local` records stay directly comparable to every record minted
before #146. The executor provenance (`executor`, `hosts`, `region`,
`instance_type`, `spot`, cost estimates, `fallback_reason`) appears only
when a run actually asked for a non-local backend.

## The remote half (what produces it, once 2AMLogic/2am#934 lands)

On a host that has the scoped profile and the matching key, with the
environment below set (see `sim/harness/README.md` → "Configuration" for the
full table — no value of any of these belongs in this repo):

```sh
export SKY130_PLL_REMOTE_REGION=<region>
export SKY130_PLL_REMOTE_KEY_NAME=<your-ec2-keypair-name>
export SKY130_PLL_REMOTE_SSH_KEY=~/.ssh/<your-ec2-keypair-name>.pem
export SKY130_PLL_REMOTE_AWS_PROFILE=<aws-profile>
export SKY130_PLL_REMOTE_LAUNCHER_CIDR=<this-host>/32

python3 sim/run_corners.py divider-n5 --executor remote --jobs 1 \
  --corners tt --temps 27 --supply-tol 0 \
  --subset-reason "executor-equivalence fixture for issue #146: the remote half of the local-vs-remote comparison in sim/executor-equivalence/. Not a design claim."
```

Then update the table above with the new record id, and add the comparison
section below.

**Confirm it really ran remotely before recording it as the remote half.**
The run is *designed* to fall back silently-but-loudly to local, so a record
is the remote half only if its `**Execution**` bullet reads
``executor: `remote` `` and carries an `instance_type` — a bullet reading
``executor: `local` (requested `remote`)`` with a `fallback_reason` is a
fallback, and belongs in this README as a note, not in the remote slot.

## What "agree" will mean

The two records must agree on:

- the **verdict** for the point (`PASS`), and the reason string;
- **locked** (`yes`) and **f_out** at the record's own printed precision;
- **time-to-lock** and **duty** within the harness's own measurement
  tolerance — the manifest's `lock.tolerance_frac` (2 %) is the band the
  reducer itself judges against, so that is the band a cross-executor
  comparison is entitled to, not bit-equality. Two ngspice runs of the same
  deck on different CPUs are not expected to agree bit-for-bit; agreeing
  *inside the criterion the record is judged by* is the claim.

Not compared: wall-clock time and cost, which differ by construction — they
are recorded (the remote record's `**Execution**` bullet carries region,
instance type, spot flag and the launcher's hourly estimate) so the pilot's
economics are auditable, not so they match.
