#!/usr/bin/env python3
"""A campaign must outlive the checkout it was started from (issue #212).

    python3 -m unittest discover -s sim/tests -v

The incident these tests pin: a multi-hour Monte Carlo campaign was running
from a Loom-managed worktree; another process removed that worktree; the
working directory -- which held every unit's artifacts *and* the
`checkpoint.json` that `--resume` reads -- was unlinked beneath five live
ngspice processes, and 4 h 26 min of simulator time became unrecoverable. Not
because the work was lost (the finished units were all in the checkpoint) but
because the only record of it lived inside the directory being deleted.

No PDK, no ngspice and no xschem: every simulator call is stubbed, exactly as
in `test_execution.py`, whose `_Harness` fixture this module reuses. What is
under test is *which directory the harness writes to, and whether a campaign
can be picked up from a checkout that did not run it* -- not what ngspice
computes.

The properties pinned here are the ones an implementation could plausibly get
wrong while still passing every existing test:

  - a campaign in a reapable checkout puts its checkpoint outside that
    checkout, automatically, with no flag;
  - a campaign in a normal clone still writes exactly where it always did,
    and its record and committed artifacts are unchanged;
  - after the originating worktree is deleted outright, a *different*
    checkout can resume the campaign and re-simulates only the unfinished
    units;
  - promotion copies the committed artifact classes and never the waveform
    dumps or the transient checkpoint;
  - the resume fingerprint is not sensitive to which checkout netlisted the
    DUT -- but is still sensitive to the DUT.
"""

from __future__ import annotations

