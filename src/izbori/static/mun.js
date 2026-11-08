// The municipality's page for a coordinator: the parts that depend on "my list". The page is rendered for the
// municipality's leading list; this redoes them for the list the reader picks, and keeps that choice in the
// browser (localStorage 'viewed'.lists[round id]) so the next municipality page opens on the same list. No
// framework; the markup rebuilt here mirrors municipality.html.
(function () {
  'use strict';
  const dataEl = document.getElementById('mun-data');
  const select = document.querySelector('[data-my-list]');
  if (!dataEl || !select) return;
  const data = JSON.parse(dataEl.textContent);
  const L = data.i18n;
  const sr = (document.documentElement.lang || 'sr').indexOf('en') !== 0;
  const mem = {
    read() { try { return JSON.parse(localStorage.getItem('viewed') || '{}'); } catch (e) { return {}; } },
    write(v) { try { localStorage.setItem('viewed', JSON.stringify(v)); } catch (e) { /* private window */ } },
  };
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const num = (x, d) => {
    const s = Math.abs(x).toFixed(d);
    const [a, b] = s.split('.');
    const grouped = a.replace(/\B(?=(\d{3})+(?!\d))/g, sr ? '.' : ',');
    return (x < 0 ? '−' : '') + grouped + (b ? (sr ? ',' : '.') + b : '');
  };
  const pct = (x, d) => num(100 * x, d === undefined ? 1 : d) + '%';
  const signed = (x, d) => (x >= 0 ? '+' : '') + num(x, d);
  const fill = (s, vals) => s.replace(/\{(\w+)\}/g, (m, k) => (k in vals ? vals[k] : m));

  function indexOf(number) {
    return data.lists.findIndex((l) => String(l.n) === String(number));
  }
  function ctrlOf(st, idx) {
    return st.ctrl ? st.ctrl[idx] : null; // 'm', 'd', 'n' or null when no decision was read
  }

  function renderWithout(idx) {
    const box = document.querySelector('[data-mine="without"]');
    if (!box) return;
    const without = data.stations.filter((st) => ctrlOf(st, idx) === 'n');
    const read = data.stations.filter((st) => ctrlOf(st, idx) !== null).length;
    const groups = new Map();
    without.forEach((st) => { const k = st.set || ''; if (!groups.has(k)) groups.set(k, []); groups.get(k).push(st); });
    const ordered = [...groups.entries()].sort((a, b) => b[1].length - a[1].length || a[0].localeCompare(b[0]));
    const n = box.querySelector('.wk-n');
    n.innerHTML = esc(num(without.length, 0)) + '<small>' + esc(read ? fill(L.ofRead, { n: num(read, 0) }) : L.stations) + '</small>';
    n.classList.toggle('ok', without.length === 0);
    box.querySelector('.wk-rule').textContent = fill(L.rule3, { number: data.lists[idx].n });
    let list = box.querySelector('.wk-list');
    if (!list) { list = document.createElement('ul'); list.className = 'wk-list'; box.querySelector('.wk-rule').after(list); }
    list.innerHTML = ordered.slice(0, 5).map(([set, sts]) =>
      '<li><b>' + esc(set || data.name) + '</b> · ' + esc(L.stationNo) + ' ' + esc(sts.map((s) => s.n).join(', ')) + '</li>').join('');
    list.hidden = ordered.length === 0;
  }

  function renderChart(idx) {
    const box = document.querySelector('[data-mine="chart"]');
    if (!box) return;
    const counted = data.stations.filter((st) => st.valid);
    const totalVotes = counted.reduce((a, st) => a + (st.v[idx] || 0), 0);
    const totalValid = counted.reduce((a, st) => a + st.valid, 0);
    const rows = counted.map((st) => {
      const v = st.v[idx] || 0;
      const restValid = totalValid - st.valid;
      const rest = restValid ? (totalVotes - v) / restValid : null;
      const here = v / st.valid;
      return { st, dev: rest === null ? 0 : here - rest };
    }).sort((a, b) => Math.abs(b.dev) - Math.abs(a.dev));
    const span = rows.length && rows[0].dev ? Math.abs(rows[0].dev) : 0.01;
    const first = 12;
    const html = rows.map((r, k) => {
      const w = (50 * Math.abs(r.dev) / span).toFixed(1);
      const bar = r.dev >= 0 ? '<i style="left: 50%; width: ' + w + '%"></i>' : '<i class="neg" style="right: 50%; width: ' + w + '%"></i>';
      const nc = ctrlOf(r.st, idx) === 'n' ? '<span class="nc" title="' + esc(L.legendNc) + '"></span>' : '';
      return '<div class="dv' + (k >= first ? ' dv-rest' : '') + '"><a class="lab" href="' + esc(r.st.href) + '"><b>' + esc(L.stationNo) + ' ' + esc(r.st.n) + '</b> ' + esc(r.st.set || r.st.name || '') + '</a><span class="ax">' + bar + nc + '</span><span class="val">' + esc(signed(100 * r.dev, 1)) + '</span></div>';
    }).join('');
    const wrap = box.querySelector('[data-dev-rows]');
    const open = wrap.classList.contains('open');
    wrap.innerHTML = html + (rows.length > first ? '<button type="button" class="link-button dev-more" data-dev-more>' + esc(fill(L.rest, { n: num(rows.length - first, 0) })) + '</button>' : '');
    wrap.classList.toggle('open', open);
    const avg = totalValid ? totalVotes / totalValid : 0;
    const note = box.querySelector('[data-dev-note]');
    if (note) note.textContent = fill(L.devNote, { avg: pct(avg) });
  }

  function renderTable(idx) {
    document.querySelectorAll('#station-list tr[data-bm]').forEach((tr) => {
      const st = data.stations.find((s) => String(s.n) === tr.dataset.bm);
      if (!st) return;
      const share = tr.querySelector('[data-cell="share"]');
      if (share) share.textContent = st.valid ? pct((st.v[idx] || 0) / st.valid) : '';
      const cell = tr.querySelector('[data-cell="ctrl"]');
      if (cell) {
        const c = ctrlOf(st, idx);
        cell.textContent = c === 'm' ? L.member : c === 'd' ? L.deputy : c === 'n' ? L.none : L.notRead;
        cell.className = c === 'n' ? 'ctrl-none' : c ? 'ctrl-yes' : 'muted';
      }
    });
  }

  function apply(idx) {
    renderWithout(idx);
    renderChart(idx);
    renderTable(idx);
  }

  document.addEventListener('click', (e) => {
    const more = e.target.closest('[data-dev-more]');
    if (!more) return;
    more.closest('[data-dev-rows]').classList.add('open');
    more.remove();
  });

  // the remembered list, when this election has it
  const remembered = (mem.read().lists || {})[data.rid];
  let idx = remembered !== undefined ? indexOf(remembered) : -1;
  if (idx < 0) idx = data.default;
  if (idx !== data.default) { select.value = String(data.lists[idx].n); apply(idx); }

  select.addEventListener('change', () => {
    const i = indexOf(select.value);
    if (i < 0) return;
    const v = mem.read();
    v.lists = v.lists || {};
    v.lists[data.rid] = data.lists[i].n;
    mem.write(v);
    apply(i);
  });
})();
