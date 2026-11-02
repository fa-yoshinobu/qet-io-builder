"""Q-series regression anchors from the official terminal tables.

Document and page references are recorded in the model definitions.
"""
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "parts/plc/mitsubishi/q"


def definition(category, model):
    return json.loads((ROOT / category / (model + ".json")).read_text(encoding="utf-8"))["definition"]


class QManualFixesTest(unittest.TestCase):
    def test_all_analog_signal_and_auxiliary_pin_numbers_are_explicit(self):
        for path in (ROOT / "analog_io").glob("*.json"):
            spec = definition("analog_io", path.stem)
            with self.subTest(model=path.stem):
                pins = spec["pins_by_channel"]
                self.assertEqual(len(pins), len(spec["channels"]))
                used = []
                for i, direction in enumerate(spec["channels"]):
                    terms = spec.get("terminals_by_channel", [])[i] if spec.get("terminals_by_channel") else spec.get("terminals_by_direction", {}).get(direction, spec["terminals"])
                    self.assertEqual(len(pins[i]), len(terms))
                    used.extend(pins[i])
                used.extend(spec.get("power_pins", []))
                used.extend(item["pin"] for item in spec.get("auxiliary_terminals", []))
                self.assertEqual(len(used), len(set(used)), "signal/power/auxiliary pin overlap")

    def test_isolated_da_has_channel_specific_common_and_different_channel_two_pins(self):
        spec = definition("analog_io", "Q62DA-FG")
        self.assertEqual(spec["pins_by_channel"], [["1", "2", "3"], ["9", "10", "11"]])
        self.assertEqual([spec["terminals"][1].format(n=n) for n in (1, 2)], ["COM1", "COM2"])
        self.assertTrue(spec["channel_isolation"])
        self.assertIn("SH-080281E-N", spec["source"])

    def test_dah_has_three_shield_terminals_not_four(self):
        spec = definition("analog_io", "Q64DAH")
        self.assertEqual([(p["pin"], p["signal"]) for p in spec["auxiliary_terminals"]], [("4", "SLD"), ("8", "SLD"), ("12", "SLD")])
        self.assertEqual(spec["power_pins"], ["16", "17", "18"])
        self.assertIn("SH-081101ENG-B", spec["source"])

    def test_eight_channel_da_ground_is_outside_eighteen_pin_block(self):
        for model in ("Q68DAVN", "Q68DAIN"):
            spec = definition("analog_io", model)
            with self.subTest(model=model):
                self.assertEqual(spec["pins_by_channel"][-1], ["15", "16"])
                self.assertEqual(list(zip(spec["power_pins"], spec["power"])), [("17", "24V"), ("18", "24G"), ("FGねじ", "FG")])

    def test_combined_module_keeps_signal_eighteen_separate_from_power_connector(self):
        spec = definition("analog_io", "Q64AD2DA")
        self.assertEqual(spec["channels"], ["入力"] * 4 + ["出力"] * 2)
        self.assertEqual(spec["pins_by_channel"][4:], [["13", "14", "15"], ["16", "17", "18"]])
        self.assertEqual(spec["power_connection"], "separate_connector")
        self.assertEqual(spec["power_pins"], ["+24V", "24G", "⏚"])
        self.assertNotIn("短絡", spec["signal_labels_by_direction"]["出力"]["I+"])

    def test_cold_junction_compensation_is_not_external_power(self):
        for model in ("Q64TD", "Q64TDV-GH"):
            spec = definition("analog_io", model)
            with self.subTest(model=model):
                self.assertEqual(spec["pins_by_channel"], [["8", "10", "6"], ["9", "11", "7"], ["12", "14", "16"], ["13", "15", "17"]])
                self.assertEqual(spec["power"], ["FG"])
                self.assertEqual([(p["pin"], p["signal"], p["group"]) for p in spec["auxiliary_terminals"]], [("1", "RTD+", "冷接点補償"), ("3", "RTD-", "冷接点補償")])

    def test_resistance_input_keeps_case_sensitive_four_wire_names(self):
        for model in ("Q64RD", "Q64RD-G"):
            spec = definition("analog_io", model)
            self.assertEqual(spec["terminals"], ["a{n}", "A{n}", "B{n}", "b{n}"])
            self.assertEqual(spec["power_pins"], ["18"])
            self.assertEqual(spec["auxiliary_terminals"][0]["pin"], "17")

    def test_separate_power_network_units_reserve_two_slots_in_document_order(self):
        for model in ("QJ71GP21S-SX", "QJ71LP21S-25"):
            spec = definition("network", model)
            with self.subTest(model=model):
                self.assertEqual(spec["slots"], 2)
                self.assertEqual(spec["occupied_io_points"], 48)
                self.assertEqual(spec["slot_io_points"], [16, 32])

    def test_cclink_ground_and_power_module_terminal_order(self):
        cc = definition("network", "QJ61BT11N")
        self.assertEqual(cc["internal_connections"], [["SLD", "FG"]])
        self.assertIn("SH-080394E-S", cc["source"])
        power = definition("power_supply", "Q61P")
        self.assertEqual(power["terminal_labels_top_to_bottom"], ["ERR.", "ERR.", "FG", "LG", "N", "L"])
        self.assertFalse(power["service_24v"])

    def test_base_slot_counts_exclude_cpu_and_power(self):
        for model, slots in {"Q35B": 5, "Q38B": 8, "Q312B": 12, "Q52B": 2, "Q55B": 5, "Q63B": 3, "Q65B": 5, "Q68B": 8, "Q612B": 12}.items():
            with self.subTest(model=model):
                spec = definition("base", model)
                self.assertEqual(spec["slots"], slots)
                if spec.get("extension"):
                    self.assertEqual(spec["power_required"], model not in ("Q52B", "Q55B"))


if __name__ == "__main__":
    unittest.main()
