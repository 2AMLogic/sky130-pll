"""Shared `klt sim --backend batch` submit with capacity retry.

The fleet is shared and capped. A launch refused for capacity ran nothing, so
waiting and resubmitting the same job is safe; any other failure is returned
to the caller to judge. There is never a local fallback. Stdlib only.
"""

from __future__ import annotations

CAPACITY_MARKERS = ("BATCH_MAX_CONCURRENT_INSTANCES", "batch_no_capacity", "no capacity in any")


def is_capacity_refusal(text: str) -> bool:
    """True when a `klt sim` failure is the fleet refusing to launch for lack of
    capacity (the job never started), as opposed to a job that ran and failed."""
    return any(m in text for m in CAPACITY_MARKERS)


def submit_with_capacity_retry(cmd, *, runner, timeout, usable_exit, retries, wait_s, sleep,
                               log, label):
    """Run `cmd`, resubmitting while the fleet refuses for capacity, at most
    `retries` times, `wait_s` apart. -> (proc, attempts), `attempts` being the
    number of retries made. `OSError` / `subprocess.TimeoutExpired` from
    `runner` propagate; each caller owns how that failure is reported."""
    attempt = 0
    while True:
        proc = runner(cmd, capture_output=True, text=True, timeout=timeout)
        if (proc.returncode not in usable_exit and attempt < retries
                and is_capacity_refusal((proc.stdout or "") + (proc.stderr or ""))):
            attempt += 1
            log(f"{label}: fleet at capacity; retry {attempt}/{retries} in {wait_s:g}s")
            sleep(wait_s)
            continue
        return proc, attempt
