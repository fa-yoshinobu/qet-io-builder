import contextlib
import csv
import io
import json
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
MODELS = (
    "NZ2EX2B1-16D", "NZ2EX2B1-16T", "NZ2EX2B1-16TE",
    "NZ2EX2B1N-16D", "NZ2EX2B1N-16T", "NZ2EX2B1N-16TE",
    "NZ2EX2S1-16D", "NZ2EX2S1-16T", "NZ2EX2S1-16TE",
    "NZ2GF2B1-32DT", "NZ2GF2B1-32DTE", "NZ2GF2B2-16R",
    "NZ2GF2S1-16T", "NZ2GF2S1-16TE", "NZ2GF2S2-16R",
    "NZ2GFCE3-16T", "NZ2GFCE3-16TE", "NZ2GFCE3-32DT",
    "NZ2GFCE3-32T", "NZ2GFCE3N-32DT", "NZ2GFCE3N-32T",
    "NZ2GFCF1-32DT", "NZ2GFCF1-32T", "NZ2GFCM1-16T", "NZ2GFCM1-16TE",
)


def information(diagram):
    return [x.text for x in diagram.findall(".//elementInformation")]


class GfVariantDefinitionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.items = {}
        for model in MODELS:
            p = ROOT / "parts/plc/mitsubishi/cclink_ie/digital_io" / (model + ".json")
            cls.items[model] = json.loads(p.read_text(encoding="utf-8-sig"))

    def test_models_and_sources(self):
        self.assertEqual(len(self.items), 25)
        self.assertEqual(sum(x["category"] == "remote_mixed" for x in self.items.values()), 5)
        for model, item in self.items.items():
            with self.subTest(model=model):
                spec = item["definition"]
                self.assertEqual(item["model"], model)
                self.assertTrue(spec["confirmed"])
                self.assertEqual(spec["source_reference"]["document"], "SH-081114ENG-T")
                self.assertTrue(spec["source_reference"]["section"])
                self.assertTrue(spec["source_reference"]["pdf_pages"])
                if item["category"] == "remote_io":
                    self.assertEqual(len(spec["pins"]), spec["points"])
                    self.assertEqual(len(set(spec["pins"])), spec["points"])

    def test_extensions_have_no_own_network_or_unit_power_connector(self):
        for model in MODELS[:9]:
            with self.subTest(model=model):
                spec = self.items[model]["definition"]
                self.assertEqual(spec["module_role"], "extension")
                self.assertEqual(spec["network"], "")
                self.assertEqual(spec["network_connectors"], [])
                self.assertEqual(spec["power_connectors"], [])
                self.assertEqual(spec["power_ports"], [])
                self.assertEqual(spec["unit_power_source"], "main_module")
                if spec["io"] == "in":
                    self.assertEqual(spec["common"], ["TB17", "TB18"])
                else:
                    self.assertEqual((spec["vplus"], spec["com"]), ("TB17", "TB18"))
                    self.assertEqual(spec["terminal_names"]["TB17"],
                                     "COM+" if model.endswith("TE") else "CTL+")

    def test_relay_common_b_bus_is_not_common_a(self):
        for model in ("NZ2GF2B2-16R", "NZ2GF2S2-16R"):
            spec = self.items[model]["definition"]
            self.assertEqual(spec["pins"], [f"TB{i}" for i in range(1, 32, 2)])
            self.assertEqual(spec["paired_com_pins"], [f"TB{i}" for i in range(2, 33, 2)])
            self.assertEqual(spec["paired_power_terminals"],
                             [["COM A", "TB33", "P"], ["COM B", "TB34", "N"]])
            self.assertEqual(len(spec["network_connectors"]), 2)

    def test_econ_mixed_connector_numbers_and_nc(self):
        for model in ("NZ2GFCE3-32DT", "NZ2GFCE3N-32DT"):
            spec = self.items[model]["definition"]
            for key, first in (("input", 1), ("output", 17)):
                connectors = spec[key]["io_connectors"]
                self.assertEqual([x["name"] for x in connectors],
                                 [f"CON{i}" for i in range(first, first + 16)])
                for c in connectors:
                    if key == "input":
                        self.assertEqual(dict(c["pins"])["2"], "+V")
                        self.assertEqual(c["no_connect_pins"], [])
                    else:
                        self.assertEqual(dict(c["pins"])["2"], "NC")
                        self.assertEqual(c["no_connect_pins"], ["2"])
        self.assertEqual(self.items["NZ2GFCE3-32DT"]["definition"]["output_supply_voltage_status"],
                         "未確認")
        self.assertNotIn("output_supply_voltage_status", self.items["NZ2GFCE3N-32DT"]["definition"])

    def test_mil_source_and_sink_power_polarity(self):
        for suffix, positive, negative in (("T", (1, 2), (3, 4)), ("TE", (3, 4), (1, 2))):
            spec = self.items["NZ2GFCM1-16" + suffix]["definition"]
            pins = dict(spec["io_connectors"][0]["pins"])
            self.assertTrue(all(pins[str(x)] == "+24V I/O" for x in positive))
            self.assertTrue(all(pins[str(x)] == "24G I/O" for x in negative))
            self.assertEqual((pins["20"], pins["6"], pins["19"], pins["5"]),
                             ("Y0", "Y7", "Y8", "YF"))
            self.assertEqual(spec["vplus"], "")
            self.assertEqual(spec["com"], "")
            self.assertIn("同時給電しない", spec["power_notes"][0])

    def test_fcn_and_mixed_offset(self):
        for item in self.items.values():
            if item["category"] != "remote_mixed":
                continue
            spec = item["definition"]
            self.assertEqual((spec["input"]["points"], spec["output"]["points"]), (16, 16))
            self.assertEqual((spec["input"]["start_offset"], spec["output"]["start_offset"]), (0, 16))
        spec = self.items["NZ2GFCF1-32DT"]["definition"]
        self.assertEqual(spec["input"]["pins"],
                         [f"{s}{i}" for s in ("B", "A") for i in range(20, 12, -1)])
        self.assertEqual(spec["output"]["pins"],
                         [f"{s}{i}" for s in ("B", "A") for i in range(10, 2, -1)])
        self.assertEqual(spec["input"]["common"], ["A12", "B12"])
        self.assertEqual((spec["output"]["vplus"], spec["output"]["com"]),
                         ("A1/B1", "A2/B2"))
        self.assertEqual(spec["io_connectors"][0]["no_connect_pins"], ["A11", "B11"])


