'use strict';
/* PLC・GOT 図面生成 画面。処理はすべて Python(webgui/api.py)が行い、ここは表示と操作だけ。 */

const $ = (selector, root = document) => root.querySelector(selector);
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

// ------------------------------------------------------------ Python との接続
const apiReady = new Promise((resolve) => {
  if (window.BROWSER_MODE) {
    resolve((name) => (...args) => fetch('/api/' + name, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(args),
    }).then((r) => r.json()));
    return;
  }
  const done = () => resolve((name) => (...args) => window.pywebview.api[name](...args));
  if (window.pywebview && window.pywebview.api) done();
  else window.addEventListener('pywebviewready', done);
});

async function call(name, ...args) {
  const api = await apiReady;
  try {
    return await api(name)(...args);
  } catch (error) {
    return { error: String(error && error.message ? error.message : error) };
  }
}

// エラーは画面に出して null を返す。取消も null。
async function run(name, ...args) {
  const result = await call(name, ...args);
  if (!result) return null;
  if (result.error) {
    await showMessage('エラー', result.error, { error: true });
    if (result.snapshot) applySnapshot(result.snapshot);
    return null;
  }
  if (result.cancelled) return null;
  return result;
}

// ------------------------------------------------------------ 状態
const S = {
  collapsed: new Set(),
  meta: null,
  snap: null,      // プロジェクト全体(ページ一覧など)
  index: null,     // 選択ページ。null はプロジェクト設定
  page: null,      // 選択ページの詳細
  sel: null,       // ベース図で選んだ項目の id
  status: { text: '', warn: false },
  mode: 'home',    // home: 最初のメニュー / drawing: PLC・GOT 図面 / parts: 制御部品の書出し・ユーザーコレクション登録
};
const MODEL_KEYS = ['model', 'left_model', 'right_model', 'power_model', 'base_model'];
const CSV_KEYS = ['csv', 'input_csv', 'output_csv'];
const CPU_KEYS = ['model', 'tag', 'battery', 'battery_model', 'batteryless', 'sd_card', 'sd_card_model', 'memory_cassette', 'memory_cassette_model',
  'memory_card', 'memory_card_model', 'board_model', 'board_tag'];
const POWER_KEYS = ['power_model', 'power_tag'];
const BASE_KEYS = ['base_model', 'base_tag'];
const FREE_SELECT = ['sd_card_model'];   // 候補から選ぶか自由に入力
const GROUP_LABEL = { in: '入力', out: '出力', analog: 'アナログ', comm: '通信・インテリ', mixed: '入出力混合' };
const LINEAR_KINDS = ['fx5body', 'mxbody', 'kvbody', 'nxbody'];
const VENDOR_BODY_KINDS = ['kvbody', 'nxbody'];
const KV_CONFIGURATION_SERIES = ['KV Nano', 'KV-8000', 'KV-7000', 'KV-X'];

function isLinearRack(rack = S.page && S.page.rack) { return !!rack && LINEAR_KINDS.includes(rack.kind); }
function isVendorRack(rack = S.page && S.page.rack) { return !!rack && VENDOR_BODY_KINDS.includes(rack.kind); }
function projectMaker() { return (S.snap && S.snap.maker) || 'mitsubishi'; }
function drawingTitle() {
  return { keyence: 'キーエンス KV 構成・図面', omron: 'オムロン NX 構成・図面' }[projectMaker()] || TITLES.drawing;
}

function fieldLabel(key) {
  if (key === 'maker') return 'メーカー';
  if (key === 'series') return 'シリーズ';
  const found = S.meta.fields.find(([k]) => k === key);
  return found ? found[1] : key;
}

function setStatus(text, warn = false) {
  S.status = { text, warn };
  const el = $('#status');
  el.textContent = text;
  el.className = 'status' + (warn ? ' warn' : '');
}

function applySnapshot(snap) {
  if (!snap || !snap.pages) return;
  S.snap = snap;
  if (S.index !== null && S.index >= snap.pages.length) {
    S.index = null;
    S.page = null;
  }
}

function applyPage(result) {
  if (!result) return;
  if (result.pages) {
    S.snap.pages = result.pages;
  }
  if (result.dirty !== undefined) S.snap.dirty = result.dirty;
  for (const key of ['can_undo', 'can_redo']) if (result[key] !== undefined) S.snap[key] = result[key];
  if (result.values) S.page = result;
}