import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SIM_DIR = Path(__file__).resolve().parents[1]
TESTS_DIR = Path(__file__).resolve().parent
for _p in (str(SIM_DIR), str(TESTS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from harness import checkpoint as checkpoint_mod  # noqa: E402
from harness import corners as corners_mod  # noqa: E402
from harness import staging as staging_mod  # noqa: E402
from test_execution import (  # noqa: E402
    MANIFEST,
    NETLIST,
    RECORD_ID,
    _Harness,
    _point_result,
    _StubPdk,
    _table_rows,
)

ALL_POINT_IDS = [p.corner_id for p in corners_mod.build_matrix(MANIFEST, _StubPdk.process_corners)]

_UTC_STAMP_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")


def _without_run_time(record_text: str) -> str:
    """A record minus the one field two runs can never share: when they ran."""
    return _UTC_STAMP_RE.sub("<utc>", record_text)


def _make_linked_worktree(path: Path, main_clone: Path) -> Path:
    """A directory shaped exactly like a linked git worktree.

    The shape is the whole point: `git worktree add` writes a `.git` *file*
    holding `gitdir: <main>/.git/worktrees/<name>`, and that is precisely the
    kind of checkout `git worktree remove` deletes. A normal clone's `.git` is
    a directory and no worktree command removes it.
    """
    path.mkdir(parents=True, exist_ok=True)
    (path / ".git").write_text(f"gitdir: {main_clone}/.git/worktrees/{path.name}\n")
    return path


def _make_clone(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / ".git").mkdir(exist_ok=True)
    return path


class CheckoutDetectionTests(unittest.TestCase):
    """The trigger: which checkouts can be removed under a running campaign."""

    def test_a_linked_worktree_is_detected_from_any_depth(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clone = _make_clone(root / "main")
            wt = _make_linked_worktree(root / "wt", clone)
            deep = wt / "sim" / "fake-exp" / "corners"
            deep.mkdir(parents=True)
            self.assertEqual(staging_mod.linked_worktree_root(deep), wt.resolve())

    def test_a_normal_clone_is_not_a_worktree(self):
        with tempfile.TemporaryDirectory() as tmp:
            clone = _make_clone(Path(tmp) / "main")
            deep = clone / "sim" / "fake-exp"
            deep.mkdir(parents=True)
            self.assertIsNone(staging_mod.linked_worktree_root(deep))

    def test_a_directory_in_no_checkout_is_not_a_worktree(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(staging_mod.linked_worktree_root(Path(tmp)))

    def test_a_clone_inside_a_worktree_shadows_it(self):
        # The nearest `.git` wins: a real clone nested under a worktree path
        # is not itself reapable by `git worktree remove`.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wt = _make_linked_worktree(root / "wt", _make_clone(root / "main"))
            inner = _make_clone(wt / "vendor" / "inner")
            self.assertIsNone(staging_mod.linked_worktree_root(inner / "sim"))


class ResolveTests(unittest.TestCase):
    """Where a run's work goes, and -- for a resume -- where it came from."""

    def _exp_dir(self, tmp: Path, *, worktree: bool) -> Path:
        root = tmp / "checkout"
        if worktree:
            _make_linked_worktree(root, _make_clone(tmp / "main"))
        else:
            _make_clone(root)
        exp_dir = root / "sim" / "fake-exp"
        exp_dir.mkdir(parents=True)
        return exp_dir

    def _environ(self, tmp: Path) -> dict:
        return {"XDG_CACHE_HOME": str(tmp / "cache")}

    def test_a_normal_clone_stages_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            got = staging_mod.resolve(
                exp_dir=self._exp_dir(tmp, worktree=False),
                slug="fake-exp",
                record_id=RECORD_ID,
                environ=self._environ(tmp),
            )
            # The status quo, byte for byte: every committed record was minted
            # this way and a re-run of one still is.
            self.assertIsNone(got)

    def test_a_worktree_stages_under_the_cache_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            exp_dir = self._exp_dir(tmp, worktree=True)
            got = staging_mod.resolve(
                exp_dir=exp_dir,
                slug="fake-exp",
                record_id=RECORD_ID,
                environ=self._environ(tmp),
            )
            self.assertIsNotNone(got)
            self.assertEqual(
                got.work_dir,
                tmp / "cache" / "sky130-pll" / "sim-stage" / "fake-exp" / RECORD_ID,
            )
            self.assertEqual(got.final_dir, exp_dir / "corners" / RECORD_ID)
            # Nothing inside the checkout, which is the entire claim.
            self.assertNotIn(str(exp_dir), str(got.work_dir))
            self.assertTrue(got.work_dir.is_dir())

    def test_the_environment_variable_stages_even_in_a_clone(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            environ = dict(self._environ(tmp), **{staging_mod.ENV_ROOT: str(tmp / "scratch")})
            got = staging_mod.resolve(
                exp_dir=self._exp_dir(tmp, worktree=False),
                slug="fake-exp",
                record_id=RECORD_ID,
                environ=environ,
            )
            self.assertEqual(got.work_dir, tmp / "scratch" / "fake-exp" / RECORD_ID)

    def test_an_explicit_root_beats_the_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            environ = dict(self._environ(tmp), **{staging_mod.ENV_ROOT: str(tmp / "ignored")})
            got = staging_mod.resolve(
                exp_dir=self._exp_dir(tmp, worktree=True),
                slug="fake-exp",
                record_id=RECORD_ID,
                explicit=str(tmp / "chosen"),
                environ=environ,
            )
            self.assertEqual(got.work_dir, tmp / "chosen" / "fake-exp" / RECORD_ID)

    def test_disabled_stages_nothing_even_in_a_worktree(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            got = staging_mod.resolve(
                exp_dir=self._exp_dir(tmp, worktree=True),
                slug="fake-exp",
                record_id=RECORD_ID,
                disabled=True,
                environ=self._environ(tmp),
            )
            self.assertIsNone(got)

    def test_an_unusable_root_fails_before_anything_simulates(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            blocker = tmp / "not-a-directory"
            blocker.write_text("")
            with self.assertRaises(staging_mod.StagingError):
                staging_mod.resolve(
                    exp_dir=self._exp_dir(tmp, worktree=True),
                    slug="fake-exp",
                    record_id=RECORD_ID,
                    explicit=str(blocker),
                    environ=self._environ(tmp),
                )

    def test_a_resume_follows_an_in_tree_checkpoint(self):
        # A campaign started before this seam existed (or in the main clone)
        # checkpointed in the tree. Resuming it from a worktree must find it
        # there, not report "no checkpoint" about a directory it never used.
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            exp_dir = self._exp_dir(tmp, worktree=True)
            in_tree = exp_dir / "corners" / RECORD_ID
            in_tree.mkdir(parents=True)
            (in_tree / checkpoint_mod.CHECKPOINT_NAME).write_text("{}")
            got = staging_mod.resolve(
                exp_dir=exp_dir,
                slug="fake-exp",
                record_id=RECORD_ID,
                resuming=True,
                environ=self._environ(tmp),
            )
            self.assertIsNone(got)

    def test_a_resume_in_a_clone_finds_a_staged_campaign(self):
        # The recovery path the incident needs: the worktree that staged the
        # campaign is gone, and the checkout resuming it is an ordinary clone
        # that would not stage anything of its own.
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            exp_dir = self._exp_dir(tmp, worktree=False)
            environ = self._environ(tmp)
            staged = (
                tmp / "cache" / "sky130-pll" / "sim-stage" / "fake-exp" / RECORD_ID
            )
            staged.mkdir(parents=True)
            (staged / checkpoint_mod.CHECKPOINT_NAME).write_text("{}")
            got = staging_mod.resolve(
                exp_dir=exp_dir,
                slug="fake-exp",
                record_id=RECORD_ID,
                resuming=True,
                environ=environ,
            )
            self.assertIsNotNone(got)
            self.assertEqual(got.work_dir, staged)


class PromotionTests(unittest.TestCase):
    """What crosses from the staging directory into the committed tree."""

    def _staged(self, tmp: Path) -> staging_mod.Staging:
        work = tmp / "stage"
        work.mkdir()
        (work / "tb_fake.spice").write_text("* netlisted DUT\n")
        (work / "tt_27c_1.80v.spice").write_text("* patched\n")
        (work / "tt_27c_1.80v.log").write_text("Total analysis time\n")
        (work / ".spiceinit").write_text("set ngbehavior=hsa\n")
        (work / "tt_27c_1.80v-v-clk.raw").write_text("0 1\n")
        (work / checkpoint_mod.CHECKPOINT_NAME).write_text("{}")
        (work / ".checkpoint-abc.tmp").write_text("{}")
        return staging_mod.Staging(
            work_dir=work, final_dir=tmp / "corners" / RECORD_ID, reason="test"
        )

    def test_promotes_the_committed_classes_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            staging = self._staged(Path(tmp))
            staging_mod.promote(staging)
            landed = sorted(p.name for p in staging.final_dir.iterdir())
            self.assertEqual(
                landed,
                [".spiceinit", "tb_fake.spice", "tt_27c_1.80v.log", "tt_27c_1.80v.spice"],
            )
            # The waveform dump stays behind (sim/README.md's retention
            # policy), and so does the transient checkpoint -- promoting it
            # would put run state into the append-only evidence trail.
            self.assertTrue((staging.work_dir / "tt_27c_1.80v-v-clk.raw").is_file())
            self.assertFalse((staging.final_dir / checkpoint_mod.CHECKPOINT_NAME).exists())

    def test_promotion_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            staging = self._staged(Path(tmp))
            first = staging_mod.promote(staging)
            second = staging_mod.promote(staging)
            self.assertEqual(sorted(first), sorted(second))
            self.assertEqual(
                (staging.final_dir / "tt_27c_1.80v.log").read_text(),
                "Total analysis time\n",
            )


class FingerprintPortabilityTests(unittest.TestCase):
    """A resume must not be refused merely for happening elsewhere."""

    POINT = corners_mod.PvtPoint(corner="tt", temp_c=27.0, supply_v=1.8)

    def _fp(self, netlist: str, repo_root):
        return checkpoint_mod.fingerprint(
            mode="pvt",
            manifest=MANIFEST,
            netlist_text=netlist,
            pdk=_StubPdk(),
            units=[self.POINT],
            repo_root=repo_root,
        )

    def test_the_same_dut_from_two_checkouts_fingerprints_identically(self):
        # xschem stamps the absolute schematic path into the netlist, so the
        # same DUT netlisted from two worktrees differs textually. Before
        # #212 that alone refused the resume the incident needed.
        a_root = "/tmp/repo/.loom/worktrees/issue-202"
        b_root = "/tmp/repo/.loom/worktrees/issue-999"
        a = f"** sch_path: {a_root}/sim/fake-exp/testbench/tb_fake.sch\n{NETLIST}"
        b = f"** sch_path: {b_root}/sim/fake-exp/testbench/tb_fake.sch\n{NETLIST}"
        self.assertNotEqual(a, b)
        self.assertEqual(
            self._fp(a, a_root)["netlist_sha256"], self._fp(b, b_root)["netlist_sha256"]
        )

    def test_a_different_dut_still_refuses(self):
        root = "/tmp/repo/.loom/worktrees/issue-202"
        a = f"** sch_path: {root}/sim/fake-exp/testbench/tb_fake.sch\n{NETLIST}"
        b = f"** sch_path: {root}/sim/fake-exp/testbench/tb_other.sch\n{NETLIST}"
        self.assertNotEqual(
            self._fp(a, root)["netlist_sha256"], self._fp(b, root)["netlist_sha256"]
        )
        edited = a + "R9 CLK GND 1k\n"
        self.assertNotEqual(
            self._fp(a, root)["netlist_sha256"], self._fp(edited, root)["netlist_sha256"]
        )

    def test_a_path_outside_the_checkout_is_left_alone(self):
        root = "/tmp/repo"
        text = "** sch_path: /opt/shared/tb_fake.sch\n" + NETLIST
        self.assertEqual(checkpoint_mod.canonical_netlist_text(text, root), text)


class ReapedWorktreeTests(unittest.TestCase):
    """End to end: the incident, reproduced and then survived."""

    def _kill_after(self, n: int, reason="first segment"):
        state = {"done": 0}

        def run_point(pdk, spiceinit, manifest, netlist_text, point, work_dir):
            if state["done"] >= n:
                raise KeyboardInterrupt("simulated worktree reap, mid-point")
            state["done"] += 1
            return _point_result(point, reason=reason)

        return run_point

    def _recorder(self, reason="second segment"):
        seen = []

        def run_point(pdk, spiceinit, manifest, netlist_text, point, work_dir):
            seen.append(point.corner_id)
            (work_dir / f"{point.corner_id}.log").write_text("Total analysis time\n")
            (work_dir / f"{point.corner_id}.spice").write_text("* patched\n")
            (work_dir / f"{point.corner_id}-v-clk.raw").write_text("0 1\n")
            seen_reason = reason
            return _point_result(point, reason=seen_reason)

        return seen, run_point

    def _staged_dir(self, cache: Path, slug: str = "fake-exp") -> Path:
        return cache / "sky130-pll" / "sim-stage" / slug / RECORD_ID

    def test_a_worktree_campaign_checkpoints_outside_the_worktree(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            cache = tmp / "cache"
            wt = _make_linked_worktree(tmp / "wt", _make_clone(tmp / "main"))
            h = _Harness(wt)
            with mock.patch.dict("os.environ", {"XDG_CACHE_HOME": str(cache)}):
                with self.assertRaises(KeyboardInterrupt):
                    h.run([], self._kill_after(2))

            # Nothing about the campaign is inside the reapable checkout...
            self.assertFalse(h.checkpoint_path.exists())
            self.assertFalse((h.exp_dir / "corners").exists())
            # ...and the finished units are recorded where a reap cannot reach.
            staged = self._staged_dir(cache) / checkpoint_mod.CHECKPOINT_NAME
            self.assertTrue(staged.is_file())
            _header, done = checkpoint_mod.load(staged)
            self.assertEqual(list(done), ALL_POINT_IDS[:2])

    def test_the_campaign_survives_the_worktree_and_resumes_in_a_new_one(self):
        """`git worktree remove --force` mid-campaign, then finish it elsewhere.

        The directory removal is the whole mechanism of the incident -- the
        worktree is unlinked while units are still running -- so the test
        performs it literally, on a checkout shaped exactly like one `git
        worktree add` produces, and then asks a *different* checkout to finish
        the campaign.
        """
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            cache = tmp / "cache"
            clone = _make_clone(tmp / "main")
            first = _make_linked_worktree(tmp / "wt-a", clone)
            h1 = _Harness(first)

            with mock.patch.dict("os.environ", {"XDG_CACHE_HOME": str(cache)}):
                with self.assertRaises(KeyboardInterrupt):
                    h1.run([], self._kill_after(2))

                # The reap: the entire checkout goes, mid-campaign.
                shutil.rmtree(first)
                self.assertFalse(first.exists())

                # A fresh worktree of the same branch: same slug, same
                # manifest, same DUT -- a different directory.
                second = _make_linked_worktree(tmp / "wt-b", clone)
                h2 = _Harness(second)
                seen, run_point = self._recorder()
                rc, out = h2.run(["--resume", RECORD_ID], run_point)

            self.assertEqual(rc, 0, out)
            # Only the units the first segment never reached were simulated:
            # the 4 h 26 min that was lost in the incident is reloaded here.
            self.assertEqual(seen, ALL_POINT_IDS[2:])

            rows = _table_rows(h2.record_path.read_text())
            self.assertEqual(len(rows), len(ALL_POINT_IDS))
            self.assertEqual(sum("first segment" in r for r in rows), 2)
            self.assertEqual(sum("second segment" in r for r in rows), 4)

            # The record landed in the surviving checkout, with its evidence
            # artifacts promoted beside it in the usual place...
            corners_dir = h2.exp_dir / "corners" / RECORD_ID
            landed = sorted(p.name for p in corners_dir.iterdir())
            self.assertIn(f"{ALL_POINT_IDS[2]}.log", landed)
            self.assertIn(f"{ALL_POINT_IDS[2]}.spice", landed)
            # ...without the waveform dumps or the checkpoint.
            self.assertEqual([p for p in landed if p.endswith(".raw")], [])
            self.assertNotIn(checkpoint_mod.CHECKPOINT_NAME, landed)
            # A completed record leaves no checkpoint anywhere.
            self.assertFalse(
                (self._staged_dir(cache) / checkpoint_mod.CHECKPOINT_NAME).exists()
            )

    def test_no_stage_reproduces_the_original_loss(self):
        """The escape hatch does what it says -- and why it is not the default.

        With `--no-stage` the campaign writes into the worktree exactly as
        before, so removing the worktree takes the checkpoint with it and the
        completed units are gone. Pinning this keeps the flag honest.
        """
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            cache = tmp / "cache"
            clone = _make_clone(tmp / "main")
            first = _make_linked_worktree(tmp / "wt-a", clone)
            h1 = _Harness(first)

            with mock.patch.dict("os.environ", {"XDG_CACHE_HOME": str(cache)}):
                with self.assertRaises(KeyboardInterrupt):
                    h1.run(["--no-stage"], self._kill_after(2))
                self.assertTrue(h1.checkpoint_path.is_file())
                shutil.rmtree(first)

                second = _make_linked_worktree(tmp / "wt-b", clone)
                h2 = _Harness(second)
                seen, run_point = self._recorder()
                rc, out = h2.run(["--resume", RECORD_ID], run_point)

            self.assertEqual(rc, 1)
            self.assertIn("no checkpoint", out)
            self.assertEqual(seen, [])
            self.assertFalse(h2.record_path.exists())

    def test_a_normal_clone_run_is_unchanged(self):
        """The additive half of the change: no worktree, no staging, and the
        record plus its artifacts land exactly where they always did."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            cache = tmp / "cache"
            h = _Harness(_make_clone(tmp / "main"))
            seen, run_point = self._recorder(reason="ok")
            with mock.patch.dict("os.environ", {"XDG_CACHE_HOME": str(cache)}):
                rc, out = h.run([], run_point)

            self.assertEqual(rc, 0, out)
            self.assertEqual(seen, ALL_POINT_IDS)
            self.assertFalse(cache.exists())  # nothing was staged at all
            self.assertNotIn("staging this campaign's work", out)
            corners_dir = h.exp_dir / "corners" / RECORD_ID
            # Including the waveform dumps, which an unstaged run has always
            # left in place next to the logs.
            self.assertTrue((corners_dir / f"{ALL_POINT_IDS[0]}-v-clk.raw").is_file())
            self.assertFalse((corners_dir / checkpoint_mod.CHECKPOINT_NAME).exists())
            # An uninterrupted serial run's record shape is untouched: no
            # execution note, and no mention of where the work was staged.
            text = h.record_path.read_text()
            self.assertNotIn("**Execution**", text)
            self.assertNotIn("sim-stage", text)

    def test_a_staged_run_mints_the_same_record_as_an_unstaged_one(self):
        """Staging changes where ngspice's scratch went, nothing else."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            plain = _Harness(_make_clone(tmp / "main"), slug="fake-exp")
            _seen_a, run_a = self._recorder(reason="ok")
            rc_a, out_a = plain.run([], run_a)

            worktree = _make_linked_worktree(tmp / "wt", _make_clone(tmp / "other"))
            staged = _Harness(worktree, slug="fake-exp")
            _seen_b, run_b = self._recorder(reason="ok")
            with mock.patch.dict("os.environ", {"XDG_CACHE_HOME": str(tmp / "cache")}):
                rc_b, out_b = staged.run([], run_b)

            self.assertEqual((rc_a, rc_b), (0, 0), out_a + out_b)
            # Byte-identical but for the run's own wall-clock stamp, which
            # differs between any two runs, staged or not.
            self.assertEqual(
                _without_run_time(plain.record_path.read_text()),
                _without_run_time(staged.record_path.read_text()),
            )
            # The promoted tree holds exactly what an unstaged run committed:
            # the waveform dumps are the only difference, and they are not
            # committed evidence either way (sim/README.md's retention policy).
            promoted = sorted(
                p.name for p in (staged.exp_dir / "corners" / RECORD_ID).iterdir()
            )
            unstaged = sorted(
                p.name
                for p in (plain.exp_dir / "corners" / RECORD_ID).iterdir()
                if not p.name.endswith(".raw")
            )
            self.assertEqual(promoted, unstaged)


if __name__ == "__main__":
    unittest.main()
