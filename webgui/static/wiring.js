'use strict';
// 配線情報ダイアログ
async function editWiring() {
  const data = await run('wiring', S.index);
  if (!data) return;
  const W = { group: 'connections', value: JSON.parse(JSON.stringify(data.value)), current: { connections: null, boundaries: null } };
  const form = { connections: { ...data.defaults.connections }, boundaries: { ...data.defaults.boundaries } };
  const numeric = (group) => data.position_fields[group].map(([k]) => k);
  const summary = (group, row) => group === 'boundaries'
    ? [row.part, row.left, row.right, row.x, `${row.top} - ${row.bottom}`]
    : [row.part, [row.unit_tag, row.unit_terminal].filter(Boolean).join(':'), [row.terminal_block, row.level, row.terminal].filter(Boolean).join(':'),
      row.wire, [row.cable, row.core].filter(Boolean).join(' / '), [row.peer_tag, row.peer_terminal].filter(Boolean).join(':'),
      [row.destination, row.reference, row.link_id].filter(Boolean).join(' / ')];
  const heads = { connections: ['分割頁', '対象機器 / 端子', '端子台', '線番', 'ケーブル', '相手機器', '送り先 / 参照'], boundaries: ['分割頁', '左側', '右側', '横位置', '上端 - 下端'] };
  const host = openDialog(`<div class="dialog-head"><span class="t">配線情報 — ${esc(data.name)}</span>
      <button type="button" class="x" data-close aria-label="閉じる">×</button></div>
    <div class="dialog-body" id="wd-body"></div>
    <div class="dialog-foot"><span class="hint">位置はQETでも移動できます。送り・受けは同じ参照IDの2件で対応します。未入力の項目は表示しません。</span>
      <button type="button" class="btn" data-close>取消</button><button type="button" class="btn solid" data-apply>適用</button></div>`);
  const readForm = () => {
    const row = { ...form[W.group] };
    for (const key of numeric(W.group)) {
      const n = Number(row[key]);
      if (row[key] === '' || !Number.isFinite(n) || (key === 'part' && !Number.isInteger(n))) throw new Error('分割頁は整数、配置位置は数値で入力してください');
      row[key] = n;
    }
    if (W.group === 'connections' && !data.content_fields.connections.some(([k]) => String(row[k] || '').trim())) throw new Error('接続注記の内容を1項目以上入力してください');
    for (const [k] of data.content_fields[W.group]) row[k] = String(row[k] || '').trim();
    return row;
  };
  const draw = () => {
    const g = W.group;
    const rows = W.value[g];
    let html = `<label style="display:flex;gap:8px;align-items:center;margin-bottom:10px"><input type="checkbox" id="wd-plan" ${W.value.terminal_plan ? 'checked' : ''}>端子台接続図を追加</label>
      <div class="tabs"><button type="button" class="tab${g === 'connections' ? ' on' : ''}" data-tab="connections">接続注記・端子台</button>
      <button type="button" class="tab${g === 'boundaries' ? ' on' : ''}" data-tab="boundaries">盤内外境界</button></div>
      <div style="max-height:220px;overflow:auto;border:1px solid var(--line-soft);border-radius:4px"><table class="list"><thead><tr>${heads[g].map((h) => `<th>${h}</th>`).join('')}</tr></thead><tbody>`;
    rows.forEach((row, i) => {
      html += `<tr class="row${W.current[g] === i ? ' on' : ''}" data-row="${i}">${summary(g, row).map((v) => `<td>${esc(v)}</td>`).join('')}</tr>`;
    });
    if (!rows.length) html += `<tr><td colspan="${heads[g].length}" class="muted" style="padding:14px">まだありません。下の欄に入力して「追加」を押します。</td></tr>`;
    html += `</tbody></table></div>
      <div class="toolbar-row"><button type="button" class="btn solid" data-w="add">追加</button><button type="button" class="btn" data-w="update"${W.current[g] === null ? ' disabled' : ''}>更新</button>
      <button type="button" class="btn danger" data-w="delete"${W.current[g] === null ? ' disabled' : ''}>削除</button><button type="button" class="btn" data-w="clear">入力をクリア / 次行</button></div>
      <div class="sub-head" style="font-size:12px;font-weight:700;margin:6px 0">内容</div><div class="grid2">`;
    for (const [k, label] of data.content_fields[g]) {
      const v = form[g][k] ?? '';
      html += `<label>${esc(label)}${k === 'reference'
        ? `<select data-wf="${k}">${['', '送り', '受け'].map((o) => `<option value="${o}"${o === v ? ' selected' : ''}>${o || '—'}</option>`).join('')}</select>`
        : `<input type="text" data-wf="${k}" value="${esc(v)}">`}</label>`;
    }
    html += '</div><div class="sub-head" style="font-size:12px;font-weight:700;margin:12px 0 6px">配置</div><div class="grid2">';
    for (const [k, label] of data.position_fields[g]) html += `<label>${esc(label)}<input type="text" data-wf="${k}" value="${esc(form[g][k] ?? '')}"></label>`;
    $('#wd-body', host).innerHTML = html + '</div>';
  };
  draw();
  const report = (error) => showMessage('配線情報', error.message || String(error), { error: true });
  host.addEventListener('input', (e) => {
    if (e.target.dataset.wf) form[W.group][e.target.dataset.wf] = e.target.value;
  });
  host.addEventListener('change', (e) => {
    if (e.target.dataset.wf) form[W.group][e.target.dataset.wf] = e.target.value;
    if (e.target.id === 'wd-plan') W.value.terminal_plan = e.target.checked;
  });
  host.addEventListener('click', async (e) => {
    const g = W.group;
    const tab = e.target.closest('[data-tab]');
    const row = e.target.closest('tr.row');
    const act = e.target.closest('[data-w]');
    if (tab) { W.group = tab.dataset.tab; draw(); return; }
    if (row) {
      const i = Number(row.dataset.row);
      W.current[g] = i;
      form[g] = { ...W.value[g][i] };
      draw();
      return;
    }
    if (act) {
      try {
        if (act.dataset.w === 'add') { W.value[g].push(readForm()); W.current[g] = W.value[g].length - 1; }
        if (act.dataset.w === 'update' && W.current[g] !== null) W.value[g][W.current[g]] = readForm();
        if (act.dataset.w === 'delete' && W.current[g] !== null) { W.value[g].splice(W.current[g], 1); W.current[g] = null; form[g] = { ...data.defaults[g] }; }
        if (act.dataset.w === 'clear') {
          const next = { ...data.defaults[g] };
          if (g === 'connections') {
            const part = Number(form[g].part), x = Number(form[g].x);
            if (!Number.isInteger(part) || !Number.isFinite(x)) throw new Error('分割頁は整数、横位置は数値で入力してください');
            next.part = part; next.x = x;
            const ys = W.value[g].filter((r) => r.part === part && r.x === x).map((r) => r.y);
            if (ys.length) next.y = Math.max(...ys) + 100;
          }
          W.current[g] = null;
          form[g] = next;
        }
        draw();
      } catch (error) { report(error); }
      return;
    }
    if (e.target.closest('[data-apply]')) {
      const result = await run('set_wiring', S.index, W.value);
      if (result) { applyPage(result); host.close(); render(); setStatus('配線情報を反映しました'); }
      return;
    }
    if (e.target.closest('[data-close]')) host.close();
  });
  host.onKey = (e) => { if (e.key === 'Escape') host.close(); };
}
