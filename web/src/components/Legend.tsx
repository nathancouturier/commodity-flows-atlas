/** Small map legend: only describes what is currently drawn. It can be folded away to free the map. */
import { useState } from 'preact/hooks';
import { choroInfo, mapNotice, commodity, family, landFlowsShown, layers, selection } from '../lib/store';
import { commodityMeta } from '../lib/data';
import { SEGMENT_COLOR, SEGMENT_LABEL } from '../lib/freight';
import { FAMILY_COLOR, FAMILY_LABEL, pct, shareOpacity } from '../lib/format';
import { STATUS_COLOR } from '../map/modules/infrastructure';
import type { Family, Segment } from '../types';

const SEGMENTS: Segment[] = ['dry', 'tanker', 'gas'];

function hexA(hex: string, a: number): string {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${n >> 16}, ${(n >> 8) & 255}, ${n & 255}, ${a.toFixed(2)})`;
}

const FOLD_KEY = 'cfa-legend-folded';

function readFolded(): boolean {
  try {
    const v = localStorage.getItem(FOLD_KEY);
    if (v !== null) return v === '1';
  } catch {
    /* storage blocked: fall through to the default */
  }
  // phones start with the legend folded into a small "Legend" button
  return window.matchMedia('(max-width: 760px)').matches;
}

function saveFolded(v: boolean) {
  try {
    localStorage.setItem(FOLD_KEY, v ? '1' : '0');
  } catch {
    /* private mode: the choice just isn't remembered */
  }
}

export function Legend() {
  const [folded, setFolded] = useState(readFolded);
  const fold = (v: boolean) => {
    setFolded(v);
    saveFolded(v);
  };
  const fam = family.value;
  const k = commodity.value;
  const sel = selection.value;
  const choro = choroInfo.value;
  const infraOn = layers.value.infrastructure;
  const land = landFlowsShown.value;

  const flowsOn = layers.value.flows && (!!k || fam !== 'freight') && !mapNotice.value;
  const routesOn = layers.value.routes || fam === 'freight';
  const chokeOn =
    layers.value.chokepoints || fam === 'freight' || sel?.kind === 'route' || sel?.kind === 'lane' || sel?.kind === 'chokepoint';

  let families: Family[] = [];
  if (flowsOn) {
    const own = k ? commodityMeta(k)?.family : undefined;
    families = own ? [own] : fam === 'all' || fam === 'freight' ? ['energy', 'metals', 'softs'] : [fam];
  }
  if (!flowsOn && !routesOn && !chokeOn && !infraOn && !choro) return null;
  if (folded)
    return (
      <button class="legend legend-pill glass" aria-expanded="false" title="Show the map legend" onClick={() => fold(false)}>
        <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><path d="M2 3h8M2 6h8M2 9h5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" /></svg>
        Legend
      </button>
    );
  return (
    <div class="legend glass" role="group" aria-label="Map legend">
      <button class="legend-fold" aria-expanded="true" aria-label="Hide the legend" title="Hide the legend" onClick={() => fold(true)}>
        <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true"><path d="M2 3.5 5 6.5 8 3.5" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" /></svg>
      </button>
      {families.map((f) => (
        <span class="legend-item">
          <span class="legend-swatch" style={{ background: FAMILY_COLOR[f] }} />
          {FAMILY_LABEL[f]}
        </span>
      ))}
      {land > 0 && (
        <span class="legend-item" title="Customs flows by land or pipeline, drawn between country anchor points (no route geometry)">
          <span class="legend-swatch legend-dash" style={{ color: k ? FAMILY_COLOR[commodityMeta(k)?.family ?? 'energy'] : FAMILY_COLOR.energy }} />
          Overland / pipeline
        </span>
      )}
      {routesOn &&
        SEGMENTS.map((s) => (
          <span class="legend-item">
            <span class="legend-swatch" style={{ background: SEGMENT_COLOR[s] }} />
            {SEGMENT_LABEL[s]}
          </span>
        ))}
      {(flowsOn || routesOn) && (
        <span class="legend-item legend-width" title={flowsOn ? 'Line width scales with the square root of volume' : 'Benchmark routes are drawn thicker'}>
          <svg width="30" height="10" viewBox="0 0 30 10" aria-hidden="true">
            <path d="M0 5 L30 1.5 L30 8.5 Z" fill="currentColor" opacity="0.7" />
          </svg>
          {flowsOn ? 'Line width = volume' : 'Benchmarks thicker'}
        </span>
      )}
      {chokeOn && (
        <span class="legend-item">
          <span class="legend-cp" />
          Chokepoint
        </span>
      )}
      {choro && (
        <div class="legend-block legend-ramp">
          <div class="legend-ramp-bar">
            <span class="num">{pct(choro.min)}</span>
            <span
              class="ramp"
              aria-hidden="true"
              style={{
                background: `linear-gradient(90deg, ${[0, 0.25, 0.5, 0.75, 1]
                  .map((t) => hexA(choro.color, shareOpacity(choro.min + (choro.max - choro.min) * t)))
                  .join(', ')})`,
              }}
            />
            <span class="num">{pct(choro.max)}</span>
          </div>
          <div class="muted">
            Share of world {choro.metric} ({choro.unit}) · {choro.source}, {choro.year}
          </div>
        </div>
      )}
      {infraOn && (
        <div class="legend-block legend-infra">
          <div class="legend-infra-status">
            <span class="legend-item"><span class="status-key" style={{ borderColor: STATUS_COLOR.damaged }} />Damaged</span>
            <span class="legend-item"><span class="status-key" style={{ borderColor: STATUS_COLOR.idle }} />Idle / suspended</span>
            <span class="legend-item"><span class="status-key dashed" style={{ borderColor: STATUS_COLOR.planned }} />Planned / under construction</span>
            <span class="legend-item muted">Dashed pipeline = not operating</span>
          </div>
        </div>
      )}
    </div>
  );
}
