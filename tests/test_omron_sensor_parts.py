import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1] / "parts/control/omron"


def definition(series, model):
    return json.loads((ROOT / series / "sensor" / (model + ".json")).read_text(encoding="utf-8"))["definition"]


class OmronSensorPartsTest(unittest.TestCase):
    def test_lead_wire_names_have_no_invented_connector_numbers(self):
        files = [p for s in ("e2e_next", "e3z") for p in (ROOT / s / "sensor").glob("*.json")]
        self.assertTrue(files)
        for p in files:
            raw = json.loads(p.read_text(encoding="utf-8"))
            self.assertEqual(raw["model"], p.stem)
            d = raw["definition"]
            if d['wire_count'] == 4:
                continue  # 同時2出力の線色・4端子は専用テストで検証する。
            self.assertEqual(d["wire_count"], 3)
            self.assertEqual(d["wire_colors"], {"plus": "茶", "minus": "青", "out": "黒"})
            self.assertEqual([(x["wire_color"], x["signal"]) for x in d["pins"]], [("茶", "+V"), ("青", "0V"), ("黒", "OUT")])
            for b in d.get("symbol_bindings", []) + [b for o in d.get("configuration_options", []) for b in o["symbol_bindings"]]:
                self.assertEqual(b["terminals"], {"plus": ["茶 +V"], "minus": ["青 0V"], "out": ["黒 OUT"]})

    def test_e2e_npn_pnp_and_fixed_no_nc_follow_d121(self):
        for model, output, mode in [("E2E-X2C112 2M", "NPN", "NO"), ("E2E-X2C212 2M", "NPN", "NC"), ("E2E-X2B212 2M", "PNP", "NC")]:
            d = definition("e2e_next", model)
            self.assertEqual(d["output_type"], output + " open collector")
            self.assertEqual(d["operation"], mode)
            self.assertEqual(d["symbol_bindings"][0]["symbol"], "inductive_sensor_" + mode.lower())
            self.assertEqual(d["ratings"]["load_current_ma_max"], 200)
            self.assertEqual(d["sensing_distance_mm"], 2)

    def test_iolink_capable_model_requires_explicit_sio_confirmation(self):
        d = definition("e2e_next", "E2E-X2B1D12 2M")
        self.assertTrue(d["configuration_required"])
        self.assertNotIn("symbol_bindings", d)
        self.assertEqual([o["id"] for o in d["configuration_options"]], ["sio_no"])
        self.assertEqual(d["configuration_options"][0]["symbol_bindings"][0]["symbol"], "inductive_sensor_no")

    def test_e3z_mode_is_never_implicitly_assumed(self):
        for code, output, distance in [("D61", "NPN", 100), ("D62", "NPN", 1000), ("D81", "PNP", 100), ("D82", "PNP", 1000)]:
            d = definition("e3z", "E3Z-" + code + " 2M")
            self.assertEqual(d["output_type"], output + " open collector")
            self.assertEqual(d["sensing_distance_mm"], distance)
            self.assertEqual(d["ratings"]["load_current_ma_max"], 100)
            self.assertTrue(d["configuration_required"])
            self.assertNotIn("symbol_bindings", d)
            self.assertEqual([(o["id"], o["symbol_bindings"][0]["symbol"]) for o in d["configuration_options"]], [("light_on", "photoelectric_sensor_no"), ("dark_on", "photoelectric_sensor_nc")])


if __name__ == "__main__":
    unittest.main()
