'use strict';
// 操作は1つずつ順に処理する(前の結果で画面を描き直してから次へ)
let chain = Promise.resolve();
function serial(task) {
  const next = chain.then(task, task);
  chain = next.catch(() => {});
  return next;
}

document.addEventListener('click', (e) => {
  if (dialogDepth && !e.target.closest('.overlay')) return;
  if (S.mode === 'parts' && !e.target.closest('.overlay')) {
    const group = e.target.closest('[data-pv-group]');
    const row = e.target.closest('tr[data-pv-model]');
    if (group) { PV.group = group.dataset.pvGroup; renderPartsFilters(); renderPartsTable(); return; }
    if (row) { selectPart(row.dataset.pvModel); return; }
  }
  const el = e.target.closest('[data-action]');
  if (!el || el.closest('.overlay')) return;
  const action = actions[el.dataset.action];
  if (action) serial(() => action(el));
});

document.addEventListener('change', (e) => {
  if (e.target.closest('.overlay')) return;
  serial(() => onChange(e.target));
});

document.addEventListener('input', (e) => {
  if (e.target.id === 'pv-q') { PV.q = e.target.value; renderPartsTable(); }
  if (e.target.id === 'nx-search' || e.target.id === 'kv-search') showMakerModels(e.target.id.slice(0, 2));
});

async function onChange(el) {
  if (el.name === 'kv-task' || el.name === 'nx-task') { renderConfigurationMenu(); return; }
  if (el.id === 'terminal-plc') { showTerminalBlocks(); return; }
  if (el.id === 'terminal-cable') { showTerminalPorts(); return; }
  if (el.id === 'terminal-model') { showTerminalCables(); return; }
  if (el.id === 'nx-series' || el.id === 'kv-series') { showMakerModels(el.id.slice(0, 2)); return; }
  if (el.id === 'kv-model') { showKvSettings(); return; }
  if (el.dataset.settingVisible) {
    const result = await run('set_setting_visibility', S.index, el.dataset.settingVisible, el.checked);
    if (result) { applyPage(result); render(); }
    else await loadPage(S.index, true);
    return;
  }
  if (el.id === 'pv-maker') { PV.maker = el.value; PV.group = ''; renderPartsFilters(); renderPartsTable(); return; }
  if (el.id === 'pv-aux') { PV.choice.auxiliary = el.value; return; }
  if (el.id === 'pv-conf') { PV.choice.configuration = el.value; return; }
  if (el.id === 'pv-q') return;
  if (el.dataset.project || el.dataset.power || el.dataset.projectCheck) {
    const values = { power: {} };
    document.querySelectorAll('[data-project]').forEach((input) => { values[input.dataset.project] = input.value; });
    document.querySelectorAll('[data-power]').forEach((input) => { values.power[input.dataset.power] = input.value; });
    const check = document.querySelector('[data-project-check]');
    if (check) values.front_pages = check.checked;
    const snap = await run('set_project', values);
    if (snap) { applySnapshot(snap); renderHeader(); renderPages(); }
    return;
  }
  if (el.dataset.field) {
    S.page.values[el.dataset.field] = el.value;
    const result = await updatePage(el.dataset.field);
    if (result && el.dataset.field === 'kind') await setupRack();
    return;
  }
  if (el.dataset.extra !== undefined) {
    await updatePage('extra');
    return;
  }
  if (el.dataset.moduleStart !== undefined) {
    const result = await run('set_module_start', S.index, Number(el.dataset.stage), Number(el.dataset.slot), el.value);
    if (result) {
      applyPage(result);
      render();
      const alarms = (result.rack && result.rack.alarms) || [];
      setStatus(alarms.length ? `XY割付の警告が${alarms.length}件あります` : '先頭XYを反映しました', alarms.length > 0);
    } else {
      await loadPage(S.index, true);
    }
    return;
  }
  if (el.dataset.moduleTag !== undefined) {
    const result = await run('set_module_tag', S.index, Number(el.dataset.stage), Number(el.dataset.slot), el.value);
    if (result) { applyPage(result); render(); }
    return;
  }
  if (el.dataset.moduleMode !== undefined) {
    const result = await run('set_module_mode', S.index, Number(el.dataset.stage), Number(el.dataset.slot), el.value);
    if (result) { applyPage(result); render(); setStatus('通信方式を変更しました'); }
    else await loadPage(S.index, true);
    return;
  }
  if (el.dataset.moduleBus !== undefined) {
    const result = await run('set_module_bus', S.index, Number(el.dataset.stage), Number(el.dataset.slot), el.value);
    if (result) { applyPage(result); render(); setStatus('接続位置を変更しました'); }
    else await loadPage(S.index, true);
    return;
  }
  if (el.dataset.stageTag) {
    const result = await run('set_stage_part', S.index, Number(el.dataset.stage), el.dataset.stageTag, null, el.value);
    if (result) { applyPage(result); render(); }
  }
}

