/**
 * Left parameters panel: commodity picker, layer toggles, map colouring, filters.
 * Everything beyond the default "flows" layer is one click away here.
 */
import { useEffect, useRef, useState } from 'preact/hooks';
import type { ComponentChildren } from 'preact';
import { commodities, countryName } from '../lib/data';
import {
  family,
  commodity,
  metric,
  select,
  panelCollapsed,
  selection,
  vesselClasses,
  toggleInSet,
  sheetSnap,
  layers,
  infraTypes,
  rfOrigin,
  rfDest,
  type Metric,
  type SheetSnap,
} from '../lib/store';
import { FAMILY_COLOR, FAMILY_LABEL } from '../lib/format';
import { SEGMENT_COLOR, SEGMENT_LABEL, loadRoutes, segmentOf, vesselClassList, vesselFamily, vesselMatches, vesselName } from '../lib/freight';
import { RouteFinderSlot } from './RouteFinder';
import { LayerSwitches, InfraTypeChips } from './LayerSwitches';
import { flyToWorld } from '../map/controller';
import { Section, INFRA_META, INFRA_ORDER } from './ui';
import type { CommodityMeta, Family, Route, Segment } from '../types';

const METRICS: { id: Metric; label: string }[] = [
  { id: 'none', label: 'Off' },
  { id: 'production', label: 'Production' },
  { id: 'reserves', label: 'Reserves' },
  { id: 'consumption', label: 'Consumption' },
  { id: 'exports', label: 'Exports' },
  { id: 'imports', label: 'Imports' },
];

const FAMILIES: Family[] = ['energy', 'metals', 'softs'];

export function SidePanel() {
  const fam = family.value;
  const freight = fam === 'freight';
  const current = commodities.value.find((c) => c.id === commodity.value);

  return (
    <aside
      id="controls"
      tabIndex={-1}
      class={`side-panel glass snap-${sheetSnap.value} ${panelCollapsed.value ? 'collapsed' : ''}`}
      aria-label="Map parameters"
    >
      <SheetHead summary={current?.name} />
      <div class="panel-scroll">
        <CommoditySection current={current} />
        <div class="panel-block">
          {freight ? (
            <Dropdown name="Routes by vessel class" value={<FreightSummary />} defaultOpen onClear={vesselClasses.value.size ? () => (vesselClasses.value = new Set()) : undefined}>
              <VesselFilter />
              <RouteList />
            </Dropdown>
          ) : (
            <VesselQuick />
          )}
        </div>
        <div class="panel-block">
          <Dropdown name="Route finder" value={<RouteFinderSummary />}>
            <RouteFinderSlot always />
          </Dropdown>
        </div>
        <div class="panel-block">
          <Dropdown name="Map layers" value={<LayersSummary />}>
            <LayerSwitches />
          </Dropdown>
        </div>
        {layers.value.infrastructure && (
          <div class="panel-block">
            <Dropdown name="Infrastructure types" value={<InfraSummary />} onClear={infraTypes.value.size ? () => (infraTypes.value = new Set()) : undefined}>
              <InfraTypeChips />
            </Dropdown>
          </div>
        )}
        <ColourBySection current={current} />
      </div>
    </aside>
  );
}

/** Infrastructure type filter: empty selection = all types. */


/** A collapsible block styled like a dropdown; the summary shows the current choice. */
function Dropdown(props: {
  name: string;
  value?: ComponentChildren;
  onClear?: () => void;
  defaultOpen?: boolean;
  open?: boolean;
  onToggle?: (open: boolean) => void;
  children: ComponentChildren;
}) {
  const [inner, setInner] = useState(!!props.defaultOpen);
  const open = props.open ?? inner;
  const hasValue = props.value != null && props.value !== false && props.value !== '';
  return (
    <details
      class="cc-browse dd"
      open={open}
      onToggle={(e) => {
        const o = (e.currentTarget as HTMLDetailsElement).open;
        if (props.onToggle) props.onToggle(o);
        else setInner(o);
      }}
    >
      <summary>
        <span class="dd-name">{props.name}</span>
        {hasValue && <span class="dd-value">{props.value}</span>}
        {hasValue && props.onClear && (
          <button
            class="dd-clear"
            aria-label={`Clear ${props.name}`}
            title="Clear"
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              props.onClear!();
            }}
          >
            ×
          </button>
        )}
      </summary>
      <div class="dd-body">{props.children}</div>
    </details>
  );
}


