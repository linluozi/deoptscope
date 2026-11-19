import json
import unittest

from deoptscope.census import (
    ADAPTIVE_BASES,
    SPECIALIZED_TO_BASE,
    census_code,
    classify,
    profile_workload,
    quickened_ratio,
)
from deoptscope.kernels import int_loop


def warm(fn, *args, times=300):
    for _ in range(times):
        fn(*args)


class ClassifyTests(unittest.TestCase):
    def test_specialized_and_generic(self):
        self.assertEqual(classify("LOAD_GLOBAL_BUILTIN"), ("specialized", "LOAD_GLOBAL"))
        self.assertEqual(classify("LOAD_GLOBAL"), ("generic", "LOAD_GLOBAL"))
        self.assertEqual(classify("BINARY_OP_ADD_INT"), ("specialized", "BINARY_OP"))
        self.assertEqual(classify("BINARY_OP"), ("generic", "BINARY_OP"))

    def test_fused_and_fixed(self):
        self.assertEqual(classify("LOAD_FAST__LOAD_CONST"), ("fused", None))
        self.assertEqual(classify("RETURN_VALUE"), ("fixed", None))

    def test_every_specialization_maps_to_adaptive_base(self):
        self.assertGreater(len(SPECIALIZED_TO_BASE), 20)
        for specialized, base in SPECIALIZED_TO_BASE.items():
            if "__" in specialized:  # fused superinstruction, not a variant
                continue
            self.assertIn(base, ADAPTIVE_BASES, msg=specialized)
        self.assertNotIn("LOAD_CONST", ADAPTIVE_BASES)
        self.assertNotIn("LOAD_FAST", ADAPTIVE_BASES)


class CensusTests(unittest.TestCase):
    def test_warm_function_has_specialized_slots(self):
        warm(int_loop, 60)
        c = census_code(int_loop.__code__)
        self.assertGreater(c.specialized, 0)
        self.assertIsNotNone(c.quickened_ratio)
        self.assertEqual(
            c.slots, c.specialized + c.generic + c.fused + c.fixed
        )
        opnames = {s.opname for s in c.sites}
        self.assertIn("BINARY_OP_ADD_INT", opnames)
        self.assertIn("FOR_ITER_RANGE", opnames)

    def test_fresh_code_object_is_unquickened(self):
        from deoptscope.bench import make_fresh_function

        warm(int_loop, 60)
        clone = make_fresh_function(int_loop)
        fresh = census_code(clone.__code__)
        self.assertEqual(fresh.specialized, 0)
        self.assertGreater(fresh.generic, 0)
        self.assertIsNone(quickened_ratio(clone.__code__) if fresh.adaptive == 0 else None)

    def test_census_does_not_mutate_state(self):
        warm(int_loop, 60)
        before = census_code(int_loop.__code__).as_dict(include_sites=True)
        again = census_code(int_loop.__code__).as_dict(include_sites=True)
        self.assertEqual(before, again)

    def test_profile_counts_calls_and_attributes_generic_sites(self):
        def inner(n):
            return sum(range(n))

        def outer(n):
            total = 0
            for _ in range(4):
                total += inner(n)
            return total

        result = profile_workload(outer, 40, warmup=5)
        self.assertEqual(result["profiled_calls"], 5)  # 1 outer + 4 inner
        self.assertEqual(result["code_objects"], 2)
        self.assertEqual(result["python"].count("."), 2)
        self.assertGreater(result["slots"]["adaptive"], 0)
        self.assertIsNotNone(result["quickened_ratio_unique"])
        # JSON-safe, sites are plain dicts
        json.dumps(result)
        names = [row["qualname"] for row in result["hot_functions"]]
        self.assertEqual(len(names), 2)
        self.assertTrue(any(name.endswith("outer") for name in names), names)
        self.assertTrue(any(name.endswith("inner") for name in names), names)
        for site in result["generic_sites"]:
            self.assertEqual(site["opname"], site["base"])
            self.assertGreater(site["weighted_calls"], 0)

    def test_monitoring_does_not_change_census(self):
        warm(int_loop, 80)
        before = census_code(int_loop.__code__)
        profile_workload(int_loop, 40, warmup=1)
        after = census_code(int_loop.__code__)
        self.assertEqual(before.specialized, after.specialized)
        self.assertEqual(before.generic, after.generic)

    def test_warmup_must_be_positive(self):
        with self.assertRaises(ValueError):
            profile_workload(int_loop, 10, warmup=0)


if __name__ == "__main__":
    unittest.main()
