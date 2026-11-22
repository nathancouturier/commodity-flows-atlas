/**
 * Chokepoints layer: HTML markers (coral ring with a soft pulse and a short label).
 * Labels are HTML on purpose: the base map has no glyph server, so symbol layers cannot draw text.
 *
 * Visible when the layer is on or the Freight tab is active; when a route / lane /
 * chokepoint is selected, only the chokepoints it crosses (plus the selected one) are shown,
 * even when the layer itself is on (keeps the map uncluttered).
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

interface Entry {
  el: HTMLElement;
  marker: maplibregl.Marker;
}

function tooltip(c: Chokepoint): string {
  const t = c.traffic;
  return (
    `<div><b>${esc(c.name)}</b></div>` +
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
      el.addEventListener('keydown', (ev) => (ev as KeyboardEvent).key === 'Enter' && open(ev));
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

    const apply = (crossed: Set<string> | null, selectedId: string | null) => {
      for (const [id, { el }] of entries) {
        const hit = crossed?.has(id) ?? false;
        // a selection narrows the set to the chokepoints it crosses
        const visible = crossed ? hit : on;
        el.classList.toggle('cp-hidden', !visible);
        el.classList.toggle('cp-minor', lowZoom && !MAJOR_CHOKEPOINTS.has(id));
        el.classList.toggle('cp-on', hit);
        el.classList.toggle('cp-sel', id === selectedId);
      }
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
          if (my === seq) apply(new Set(f.lanes.find((l) => l.id === sel.id)?.via ?? []), null);
        })
        .catch(() => undefined);
    } else {
      apply(null, null);
    }
  });
});
