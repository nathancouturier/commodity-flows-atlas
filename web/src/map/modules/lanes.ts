/**
 * "Physical flows" layer: seaborne trade lanes (origin -> destination country pairs).
 *
 * - no commodity: overview = top N lanes per group (OVERVIEW), coloured by commodity family
 * - commodity: every lane of the commodity's groups
 * - filters: family tab, vessel classes, year; a selected country / chokepoint / lane
 *   keeps its lanes bright and dims the rest
 * - with no year (or the latest) only the main set is drawn; with a past year every lane that has a figure
 *   that year is, history-only lanes included. A year with no figure (hidden as suspect, or no customs
 *   record) is not drawn and the legend says how many lanes are in that case
 * - a mixed lane (by sea and overland, split not known) is dashed
 */
import { effect, signal } from '@preact/signals';
import type { Feature, LineString } from 'geojson';
import type { Lane, LaneFile } from '../../types';
import { registerLayerModule } from '../layers';
import { setLineSet, flyToLine, type LineFeatureProps } from '../controller';
import { commodity, family, laneVia, layers, selection, vesselClasses, year } from '../../lib/store';
import { commodities, commodityMeta, countries, countryName, sourceLabel, sources } from '../../lib/data';
import { LANE_GROUPS, OVERVIEW, chokepointList, chokepointName, laneEst, laneGroup, loadLaneFile, vesselClassList, vesselMatches, vesselName } from '../../lib/freight';
import { FAMILY_COLOR, escapeHtml as esc, fmt, fmtEst, pct } from '../../lib/format';
import '../../styles/lane-engine.css';

const NEUTRAL = '#8aa0b8';

/**
 * Width scale of the lanes now drawn: `max` is the volume drawn at full width (null = no lanes drawn).
 * It is the largest lane of the whole series (every year) of the commodity or family in view, so a lane
 * keeps the same width for the same volume whatever the year, the vessel filter or the selection.
 */
export const laneScale = signal<{ max: number; unit: string } | null>(null);

/** Lanes in view that have no figure for the chosen past year (so are not drawn); null = none, or no past year. */
export const laneGap = signal<{ year: number; n: number } | null>(null);
/** Mixed (sea and overland) lanes now drawn, for the legend. */
export const mixedLanesShown = signal(0);

/** Line width in px for a volume; the two ends are the 'lanes-line' widths in map/controller.ts. */
export const LANE_PX = { min: 0.8, max: 4.5 };
export function laneWidthPx(v: number, max: number): number {
  return LANE_PX.min + (LANE_PX.max - LANE_PX.min) * Math.sqrt(Math.min(1, Math.max(0, v / max)));
}

/** A past year of the timeline: not the latest year, which is the default view. */
export function isPastYear(file: LaneFile, yr: number | null): yr is number {
  return yr != null && yr !== file.y && file.years.includes(yr);
}

/** Annual value of a lane for the chosen year; null when the lane has no figure that year (not 0). */
export function laneValue(lane: Lane, file: LaneFile, yr: number | null): number | null {
  if (isPastYear(file, yr)) return lane.hist[file.years.indexOf(yr)] ?? null;
  return lane.flow.v;
}

function laneLabel(lane: Lane, file: LaneFile, v: number | null, yr: number | null): string {
  const past = isPastYear(file, yr);
  const i = past ? file.years.indexOf(yr) : -1;
  const shown = past ? yr : lane.flow.y;
  const est = past ? lane.histFlags?.[String(yr)] === 'est' : laneEst(lane);
  const mixed = lane.mode === 'mixed';
  const share = mixed ? null : past ? (v && file.seaborne[i] ? v / file.seaborne[i] : null) : lane.share;
  const name = file.label || commodityMeta(lane.k)?.name || lane.k;
  const via = lane.via.length ? ` · via ${lane.via.map((c) => esc(chokepointName(c))).join(', ')}` : '';
  const vessel = lane.vclass.length ? `${esc(vesselName(lane.vclass[0]))} · ` : '';
  // sea through a foreign port: both ports when both ends are landlocked
  const transitPorts = [lane.transit, lane.transit2].filter((t): t is NonNullable<typeof t> => !!t).map((t) => esc(file.ports[t.port]?.name ?? t.port));
  const transit = transitPorts.length ? `<div class="muted">Sea via ${transitPorts.join(' and ')}</div>` : '';
  const figure = `${fmtEst(v, est)} ${esc(lane.flow.u)}`;
  const tail = mixed ? ' · by sea and overland (split not known)' : ` · ${pct(share, (v ?? 0) > 0)} of seaborne trade`;
  return (
    `<div><b>${esc(countryName(lane.o))} → ${esc(countryName(lane.d))}</b> · ${esc(name)}</div>` +
    (v != null && v > 0
      ? `<div class="num">${figure}${est ? ' · Atlas estimate' : ''}${tail}</div>`
      : `<div class="num">No figure for ${shown}</div>`) +
    transit +
    `<div class="muted">${vessel}${fmt(lane.days)} days${via}</div>` +
    `<div class="src-line">${esc(est ? `${sourceLabel(file.s)}, declared value` : sourceLabel(past ? file.s : lane.flow.s))} · ${esc(String(shown))}</div>`
  );
}