class GfVariantGenerationTest(unittest.TestCase):
    def test_all_models_generate_and_appear_in_picker(self):
        import gen_io_page as gen
        import gui_core as gui
        cfg = json.loads((ROOT / "tests/fixtures/project.json").read_text(encoding="utf-8"))
        for model in MODELS:
            with self.subTest(model=model), tempfile.TemporaryDirectory() as folder:
                p = Path(folder)
                raw = json.loads((ROOT / "parts/plc/mitsubishi/cclink_ie/digital_io" /
                                  (model + ".json")).read_text(encoding="utf-8"))
                spec = raw["definition"]
                mixed = raw["category"] == "remote_mixed"
                directions = ("input", "output") if mixed else ("input" if spec["io"] == "in" else "output",)
                pages = [{"kind": "remotebody", "model": model}]
                io_page = {"kind": "remotemixed" if mixed else directions[0], "model": model}
                for direction in directions:
                    ds = spec[direction] if mixed else spec
                    offset = ds.get("start_offset", 0)
                    prefix = "X" if direction == "input" else "Y"
                    name = direction + ".csv"
                    with (p / name).open("w", encoding="utf-8-sig", newline="") as f:
                        w = csv.writer(f)
                        w.writerow(["アドレス", "機器番号", "信号名"])
                        w.writerows([[f"{prefix}{i+offset:X}", "", "予備"] for i in range(ds["points"])])
                    io_page[direction + "_csv" if mixed else "csv"] = name
                    self.assertIn(model, gui.part_catalog("model", "remotemixed" if mixed else direction)
                                  ["mitsubishi"]["cclink_ie"])
                pages.append(io_page)
                cfg["pages"] = pages
                (p / "in.json").write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
                with contextlib.redirect_stdout(io.StringIO()):
                    gen.main(str(p / "in.json"), str(p / "out.qet"))
                diagrams = ET.parse(p / "out.qet").getroot().findall(".//diagram")
                body = ET.tostring(diagrams[0], encoding="unicode")
                values = information(diagrams[1])
                for direction in directions:
                    ds = spec[direction] if mixed else spec
                    self.assertIn(ds["pins"][0], values)
                    self.assertIn(ds["pins"][-1], values)
                if model.startswith("NZ2EX"):
                    self.assertNotIn("/module_rj45.elmt", body)
                    self.assertNotIn("IPアドレス", body)
                    self.assertNotIn("局番", body)
                    self.assertNotIn("FG", body)
                else:
                    self.assertIn("P1", body)
                    self.assertIn("P2", body)
                if mixed:
                    self.assertIn("Y10", values)
                    self.assertIn("Y1F", values)
                if model == "NZ2GFCF1-32DT":
                    individual = {part for value in values if value for part in value.split("/")}
                    for pin in ("A1", "B1", "A2", "B2"):
                        self.assertIn(pin, individual)
                    paired = []
                    for element in diagrams[1].findall("./elements/element"):
                        kind = element.get("type", "")
                        if kind.endswith(("/plc_in.elmt", "/plc_out.elmt", "/plc_out_common_2.elmt")):
                            self.assertLessEqual(float(element.get("y")), 800,
                                                 "FCN common must stay within the drawing frame")
                        if kind.endswith("/plc_out_common_2.elmt"):
                            paired.append(element)
                            self.assertEqual(len(element.findall("./terminals/terminal")), 2)
                    self.assertEqual(len(paired), 2)
                if model.endswith("-16R"):
                    for d in diagrams[1:3]:
                        self.assertTrue(all(f"TB{i}" in information(d) for i in range(2, 33, 2)
                                            if f"TB{i-1}" in information(d)))
                connector_diagrams = " ".join(ET.tostring(d, encoding="unicode") for d in diagrams[2:])
                if spec.get("io_connectors") or any(spec.get(x, {}).get("io_connectors") for x in ("input", "output")):
                    self.assertTrue("CON1" in connector_diagrams, model + ": missing CON1 details")
                    if "CE3" in model:
                        self.assertTrue("NC" in connector_diagrams, model + ": missing NC note")
                        last = "CON32" if spec.get("points") == 32 or mixed else "CON16"
                        self.assertTrue(last in connector_diagrams, model + ": missing " + last)


if __name__ == "__main__":
    unittest.main()