/** Map colouring by the selected commodity's country table (last block of the panel). */
function ColourBySection(props: { current: CommodityMeta | undefined }) {
  const { current } = props;
  const [metricOpen, setMetricOpen] = useState(false);
  return (
    <div class="panel-block">
      <Dropdown
        name="Colour countries by"
        value={metric.value !== 'none' ? METRICS.find((m) => m.id === metric.value)?.label : 'Off'}
        open={metricOpen}
        onToggle={setMetricOpen}
      >
        <div role="radiogroup" aria-label="Colour countries by">
          {METRICS.map((m) => {
            const noData = m.id !== 'none' && !!current && !current.has.includes(m.id);
            const off = m.id !== 'none' && (!current || noData);
            return (
              <button
                class="list-btn"
                role="radio"
                aria-checked={metric.value === m.id}
                aria-pressed={metric.value === m.id}
                disabled={off}
                title={!current && m.id !== 'none' ? 'Choose a commodity first' : noData ? 'No free country-level data' : undefined}
                style={{ opacity: off ? 0.4 : 1 }}
                onClick={() => {
                  metric.value = m.id;
                  setMetricOpen(false);
                }}
              >
                {m.label}
                {noData && <span class="meta">no data</span>}
              </button>
            );
          })}
        </div>
      </Dropdown>
      {!current && <p class="muted cc-hint">Choose a commodity: its producing countries are coloured, with their share of world output on the map.</p>}
    </div>
  );
}

/** Commodity choice first: picking one colours its producers, draws its flows and opens its page. */
function CommoditySection(props: { current: CommodityMeta | undefined }) {
  const { current } = props;
  const fam = family.value;
  const fams = FAMILIES.filter((f) => fam === 'all' || fam === 'freight' || f === fam);
  const [browseOpen, setBrowseOpen] = useState(false);
  const choose = (v: string | null) => {
    setBrowseOpen(false);
    commodity.value = v;
    if (v) {
      select({ kind: 'commodity', id: v });
      flyToWorld(true);
    } else if (selection.peek()?.kind === 'commodity') {
      select(null);
    }
  };
  return (
    <div class="panel-block">
      <Dropdown
        name="Browse all commodities"
        value={current ? <><span class="dot" style={{ color: FAMILY_COLOR[current.family], width: '6px', height: '6px' }} /> {current.name}</> : null}
        onClear={() => choose(null)}
        open={browseOpen}
        onToggle={setBrowseOpen}
      >
        {fams.map((g) => (
          <div key={g} class="cc-group">
            <div class="vc-label" style={{ color: FAMILY_COLOR[g] }}>{FAMILY_LABEL[g]}</div>
            {commodities.value.filter((c) => c.family === g).map((c) => (
              <button class="list-btn" aria-pressed={commodity.value === c.id} onClick={() => choose(commodity.value === c.id ? null : c.id)}>
                <span class="dot" style={{ color: FAMILY_COLOR[c.family], width: '6px', height: '6px' }} />
                {c.name}
                <span class="meta">{c.unit}</span>
              </button>
            ))}
          </div>
        ))}
      </Dropdown>
    </div>
  );
}

// ---------------------------------------------------------------- freight tab

const SEGMENTS: Segment[] = ['dry', 'tanker', 'gas'];

/** Vessel class chips grouped by segment; multi-select drives the lanes and routes layers. */
function VesselFilter() {
  const sel = vesselClasses.value;
  const list = vesselClassList.value;
  return (
    <Section
      title="Vessel class"
      aside={
        sel.size > 0 ? (
          <button class="link-btn" onClick={() => (vesselClasses.value = new Set())}>
            Clear
          </button>
        ) : null
      }
    >
      {SEGMENTS.map((seg) => {
        const items = list.filter((v) => v.segment === seg);
        if (!items.length) return null;
        return (
          <div class="vc-group" key={seg}>
            <div class="vc-label">{SEGMENT_LABEL[seg]}</div>
            <div class="chips">
              {items.map((v) => (
                <button
                  class="chip"
                  aria-pressed={sel.has(v.id)}
                  style={{ '--chip-color': SEGMENT_COLOR[seg] }}
                  title={vesselFamily(v.id).length > 1 ? `Also matches ${vesselFamily(v.id).filter((x) => x !== v.id).map(vesselName).join(', ')}` : undefined}
                  onClick={() => toggleInSet(vesselClasses, v.id)}
                >
                  {v.name}
                </button>
              ))}
            </div>
          </div>
        );
      })}
    </Section>
  );
}

