"""Confirmed SH-082451Q / SH-081802ENG-K terminal facts, independent of layout."""
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class IqfManualCorrectionsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.items = {}
        for path in (ROOT / "parts/plc/mitsubishi/iq_f").glob("*/*.json"):
            item = json.loads(path.read_text(encoding="utf-8-sig"))
            cls.items[item["model"]] = item["definition"]

    def test_all_existing_models_keep_a_source(self):
        self.assertTrue(self.items)
        for model, spec in self.items.items():
            with self.subTest(model=model):
                self.assertTrue(spec.get("source"))

    def test_grounding_points_and_actual_markings(self):
        ad = self.items["FX5-4AD"]
        da = self.items["FX5-4DA"]
        self.assertEqual(ad["power"], ["FG"] * 4)
        self.assertEqual([x["side"] for x in ad["power_terminal_details"]],
                         ["left", "left", "right", "right"])
        self.assertTrue(all("internal_group" not in x for x in ad["power_terminal_details"]))
        self.assertEqual(da["power"], ["24V", "24G", "接地", "接地"])
        self.assertEqual(da["power_pins"], ["24V", "24G", "⏚", "⏚"])
        self.assertEqual([x["internal_group"] for x in da["power_terminal_details"][-2:]],
                         ["ground", "ground"])

    def test_common_contact_counts_from_terminal_drawings(self):
        # Counts from HW PDF102/103/113/116/122, not electrical I/O counts.
        expected = {
            "FX5UC-32MR/DS-TS": (4, 4),
            "FX5UC-32MT/D": (2, 2), "FX5UC-32MT/DSS": (2, 2),
            "FX5UC-32MT/DS-TS": (2, 2), "FX5UC-32MT/DSS-TS": (2, 2),
            "FX5UC-64MT/D": (4, 4), "FX5UC-64MT/DSS": (4, 4),
            "FX5UC-96MT/D": (6, 6), "FX5UC-96MT/DSS": (6, 6),
            "FX5-C16EX/D": (2, 0), "FX5-C16EX/DS": (2, 0),
            "FX5-C16EYR/D-TS": (0, 4),
            "FX5-C16EYT/D": (0, 2), "FX5-C16EYT/DSS": (0, 2),
            "FX5-C32ET/D": (2, 2), "FX5-C32ET/DS-TS": (2, 2),
            "FX5-C32ET/DSS": (2, 2), "FX5-C32ET/DSS-TS": (2, 2),
            "FX5-C32EX/D": (4, 0), "FX5-C32EX/DS": (4, 0),
            "FX5-C32EX/DS-TS": (4, 0),
            "FX5-C32EYT/D": (0, 4), "FX5-C32EYT/D-TS": (0, 4),
            "FX5-C32EYT/DSS": (0, 4), "FX5-C32EYT/DSS-TS": (0, 4),
        }
        actual = {m for m, s in self.items.items() if "physical_io" in s}
        self.assertEqual(actual, set(expected))
        for model, counts in expected.items():
            with self.subTest(model=model):
                spec = self.items[model]
                io = spec["physical_io"]
                self.assertEqual(tuple(sum(c["contacts"] for c in io[k])
                                       for k in ("input_commons", "output_commons")), counts)
                addresses = [int(c["start"], 8) + i for c in io["input_commons"]
                             for i in range(c["points"])]
                self.assertEqual(addresses, list(range(spec["inputs"])))
                self.assertEqual([c["group"] for c in io["output_commons"]],
                                 [g[0] for g in spec["outputs"]])
                self.assertEqual(io["source"]["document"], "SH-082451Q")
                self.assertTrue(io["source"]["section"])
                self.assertTrue(io["source"]["printed_pages"])
                self.assertTrue(io["source"]["pdf_pages"])

    def test_repeated_signal_contacts_are_only_confirmed_ts_relay_models(self):
        for model, spec in self.items.items():
            if "physical_io" not in spec:
                continue
            io = spec["physical_io"]
            self.assertEqual(io["input_signal_contacts"],
                             2 if model == "FX5UC-32MR/DS-TS" else 1)
            self.assertEqual(io["output_signal_contacts"],
                             2 if model in ("FX5UC-32MR/DS-TS", "FX5-C16EYR/D-TS") else 1)

    def test_connector_signal_and_unused_pin_partition(self):
        for model in ("FX5-232-BD", "FX5-232ADP"):
            c = self.items[model]["connector"]
            self.assertEqual((c["type"], c["pins"], c["gender"]), ("D-sub", 9, "male"))
            self.assertEqual(c["signals"], {"1": "CD", "2": "RD", "3": "SD",
                                            "4": "ER", "5": "SG", "6": "DR"})
            self.assertEqual(c["unused_pins"], ["7", "8", "9"])
            self.assertFalse(set(c["signals"]) & set(c["unused_pins"]))
        for model in ("FX5-8AD", "FX5UC-32MT/D"):
            pins = self.items[model]["power_terminal_details"]
            self.assertEqual([(x["pin"], x["name"], x["wire_color"]) for x in pins],
                             [("1", "+", "赤"), ("2", "-", "黒"), ("3", "⏚", "緑")])

    def test_current_input_and_temperature_conditions_are_model_specific(self):
        for model, required in (("FX5-4A-ADP", True), ("FX5-4AD-ADP", True),
                                ("FX5-4AD", False), ("FX5-8AD", False),
                                ("FX5-3A-BD", False)):
            self.assertIs(self.items[model]["current_input_jumper"], required)
        self.assertEqual(self.items["FX5-4AD-PT-ADP"]["sensor_wire_count"], 3)
        self.assertTrue(self.items["FX5-4AD-TC-ADP"]["isolated_sensor_required"])


if __name__ == "__main__":
    unittest.main()
