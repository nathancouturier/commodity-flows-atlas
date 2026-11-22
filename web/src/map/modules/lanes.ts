/**
 * "Physical flows" layer: seaborne trade lanes (origin -> destination country pairs).
 *
 * - no commodity: overview = top N lanes per group (OVERVIEW), coloured by commodity family
 * - commodity: every lane of the commodity's groups
 * - filters: family tab, vessel classes, year; a selected country / chokepoint / lane
 *   keeps its lanes bright and dims the rest
 */
import { effect } from '@preact/signals';
import type { Feature, LineString } from 'geojson';
import type { Lane, LaneFile } from '../../types';
import { registerLayerModule } from '../layers';
import { setLineSet, flyToLine, type LineFeatureProps } from '../controller';
import { commodity, family, layers, selection, vesselClasses, year } from '../../lib/store';
import { commodities, commodityMeta, countries, countryName, sourceLabel, sources } from '../../lib/data';
import { LANE_GROUPS, OVERVIEW, chokepointList, chokepointName, laneGroup, loadLaneFile, vesselClassList, vesselName } from '../../lib/freight';
import { FAMILY_COLOR, escapeHtml as esc, fmt, pct } from '../../lib/format';

const NEUTRAL = '#8aa0b8';

/** Annual value of a lane for the chosen year (null when the lane has no data that year). */
export function laneValue(lane: Lane, file: LaneFile, yr: number | null): number {
  if (yr != null) {
    const i = file.years.indexOf(yr);
    if (i >= 0) return lane.hist[i] ?? 0;
  }
  return lane.flow.v;
}

function laneLabel(lane: Lane, file: LaneFile, v: number, yr: number | null): string {
  const i = yr != null ? file.years.indexOf(yr) : -1;
  const shown = i >= 0 ? yr! : lane.flow.y;
  const share = i >= 0 ? (file.seaborne[i] ? v / file.seaborne[i] : null) : lane.share;
  const name = file.label || commodityMeta(lane.k)?.name || lane.k;
  const via = lane.via.length ? ` · via ${lane.via.map((c) => esc(chokepointName(c))).join(', ')}` : '';
  const vessel = lane.vclass.length ? `${esc(vesselName(lane.vclass[0]))} · ` : '';
  return (
    `<div><b>${esc(countryName(lane.o))} → ${esc(countryName(lane.d))}</b> · ${esc(name)}</div>` +
    `<div class="num">${fmt(v)} ${esc(lane.flow.u)} · ${pct(share)} of seaborne trade</div>` +
    `<div class="muted">${vessel}${fmt(lane.days)} days${via}</div>` +
    `<div class="src-line">${esc(sourceLabel(lane.flow.s))} · ${esc(String(shown))}</div>`
  );
}

registerLayerModule(() => {
  let seq = 0;
  let flown: string | null = null;

  effect(() => {
    // read every dependency synchronously (signals read after an await are not tracked)
    const on = layers.value.flows;
    const fam = family.value;
    const k = commodity.value;
    const vc = vesselClasses.value;
    const sel = selection.value;
    const yr = year.value;
    void [commodities.value, countries.value, vesselClassList.value, chokepointList.value, sources.value];

    const my = ++seq;
    if (!on) {
      setLineSet('lanes', []);
      return;
    }

    // which groups to load, and how many lanes of each to keep (undefined = all)
    let plan: { group: string; top?: number }[];
    if (k) plan = (LANE_GROUPS[k] ?? []).map((group) => ({ group }));
    else if (fam === 'freight') plan = [];
    else plan = OVERVIEW;
    const selLane = sel?.kind === 'lane' ? sel.id : null;
    const groups = new Set(plan.map((p) => p.group));
    if (selLane) groups.add(laneGroup(selLane));

    Promise.all([...groups].map((g) => loadLaneFile(g).catch(() => null))).then((files) => {
      if (my !== seq) return; // stale
      const byGroup = new Map(files.filter((f): f is LaneFile => !!f).map((f) => [f.group, f]));
      type Item = { lane: Lane; file: LaneFile; v: number };
      let items: Item[] = [];

      for (const { group, top } of plan) {
        const file = byGroup.get(group);
        if (!file) continue;
        let part: Item[] = [];
        for (const lane of file.lanes) {
          if (!k && fam !== 'all' && commodityMeta(lane.k)?.family !== fam) continue;
          if (vc.size && !lane.vclass.some((c) => vc.has(c))) continue;
          const v = laneValue(lane, file, yr);
          if (v > 0) part.push({ lane, file, v });
        }
        part.sort((a, b) => b.v - a.v);
        if (top) part = part.slice(0, top);
        items = items.concat(part);
      }

      // a selected lane is always drawn, even outside the overview / filters
      let picked: Item | undefined = items.find((i) => i.lane.id === selLane);
      if (selLane && !picked) {
        const file = byGroup.get(laneGroup(selLane));
        const lane = file?.lanes.find((l) => l.id === selLane);
        if (file && lane) {
          picked = { lane, file, v: laneValue(lane, file, yr) || lane.flow.v };
          items.push(picked);
        }
      }

      const max = Math.max(...items.map((i) => i.v), 1e-9);
      const isBright = (l: Lane): boolean => {
        if (selLane) return l.id === selLane;
        if (sel?.kind === 'country') return l.o === sel.id || l.d === sel.id;
        if (sel?.kind === 'chokepoint') return l.via.includes(sel.id);
        return true;
      };

      const features: Feature<LineString, LineFeatureProps>[] = [];
      // biggest first so thin lanes are drawn on top
      for (const { lane, file, v } of items.sort((a, b) => b.v - a.v)) {
        const fam2 = commodityMeta(lane.k)?.family;
        features.push({
          type: 'Feature',
          geometry: { type: 'LineString', coordinates: lane.g },
          properties: {
            id: lane.id,
            kind: 'lane',
            color: fam2 ? FAMILY_COLOR[fam2] : NEUTRAL,
            w: Math.sqrt(v / max),
            dim: !isBright(lane),
            hl: lane.id === selLane,
            label: laneLabel(lane, file, v, yr),
          },
        });
      }
      // alternative routing of the selected lane, dashed
      if (picked?.lane.alt) {
        features.push({
          type: 'Feature',
          geometry: { type: 'LineString', coordinates: picked.lane.alt.g },
          properties: {
            id: `${picked.lane.id}:alt`,
            kind: 'lane',
            dash: true,
            color: NEUTRAL,
            w: 0.4,
            label: `<div><b>Alternative routing</b></div><div class="muted">${esc(picked.lane.alt.label)}</div>`,
          },
        });
      }
      setLineSet('lanes', features);

      if (selLane && picked && flown !== selLane) flyToLine(picked.lane.g);
      flown = selLane;
    });
  });
});