/** Vessel-class families: one click shows every route of that class on the map (any tab). */
const QUICK: { seg: Segment; items: { id: string; label: string }[] }[] = [
  { seg: 'dry', items: [{ id: 'capesize', label: 'Capesize' }, { id: 'panamax', label: 'Panamax' }, { id: 'supramax', label: 'Supramax' }, { id: 'handysize', label: 'Handysize' }] },
  { seg: 'tanker', items: [{ id: 'vlcc', label: 'VLCC' }, { id: 'suezmax', label: 'Suezmax' }, { id: 'aframax', label: 'Aframax' }, { id: 'lr2', label: 'LR2' }, { id: 'lr1', label: 'LR1' }, { id: 'mr', label: 'MR' }] },
  { seg: 'gas', items: [{ id: 'lng', label: 'LNG' }, { id: 'vlgc', label: 'VLGC' }] },
];

function VesselQuick() {
  const sel = vesselClasses.value;
  const [routes, setRoutes] = useState<Route[]>([]);
  useEffect(() => {
    loadRoutes().then(setRoutes).catch(() => undefined);
  }, []);
  const active = (id: string) => vesselFamily(id).some((m) => sel.has(m));
  const [open, setOpen] = useState(false);
  const pick = (id: string) => {
    // single family at a time here: clicking the active one clears it
    vesselClasses.value = active(id) ? new Set() : new Set(vesselFamily(id));
    setOpen(false);
  };
  const matched = sel.size ? routes.filter((r) => !r.discontinued && vesselMatches(r.vclass, sel)) : [];
  const current = QUICK.flatMap((g) => g.items.map((it) => ({ ...it, seg: g.seg }))).find((it) => active(it.id));
  const summary = current ? (
    <>
      <span class="dot" style={{ color: SEGMENT_COLOR[current.seg], width: '6px', height: '6px' }} /> {current.label} ({matched.length})
    </>
  ) : null;
  return (
    <>
      <Dropdown name="Routes by vessel class" value={current ? summary : null} onClear={() => (vesselClasses.value = new Set())} open={open} onToggle={setOpen}>
      {QUICK.map((g) => (
        <div class="vc-group" key={g.seg}>
          <div class="vc-label">{SEGMENT_LABEL[g.seg]}</div>
          <div class="chips">
            {g.items.map((it) => (
              <button
                key={it.id}
                class="chip"
                aria-pressed={active(it.id)}
                style={{ '--chip-color': SEGMENT_COLOR[g.seg] }}
                title={vesselFamily(it.id).length > 1 ? `Includes ${vesselFamily(it.id).map(vesselName).join(', ')}` : vesselName(it.id)}
                onClick={() => pick(it.id)}
              >
                {it.label}
              </button>
            ))}
          </div>
        </div>
      ))}
      {sel.size > 0 && (
        <div class="vq-list">
          <div class="muted" style={{ fontSize: '12px', margin: '6px 0 4px' }}>
            {matched.length} route{matched.length === 1 ? '' : 's'} on the map
          </div>
          {matched.map((r) => (
            <button class="list-btn route-row" key={r.id} onClick={() => select({ kind: 'route', id: r.id })}>
              {r.benchmark ? <span class="code">{r.id}</span> : <span class="dot" style={{ color: SEGMENT_COLOR[segmentOf(r.vclass)], width: '6px', height: '6px' }} />}
              <span class="route-name">{r.name}</span>
            </button>
          ))}
        </div>
      )}
      </Dropdown>
    </>
  );
}

/** Summary line of the Freight-tab route dropdown. */
function FreightSummary() {
  const n = vesselClasses.value.size;
  return n ? <>{[...vesselClasses.value].map(vesselName).join(', ')}</> : <>All</>;
}

/** Summary line of the map layers dropdown: "All" or the visible layers. */
function LayersSummary() {
  const l = layers.value;
  const names: [keyof typeof l, string][] = [['flows', 'Flows'], ['routes', 'Routes'], ['chokepoints', 'Chokepoints'], ['infrastructure', 'Infrastructure']];
  const on = names.filter(([k]) => l[k]).map(([, n]) => n);
  return <>{on.length === names.length ? 'All' : on.length ? on.join(', ') : 'None'}</>;
}

/** Summary line of the infrastructure dropdown: the asset types shown. */
function InfraSummary() {
  const sel = infraTypes.value;
  if (!sel.size) return <>All</>;
  return <>{INFRA_ORDER.filter((t) => sel.has(t)).map((t) => INFRA_META[t].plural).join(', ')}</>;
}

/** Summary line of the route finder dropdown: the current question, if any. */
function RouteFinderSummary() {
  const o = rfOrigin.value;
  const d = rfDest.value;
  if (o && d) return <>{countryName(o)} → {countryName(d)}</>;
  return null;
}

