import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


def definitions(maker, series, kind):
    return [json.loads(p.read_text(encoding="utf-8")) for p in (ROOT / "parts/control" / maker / series / kind).glob("*.json")]


class StandardFieldSwitchTest(unittest.TestCase):
    def test_twelve_parts_have_source_and_wiring_state(self):
        items = definitions("omron", "wl", "limit_switch") + definitions("smc", "is10", "pressure_switch") + definitions("nohken", "fq", "float_switch")
        self.assertEqual(len(items), 12)
        for item in items:
            self.assertEqual(item["category"], "standard_device")
            d = item["definition"]
            for key in ("source", "official_html", "normal_state", "operation", "terminal_view", "ratings"):
                self.assertTrue(d[key], (item["model"], key))

    def test_wl_is_two_independent_contacts_not_shared_common(self):
        for item in definitions("omron", "wl", "limit_switch"):
            self.assertEqual(item["definition"]["symbol_bindings"], [
                {"name": "NO", "symbol": "limit_no", "terminals": {"first": ["3"], "second": ["4"]}},
                {"name": "NC", "symbol": "limit_nc", "terminals": {"first": ["1"], "second": ["2"]}},
            ])

    def test_is10_is_unpowered_pressure_contact_not_three_wire_sensor(self):
        items = {i["model"]: i["definition"] for i in definitions("smc", "is10", "pressure_switch")}
        self.assertEqual(items["IS10-01-L"]["ratings"]["lead_length_m"], 3)
        self.assertEqual(items["IS10-01-Z"]["ratings"]["lead_length_m"], 5)
        self.assertEqual(items["IS10-01-6"]["ratings"]["setting_range_mpa"], [0.1, 0.6])
        for d in items.values():
            b = d["symbol_bindings"][0]
            self.assertEqual(b["symbol"], "pressure_reed_no")
            self.assertEqual(len(b["terminals"]), 2)
            self.assertIn("下降", d["operation"])

    def test_float_temperature_variants_and_self_retention(self):
        items = {i["model"]: i["definition"] for i in definitions("nohken", "fq", "float_switch")}
        self.assertEqual(items["FQ-6T"]["ratings"]["temperature_c"], [-10, 90])
        self.assertEqual(items["FQ-8T"]["ratings"]["temperature_c"], [-20, 70])
        self.assertEqual(items["FQ-6"]["ratings"]["control_width_m"], [0.27, 1])
        self.assertEqual(items["FQ-8"]["ratings"]["control_width_m"], [0.33, 4])
        for d in items.values():
            self.assertIn("自己保持", d["operation"])
            self.assertEqual(d["symbol_bindings"][0]["symbol"], "float_no")
            self.assertNotIn("power", d)


if __name__ == "__main__":
    unittest.main()
