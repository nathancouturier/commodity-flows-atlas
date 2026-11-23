/**
 * Chokepoints layer: HTML markers (coral ring with a soft pulse and a short label).
 * Labels are HTML on purpose: the base map has no glyph server, so symbol layers cannot draw text.
 *
 * Visible when the layer is on or the Freight tab is active; when a route / lane /
 * chokepoint is selected, only the chokepoints it crosses (plus the selected one) are shown,
 * even when the layer itself is on (keeps the map uncluttered). A selected lane also shows, dimmed and
 * dashed, the passages it may cross (parallel straits, passages of one coast option only).
 */
import { effect, signal } from '@preact/signals';
import maplibregl, { type Map as MLMap } from 'maplibre-gl';
import type { Chokepoint } from '../../types';
import { setMarkerHover } from '../controller';
import { registerLayerModule } from '../layers';
import { hovered, laneVia, layers, routeVia, select, selection } from '../../lib/store';
import { sourceLabel, sources } from '../../lib/data';
import { MAJOR_CHOKEPOINTS, chokepointList, laneGroup, loadLaneFile, loadRoutes } from '../../lib/freight';
import { escapeHtml as esc, fmt } from '../../lib/format';
import '../../styles/lane-engine.css';

interface Entry {
  el: HTMLElement;
  marker: maplibregl.Marker;
}

/** Passages that the selected lane may cross, but not on every option (set while a lane is selected). */
let mayCross = new Set<string>();

function tooltip(c: Chokepoint): string {
  const t = c.traffic;
  return (
    `<div><b>${esc(c.name)}</b></div>` +
    (mayCross.has(c.id) ? `<div class="muted">A passage the selected lane may use, not on every option</div>` : '') +
    // a counter that covers only part of the chokepoint is named next to its figure
    (t && c.portwatchLabel ? `<div class="src-line">${esc(c.portwatchLabel)}</div>` : '') +
    (t ? `<div class="num">${fmt(t.v)} ${esc(t.u)}</div><div class="src-line">${esc(sourceLabel(t.s))} · ${esc(String(t.y))}</div>` : '')
  );
}

registerLayerModule((m: MLMap) => {
  const entries = new Map<string, Entry>();
  const container = m.getContainer();

  // labels appear from zoom 2 (always on hover); below zoom 2 the minor chokepoints are drawn smaller
  const world = signal(m.getZoom() < 2);
  const syncZoom = () => {
    container.classList.toggle('cp-labels', m.getZoom() >= 2);
    world.value = m.getZoom() < 2;
  };
  m.on('zoom', syncZoom);
  syncZoom();

  // touch: a marker is tapped through its transparent ring (see .cp::before), whose radius stops at half the
  // distance to the nearest visible neighbour, so that a tap on one marker never lands on the next (Malacca
  // and Singapore sit 10 px apart at world zoom). --cp-tap is how far the ring reaches past the 8 px radius
  // of the marker: 8 px at most, and down to -4 px where markers almost touch.
  const syncTap = () => {
    const shown = [...entries.values()].filter(({ el }) => !el.classList.contains('cp-hidden'));
    const pts = shown.map(({ marker }) => m.project(marker.getLngLat()));
    shown.forEach(({ el }, i) => {
      let nn = Infinity;
      pts.forEach((q, j) => {
        if (j !== i) nn = Math.min(nn, Math.hypot(q.x - pts[i].x, q.y - pts[i].y));
      });
      el.style.setProperty('--cp-tap', `${Math.max(-4, Math.min(8, nn / 2 - 8))}px`);
    });
  };
  m.on('moveend', syncTap);

  /** (Re)create markers when the chokepoint catalogue arrives. */
  effect(() => {
    void sources.value;
    for (const c of chokepointList.value) {
      if (entries.has(c.id)) continue;
      const el = document.createElement('div');
      el.className = 'cp cp-hidden';
      el.setAttribute('role', 'button');
      el.setAttribute('aria-label', c.name);
      el.tabIndex = 0;
      el.innerHTML = `<span class="cp-ring"></span><span class="cp-label">${esc(c.name.replace(/\s*\(.*\)$/, ''))}</span>`;
      const open = (ev: Event) => {
        ev.stopPropagation();
        select({ kind: 'chokepoint', id: c.id });
      };
      el.addEventListener('click', open);
      // role=button: Enter and Space both activate (Space must not scroll the page or pan the map)
      el.addEventListener('keydown', (ev) => {
        const key = (ev as KeyboardEvent).key;
        if (key !== 'Enter' && key !== ' ') return;
        ev.preventDefault();
        open(ev);
      });
      // the marker owns the tooltip while the pointer is on it (the layers underneath stay quiet)
      el.addEventListener('mouseenter', (ev) => {
        setMarkerHover(true);
        hovered.value = { x: ev.clientX, y: ev.clientY, html: tooltip(c) };
      });
      el.addEventListener('mousemove', (ev) => {
        hovered.value = { x: ev.clientX, y: ev.clientY, html: tooltip(c) };
      });
      el.addEventListener('mouseleave', () => {
        setMarkerHover(false);
        hovered.value = null;
      });
      const marker = new maplibregl.Marker({ element: el, anchor: 'center' }).setLngLat(c.at).addTo(m);
      entries.set(c.id, { el, marker });
    }
  });

  // which chokepoints are crossed by the current selection
  let seq = 0;
  effect(() => {
    const on = layers.value.chokepoints;
    const sel = selection.value;
    const lowZoom = world.value;
    void chokepointList.value;
    const my = ++seq;

    const apply = (crossed: Set<string> | null, selectedId: string | null, maybe: Set<string> = new Set()) => {
      mayCross = maybe;
      for (const [id, { el }] of entries) {
        const hit = crossed?.has(id) ?? false;
        const may = !hit && maybe.has(id);
        // a selection narrows the set to the chokepoints it crosses (and, dimmed, those it may cross)
        const visible = crossed ? hit || may : on;
        el.classList.toggle('cp-hidden', !visible);
        el.classList.toggle('cp-minor', lowZoom && !MAJOR_CHOKEPOINTS.has(id));
        el.classList.toggle('cp-on', hit);
        el.classList.toggle('cp-alt', may);
        el.classList.toggle('cp-sel', id === selectedId);
      }
      syncTap();
    };

    if (sel?.kind === 'country') {
      const lv = laneVia.value;
      const rv = routeVia.value;
      apply(new Set([...(lv ?? []), ...(rv ?? [])]), null);
    } else if (sel?.kind === 'chokepoint') {
      apply(new Set([sel.id]), sel.id);
    } else if (sel?.kind === 'route') {
      apply(null, null); // provisional, avoids a flash of the wrong set
      loadRoutes().then((routes) => {
        if (my === seq) apply(new Set(routes.find((r) => r.id === sel.id)?.via ?? []), null);
      });
    } else if (sel?.kind === 'lane') {
      apply(null, null);
      loadLaneFile(laneGroup(sel.id))
        .then((f) => {
          if (my !== seq) return;
          const lane = f.lanes.find((l) => l.id === sel.id);
          apply(new Set(lane?.via ?? []), null, new Set((lane?.viaAlt ?? []).flat()));
        })
        .catch(() => undefined);
    } else {
      apply(null, null);
    }
  });
});