document.addEventListener('keydown', async (e) => {
  const top = $('#dialogs').lastElementChild;
  if (top && top.onKey) { top.onKey(e); return; }
  if ((e.ctrlKey || e.metaKey) && ['z', 'y'].includes(e.key.toLowerCase()) && S.mode === 'drawing') {
    if (e.target.matches('input, textarea, [contenteditable=true]')) return;
    e.preventDefault();
    serial(() => actions[e.key.toLowerCase() === 'y' || e.shiftKey ? 'redo' : 'undo']());
    return;
  }
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's' && S.mode === 'drawing') {
    e.preventDefault();
    if (document.activeElement && document.activeElement.blur) document.activeElement.blur();
    setTimeout(() => serial(save), 0);
  }
  if (e.key === 'Enter' && e.target.matches('input[type=text]') && !e.target.closest('.overlay')) e.target.blur();
});

// ページ一覧のドラッグで並べ替え
let dragFrom = null;
function dropPlace(e) {
  const item = e.target.closest('.page-item[data-index]');
  if (!item) return null;
  const box = item.getBoundingClientRect();
  return { item, before: e.clientY < box.top + box.height / 2 };
}
function clearDropMarks() {
  document.querySelectorAll('.page-item.drop-before, .page-item.drop-after').forEach((el) => el.classList.remove('drop-before', 'drop-after'));
}
document.addEventListener('dragstart', (e) => {
  const item = e.target.closest && e.target.closest('.page-item[data-index]');
  if (!item) return;
  dragFrom = Number(item.dataset.index);
  item.classList.add('dragging');
  e.dataTransfer.effectAllowed = 'move';
  e.dataTransfer.setData('text/plain', String(dragFrom));
});
document.addEventListener('dragover', (e) => {
  if (dragFrom === null) return;
  const place = dropPlace(e);
  if (!place) return;
  e.preventDefault();
  clearDropMarks();
  place.item.classList.add(place.before ? 'drop-before' : 'drop-after');
});
document.addEventListener('dragend', () => {
  dragFrom = null;
  clearDropMarks();
  document.querySelectorAll('.page-item.dragging').forEach((el) => el.classList.remove('dragging'));
});
document.addEventListener('drop', (e) => {
  if (dragFrom === null) return;
  const place = dropPlace(e);
  const from = dragFrom;
  dragFrom = null;
  clearDropMarks();
  if (!place) return;
  e.preventDefault();
  let to = Number(place.item.dataset.index) + (place.before ? 0 : 1);
  if (from < to) to -= 1;
  if (to === from) return;
  serial(async () => {
    const result = await run('move_page_to', from, to);
    if (result) {
      const selected = S.index === null ? null : S.index === from ? result.index
        : S.index > from && S.index <= to ? S.index - 1 : S.index < from && S.index >= to ? S.index + 1 : S.index;
      await refreshAll(result, selected);
      setStatus(`${from + 1}ページ目を${to + 1}ページ目へ移しました`);
    }
  });
});

window.addEventListener('beforeunload', (e) => {
  if (window.BROWSER_MODE && S.snap && S.snap.dirty) { e.preventDefault(); e.returnValue = ''; }
});

(async function start() {
  S.meta = await call('meta');
  S.snap = await call('snapshot');
  if (!S.meta || S.meta.error || !S.snap || S.snap.error) {
    document.body.textContent = '起動できませんでした: ' + ((S.meta && S.meta.error) || (S.snap && S.snap.error) || '');
    return;
  }
  for (const entry of document.querySelectorAll('[data-terminal-maker]')) {
    entry.hidden = !S.meta.terminal_blocks[entry.dataset.terminalMaker];
  }
  setMode('home');
  setStatus(S.meta.browser_paths ? 'ブラウザ確認モード: ファイルはパスを入力して指定します' : '');
})();
