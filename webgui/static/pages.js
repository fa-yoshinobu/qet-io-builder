'use strict';
// ------------------------------------------------------------ 操作
async function loadPage(index, keepSel = false) {
  const result = await run('page', index);
  if (!result) return;
  S.index = index;
  S.page = result;
  const parent = S.snap.pages[index] && S.snap.pages[index].parent;
  if (parent !== null && parent !== undefined) S.collapsed.delete(parent);
  if (!keepSel) S.sel = null;
  render();
}

async function refreshAll(snap, index = S.index) {
  applySnapshot(snap);
  if (index !== null && index !== undefined && index < S.snap.pages.length) await loadPage(index, true);
  else { S.index = null; S.page = null; render(); }
}

async function updatePage(changed = '') {
  if (S.index === null || !S.page) return;
  const extraEl = $('#extra');
  const extra = extraEl ? extraEl.value : S.page.extra;
  const result = await run('update_page', S.index, S.page.values, extra, changed);
  if (result) {
    applyPage(result);
  } else {
    await loadPage(S.index, true);
    return;
  }
  render();
  return result;
}

async function confirmDiscard() {
  if (!S.snap.dirty) return true;
  return confirmBox('保存していない変更を破棄しますか？', '破棄する');
}

async function saveAs() {
  const path = await pathFor('名前を付けて保存', S.snap.path || '');
  if (path === null) return false;
  let result = await run('save_as', path);
  if (result && result.confirm) {
    if (!(await confirmBox(result.confirm, '保存する'))) return false;
    result = await run('save_as', result.path, true);
  }
  if (!result) return false;
  applySnapshot(result);
  render();
  setStatus('保存しました: ' + result.path);
  return true;
}

async function save() {
  const result = await run('save');
  if (!result) return false;
  if (result.need_save_as) return saveAs();
  applySnapshot(result);
  render();
  setStatus('保存しました: ' + result.path);
  return true;
}

async function generate(includeDetails = null) {
  const vendor = includeDetails !== null;
  if (!vendor && !S.snap.path && !(await saveAs())) return;
  const stem = S.snap.path ? S.snap.path.replace(/\.json$/i, '') : S.snap.pages.find((page) => VENDOR_BODY_KINDS.includes(page.kind))?.model || 'project';
  const out = await pathFor('図面の保存先（.qet）', stem + (includeDetails === false ? '_構成.qet' : '.qet'));
  if (out === null) return;
  setStatus('図面を生成しています…');
  const method = vendor ? ['generate_configuration', includeDetails] : ['generate'];
  let result = await run(...method, out);
  if (result && result.confirm) {
    if (!(await confirmBox(result.confirm, '上書きする'))) { setStatus(''); return; }
    result = await run(...method, result.out, true);
  }
  if (!result) { setStatus(''); return; }
  if (result.need_save_as) return;
  if (vendor) await refreshAll(result, S.index === null ? null : result.index);
  else { applySnapshot(result.snapshot); render(); }
  setStatus('図面を生成しました: ' + result.out);
  const buttons = S.meta.browser_paths ? [['ok', 'OK', true]] : [['close', '閉じる', false], ['open', 'QETで開く', true]];
  if ((await showMessage('生成完了', result.message, { buttons })) === 'open') await run('open_file', result.out);
}

function showMakerModels(prefix) {
  const series = $('#' + prefix + '-series');
  if (series.dataset.task === 'configuration') return;
  const select = $('#' + prefix + '-model');
  const previous = select.value;
  const query = $('#' + prefix + '-search').value.normalize('NFKC').trim().toUpperCase();
  const kv = prefix === 'kv';
  const seriesByModel = kv ? S.meta.kv_models : S.meta.omron_series;
  const functions = kv ? S.meta.kv_functions : S.meta.nx_models;
  const choices = Object.entries(seriesByModel).filter(([model, families]) => {
    const role = functions[model];
    const keywords = role === 'パルス出力' ? 'パルス出力 位置決め' : role;
    return (role === 'タッチパネル') === (series.dataset.task === 'panel')
      && (!series.value || families.includes(series.value))
      && (model + ' ' + keywords).normalize('NFKC').toUpperCase().includes(query);
  }).map(([model]) => new Option(model + '　' + functions[model], model));
  select.replaceChildren(...(choices.length ? choices : [new Option('該当する形名がありません', '')]));
  if (choices.some((option) => option.value === previous)) select.value = previous;
  select.disabled = !choices.length;
  $('[data-action="' + prefix + '-generate"]').disabled = !choices.length;
  if (kv) showKvSettings();
}

function showKvSettings() {
  const model = $('#kv-model').value;
  const role = S.meta.kv_functions[model] || '';
  $('#kv-wiring-note').hidden = !(role.startsWith('デジタル') || role === 'CPU・内蔵I/O');
  const modes = S.meta.kv_modes[model] || [];
  $('#kv-mode-field').hidden = modes.length === 0;
  const select = $('#kv-mode');
  if (select.dataset.model !== model) {
    select.replaceChildren(...modes.map((mode) => new Option(mode, mode)));
    select.dataset.model = model;
  }
  const settings = S.meta.kv_settings[model] || [];
  for (const key of ['ip', 'communication']) {
    $('#kv-' + key + '-field').hidden = !settings.includes(key);
  }
}
