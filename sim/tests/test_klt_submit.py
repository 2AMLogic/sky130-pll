import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from sim.harness import klt_submit as S  # noqa: E402

CAP = SimpleNamespace(returncode=1, stdout='{"error": "batch_no_capacity"}', stderr="")
OK = SimpleNamespace(returncode=0, stdout="{}", stderr="")
BAD = SimpleNamespace(returncode=2, stdout="", stderr="boom")


def submit(results, retries=2, usable=(0, 3)):
    calls, waits, logs = [], [], []

    def runner(cmd, **kw):
        calls.append((cmd, kw))
        r = results[len(calls) - 1]
        if isinstance(r, Exception):
            raise r
        return r

    out = S.submit_with_capacity_retry(
        ["klt"], runner=runner, timeout=7, usable_exit=usable, retries=retries, wait_s=1.5,
        sleep=waits.append, log=logs.append, label="L")
    return out, calls, waits, logs


class SubmitWithCapacityRetry(unittest.TestCase):
    def test_predicate(self):
        self.assertTrue(S.is_capacity_refusal("x no capacity in any region"))
        self.assertFalse(S.is_capacity_refusal("simulation failed"))

    def test_retries_then_succeeds(self):
        (proc, attempts), calls, waits, logs = submit([CAP, CAP, OK])
        self.assertIs(proc, OK)
        self.assertEqual((attempts, len(calls), waits), (2, 3, [1.5, 1.5]))
        self.assertEqual(calls[0][1]["timeout"], 7)
        self.assertIn("retry 1/2", logs[0])

    def test_persistent_refusal_stops_at_bound(self):
        (proc, attempts), calls, _, _ = submit([CAP] * 5)
        self.assertIs(proc, CAP)
        self.assertEqual((attempts, len(calls)), (2, 3))

    def test_other_failure_not_retried(self):
        (proc, attempts), calls, _, _ = submit([BAD, OK])
        self.assertEqual((proc, attempts, len(calls)), (BAD, 0, 1))

    def test_usable_exit_not_retried(self):
        refused_but_usable = SimpleNamespace(returncode=4, stdout="batch_no_capacity", stderr="")
        (_, attempts), _, _, _ = submit([refused_but_usable], usable=(0, 3, 4))
        self.assertEqual(attempts, 0)

    def test_runner_errors_propagate(self):
        with self.assertRaises(subprocess.TimeoutExpired):
            submit([subprocess.TimeoutExpired("klt", 7)])


class ResolveKlt(unittest.TestCase):
    def test_explicit_argument_wins(self):
        self.assertEqual(S.resolve_klt("bin/klt", environ={"SKY130_PLL_KLT": "other/klt"}),
                         "bin/klt")

    def test_env_var_before_path_lookup(self):
        self.assertEqual(S.resolve_klt(None, environ={"SKY130_PLL_KLT": "env/klt"}), "env/klt")

    def test_path_lookup_last(self):
        with mock.patch.object(S.shutil, "which", return_value="/usr/bin/klt"):
            self.assertEqual(S.resolve_klt(None, environ={}), "/usr/bin/klt")

    def test_unresolved_returns_none(self):
        with mock.patch.object(S.shutil, "which", return_value=None):
            self.assertIsNone(S.resolve_klt(None, environ={}))


class PreflightBatch(unittest.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.tmp = Path(td.name)
        self.prov = self.tmp / "prov.sh"
        self.prov.write_text("")

    def env(self, prov=None):
        return {"KLT_BATCH_PROVISION_SCRIPT": str(self.prov if prov is None else prov)}

    def test_passing_check_returns_klt(self):
        self.assertEqual(S.preflight_batch("bin/klt", environ=self.env()), "bin/klt")

    def test_missing_klt(self):
        with self.assertRaises(RuntimeError) as cm:
            S.preflight_batch(None, environ=self.env())
        self.assertEqual(str(cm.exception),
                         "`klt` is not on PATH (set SKY130_PLL_KLT to its path)")

    def test_missing_provision_variable(self):
        with self.assertRaises(RuntimeError) as cm:
            S.preflight_batch("bin/klt", environ={})
        self.assertEqual(str(cm.exception),
                         "KLT_BATCH_PROVISION_SCRIPT does not name an existing "
                         "batch-fleet-provision.sh")

    def test_nonexistent_provision_script(self):
        with self.assertRaises(RuntimeError) as cm:
            S.preflight_batch("bin/klt", environ=self.env(prov=self.tmp / "absent.sh"))
        self.assertEqual(str(cm.exception),
                         "KLT_BATCH_PROVISION_SCRIPT does not name an existing "
                         "batch-fleet-provision.sh")

    def test_custom_error_class(self):
        class Marker(RuntimeError):
            pass

        with self.assertRaises(Marker):
            S.preflight_batch(None, environ=self.env(), error_cls=Marker)


if __name__ == "__main__":
    unittest.main()
