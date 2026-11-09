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
    const avg = totalValid ? totalVotes / totalValid : 0;
    // one bar per station, the list's share from zero, strongest first; the line is the municipality's share
    const rows = counted.map((st) => ({ st, share: (st.v[idx] || 0) / st.valid })).sort((a, b) => b.share - a.share);
    const top = rows.length && rows[0].share ? rows[0].share : 0.01;
    const fold = rows.length > 12;
    const html = rows.map((r, k) => {
      const w = (100 * r.share / top).toFixed(1);
      const bar = '<i' + (r.share < avg ? ' class="neg"' : '') + ' style="width: ' + w + '%"></i>';
      const nc = ctrlOf(r.st, idx) === 'n' ? '<span class="nc" style="left: calc(' + w + '% + 4px)" title="' + esc(L.legendNc) + '"></span>' : '';
      const hidden = fold && k >= 6 && k < rows.length - 6;
      const more = fold && k === 5 ? '<button type="button" class="link-button dev-more" data-dev-more>' + esc(fill(L.rest, { n: num(rows.length - 12, 0) })) + '</button>' : '';
      return '<div class="dv' + (hidden ? ' dv-rest' : '') + '"><a class="lab" href="' + esc(r.st.href) + '"><b>' + esc(L.stationNo) + ' ' + esc(r.st.n) + '</b> ' + esc(r.st.set || r.st.name || '') + '</a><span class="ax">' + bar + nc + '</span><span class="val">' + esc(pct(r.share)) + ' <small class="muted">' + esc(signed(100 * (r.share - avg), 1)) + '</small></span></div>' + more;
    }).join('');
    const wrap = box.querySelector('[data-dev-rows]');
    const open = wrap.classList.contains('open');
    wrap.innerHTML = html;
    wrap.style.setProperty('--avg', (100 * avg / top).toFixed(1) + '%');
    wrap.classList.toggle('open', open);
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

  function renderVillages(idx) {
    document.querySelectorAll('#village-list tr[data-set]').forEach((tr) => {
      const cell = tr.querySelector('[data-cell="vshare"]');
      if (!cell) return;
      const sts = data.stations.filter((st) => (st.set || '') === tr.dataset.set && st.valid);
      const valid = sts.reduce((a, st) => a + st.valid, 0);
      cell.textContent = valid ? pct(sts.reduce((a, st) => a + (st.v[idx] || 0), 0) / valid) : '';
    });
  }

  function apply(idx) {
    renderWithout(idx);
    renderChart(idx);
    renderTable(idx);
    renderVillages(idx);
    renderPanel(idx);
  }

  // a click on a settlement of the map: its polling stations under the map (link, turnout, my list, controller)
  const panel = document.querySelector('[data-village-panel]');
  const mainFig = document.querySelector('[data-map-main]');
  const smap = mainFig ? mainFig.querySelector('svg.smap') : null;
  let shownSet = null;
  function renderPanel(idx) {
    if (!panel || shownSet === null) return;
    const sts = data.stations.filter((st) => (st.set || '') === shownSet);
    const row = (st) => {
      const c = ctrlOf(st, idx);
      const ctrl = c === 'm' ? L.member : c === 'd' ? L.deputy : c === 'n' ? L.none : L.notRead;
      return '<tr><td><a href="' + esc(st.href) + '"><b>' + esc(L.stationNo) + ' ' + esc(st.n) + '</b> ' + esc(st.name || '') + '</a></td>'
        + '<td class="num">' + (st.turnout === null ? '' : esc(pct(st.turnout))) + '</td>'
        + '<td class="num">' + (st.valid ? esc(pct((st.v[idx] || 0) / st.valid)) : '') + '</td>'
        + '<td class="' + (c === 'n' ? 'ctrl-none' : c ? 'ctrl-yes' : 'muted') + '">' + esc(ctrl) + '</td></tr>';
    };
    panel.innerHTML = '<div class="vi-panel-head"><strong>' + esc(fill(L.panelTitle, { name: shownSet, n: num(sts.length, 0) })) + '</strong>'
      + '<button type="button" class="link-button" data-panel-close>' + esc(L.panelClose) + '</button></div>'
      + '<table class="compact"><thead><tr><th>' + esc(L.station) + '</th><th class="num">' + esc(L.turnout) + '</th><th class="num">' + esc(L.myList) + '</th><th>' + esc(L.controller) + '</th></tr></thead><tbody>'
      + sts.map(row).join('') + '</tbody></table>';
    panel.hidden = false;
  }
  const clearActive = () => document.querySelectorAll('svg.smap .mp-active').forEach((x) => x.classList.remove('mp-active'));
  const closePanel = () => { shownSet = null; if (panel) panel.hidden = true; clearActive(); };
  function wire(map) {
    map.querySelectorAll('path[data-set]').forEach((p) => { if (p.dataset.set) { p.setAttribute('tabindex', '0'); p.setAttribute('role', 'button'); } });
    const pick = (p) => {
      // the city settlement with a page of its own by quarters (Novi Sad): the click opens that page
      if (mainFig.dataset.city && p.dataset.set === mainFig.dataset.city) { location.href = mainFig.dataset.cityHref; return; }
      clearActive();
      if (shownSet === p.dataset.set) { closePanel(); return; }
      shownSet = p.dataset.set; p.classList.add('mp-active');
      renderPanel(indexOf(select.value));
    };
    map.addEventListener('click', (e) => { const p = e.target.closest('path[data-set]'); if (p && p.dataset.set) pick(p); });
    map.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { const p = e.target.closest('path[data-set]'); if (p && p.dataset.set) { e.preventDefault(); pick(p); } } });
  }
  if (smap && panel) {
    wire(smap);
    panel.addEventListener('click', (e) => { if (e.target.closest('[data-panel-close]')) closePanel(); });
    const hint = document.createElement('p'); hint.className = 'small muted vi-hint'; hint.textContent = L.panelHint; panel.before(hint);
  }

  document.addEventListener('click', (e) => {
    const more = e.target.closest('[data-dev-more]');
    if (!more) return;
    more.closest('[data-dev-rows]').classList.add('open');
    more.remove();
  });

  // the map as a PNG: the SVG repainted in the light palette whatever theme the page is in (the image has a
  // white background), a title, the legend, a few facts and the source line, drawn on a canvas at twice the
  // size and saved; everything happens in the browser, nothing is sent anywhere
  const LIGHT = { 1: '#2a78d6', 2: '#eb6834', 3: '#1baf7a', 4: '#eda100', 5: '#e87ba4', 6: '#008300', 7: '#6250d6',
    8: '#e34948', 9: '#44607f', none: '#e6e3de' }; // site.css :root --s1 … --s8, --ink-2, --mp-none (a grey with no blue in it)
  // the top step (maps.DEEP) is the colour darkened, as site.css does with brightness(0.72)
  const deepen = (hex) => '#' + [1, 3, 5].map((k) => Math.round(parseInt(hex.slice(k, k + 2), 16) * 0.72).toString(16).padStart(2, '0')).join('');
  const isDeep = (el) => /(^|\s)(mp-deep|sw-deep)(\s|$)/.test(el.getAttribute('class') || '');
  const colourOf = (el) => { const m = (el.getAttribute('class') || '').match(/mp-(\d|none)/); return m ? LIGHT[m[1]] : LIGHT.none; };
  // how the largest settlements voted, beside the map in the PNG (9 Nov 2026, in place of turnout by settlement):
  // the twelve largest by registered voters, each a bar of 100% split among the municipality's four largest lists
  // in their map colours, the rest grey, the leading list's share in the settlement on the right
  const TEXT = { 4: '#a87200', 5: '#c4527e' };  // yellow and pink as text on white
  function sideChart(sets, result) {
    if (sets.length < 2) return null;
    const slotOf = (i) => LIGHT[data.lists[i].slot] || LIGHT[9];
    const big = sets.slice().sort((a, b) => b.reg - a.reg).slice(0, 12);
    const top = result.slice(0, 4).map((r) => r.i);
    return { h: 22 + big.length * 20 + 26 + 15, draw(ctx, cx, cy, barX, barW, colW) {
      ctx.textAlign = 'left'; ctx.fillStyle = '#0f1f33'; ctx.font = '600 15px system-ui, sans-serif';
      ctx.fillText(L.chartPlaces, cx, cy); cy += 14;
      ctx.font = '12px system-ui, sans-serif';
      big.forEach((g) => {
        let x = barX;
        top.forEach((i) => { const w = barW * g.v[i] / g.valid; ctx.fillStyle = slotOf(i); ctx.fillRect(x, cy, w, 14); x += w; });
        ctx.fillStyle = '#d6d2cb'; ctx.fillRect(x, cy, barX + barW - x, 14);
        ctx.fillStyle = '#ffffff'; ctx.fillRect(barX + barW * 0.5 - 0.5, cy - 2, 1, 18);  // half
        ctx.fillStyle = '#0f1f33'; ctx.textAlign = 'right';
        ctx.fillText(g.name.length > 20 ? g.name.slice(0, 19) + '…' : g.name, barX - 8, cy + 11);
        // the share in the leading list's colour, so the number says whose it is (a light colour darkened to read)
        ctx.textAlign = 'left'; ctx.font = '600 12px system-ui, sans-serif'; ctx.fillStyle = TEXT[data.lists[g.lead].slot] || slotOf(g.lead);
        ctx.fillText(pct(g.share, 0), barX + barW + 6, cy + 11); ctx.font = '12px system-ui, sans-serif';
        cy += 20;
      });
      // the note under the bars, on two lines when it doesn't fit the column
      ctx.fillStyle = '#44607f'; ctx.font = '11px system-ui, sans-serif';
      const parts = L.chartPlacesNote.split(' · ');
      const one = ctx.measureText(L.chartPlacesNote).width <= colW;
      (one ? [L.chartPlacesNote] : parts).forEach((t, k) => ctx.fillText(t, cx, cy + 6 + k * 15));
      return cy + 26 + (one ? 0 : 15 * (parts.length - 1));
    } };
  }

  document.querySelectorAll('figure.smap-wrap').forEach((fig) => {
  const png = fig.querySelector('[data-map-png]');
  const svg = fig.querySelector('svg.smap');
  if (png && svg && window.URL && document.createElement('canvas').getContext) {
    png.hidden = false;
    png.addEventListener('click', () => {
      const copy = svg.cloneNode(true);
      copy.querySelectorAll('pattern').forEach((pt) => {
        pt.querySelector('.hb').setAttribute('fill', '#ffffff');
        pt.querySelector('.hf').setAttribute('fill', colourOf(pt));
      });
      copy.querySelectorAll('path').forEach((p) => {
        const close = /mp-close/.test(p.getAttribute('class') || '');
        const k = ((p.getAttribute('class') || '').match(/mp-(\d)/) || [])[1];
        p.setAttribute('fill', close && k ? 'url(#' + copy.querySelector('pattern.mp-' + k).id + ')' : isDeep(p) ? deepen(colourOf(p)) : colourOf(p));
        p.setAttribute('stroke', '#ffffff'); p.setAttribute('stroke-width', '1');
        p.querySelector('title') && p.removeChild(p.querySelector('title'));
      });
      // the map is drawn MAP_K times its size on the page with its names at their size, so the settlements get
      // more room around their names (Vranje: 90 settlements in 640 px were a crowd)
      const MAP_K = 1.6;
      copy.querySelectorAll('path').forEach((p) => p.setAttribute('stroke-width', String(1 / MAP_K)));
      copy.querySelectorAll('text').forEach((t) => {
        const cls = t.getAttribute('class') || '';
        t.setAttribute('font-family', 'system-ui, sans-serif'); t.setAttribute('fill', '#0f1f33');
        t.setAttribute('font-size', String((/small/.test(cls) ? 9 : /num/.test(cls) ? 10 : 11) / MAP_K));
        if (/num/.test(cls)) t.setAttribute('font-weight', '700');
        t.setAttribute('text-anchor', 'middle'); t.setAttribute('dominant-baseline', 'middle');
        t.setAttribute('paint-order', 'stroke'); t.setAttribute('stroke', '#ffffff'); t.setAttribute('stroke-width', String(3 / MAP_K)); t.setAttribute('stroke-linejoin', 'round');
      });
      copy.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
      // the drawing cropped to the municipality's own outline: a narrow one left the right of the box empty
      let bb = null;
      try { bb = svg.getBBox(); } catch (e) { bb = null; }
      if (bb && bb.width > 0 && bb.height > 0) {
        copy.setAttribute('viewBox', [bb.x - 4, bb.y - 4, bb.width + 8, bb.height + 8].map((x) => x.toFixed(1)).join(' '));
      }
      const [, , vw0, vh0] = copy.getAttribute('viewBox').split(' ').map(Number);
      const vw = vw0 * MAP_K; const vh = vh0 * MAP_K;
      const scale = 2; const pad = 28; const top = 96; const gap = 36; const colW = 440;
      const W = vw + 2 * pad + gap + colW;  // the map on the left, two charts on the right
      // the charts' data: the municipality's result (top six lists, with the country's share as a tick) and how
      // the settlements voted (sideChart), from the page's own data
      const counted = data.stations.filter((st) => st.valid);
      const validAll = counted.reduce((a, st) => a + st.valid, 0);
      const result = data.lists.map((l, i) => ({ i, label: l.label, slot: l.slot, country: l.country,
        share: validAll ? counted.reduce((a, st) => a + (st.v[i] || 0), 0) / validAll : 0 }))
        .sort((a, b) => b.share - a.share).slice(0, 6);
      // per settlement: registered, valid votes and each list's votes, from the page's own stations
      const bySet = new Map();
      data.stations.forEach((st) => {
        const where = st.set;
        if (!where || !st.valid) return;
        const g = bySet.get(where) || { name: where, reg: 0, valid: 0, v: data.lists.map(() => 0) };
        g.reg += st.reg; g.valid += st.valid; st.v.forEach((x, i) => { g.v[i] += x || 0; }); bySet.set(where, g);
      });
      const sets = [...bySet.values()].map((g) => { const lead = g.v.indexOf(Math.max(...g.v)); return Object.assign(g, { lead, share: g.valid ? g.v[lead] / g.valid : 0 }); });
      const side = sideChart(sets, result);
      const chartH = 30 + result.length * 24 + 40 + (side ? side.h : 0) + 32;
      const legend = [];
      fig.querySelectorAll('.smap-legend > span:not([hidden])').forEach((sp) => {
        if (sp.hasAttribute('data-ramp')) {
          sp.querySelectorAll(':scope > b, :scope > span').forEach((x) => {
            const sw = x.querySelector('.sw');
            legend.push(sw ? { text: x.textContent.trim(), colour: isDeep(sw) ? deepen(colourOf(sw)) : colourOf(sw), alpha: Number(sw.style.opacity || 1) } : { text: x.textContent.trim(), colour: null, br: true });
          });
          return;
        }
        const sws = [...sp.querySelectorAll('.sw')]; const cls = sws[0].getAttribute('class') || '';
        if (sws.length > 1) {  // a list's shades: one small swatch per step
          legend.push({ text: sp.textContent.trim(), colour: colourOf(sws[0]), steps: sws.map((x) => Number(x.style.opacity || 1)), deep: sws.map(isDeep) });
          return;
        }
        legend.push({ text: sp.textContent.trim(), colour: /mp-close-sw/.test(cls) ? 'hatch' : colourOf(sws[0]), alpha: Number(sws[0].style.opacity || 1) });
      });
      // the numbers' key goes beside the map, under the charts, small and in two columns
      const keyItems = [...fig.querySelectorAll('[data-map-key] > span')].map((sp) => sp.textContent.trim());
      const keyH = keyItems.length ? 24 + Math.ceil(keyItems.length / 2) * 17 : 0;
      const facts = [...fig.querySelectorAll('.vi-facts [data-fact]')].map((f) => f.textContent.trim());
      // the legend flows in lines under the map; a shade scale starts a line of its own
      const lprobe = document.createElement('canvas').getContext('2d'); lprobe.font = '14px system-ui, sans-serif';
      let lx = pad; let rows = 1;
      legend.forEach((g, k) => {
        const w = (g.steps ? g.steps.length * 9 + 6 : g.colour ? 22 : 0) + lprobe.measureText(g.text).width + (g.colour ? 22 : 12);
        if (k && (g.br || lx + w > W - pad)) { rows += 1; lx = pad; }
        g.x = lx; g.row = rows - 1; lx += w;
      });
      // wrap a fact to the width of the image
      const probe = document.createElement('canvas').getContext('2d'); probe.font = '14px system-ui, sans-serif';
      const lines = [];
      facts.forEach((f) => { let line = ''; f.split(' ').forEach((w) => { const tryLine = line ? line + ' ' + w : w; if (probe.measureText(tryLine).width > W - 2 * pad - 20 && line) { lines.push(line); line = w; } else line = tryLine; }); if (line) lines.push(line); });
      const mapH = vh + 24 + rows * 26;
      const sideH = chartH + (keyH ? 24 + keyH : 0);
      const H = top + Math.max(mapH, sideH) + (lines.length ? 16 + lines.length * 22 : 0) + 56;
      const canvas = document.createElement('canvas'); canvas.width = W * scale; canvas.height = H * scale;
      const ctx = canvas.getContext('2d'); ctx.scale(scale, scale);
      ctx.fillStyle = '#ffffff'; ctx.fillRect(0, 0, W, H);
      ctx.fillStyle = '#0f1f33'; ctx.font = '600 24px Georgia, serif';
      ctx.fillText(png.dataset.title, pad, 40);
      ctx.font = '15px system-ui, sans-serif'; ctx.fillStyle = '#44607f';
      ctx.fillText(fig.dataset.heading || document.querySelector('.villages .sec-head h2').textContent, pad, 68);
      const img = new Image();
      const blob = new Blob([new XMLSerializer().serializeToString(copy)], { type: 'image/svg+xml;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      img.onload = () => {
        ctx.drawImage(img, pad, top, vw, vh);
        URL.revokeObjectURL(url);
        let y = top + vh + 30;
        ctx.font = '14px system-ui, sans-serif';
        const y0 = y;
        legend.forEach((g) => {
          const x = g.x; y = y0 + g.row * 26;
          if (g.colour === 'hatch') {
            ctx.fillStyle = '#ffffff'; ctx.fillRect(x, y - 11, 16, 12);
            ctx.strokeStyle = '#44607f'; ctx.lineWidth = 1.5; ctx.beginPath();
            for (let d = -12; d < 16; d += 4) { ctx.moveTo(x + d, y + 1); ctx.lineTo(x + d + 12, y - 11); }
            ctx.save(); ctx.beginPath(); ctx.rect(x, y - 11, 16, 12); ctx.clip(); ctx.beginPath();
            for (let d = -12; d < 16; d += 4) { ctx.moveTo(x + d, y + 1); ctx.lineTo(x + d + 12, y - 11); }
            ctx.stroke(); ctx.restore();
          } else if (g.steps) {
            g.steps.forEach((a, k) => { ctx.globalAlpha = a; ctx.fillStyle = g.deep[k] ? deepen(g.colour) : g.colour; ctx.fillRect(x + k * 9, y - 11, 8, 12); });
            ctx.globalAlpha = 1;
          } else if (g.colour) { ctx.globalAlpha = g.alpha; ctx.fillStyle = g.colour; ctx.fillRect(x, y - 11, 16, 12); ctx.globalAlpha = 1; }
          ctx.fillStyle = '#0f1f33'; ctx.fillText(g.text, g.steps ? x + g.steps.length * 9 + 6 : g.colour ? x + 22 : x, y);
        });
        // the charts
        const cx = pad + vw + gap; let cy = top + 8;
        const barX = cx + 150; const barW = colW - 150 - 56;
        ctx.fillStyle = '#0f1f33'; ctx.font = '600 15px system-ui, sans-serif'; ctx.fillText(L.chartResult, cx, cy); cy += 18;
        // what the upright tick is, said before the bars: the list's result in the whole country
        ctx.fillStyle = '#0f1f33'; ctx.fillRect(cx, cy - 9, 2, 14);
        ctx.fillStyle = '#44607f'; ctx.font = '12px system-ui, sans-serif'; ctx.fillText(L.country, cx + 8, cy + 2); cy += 14;
        const maxShare = Math.max(0.01, ...result.map((r) => Math.max(r.share, r.country || 0)));
        ctx.font = '13px system-ui, sans-serif';
        result.forEach((r) => {
          const w = barW * r.share / maxShare;
          ctx.fillStyle = LIGHT[r.slot] || LIGHT[9]; ctx.fillRect(barX, cy, w, 16);
          let end = w;  // the value goes after the bar and after the country's tick, whichever is further
          if (r.country !== null && r.country !== undefined) { const tw = barW * r.country / maxShare; ctx.fillStyle = '#0f1f33'; ctx.fillRect(barX + tw - 1, cy - 3, 2, 22); end = Math.max(end, tw); }
          ctx.fillStyle = '#0f1f33'; ctx.textAlign = 'right'; ctx.fillText(r.label.length > 22 ? r.label.slice(0, 21) + '…' : r.label, barX - 8, cy + 12);
          ctx.textAlign = 'left'; ctx.fillText(pct(r.share), barX + end + 6, cy + 12);
          if (r === result[0] && r.country !== null && r.country !== undefined) {  // the first tick named in place
            ctx.fillStyle = '#44607f'; ctx.font = '11px system-ui, sans-serif'; ctx.textAlign = 'center';
            ctx.fillText(L.countryShort + ' ' + pct(r.country), barX + barW * r.country / maxShare, cy - 6);
            ctx.textAlign = 'left'; ctx.font = '13px system-ui, sans-serif'; ctx.fillStyle = '#0f1f33';
          }
          cy += 24;
        });
        cy += 26;
        if (side) cy = side.draw(ctx, cx, cy, barX, barW, colW);
        if (keyItems.length) {  // the key of the numbers on the map
          cy += 36;
          ctx.textAlign = 'left'; ctx.fillStyle = '#44607f'; ctx.font = '600 12px system-ui, sans-serif';
          ctx.fillText(L.keyLabel, cx, cy); cy += 20;
          ctx.font = '12px system-ui, sans-serif'; ctx.fillStyle = '#0f1f33';
          const half = Math.ceil(keyItems.length / 2);
          keyItems.forEach((k, i) => ctx.fillText(k, cx + (i < half ? 0 : colW / 2), cy + (i % half) * 17));
        }
        y = top + Math.max(mapH, sideH) - 4;
        if (lines.length) {
          y += 16; ctx.fillStyle = '#0f1f33'; ctx.font = '14px system-ui, sans-serif';
          lines.forEach((l) => { y += 22; ctx.fillText('· ' + l, pad, y); });
        }
        ctx.fillStyle = '#44607f'; ctx.font = '12px system-ui, sans-serif';
        ctx.fillText(png.dataset.source, pad, H - 20);
        canvas.toBlob((out) => {
          const a = document.createElement('a'); a.href = URL.createObjectURL(out); a.download = png.dataset.file;
          document.body.appendChild(a); a.click(); a.remove();
        }, 'image/png');
      };
      img.src = url;
    });
  }
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
