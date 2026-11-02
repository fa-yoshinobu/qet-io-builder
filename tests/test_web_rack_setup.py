"""部品選択の順序と、途中取消時の確定済み項目の保持。"""
import shutil
import subprocess
import unittest
from pathlib import Path


class RackSetupTest(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'JavaScript検証用のNode.jsがありません')
    def test_selection_order_cancellation_and_existing_choices(self):
        root = Path(__file__).resolve().parents[1]
        script = r"""
const fs = require('fs'), vm = require('vm'), assert = require('assert/strict');
const source = fs.readFileSync('webgui/static/app.js', 'utf8');
const functions = source.slice(source.indexOf('async function pickField('), source.indexOf('async function addModule('));
async function check(kind, initial, cancel, action, expected) {
  const calls = [];
  const values = {kind, ...initial};
  const context = {S: {index: 0, page: {values}},
    pickPart: async ({key}) => { calls.push(key); return key === cancel ? null : {model: key + '-selected'}; },
    updatePage: async () => ({ok: true})};
  vm.createContext(context);
  await vm.runInContext(functions + ';' + action, context);
  assert.deepEqual(calls, expected);
  for (const key of calls) {
    if (key === cancel) assert.equal(values[key], undefined);
    else assert.equal(values[key], key + '-selected');
  }
  for (const [key, value] of Object.entries(initial)) assert.equal(values[key], value);
}
(async () => {
  for (const kind of ['qbody', 'iqrbody']) {
    await check(kind, {}, null, 'setupRack()', ['base_model']);
    await check(kind, {}, 'base_model', 'setupRack()', ['base_model']);
    await check(kind, {base_model: 'existing'}, null, 'setupRack()', []);
    await check(kind, {base_model: 'B', model: 'C', power_model: 'P'}, null, 'setupRack()', []);
    await check(kind, {}, null, 'pickField("model")', ['base_model', 'model']);
    await check(kind, {}, 'base_model', 'pickField("model")', ['base_model']);
  }
  await check('fx5body', {}, null, 'setupRack()', []);
})().catch(error => { console.error(error); process.exit(1); });
"""
        result = subprocess.run(['node', '-'], input=script, text=True, encoding='utf-8',
                                capture_output=True, cwd=root, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
