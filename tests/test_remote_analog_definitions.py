"""Remote analog/temperature terminal anchors from the official manuals."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
PARTS = ROOT / "parts/plc/mitsubishi/cclink_ie/analog_io"
MODELS = {
    "NZ2GF2B-60AD4", "NZ2GF2BN-60AD4", "NZ2EX2B-60AD4",
    "NZ2GF2B-60DA4", "NZ2GF2BN-60DA4", "NZ2EX2B-60DA4",
    "NZ2GN2B-60AD4", "NZ2GN2S-60AD4", "NZ2GN2B-60DA4", "NZ2GN2S-60DA4",
    "NZ2GFCE-60ADV8", "NZ2GFCE-60ADI8", "NZ2GFCE-60DAV8", "NZ2GFCE-60DAI8",
    "NZ2GF2B-60TCTT4", "NZ2GF2B-60TCRT4", "NZ2GF2S-60MD4",
}


def definition(model):
    return json.loads((PARTS / (model + ".json")).read_text(encoding="utf-8"))["definition"]


class RemoteAnalogDefinitionTest(unittest.TestCase):
    def test_seventeen_definitions_have_explicit_signal_pins(self):
        for model in MODELS:
            obj = json.loads((PARTS / (model + ".json")).read_text(encoding="utf-8"))
            spec = obj["definition"]
            with self.subTest(model=model):
                self.assertEqual(obj["category"], "remote_analog")
                self.assertFalse(spec["auto_wiring"])
                self.assertEqual(len(spec["channels"]), len(spec["pins_by_channel"]))
                for index, direction in enumerate(spec["channels"]):
                    terms = spec["terminals_by_channel"][index] if spec.get("terminals_by_channel") else spec["terminals"]
                    self.assertEqual(len(spec["pins_by_channel"][index]), len(terms))
                self.assertEqual(spec["power"], [])  # Supply belongs to the separate unit body.
                self.assertTrue(spec["power_connectors"])
                self.assertNotRegex(spec["source"], r"https?://")

    def test_independent_stations_and_expansion_units_are_distinguished(self):
        for model in MODELS:
            spec = definition(model)
            with self.subTest(model=model):
                if model.startswith("NZ2EX"):
                    self.assertEqual(spec["module_role"], "extension")
                    self.assertEqual(spec["network_connectors"], [])
                    self.assertTrue(spec["external_supply_required"])
                    self.assertTrue(spec["requires_base_analog_unit"])
                else:
                    self.assertEqual(spec["module_role"], "remote_station")
                    self.assertEqual([(p["name"], p["connector_type"]) for p in spec["network_connectors"]], [("P1", "rj45"), ("P2", "rj45")])

    def test_old_and_revised_da_terminal_starts_are_not_confused(self):
        self.assertEqual(definition("NZ2GF2BN-60DA4")["pins_by_channel"], [["3", "4", "5"], ["7", "8", "9"], ["11", "12", "13"], ["15", "16", "17"]])
        self.assertEqual(definition("NZ2GN2B-60DA4")["pins_by_channel"], [["1", "2", "3"], ["5", "6", "7"], ["9", "10", "11"], ["13", "14", "15"]])

    def test_gn_field_condition_and_current_shorting_terminal(self):
        for model in [m for m in MODELS if m.startswith("NZ2GN")]:
            spec = definition(model)
            self.assertEqual(spec["required_firmware_for_field"], "02")
            self.assertEqual(spec["field_mode_switch"], {"name": "機能設定スイッチ1", "value": "ON"})
            self.assertEqual([p[1] for p in spec["power_connectors"][0]["pins"]], ["FG", "24G", "+24V"])
            if "60AD" in model:
                self.assertEqual(spec["required_jumpers"][0]["terminals"], ["V+", "SH"])
                self.assertEqual(spec["pins_by_channel"][0], ["1", "2", "3", "4"])
                self.assertEqual(spec["signal_labels_by_direction"]["入力"]["SH"], "電流入力短絡用")

    def test_econ_keeps_channel_pin_identity_and_power_through_connection(self):
        for model in [m for m in MODELS if m.startswith("NZ2GFCE")]:
            spec = definition(model)
            self.assertEqual(len(spec["channel_connectors"]), 8)
            self.assertEqual(len({c["name"] for c in spec["channel_connectors"]}), 8)
            for connector in spec["power_connectors"]:
                self.assertEqual(connector["pins"], [["1", "FG"], ["2", "+24V"], ["3", "24G"], ["4", "NC"], ["5", "NC"]])
                self.assertEqual(connector["non_connectable_pins"], ["4", "5"])
            self.assertEqual(spec["through_current_max_amps"], 1.5)
            self.assertEqual(len(spec["internal_connections"]), 3)
            self.assertEqual(spec["terminals"][-1] == "AG", "60AD" in model)

    def test_temperature_control_outputs_and_factory_compensation_are_retained(self):
        for model in ("NZ2GF2B-60TCTT4", "NZ2GF2B-60TCRT4"):
            spec = definition(model)
            self.assertEqual(spec["channels"], ["入力"] * 4 + ["出力"] * 4)
            self.assertEqual(spec["channel_labels"][4:], ["制御OUT1", "制御OUT2", "制御OUT3", "制御OUT4"])
            self.assertEqual(spec["pins_by_channel"][4:], [["1"], ["2"], ["3"], ["4"]])
            self.assertEqual((spec["auxiliary_terminals"][0]["pin"], spec["auxiliary_terminals"][0]["signal"]), ("5", "COM-"))
            self.assertEqual(spec["output_assignments_by_mode"]["加熱冷却通常"]["OUT2"], "CH1冷却")
        cj = definition("NZ2GF2B-60TCTT4")["auxiliary_terminals"][1:]
        self.assertEqual([p["pin"] for p in cj], ["12", "14"])
        self.assertTrue(all(p["factory_installed"] and not p["connectable"] for p in cj))

    def test_multi_input_has_positions_instead_of_invented_pin_numbers(self):
        spec = definition("NZ2GF2S-60MD4")
        self.assertEqual(spec["pins_by_channel"], [[""] * 6 for _ in range(4)])
        self.assertEqual(spec["terminal_positions"], {"V-/B": "上段左", "V+/A": "上段右", "b": "中段左", "I+": "中段右", "SH2": "下段左", "SH1": "下段右"})
        self.assertEqual(spec["required_jumpers"][0]["terminals"], ["SH1", "SH2"])

    def test_all_models_generate_analog_and_unit_body_without_automatic_connections(self):
        import gen_io_page as gen
        base = json.loads((ROOT / "tests/fixtures/project.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "project.json"
            target = Path(directory) / "result.qet"
            for model in MODELS:
                with self.subTest(model=model):
                    base["pages"] = [{"kind": "remoteanalog", "model": model}, {"kind": "remotebody", "model": model}]
                    source.write_text(json.dumps(base, ensure_ascii=False), encoding="utf-8")
                    with contextlib.redirect_stdout(io.StringIO()):
                        gen.main(str(source), str(target))
                    diagrams = ET.parse(target).getroot().findall("./diagram")
                    self.assertEqual(len(diagrams), 2)
                    self.assertFalse(diagrams[0].findall("./conductors/conductor"))
                    ports = [e for e in diagrams[1].findall("./elements/element") if e.get("type").endswith("/module_rj45.elmt")]
                    self.assertEqual(len(ports), 0 if model.startswith("NZ2EX") else 2)


if __name__ == "__main__":
    unittest.main()
