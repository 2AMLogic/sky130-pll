"""Issue #441: `sim/harness/` has exactly one digest surface, and it is pinned.

Before this, four text/bytes hashers and two file hashers were hand-rolled
across six modules -- and two of them, `report.sha256_file` and
`evidence_store.sha256_file`, shared a name in one package while returning
different types (`str` vs `tuple[str, int]`). An import swapped between those
two does not raise at the import site; it fails later, where a digest is
written into an append-only `sim/` record that cannot be edited, only
superseded.

So this file does two jobs:

1. **Pin the digests.** The consolidation rested on the claim that every
   deleted body fed the same bytes to `hashlib.sha256`: `.encode()` is
   `.encode("utf-8")`, and chunked `read(1 << 20)` updates equal one
   `read_bytes()`. Each is asserted directly, including over non-ASCII text
   and a payload that straddles the 1 MiB chunk boundary.
2. **Keep the surface from eroding.** A source scan fails if any module
   outside the two sanctioned ones re-rolls `hashlib` for a digest, so the
   next copy is a test failure rather than a sixth helper.

Stdlib only.
"""

from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = SIM_DIR.parent
sys.path.insert(0, str(SIM_DIR))

from harness import evidence_store as es  # noqa: E402
from harness import report  # noqa: E402

#: Payloads chosen for the edges: empty, every byte value, a NUL run, and a
#: blob 7 bytes past the 1 MiB chunk `sha256_file_with_size` reads in.
BLOBS = {
    "empty": b"",
    "ascii": b"hello world",
    "nul-run": b"\x00" * 64,
    "all-byte-values": bytes(range(256)),
    "straddles-1mib-chunk": b"x" * ((1 << 20) + 7),
}

#: Text whose UTF-8 encoding is not its ASCII bytes -- BMP, a combining mark
#: and an astral-plane character. This is where `.encode()` and
#: `.encode("utf-8")` would diverge if they ever could.
TEXTS = {
    "empty": "",
    "ascii": "a netlist line\n",
    "non-ascii": "mu=µ ohm=Ω deg=° é \U0001f512",
    "crlf": "a\r\nb\n",
}


class TestCanonicalPair(unittest.TestCase):
    """`report.sha256_bytes` / `report.sha256_file` against plain `hashlib`."""

    def test_sha256_bytes_matches_hashlib(self):
        for name, blob in BLOBS.items():
            with self.subTest(blob=name):
                self.assertEqual(report.sha256_bytes(blob),
                                 hashlib.sha256(blob).hexdigest())

    def test_sha256_bytes_returns_a_bare_hex_string(self):
        digest = report.sha256_bytes(b"x")
        self.assertIsInstance(digest, str)
        self.assertEqual(len(digest), 64)
        self.assertEqual(digest, digest.lower().strip())

    def test_default_encode_is_utf8_encode(self):
        # The claim the four deleted text hashers collapsed on: `.encode()`
        # and `.encode("utf-8")` are the same bytes, so the digest is too.
        for name, text in TEXTS.items():
            with self.subTest(text=name):
                self.assertEqual(text.encode(), text.encode("utf-8"))
                self.assertEqual(report.sha256_bytes(text.encode()),
                                 report.sha256_bytes(text.encode("utf-8")))

    def test_sha256_file_matches_hashlib_over_the_bytes(self):
        with tempfile.TemporaryDirectory() as td:
            for name, blob in BLOBS.items():
                p = Path(td) / f"{name}.bin"
                p.write_bytes(blob)
                with self.subTest(blob=name):
                    self.assertEqual(report.sha256_file(p),
                                     hashlib.sha256(blob).hexdigest())
                    self.assertEqual(report.sha256_file(p),
                                     report.sha256_bytes(blob))

    def test_sha256_file_over_committed_design_files(self):
        # Real inputs on the path that writes digests into `sim/` records.
        files = sorted(REPO_ROOT.glob("design/*/netlist/*.spice"))
        files.append(SIM_DIR / "pdk.json")
        self.assertGreater(len(files), 3, "expected committed netlists to hash")
        for p in files:
            with self.subTest(path=p.name):
                self.assertEqual(report.sha256_file(p),
                                 hashlib.sha256(p.read_bytes()).hexdigest())


