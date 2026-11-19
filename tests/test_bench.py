import unittest

from deoptscope.bench import cold_vs_warm, make_fresh_function
from deoptscope.kernels import KERNELS, int_loop


class FreshCloneTests(unittest.TestCase):
    def test_clone_keeps_defaults_and_closure(self):
        def scale(n, factor=3):
            return n * factor

        clone = make_fresh_function(scale)
        self.assertEqual(clone(7), 21)
        self.assertEqual(clone(7, 5), 35)
        self.assertIsNot(clone.__code__, scale.__code__)

    def test_closure_value_is_shared(self):
        base = 10

        def add(n):
            return n + base

        self.assertEqual(make_fresh_function(add)(5), 15)

    def test_rejects_builtin(self):
        with self.assertRaises(TypeError):
            make_fresh_function(len)


class ColdVsWarmTests(unittest.TestCase):
    def test_distribution_shape_and_correctness(self):
        result = cold_vs_warm(int_loop, 80, samples=120, blocks=3, warmup=40)
        self.assertEqual(result["samples_per_mode"], 120)
        self.assertEqual(len(result["raw"]), 240)
        self.assertEqual(result["correctness"]["mismatches"], 0)
        self.assertGreaterEqual(result["correctness"]["checked"], 20)
        warm = result["warm"]
        cold = result["cold"]
        self.assertLessEqual(warm["p25_ns"], warm["median_ns"])
        self.assertLessEqual(warm["median_ns"], warm["p75_ns"])
        self.assertLessEqual(cold["p25_ns"], cold["median_ns"])
        self.assertLessEqual(cold["median_ns"], cold["p75_ns"])
        self.assertGreater(warm["median_ns"], 0)
        self.assertAlmostEqual(
            result["slowdown_without_quickening"],
            cold["median_ns"] / warm["median_ns"],
            places=9,
        )
        modes = {row["mode"] for row in result["raw"]}
        self.assertEqual(modes, {"warm", "cold"})

    def test_bad_arguments(self):
        with self.assertRaises(ValueError):
            cold_vs_warm(int_loop, 10, samples=5, blocks=10)
        with self.assertRaises(ValueError):
            cold_vs_warm(int_loop, 10, samples=10, blocks=0)

    def test_every_kernel_is_deterministic(self):
        for name, (fn, args, kwargs) in KERNELS.items():
            with self.subTest(kernel=name):
                self.assertEqual(fn(*args, **kwargs), fn(*args, **kwargs))


if __name__ == "__main__":
    unittest.main()
