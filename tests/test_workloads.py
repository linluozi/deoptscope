import unittest

from deoptscope import workloads
from deoptscope.census import profile_workload


class WorkloadTests(unittest.TestCase):
    def test_corpus_exists_and_is_real_text(self):
        text = workloads.CORPUS.read_text(encoding="utf-8")
        self.assertGreater(len(text), 3000)
        self.assertIn("## ", text)

    def test_each_available_workload_executes(self):
        for name in sorted(workloads.WORKLOADS):
            with self.subTest(workload=name):
                try:
                    fn = workloads.get(name)
                except Exception as exc:  # optional experiment dependency
                    self.skipTest(f"{name} unavailable: {exc}")
                result = profile_workload(fn, warmup=3)
                self.assertGreater(result["profiled_calls"], 0)
                self.assertGreater(result["code_objects"], 3)
                self.assertGreater(result["slots"]["adaptive"], 0)
                self.assertGreater(result["quickened_ratio_unique"], 0.5)


if __name__ == "__main__":
    unittest.main()
