import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class CliTests(unittest.TestCase):
    def test_bench_writes_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "bench.json"
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "deoptscope",
                    "bench",
                    "--kernel",
                    "int_loop",
                    "--samples",
                    "60",
                    "--blocks",
                    "2",
                    "--warmup",
                    "10",
                    "--out",
                    str(out),
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(out.read_text())
            self.assertIn("int_loop", payload["results"])
            self.assertEqual(payload["results"]["int_loop"]["correctness"]["mismatches"], 0)

    def test_unknown_kernel_fails(self):
        proc = subprocess.run(
            [sys.executable, "-m", "deoptscope", "bench", "--kernel", "nope",
             "--samples", "20", "--blocks", "2", "--warmup", "5"],
            capture_output=True, text=True, timeout=60,
        )
        self.assertNotEqual(proc.returncode, 0)


if __name__ == "__main__":
    unittest.main()
