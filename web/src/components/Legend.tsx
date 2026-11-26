/** Small map legend: only describes what is currently drawn. It can be folded away to free the map. */
import { useEffect, useRef, useState } from 'preact/hooks';
import { choroInfo, mapNotice, commodity, family, landFlowsShown, layers, selection, year } from '../lib/store';
import { commodityMeta } from '../lib/data';
import { SEGMENT_LABEL } from '../lib/freight';
import { FAMILY_COLOR, FAMILY_LABEL, fmt, pct, shareOpacity } from '../lib/format';
import { statusRingSvg } from '../lib/palette';
import { RouteSwatch } from './RouteSwatch';
import { LANE_PX, laneGap, laneScale, laneWidthPx, mixedLanesShown } from '../map/modules/lanes';
import { mixedArcsShown } from '../map/modules/landflows';
import { ROUTE_W } from '../map/modules/routes';
import { MIN_TINT_SHARE } from '../map/modules/choropleth';

/** The floor of the country colours as the legend prints it ("0.25%": the one-decimal rule of pct would print 0.3%). */
const FLOOR_TEXT = `${+(MIN_TINT_SHARE * 100).toPrecision(2)}%`;
import type { Family, Segment } from '../types';
import '../styles/legend-scale.css';
import '../styles/lane-engine.css';

const SEGMENTS: Segment[] = ['dry', 'tanker', 'gas'];

/** Side of the status keys: the smallest at which the three badge glyphs can be told apart on a screen of one device pixel per px. */
const STATUS_KEY_PX = 20;

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
  const mixedArcs = mixedArcsShown.value;

  const flowsOn = layers.value.flows && (!!k || fam !== 'freight') && !mapNotice.value;
  const routesOn = layers.value.routes;
  const scale = flowsOn ? laneScale.value : null;
  const mixedLanes = flowsOn ? mixedLanesShown.value : 0;
  const gap = flowsOn ? laneGap.value : null;
  const legendColor = k ? FAMILY_COLOR[commodityMeta(k)?.family ?? 'energy'] : FAMILY_COLOR.energy;
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
      {mixedLanes + mixedArcs > 0 && (
        <span
          class="legend-item"
          title={
            mixedLanes === 0
              ? 'Trade that moves both by sea and overland, with no source for the split: the arc joins the two countries and is not a route. The tonnage is the customs total for all modes. It is not in the seaborne totals.'
              : mixedArcs > 0
                ? 'Trade that moves both by sea and overland, with no source for the split: the line is the sea route where the atlas has one, otherwise an arc between the two countries that is not a route. The tonnage is the customs total for all modes. It is not in the seaborne totals.'
                : 'Trade that moves both by sea and overland, with no source for the split: the line is the sea route and the tonnage is the customs total for all modes. It is not in the seaborne totals.'
          }
        >
          <span class="legend-swatch legend-dash legend-mixed" style={{ color: k ? legendColor : 'var(--ink-1)' }} />
          Sea and overland
        </span>
      )}
      {land - mixedArcs > 0 && (
        <span class="legend-item" title="Customs flows by land or pipeline, drawn between country anchor points (no route geometry)">
          <span class="legend-swatch legend-dash" style={{ color: legendColor }} />
          Overland / pipeline
        </span>
      )}
      {gap && (
        <span class="legend-item legend-gap" title="Hidden as unreliable (the declared value does not fit the tonnage) or no customs record for that year">
          {gap.n} lane{gap.n === 1 ? ' has' : 's have'} no figure for {gap.year}, not drawn
        </span>
      )}
      {routesOn && (
        <div class="legend-block legend-routes">
          <span class="legend-label">Freight routes</span>
          {SEGMENTS.map((s) => (
            <span class="legend-item">
              <RouteSwatch segment={s} />
              {SEGMENT_LABEL[s]}
            </span>
          ))}
          <span class="legend-item legend-width" title="Freight routes have a fixed width: it does not show a volume. Benchmark routes are drawn thicker than the other routes, and the atlas's generated corridors (built from the customs pairs table, not market benchmarks) thinner still.">
            <span class="legend-ref">
              <WidthSample px={routePx(ROUTE_W.benchmark)} />
              Benchmark
            </span>
            <span class="legend-ref">
              <WidthSample px={routePx(ROUTE_W.other)} />
              Other
            </span>
            <span class="legend-ref">
              <WidthSample px={routePx(ROUTE_W.generated)} />
              Atlas corridor (generated)
            </span>
            <span class="muted" style={{ whiteSpace: 'nowrap' }}>(fixed width)</span>
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
            {/* every share under the floor has the one floor tint on the map: its own swatch, and the ramp starts above it */}
            {choro.min < MIN_TINT_SHARE && choro.max > MIN_TINT_SHARE && (
              <>
                <span class="ramp-floor" aria-hidden="true" style={{ background: hexA(choro.color, shareOpacity(MIN_TINT_SHARE)) }} />
                <span class="num">under {FLOOR_TEXT}</span>
              </>
            )}
            <span class="num">{choro.min < MIN_TINT_SHARE && choro.max > MIN_TINT_SHARE ? FLOOR_TEXT : pct(choro.min)}</span>
            <span
              class="ramp"
              aria-hidden="true"
              style={{
                background: `linear-gradient(90deg, ${[0, 0.25, 0.5, 0.75, 1]
                  .map((t) => {
                    const lo = Math.max(choro.min, choro.max > MIN_TINT_SHARE ? MIN_TINT_SHARE : choro.min);
                    return hexA(choro.color, shareOpacity(lo + (choro.max - lo) * t));
                  })
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
            <span class="legend-item"><span class="infra-ic" aria-hidden="true" dangerouslySetInnerHTML={{ __html: statusRingSvg('damaged', { size: STATUS_KEY_PX }) }} />Damaged</span>
            <span class="legend-item"><span class="infra-ic" aria-hidden="true" dangerouslySetInnerHTML={{ __html: statusRingSvg('idle', { size: STATUS_KEY_PX }) }} />Idle / suspended</span>
            <span class="legend-item"><span class="infra-ic" aria-hidden="true" dangerouslySetInnerHTML={{ __html: statusRingSvg('planned', { size: STATUS_KEY_PX }) }} />Planned</span>
            <span class="legend-item"><span class="infra-ic" aria-hidden="true" dangerouslySetInnerHTML={{ __html: statusRingSvg('construction', { size: STATUS_KEY_PX }) }} />Under construction</span>
            <span class="legend-item"><span class="infra-ic" aria-hidden="true" dangerouslySetInnerHTML={{ __html: statusRingSvg('closed', { size: STATUS_KEY_PX }) }} />Closed</span>
            <span class="legend-item muted">Dashed pipeline = not operating</span>
            {year.value != null && (
              <span class="legend-item muted" title="History: an asset whose opening year is known is dimmed before it opens. Many assets have no opening year in the data, and those are drawn at every year.">
                History: dimmed = not open yet; no opening year = drawn at every year
              </span>
            )}
          </div>
        </div>
      )}
    </div>
      )}
    </div>
  );
}
