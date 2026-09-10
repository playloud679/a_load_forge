"""Regression checks for unit and provenance errors hidden by derived T/S."""
import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "audit", Path(__file__).resolve().parents[1] / "tools/audit_catalog_consistency.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class AuditTests(unittest.TestCase):
    def test_declared_size_detects_hidden_sd_error(self):
        row = {"model": 'Subwoofer 12"', "size_in": 5, "driver": {"sd_cm2": 79.2}}
        codes = {x["code"] for x in module.audit(row)}
        self.assertIn("declared_size_sd_mismatch", codes)
        self.assertIn("declared_size_conflict", codes)

    def test_multiple_nominal_diameters(self):
        for size, sd in ((4, 50), (6.5, 132), (8, 220), (10, 350), (12, 530), (15, 855), (18, 1210), (21, 1680)):
            row = {"model": f'{size} inch woofer', "size_in": size, "driver": {"sd_cm2": sd}}
            self.assertFalse(any(x["code"] == "declared_size_sd_mismatch" for x in module.audit(row)))
            row["driver"]["sd_cm2"] /= 6.4516
            self.assertTrue(any(x["code"] == "declared_size_sd_mismatch" for x in module.audit(row)))

    def test_imperial_values_require_conversion(self):
        row = {"driver": {"vas_l": 4.19}, "website_fields": {
            "raw_measurements": {"vas_l": {"raw_value": "4.19", "unit": "cu ft"}}}}
        errors = [x for x in module.audit(row) if x["code"] == "source_unit_conversion"]
        self.assertEqual(len(errors), 1)
        self.assertAlmostEqual(errors[0]["evidence"]["expected"], 118.64758722048)
        row["driver"]["vas_l"] = 118.67
        self.assertFalse(any(x["code"] == "source_unit_conversion" for x in module.audit(row)))

    def test_size_repair_does_not_hide_missing_units(self):
        row = {"driver": {"sd_cm2": 79.2}, "size_in": 5,
               "website_fields": {"field_corrections": {"size_in": {"new_value": 5}},
                                  "raw_measurements": {"sd_cm2": {"raw_value": "79.2", "unit": ""}}}}
        codes = {x["code"] for x in module.audit(row)}
        self.assertIn("size_correction_requires_source_review", codes)
        self.assertIn("missing_source_unit", codes)

    def test_derived_inputs_are_not_independent_evidence(self):
        issues = module.audit({"driver": {}, "website_fields": {"derived_fields": ["mms_g"]}})
        self.assertTrue(any(x["code"] == "derived_values_not_independent_validation" for x in issues))


if __name__ == "__main__":
    unittest.main()