class TestStreamingVariant(unittest.TestCase):
    """`evidence_store.sha256_file_with_size` is the only other hasher, and it
    agrees with the canonical one on the digest while adding the byte count."""

    def test_name_collision_is_gone(self):
        # The defect this issue closed: two same-named functions in one
        # package returning different types. `report` keeps the name.
        self.assertFalse(hasattr(es, "sha256_file"),
                         "evidence_store must not re-export the name "
                         "`sha256_file`; that collided with report's")
        self.assertTrue(callable(es.sha256_file_with_size))
        self.assertTrue(callable(report.sha256_file))

    def test_return_shapes_stay_distinguishable(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "a.bin"
            p.write_bytes(b"abc")
            self.assertIsInstance(report.sha256_file(p), str)
            got = es.sha256_file_with_size(p)
            self.assertIsInstance(got, tuple)
            self.assertEqual(len(got), 2)
            self.assertIsInstance(got[0], str)
            self.assertIsInstance(got[1], int)

    def test_chunked_reads_equal_one_read_bytes(self):
        # The claim the file-hasher consolidation rested on. `big` is past the
        # 1 MiB chunk, so this exercises more than one `update`.
        with tempfile.TemporaryDirectory() as td:
            for name, blob in BLOBS.items():
                p = Path(td) / f"{name}.bin"
                p.write_bytes(blob)
                sha, size = es.sha256_file_with_size(p)
                with self.subTest(blob=name):
                    self.assertEqual(sha, report.sha256_file(p))
                    self.assertEqual(sha, hashlib.sha256(blob).hexdigest())
                    self.assertEqual(size, len(blob))
                    self.assertEqual(size, p.stat().st_size)

    def test_agrees_with_report_on_committed_files(self):
        files = sorted(REPO_ROOT.glob("design/*/netlist/*.spice"))
        self.assertGreater(len(files), 3)
        for p in files:
            with self.subTest(path=p.name):
                sha, size = es.sha256_file_with_size(p)
                self.assertEqual(sha, report.sha256_file(p))
                self.assertEqual(size, p.stat().st_size)


class TestNoNewHashers(unittest.TestCase):
    """Source guard: only the two sanctioned modules may touch `hashlib`.

    This is the structural half of the fix. The consolidation is only worth
    doing once if a sixth copy cannot quietly reappear, and a docstring asking
    callers not to re-roll `hashlib` is exactly what failed the first time.
    """

    #: `report.py` defines the canonical pair. `evidence_store.py` is
    #: stdlib-only by design (it is the module that must not import the rest
    #: of the harness), so it keeps its own streaming implementation.
    ALLOWED = {"report.py", "evidence_store.py"}

    #: Scanned: the harness package, plus the one module outside it that this
    #: issue repointed. `sim/phase-quadrature-model/run_cases.py` is
    #: deliberately NOT scanned -- its own sha256 is pinned inside an
    #: append-only record it reproduces byte-for-byte under `--check`, so
    #: editing it would invalidate committed evidence.
    def _scanned(self):
        paths = sorted((SIM_DIR / "harness").glob("*.py"))
        paths.append(SIM_DIR / "power" / "mint.py")
        return paths

    def test_only_sanctioned_modules_import_hashlib(self):
        paths = self._scanned()
        self.assertGreater(len(paths), 5, "expected to scan the harness package")
        offenders = []
        for p in paths:
            src = p.read_text(encoding="utf-8")
            uses = "hashlib.sha256" in src or "import hashlib" in src
            if uses and p.name not in self.ALLOWED:
                offenders.append(p.relative_to(REPO_ROOT).as_posix())
        self.assertEqual(offenders, [], "these modules re-roll hashlib instead "
                         "of calling report.sha256_bytes / report.sha256_file "
                         "(or evidence_store.sha256_file_with_size when the "
                         f"byte count is needed): {offenders}")

    def test_the_sanctioned_modules_are_actually_present(self):
        # Guards the guard: if report.py or evidence_store.py were renamed,
        # ALLOWED would silently stop matching anything and the scan above
        # would pass for the wrong reason.
        names = {p.name for p in self._scanned()}
        self.assertTrue(self.ALLOWED <= names, f"{self.ALLOWED} not in {names}")
        for name in self.ALLOWED:
            src = (SIM_DIR / "harness" / name).read_text(encoding="utf-8")
            self.assertIn("import hashlib", src,
                          f"{name} is allowlisted but no longer hashes anything")


if __name__ == "__main__":
    unittest.main()