/** With a country selected: its biggest lanes in each commodity group. */
const COUNTRY_TOP = 12;

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
    const selLane0 = sel?.kind === 'lane' ? sel.id : null;
    // with Physical flows off (e.g. on the Freight tab) a selected lane is still drawn
    if (!on && !selLane0) {
      setLineSet('lanes', []);
      laneScale.value = null;
      laneGap.value = null;
      mixedLanesShown.value = 0;
      laneVia.value = sel?.kind === 'country' ? new Set() : null;
      return;
    }

    // a selected country is isolated: only the lanes that load or discharge there are drawn
    const iso = sel?.kind === 'country' ? sel.id : null;
    // which groups to load, and how many lanes of each to keep (undefined = all)
    let plan: { group: string; top?: number }[];
    if (!on) plan = [];
    else if (k) plan = (LANE_GROUPS[k] ?? []).map((group) => ({ group }));
    else if (fam === 'freight') plan = [];
    else if (iso) plan = [...new Set(Object.values(LANE_GROUPS).flat())].map((group) => ({ group, top: COUNTRY_TOP }));
    else plan = OVERVIEW;
    if (!iso) laneVia.value = null;
    const selLane = sel?.kind === 'lane' ? sel.id : null;
    const groups = new Set(plan.map((p) => p.group));
    if (selLane) groups.add(laneGroup(selLane));

    Promise.all([...groups].map((g) => loadLaneFile(g).catch(() => null))).then((files) => {
      if (my !== seq) return; // stale
      const byGroup = new Map(files.filter((f): f is LaneFile => !!f).map((f) => [f.group, f]));
      type Item = { lane: Lane; file: LaneFile; v: number };
      let items: Item[] = [];
      let gap = 0;
      let gapYear: number | null = null;

      for (const { group, top } of plan) {
        const file = byGroup.get(group);
        if (!file) continue;
        let part: Item[] = [];
        const past = isPastYear(file, yr);
        for (const lane of file.lanes) {
          if (iso && lane.o !== iso && lane.d !== iso) continue;
          if (!k && fam !== 'all' && commodityMeta(lane.k)?.family !== fam) continue;
          if (!vesselMatches(lane.vclass, vc)) continue;
          // the latest year draws the main set; a past year draws every lane that has a figure that year
          if (!past && lane.set === 'history') continue;
          const v = laneValue(lane, file, yr);
          if (v == null) {
            // no figure that year (not zero): not drawn; counted for the legend where the whole set is in view
            if (past && (k || iso)) {
              gap++;
              gapYear = yr;
            }
            continue;
          }
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
          // no value for the chosen year: it is drawn at the minimum width, not at the width of the latest year
          picked = { lane, file, v: laneValue(lane, file, yr) ?? 0 };
          items.push(picked);
        }
      }

      if (iso) laneVia.value = new Set(items.flatMap((i) => i.lane.via));
      // one scale for every year: the largest lane, in any year, of the groups in view (of the family
      // tab on the overview); filters and the selected year do not move it
      let max = 0;
      const units = new Set<string>();
      const scaleFiles = plan.length ? plan.map((p) => byGroup.get(p.group)) : [picked?.file];
      for (const file of scaleFiles) {
        if (!file) continue;
        for (const lane of file.lanes) {
          if (!k && plan.length && fam !== 'all' && commodityMeta(lane.k)?.family !== fam) continue;
          units.add(file.unit);
          max = Math.max(max, lane.flow.v, ...lane.hist.map((h) => h ?? 0));
        }
      }
      if (!(max > 0)) max = Math.max(...items.map((i) => i.v), 1e-9);
      laneScale.value = items.length ? { max, unit: units.size === 1 ? [...units][0] : '' } : null;
      const isBright = (l: Lane): boolean => {
        if (selLane) return l.id === selLane;
        if (sel?.kind === 'country') return l.o === sel.id || l.d === sel.id;
        if (sel?.kind === 'chokepoint') return l.via.includes(sel.id);
        return true;
      };

      const features: Feature<LineString, LineFeatureProps>[] = [];
      let mixed = 0;
      // biggest first so thin lanes are drawn on top
      for (const { lane, file, v } of items.sort((a, b) => b.v - a.v)) {
        const fam2 = commodityMeta(lane.k)?.family;
        const isMixed = lane.mode === 'mixed';
        if (isMixed) mixed++;
        features.push({
          type: 'Feature',
          geometry: { type: 'LineString', coordinates: lane.g },
          properties: {
            id: lane.id,
            kind: 'lane',
            color: fam2 ? FAMILY_COLOR[fam2] : NEUTRAL,
            w: Math.sqrt(Math.min(1, v / max)),
            dim: !isBright(lane),
            hl: lane.id === selLane,
            // a mixed lane (sea and overland, split not known) is dashed, and softer unless selected
            ...(isMixed ? { dash: true, soft: lane.id !== selLane } : {}),
            label: laneLabel(lane, file, v, yr),
          },
        });
      }
      // alternative routings of the selected lane, dashed (a click on one selects the lane again)
      const alts = picked ? (picked.lane.alts?.length ? picked.lane.alts : picked.lane.alt ? [picked.lane.alt] : []) : [];
      for (const alt of alts) {
        features.push({
          type: 'Feature',
          geometry: { type: 'LineString', coordinates: alt.g },
          properties: {
            id: picked!.lane.id,
            kind: 'lane',
            dash: true,
            color: NEUTRAL,
            w: 0.4,
            label: `<div><b>Alternative routing</b></div><div class="muted">${esc(alt.label)}</div>`,
          },
        });
      }
      mixedLanesShown.value = mixed;
      laneGap.value = gap > 0 && gapYear != null ? { year: gapYear, n: gap } : null;
      setLineSet('lanes', features);

      if (selLane && picked && flown !== selLane) flyToLine(picked.lane.g);
      flown = selLane;
    });
  });
});
