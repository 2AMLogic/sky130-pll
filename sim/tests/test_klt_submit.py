import subprocess
import unittest
from types import SimpleNamespace

from sim.harness import klt_submit as S

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


if __name__ == "__main__":
    unittest.main()
