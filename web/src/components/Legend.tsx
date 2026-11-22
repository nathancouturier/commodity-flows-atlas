/** Small map legend: only describes what is currently drawn. It can be folded away to free the map. */
import { useEffect, useRef, useState } from 'preact/hooks';
import { choroInfo, mapNotice, commodity, family, landFlowsShown, layers, selection } from '../lib/store';
import { commodityMeta } from '../lib/data';
import { SEGMENT_COLOR, SEGMENT_LABEL } from '../lib/freight';
import { FAMILY_COLOR, FAMILY_LABEL, fmt, pct, shareOpacity } from '../lib/format';
import { STATUS_COLOR } from '../map/modules/infrastructure';
import { LANE_PX, laneScale, laneWidthPx } from '../map/modules/lanes';
import { ROUTE_W } from '../map/modules/routes';
import type { Family, Segment } from '../types';
import '../styles/legend-scale.css';

const SEGMENTS: Segment[] = ['dry', 'tanker', 'gas'];

function hexA(hex: string, a: number): string {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${n >> 16}, ${(n >> 8) & 255}, ${n & 255}, ${a.toFixed(2)})`;
}

/** Round volumes are 1, 2 or 5 times a power of ten; n counts along that series (0 = 1, 1 = 2, 2 = 5, 3 = 10). */
function roundVolume(n: number): number {
  return [1, 2, 5][((n % 3) + 3) % 3] * 10 ** Math.floor(n / 3);
}

/** Three round reference volumes for the lane width key: the largest at or below the scale maximum. */
function referenceVolumes(max: number): number[] {
  let n = 3 * Math.floor(Math.log10(max));
  while (roundVolume(n + 1) <= max * (1 + 1e-9)) n++;
  return [n - 5, n - 2, n].map((i) => Number(roundVolume(i).toPrecision(1)));
}

const refLabel = (v: number) => (v >= 1 ? fmt(v) : String(v));

/** A short horizontal line of the given width in px, as drawn on the map. */
function WidthSample({ px }: { px: number }) {
  return (
    <svg class="legend-line" width="16" height="6" viewBox="0 0 16 6" aria-hidden="true">
      <path d="M1.5 3 H14.5" stroke="currentColor" stroke-width={px.toFixed(2)} stroke-linecap="round" fill="none" />
    </svg>
  );
}

/** The legend is open on every load; phones start with it folded (it would cover most of the map). */
function foldedAtStart(): boolean {
  return typeof matchMedia === 'function' && matchMedia('(max-width: 760px)').matches;
}

export function Legend() {
  const [folded, setFolded] = useState(foldedAtStart);
  const dockRef = useRef<HTMLDivElement>(null);
  // publish the legend's height so the side panel never runs over it (see --legend-h in app.css)
  useEffect(() => {
    const el = dockRef.current;
    const root = document.documentElement;
    if (!el) {
      root.style.setProperty('--legend-h', '0px');
      return;
    }
    const ro = new ResizeObserver(() => root.style.setProperty('--legend-h', `${Math.ceil(el.getBoundingClientRect().height)}px`));
    ro.observe(el);
    return () => {
      ro.disconnect();
      root.style.setProperty('--legend-h', '0px');
    };
  });
  const fold = (v: boolean) => setFolded(v);
  const fam = family.value;
  const k = commodity.value;
  const sel = selection.value;
  const choro = choroInfo.value;
  const infraOn = layers.value.infrastructure;
  const land = landFlowsShown.value;

  const flowsOn = layers.value.flows && (!!k || fam !== 'freight') && !mapNotice.value;
  const routesOn = layers.value.routes;
  const scale = flowsOn ? laneScale.value : null;
  const routePx = (w: number) => LANE_PX.min + (LANE_PX.max - LANE_PX.min) * w;
  const chokeOn =
    layers.value.chokepoints || sel?.kind === 'route' || sel?.kind === 'lane' || sel?.kind === 'chokepoint';

  let families: Family[] = [];
  if (flowsOn) {
    const own = k ? commodityMeta(k)?.family : undefined;
    families = own ? [own] : fam === 'all' || fam === 'freight' ? ['energy', 'metals', 'softs'] : [fam];
  }
  if (!flowsOn && !routesOn && !chokeOn && !infraOn && !choro) return null;
  // the "Legend" button stays in the same corner: it opens the legend next to it and closes it again
  return (
    <div class={`legend-dock${folded ? ' folded' : ''}`} ref={dockRef}>
      <button
        class="legend-pill glass"
        aria-expanded={!folded}
        aria-controls="map-legend"
        title={folded ? 'Show the map legend' : 'Hide the map legend'}
        onClick={() => fold(!folded)}
      >
        <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><path d="M2 3h8M2 6h8M2 9h5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" /></svg>
        Legend
      </button>
      {!folded && (
    <div id="map-legend" class="legend legend-box glass" role="group" aria-label="Map legend">
      {flowsOn && (
        <div class="legend-block legend-lanes">
          <span class="legend-label">Seaborne lanes</span>
          {families.map((f) => (
            <span class="legend-item">
              <span class="legend-swatch" style={{ background: FAMILY_COLOR[f] }} />
              {FAMILY_LABEL[f]}
            </span>
          ))}
          {scale && scale.unit ? (
            <span
              class="legend-item legend-width legend-scale"
              title={`Lane width follows the square root of the annual volume. The scale is the same for every year: the full width is ${fmt(scale.max)} ${scale.unit}, the largest lane of the whole series.`}
            >
              Width
              {referenceVolumes(scale.max).map((v) => (
                <span class="legend-ref" key={v}>
                  <WidthSample px={laneWidthPx(v, scale.max)} />
                  <span class="num">{refLabel(v)}</span>
                </span>
              ))}
              {scale.unit} a year
            </span>
          ) : (
            <span class="legend-item legend-width" title="Lane width follows the square root of the annual volume">
              Width = volume
            </span>
          )}
        </div>
      )}
      {land > 0 && (
        <span class="legend-item" title="Customs flows by land or pipeline, drawn between country anchor points (no route geometry)">
          <span class="legend-swatch legend-dash" style={{ color: k ? FAMILY_COLOR[commodityMeta(k)?.family ?? 'energy'] : FAMILY_COLOR.energy }} />
          Overland / pipeline
        </span>
      )}
      {routesOn && (
        <div class="legend-block legend-routes">
          <span class="legend-label">Freight routes</span>
          {SEGMENTS.map((s) => (
            <span class="legend-item">
              <span class="legend-swatch" style={{ background: SEGMENT_COLOR[s] }} />
              {SEGMENT_LABEL[s]}
            </span>
          ))}
          <span class="legend-item legend-width" title="Freight routes have a fixed width: it does not show a volume. Benchmark routes are drawn thicker than the other routes.">
            <span class="legend-ref">
              <WidthSample px={routePx(ROUTE_W.benchmark)} />
              Benchmark
            </span>
            <span class="legend-ref">
              <WidthSample px={routePx(ROUTE_W.other)} />
              Other
            </span>
            <span class="muted">(fixed width)</span>
          </span>
        </div>
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
      )}
    </div>
  );
}