/** Baltic benchmarks (by segment) and other heavy-traffic routes; discontinued ones last. */
function RouteList() {
  const [routes, setRoutes] = useState<Route[]>([]);
  useEffect(() => {
    loadRoutes().then(setRoutes).catch(() => undefined);
  }, []);
  const vc = vesselClasses.value;
  const sel = selection.value;
  const selId = sel?.kind === 'route' ? sel.id : null;
  void vesselClassList.value; // segmentOf() depends on the class list

  const visible = routes
    .filter((r) => vesselMatches(r.vclass, vc))
    .sort((a, b) => Number(!!a.discontinued) - Number(!!b.discontinued)); // stable: discontinued last
  const selSeg = selId ? segmentOf(routes.find((r) => r.id === selId)?.vclass ?? '') : null;

  const row = (r: Route) => (
    <button
      class={`list-btn route-row ${r.discontinued ? 'is-off' : ''}`}
      key={r.id}
      aria-pressed={selId === r.id}
      onClick={() => select({ kind: 'route', id: r.id })}
    >
      {r.benchmark ? (
        <span class="code">{r.id}</span>
      ) : (
        <span class="dot" style={{ color: SEGMENT_COLOR[segmentOf(r.vclass)], width: '6px', height: '6px' }} />
      )}
      <span class="route-name">
        {r.name}
        {r.discontinued && <small> (discontinued)</small>}
      </span>
      <span class="meta">{vesselName(r.vclass)}</span>
    </button>
  );

  const others = visible.filter((r) => !r.benchmark);
  return (
    <Section title="Baltic benchmarks">
      {SEGMENTS.map((seg) => {
        const items = visible.filter((r) => r.benchmark && segmentOf(r.vclass) === seg);
        if (!items.length) return null;
        return (
          <details class="route-group" key={seg} open={vc.size > 0 || seg === 'dry' || seg === selSeg}>
            <summary>
              <span class="dot" style={{ color: SEGMENT_COLOR[seg], width: '6px', height: '6px' }} />
              {SEGMENT_LABEL[seg]}
              <span class="meta">{items.length}</span>
            </summary>
            {items.map(row)}
          </details>
        );
      })}
      {others.length > 0 && (
        <>
          <h4 class="route-sub">Other heavy-traffic routes</h4>
          <details class="route-group" open={vc.size > 0 || selSeg != null && others.some((r) => r.id === selId)}>
            <summary>
              {others.length} routes<span class="meta">non-benchmark</span>
            </summary>
            {others.map(row)}
          </details>
        </>
      )}
      {!visible.length && <p class="muted" style={{ fontSize: '12px' }}>No routes for the selected vessel classes.</p>}
    </Section>
  );
}

// ---------------------------------------------------------------- bottom-sheet header (tablet / phone)

const SNAPS: SheetSnap[] = ['peek', 'half', 'full'];

/** Grab handle of the bottom sheet: tap cycles peek / half / full, a vertical drag steps up or down. */
function SheetHead({ summary }: { summary?: string }) {
  const snap = sheetSnap.value;
  const start = useRef<number | null>(null);
  const step = (dir: 1 | -1) => {
    const i = SNAPS.indexOf(sheetSnap.value);
    sheetSnap.value = SNAPS[Math.max(0, Math.min(SNAPS.length - 1, i + dir))];
  };
  return (
    <div class="sheet-head">
      <button
        class="sheet-handle"
        aria-label={`Resize panel, now ${snap === 'peek' ? 'minimised' : snap === 'half' ? 'half height' : 'full height'}`}
        onPointerDown={(e) => {
          start.current = e.clientY;
          (e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId);
        }}
        onPointerUp={(e) => {
          const dy = start.current == null ? 0 : e.clientY - start.current;
          start.current = null;
          if (Math.abs(dy) > 24) step(dy < 0 ? 1 : -1);
          else sheetSnap.value = SNAPS[(SNAPS.indexOf(sheetSnap.value) + 1) % SNAPS.length];
        }}
        onKeyDown={(e) => {
          if (e.key === 'ArrowUp') step(1);
          else if (e.key === 'ArrowDown') step(-1);
        }}
        onClick={(e) => e.detail === 0 && (sheetSnap.value = SNAPS[(SNAPS.indexOf(sheetSnap.value) + 1) % SNAPS.length])}
      >
        <span class="sheet-grip" aria-hidden="true" />
      </button>
      <div class="sheet-summary">{summary ? `${summary} · map controls` : 'Map layers, commodities, route finder'}</div>
    </div>
  );
}
