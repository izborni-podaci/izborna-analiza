// The settlement map as a PNG (9 Nov 2026, shared by the municipality's page and a city's): the SVG repainted in the
// light palette whatever theme the page is in, a title, the legend, the result and how the largest places voted,
// the key of numbered places, a few facts and the source line, drawn on a canvas at twice the size and saved.
// Everything happens in the browser, nothing is sent anywhere. window.mapImage(figure, data) wires the figure's
// [data-map-png] button; data: lists [{label, slot, country}], total {valid, v}, units [{name, reg, valid, v}]
// (the map's settlements, quarters or municipalities), L (the strings), heading.
(function () {
  'use strict';
  const sr = (document.documentElement.lang || 'sr').indexOf('en') !== 0;
  const num = (x, d) => {
    const s = Math.abs(x).toFixed(d);
    const [a, b] = s.split('.');
    return (x < 0 ? '−' : '') + a.replace(/\B(?=(\d{3})+(?!\d))/g, sr ? '.' : ',') + (b ? (sr ? ',' : '.') + b : '');
  };
  const pct = (x, d) => num(100 * x, d === undefined ? 1 : d) + '%';
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
  function sideChart(sets, result, D) {
    if (sets.length < 2) return null;
    const slotOf = (i) => LIGHT[D.lists[i].slot] || LIGHT[9];
    const big = sets.slice().sort((a, b) => b.reg - a.reg).slice(0, 12);
    const top = result.slice(0, 4).map((r) => r.i);
    return { h: 22 + big.length * 20 + 26 + 15, draw(ctx, cx, cy, barX, barW, colW) {
      ctx.textAlign = 'left'; ctx.fillStyle = '#0f1f33'; ctx.font = '600 15px system-ui, sans-serif';
      ctx.fillText(D.L.chartPlaces, cx, cy); cy += 14;
      ctx.font = '12px system-ui, sans-serif';
      big.forEach((g) => {
        let x = barX;
        top.forEach((i) => { const w = barW * g.v[i] / g.valid; ctx.fillStyle = slotOf(i); ctx.fillRect(x, cy, w, 14); x += w; });
        ctx.fillStyle = '#d6d2cb'; ctx.fillRect(x, cy, barX + barW - x, 14);
        ctx.fillStyle = '#ffffff'; ctx.fillRect(barX + barW * 0.5 - 0.5, cy - 2, 1, 18);  // half
        ctx.fillStyle = '#0f1f33'; ctx.textAlign = 'right';
        ctx.fillText(g.name.length > 20 ? g.name.slice(0, 19) + '…' : g.name, barX - 8, cy + 11);
        // the share in the leading list's colour, so the number says whose it is (a light colour darkened to read)
        ctx.textAlign = 'left'; ctx.font = '600 12px system-ui, sans-serif'; ctx.fillStyle = TEXT[D.lists[g.lead].slot] || slotOf(g.lead);
        ctx.fillText(pct(g.share, 0), barX + barW + 6, cy + 11); ctx.font = '12px system-ui, sans-serif';
        cy += 20;
      });
      // the note under the bars, on two lines when it doesn't fit the column
      ctx.fillStyle = '#44607f'; ctx.font = '11px system-ui, sans-serif';
      const parts = D.L.chartPlacesNote.split(' · ');
      const one = ctx.measureText(D.L.chartPlacesNote).width <= colW;
      (one ? [D.L.chartPlacesNote] : parts).forEach((t, k) => ctx.fillText(t, cx, cy + 6 + k * 15));
      return cy + 26 + (one ? 0 : 15 * (parts.length - 1));
    } };
  }

  window.mapImage = function (fig, D) {
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
      const result = D.lists.map((l, i) => ({ i, label: l.label, slot: l.slot, country: l.country,
        share: D.total.valid ? (D.total.v[i] || 0) / D.total.valid : 0 }))
        .sort((a, b) => b.share - a.share).slice(0, 6);
      const sets = D.units.filter((g) => g.valid).map((g) => { const lead = g.v.indexOf(Math.max(...g.v)); return Object.assign({}, g, { lead, share: g.v[lead] / g.valid }); });
      const side = sideChart(sets, result, D);
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
      ctx.fillText(fig.dataset.heading || D.heading || '', pad, 68);
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
        ctx.fillStyle = '#0f1f33'; ctx.font = '600 15px system-ui, sans-serif'; ctx.fillText(D.L.chartResult, cx, cy); cy += 18;
        // what the upright tick is, said before the bars: the list's result in the whole country
        if (result.some((r) => r.country !== null && r.country !== undefined)) {  // none for one municipality's local election
          ctx.fillStyle = '#0f1f33'; ctx.fillRect(cx, cy - 9, 2, 14);
          ctx.fillStyle = '#44607f'; ctx.font = '12px system-ui, sans-serif'; ctx.fillText(D.L.country, cx + 8, cy + 2); cy += 14;
        }
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
            ctx.fillText(D.L.countryShort + ' ' + pct(r.country), barX + barW * r.country / maxShare, cy - 6);
            ctx.textAlign = 'left'; ctx.font = '13px system-ui, sans-serif'; ctx.fillStyle = '#0f1f33';
          }
          cy += 24;
        });
        cy += 26;
        if (side) cy = side.draw(ctx, cx, cy, barX, barW, colW);
        if (keyItems.length) {  // the key of the numbers on the map
          cy += 36;
          ctx.textAlign = 'left'; ctx.fillStyle = '#44607f'; ctx.font = '600 12px system-ui, sans-serif';
          ctx.fillText(D.L.keyLabel, cx, cy); cy += 20;
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
  };

})();
