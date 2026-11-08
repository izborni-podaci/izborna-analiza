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
    8: '#e34948', 9: '#44607f', none: '#b9c9dc' }; // site.css :root --s1 … --s8, --ink-2, --axis
  const colourOf = (el) => { const m = (el.getAttribute('class') || '').match(/mp-(\d|none)/); return m ? LIGHT[m[1]] : LIGHT.none; };
  const png = document.querySelector('[data-map-png]');
  const svg = document.querySelector('svg.smap');
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
        p.setAttribute('fill', close && k ? 'url(#h' + k + ')' : colourOf(p));
        p.setAttribute('stroke', '#ffffff'); p.setAttribute('stroke-width', '1');
        p.querySelector('title') && p.removeChild(p.querySelector('title'));
      });
      copy.querySelectorAll('text').forEach((t) => {
        const cls = t.getAttribute('class') || '';
        t.setAttribute('font-family', 'system-ui, sans-serif'); t.setAttribute('fill', '#0f1f33');
        t.setAttribute('font-size', /small/.test(cls) ? '9' : /num/.test(cls) ? '10' : '11');
        if (/num/.test(cls)) t.setAttribute('font-weight', '700');
        t.setAttribute('text-anchor', 'middle'); t.setAttribute('dominant-baseline', 'middle');
        t.setAttribute('paint-order', 'stroke'); t.setAttribute('stroke', '#ffffff'); t.setAttribute('stroke-width', '3'); t.setAttribute('stroke-linejoin', 'round');
      });
      copy.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
      const [, , vw, vh] = copy.getAttribute('viewBox').split(' ').map(Number);
      const scale = 2; const pad = 28; const top = 96; const gap = 36; const colW = 440;
      const W = vw + 2 * pad + gap + colW;  // the map on the left, two charts on the right
      // the charts' data: the municipality's result (top six lists, with the country's share as a tick) and
      // turnout by settlement (the twelve largest, in order of turnout), from the page's own data
      const counted = data.stations.filter((st) => st.valid);
      const validAll = counted.reduce((a, st) => a + st.valid, 0);
      const result = data.lists.map((l, i) => ({ label: l.label, slot: l.slot, country: l.country,
        share: validAll ? counted.reduce((a, st) => a + (st.v[i] || 0), 0) / validAll : 0 }))
        .sort((a, b) => b.share - a.share).slice(0, 6);
      const bySet = new Map();
      data.stations.forEach((st) => { if (!st.set || st.turnout === null) return; const g = bySet.get(st.set) || { name: st.set, reg: 0, voted: 0 }; g.reg += st.reg; g.voted += Math.round(st.turnout * st.reg); bySet.set(st.set, g); });
      const turnout = [...bySet.values()].sort((a, b) => b.reg - a.reg).slice(0, 12).map((g) => ({ name: g.name, t: g.reg ? g.voted / g.reg : 0 })).sort((a, b) => b.t - a.t);
      const chartH = 30 + result.length * 24 + 40 + 30 + turnout.length * 20 + 20;
      const legend = [...document.querySelectorAll('.smap-legend > span')].map((sp) => {
        const sw = sp.querySelector('.sw'); const cls = sw.getAttribute('class') || '';
        return { text: sp.textContent.trim(), colour: /mp-close-sw/.test(cls) ? 'hatch' : colourOf(sw) };
      });
      const keyEl = document.querySelector('[data-map-key]');
      const facts = (keyEl ? [keyEl.textContent.replace(/\s+/g, ' ').trim()] : []).concat([...document.querySelectorAll('.vi-facts [data-fact]')].map((f) => f.textContent.trim()));
      const rows = Math.ceil(legend.length / 2);
      // wrap a fact to the width of the image
      const probe = document.createElement('canvas').getContext('2d'); probe.font = '14px system-ui, sans-serif';
      const lines = [];
      facts.forEach((f) => { let line = ''; f.split(' ').forEach((w) => { const tryLine = line ? line + ' ' + w : w; if (probe.measureText(tryLine).width > W - 2 * pad - 20 && line) { lines.push(line); line = w; } else line = tryLine; }); if (line) lines.push(line); });
      const mapH = vh + 24 + rows * 26;
      const H = top + Math.max(mapH, chartH) + (lines.length ? 16 + lines.length * 22 : 0) + 56;
      const canvas = document.createElement('canvas'); canvas.width = W * scale; canvas.height = H * scale;
      const ctx = canvas.getContext('2d'); ctx.scale(scale, scale);
      ctx.fillStyle = '#ffffff'; ctx.fillRect(0, 0, W, H);
      ctx.fillStyle = '#0f1f33'; ctx.font = '600 24px Georgia, serif';
      ctx.fillText(png.dataset.title, pad, 40);
      ctx.font = '15px system-ui, sans-serif'; ctx.fillStyle = '#44607f';
      ctx.fillText(document.querySelector('.villages .sec-head h2').textContent, pad, 68);
      const img = new Image();
      const blob = new Blob([new XMLSerializer().serializeToString(copy)], { type: 'image/svg+xml;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      img.onload = () => {
        ctx.drawImage(img, pad, top, vw, vh);
        URL.revokeObjectURL(url);
        let y = top + vh + 30;
        ctx.font = '14px system-ui, sans-serif';
        legend.forEach((g, k) => {
          const x = pad + (k % 2) * (W / 2 - pad);
          if (k && k % 2 === 0) y += 26;
          if (g.colour === 'hatch') {
            ctx.fillStyle = '#ffffff'; ctx.fillRect(x, y - 11, 16, 12);
            ctx.strokeStyle = '#44607f'; ctx.lineWidth = 1.5; ctx.beginPath();
            for (let d = -12; d < 16; d += 4) { ctx.moveTo(x + d, y + 1); ctx.lineTo(x + d + 12, y - 11); }
            ctx.save(); ctx.beginPath(); ctx.rect(x, y - 11, 16, 12); ctx.clip(); ctx.beginPath();
            for (let d = -12; d < 16; d += 4) { ctx.moveTo(x + d, y + 1); ctx.lineTo(x + d + 12, y - 11); }
            ctx.stroke(); ctx.restore();
          } else { ctx.fillStyle = g.colour; ctx.fillRect(x, y - 11, 16, 12); }
          ctx.fillStyle = '#0f1f33'; ctx.fillText(g.text, x + 22, y);
        });
        // the charts
        const cx = pad + vw + gap; let cy = top + 8;
        const barX = cx + 150; const barW = colW - 150 - 56;
        ctx.fillStyle = '#0f1f33'; ctx.font = '600 15px system-ui, sans-serif'; ctx.fillText(L.chartResult, cx, cy); cy += 16;
        const maxShare = Math.max(0.01, ...result.map((r) => Math.max(r.share, r.country || 0)));
        ctx.font = '13px system-ui, sans-serif';
        result.forEach((r) => {
          const w = barW * r.share / maxShare;
          ctx.fillStyle = LIGHT[r.slot] || LIGHT[9]; ctx.fillRect(barX, cy, w, 16);
          let end = w;  // the value goes after the bar and after the country's tick, whichever is further
          if (r.country !== null && r.country !== undefined) { const tw = barW * r.country / maxShare; ctx.fillStyle = '#0f1f33'; ctx.fillRect(barX + tw - 1, cy - 3, 2, 22); end = Math.max(end, tw); }
          ctx.fillStyle = '#0f1f33'; ctx.textAlign = 'right'; ctx.fillText(r.label.length > 22 ? r.label.slice(0, 21) + '…' : r.label, barX - 8, cy + 12);
          ctx.textAlign = 'left'; ctx.fillText(pct(r.share), barX + end + 6, cy + 12);
          cy += 24;
        });
        ctx.fillStyle = '#44607f'; ctx.font = '12px system-ui, sans-serif';
        ctx.fillRect(barX, cy + 2, 2, 12); ctx.fillText(L.country, barX + 8, cy + 12); cy += 40;
        if (turnout.length > 1) {
          ctx.fillStyle = '#0f1f33'; ctx.font = '600 15px system-ui, sans-serif'; ctx.fillText(L.chartTurnout, cx, cy); cy += 16;
          const maxT = Math.max(0.01, ...turnout.map((g) => g.t), data.turnout.mun || 0);
          ctx.font = '12px system-ui, sans-serif';
          turnout.forEach((g) => {
            const w = barW * g.t / maxT;
            ctx.fillStyle = '#1e3a5f'; ctx.fillRect(barX, cy, w, 13);
            ctx.fillStyle = '#0f1f33'; ctx.textAlign = 'right'; ctx.fillText(g.name.length > 22 ? g.name.slice(0, 21) + '…' : g.name, barX - 8, cy + 11);
            ctx.textAlign = 'left'; ctx.fillText(pct(g.t), barX + w + 6, cy + 11);
            cy += 20;
          });
          if (data.turnout.mun !== null) {
            const mx = barX + barW * data.turnout.mun / maxT;
            ctx.strokeStyle = '#c9971c'; ctx.lineWidth = 2; ctx.setLineDash([4, 3]); ctx.beginPath(); ctx.moveTo(mx, cy - turnout.length * 20 - 4); ctx.lineTo(mx, cy); ctx.stroke(); ctx.setLineDash([]);
            ctx.fillStyle = '#8a6610'; ctx.fillText(L.municipality + ' ' + pct(data.turnout.mun), Math.min(mx + 6, cx + colW - 110), cy + 12);
          }
        }
        y = top + Math.max(mapH, chartH) - 4;
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
