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
  infraHidden,
  infraAvailable,
  rfOrigin,
  rfDest,
  rfCommodity,
  setFamily,
  toggleLayer,
  type FamilyFilter,
  type Metric,
  type SheetSnap,
} from '../lib/store';
import { FAMILY_COLOR, FAMILY_LABEL } from '../lib/format';
import { LANE_GROUPS, SEGMENT_COLOR, SEGMENT_LABEL, loadRoutes, segmentOf, vesselClassList, vesselFamily, vesselMatches, vesselName } from '../lib/freight';
import { RouteFinderSlot } from './RouteFinder';
import { LayerSwitches, InfraTypeChips } from './LayerSwitches';
import { flyToWorld } from '../map/controller';
import { Section, INFRA_META, INFRA_ORDER } from './ui';
import type { CommodityMeta, Family, Route, Segment, VesselClass } from '../types';

const METRICS: { id: Metric; label: string }[] = [
  { id: 'none', label: 'Off' },
  { id: 'production', label: 'Production' },
  { id: 'reserves', label: 'Reserves' },
  { id: 'consumption', label: 'Consumption' },
  { id: 'exports', label: 'Exports' },
  { id: 'imports', label: 'Imports' },
];

const FAMILIES: Family[] = ['energy', 'metals', 'softs'];

/** Typical size of a vessel class for the list, e.g. "180k dwt", "174k m³". */
function vesselSize(v: VesselClass): string {
  const u = v.size.u === 'cbm' ? 'm³' : v.size.u === 'teu' ? 'TEU' : 'dwt';
  const t = v.size.typical;
  return `${t >= 1000 ? `${Math.round(t / 1000)}k` : t} ${u}`;
}

// a shared link that opens a vessel class (#sel=vessel:capesize) also filters the map to its routes
{
  const s0 = selection.peek();
  if (s0?.kind === 'vessel' && !vesselClasses.peek().size) vesselClasses.value = new Set(vesselFamily(s0.id));
}

/** A click on the open route closes it; any other route opens. */
function toggleRoute(id: string) {
  const s = selection.peek();
  select(s?.kind === 'route' && s.id === id ? null : { kind: 'route', id });
}

// the route finder follows the commodity picked in the panel (when it has sea lanes)
commodity.subscribe((k) => {
  if (!k || !(k in LANE_GROUPS) || rfCommodity.peek() === k) return;
  rfCommodity.value = k;
  rfOrigin.value = null;
  rfDest.value = null;
});

export function SidePanel() {
  const fam = family.value;
  const freight = fam === 'freight';
  const current = commodities.value.find((c) => c.id === commodity.value);

  const hidden = panelCollapsed.value;
  return (
    <aside
      id="controls"
      tabIndex={-1}
      class={`side-panel glass snap-${sheetSnap.value} ${panelCollapsed.value ? 'collapsed' : ''}`}
      aria-label="Map parameters"
    >
      <SheetHead summary={current?.name} />
      {/* desktop: this button stays in the top-left corner and folds the panel into itself */}
      <button
        class="panel-head"
        aria-controls="controls-body"
        aria-expanded={!hidden}
        title={hidden ? 'Show the map controls' : 'Hide the map controls'}
        onClick={() => (panelCollapsed.value = !hidden)}
      >
        <svg width="13" height="13" viewBox="0 0 14 14" aria-hidden="true">
          <path d="M2 3.5h10M2 7h10M2 10.5h10" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" />
          <circle cx="5" cy="3.5" r="1.6" fill="var(--panel-solid)" stroke="currentColor" stroke-width="1.3" />
          <circle cx="9.5" cy="7" r="1.6" fill="var(--panel-solid)" stroke="currentColor" stroke-width="1.3" />
          <circle cx="6.5" cy="10.5" r="1.6" fill="var(--panel-solid)" stroke="currentColor" stroke-width="1.3" />
        </svg>
        Controls
        <svg class="panel-head-chev" width="11" height="11" viewBox="0 0 12 12" aria-hidden="true">
          <path d={hidden ? 'M3 4.5 6 7.5 9 4.5' : 'M3 7.5 6 4.5 9 7.5'} fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
      </button>
      <div class="panel-scroll" id="controls-body">
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
            <Dropdown name="Infrastructure types" value={<InfraSummary />} onClear={infraHidden.value.size ? () => (infraHidden.value = new Set()) : undefined}>
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
    </div>
  );
}

/**
 * What the map shows: a whole family (Freight, Energy, Metals, Softs; clicking a group header) or one
 * commodity (colours its producers, draws its flows and opens its page). The × goes back to everything.
 */
function CommoditySection(props: { current: CommodityMeta | undefined }) {
  const { current } = props;
  const fam = family.value;
  const [browseOpen, setBrowseOpen] = useState(false);
  const vc = vesselClasses.value;
  const sel = selection.value;
  const vessels = vesselClassList.value;
  // a whole family (group header): no commodity, no vessel-class filter
  const pickFamily = (f: FamilyFilter) => {
    setBrowseOpen(false);
    setFamily(f);
    commodity.value = null;
    vesselClasses.value = new Set();
    select(null);
  };
  const choose = (v: string | null) => {
    setBrowseOpen(false);
    if (!v) return pickFamily('all');
    // the commodity's family follows, so the highlighted group, layers and infrastructure agree
    const meta = commodities.value.find((c) => c.id === v);
    if (meta && family.peek() !== meta.family) setFamily(meta.family);
    vesselClasses.value = new Set();
    commodity.value = v;
    select({ kind: 'commodity', id: v });
    flyToWorld(true);
  };
  // a vessel class under Freight works like a commodity under Energy: its routes on the map, its page open
  const chooseVessel = (id: string) => {
    setBrowseOpen(false);
    if (sel?.kind === 'vessel' && sel.id === id) return pickFamily('freight'); // second click: all freight
    if (family.peek() !== 'freight') setFamily('freight');
    commodity.value = null;
    vesselClasses.value = new Set(vesselFamily(id));
    if (!layers.peek().routes) toggleLayer('routes', true);
    select({ kind: 'vessel', id });
  };
  const dot = (color: string) => <span class="dot" style={{ color, width: '6px', height: '6px' }} />;
  // the vessel class shown in the summary: the open one, else the first class of the active filter
  const vHead = fam === 'freight' && vc.size ? vessels.find((v) => (sel?.kind === 'vessel' ? v.id === sel.id : vc.has(v.id))) ?? vessels.find((v) => vc.has(v.id)) : undefined;
  const value = current ? (
    <>{dot(FAMILY_COLOR[current.family])} {current.name}</>
  ) : vHead ? (
    <>{dot(SEGMENT_COLOR[vHead.segment])} {vHead.name}</>
  ) : fam !== 'all' ? (
    <>{dot(FAMILY_COLOR[fam])} {FAMILY_LABEL[fam]}</>
  ) : null;
  return (
    <div class="panel-block">
      <Dropdown
        name="Browse all commodities"
        value={value}
        onClear={current || fam !== 'all' || vc.size ? () => pickFamily('all') : undefined}
        open={browseOpen}
        onToggle={setBrowseOpen}
      >
        <button class="list-btn fam-btn" aria-pressed={!current && fam === 'all'} onClick={() => pickFamily('all')}>
          All commodities
          <span class="meta">overview</span>
        </button>
        <div class="cc-group">
          <button
            class="vc-label fam-head"
            aria-pressed={!current && fam === 'freight' && !vc.size}
            style={{ color: FAMILY_COLOR.freight }}
            title="Show all freight routes"
            onClick={() => pickFamily('freight')}
          >
            {FAMILY_LABEL.freight}
            <span class="fam-all">all</span>
          </button>
          {vessels.map((v) => (
            <button class="list-btn" key={v.id} aria-pressed={vc.has(v.id)} title={`${v.name}: its routes on the map and its page`} onClick={() => chooseVessel(v.id)}>
              {dot(SEGMENT_COLOR[v.segment])}
              {v.name.replace(/\s*\(.*\)$/, '')}
              <span class="meta">{vesselSize(v)}</span>
            </button>
          ))}
        </div>
        {FAMILIES.map((g) => (
          <div key={g} class="cc-group">
            <button
              class="vc-label fam-head"
              aria-pressed={!current && fam === g}
              style={{ color: FAMILY_COLOR[g] }}
              title={`Show all of ${FAMILY_LABEL[g]}`}
              onClick={() => pickFamily(g)}
            >
              {FAMILY_LABEL[g]}
              <span class="fam-all">all</span>
            </button>
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
                  onClick={() => {
                    toggleInSet(vesselClasses, v.id);
                    if (!layers.peek().routes) toggleLayer('routes', true);
                  }}
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
    if (vesselClasses.peek().size && !layers.peek().routes) toggleLayer('routes', true);
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
            <button class="list-btn route-row" key={r.id} onClick={() => toggleRoute(r.id)}>
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
  const hidden = infraHidden.value;
  const avail = infraAvailable.value;
  const shown = INFRA_ORDER.filter((t) => !avail || avail.has(t));
  const on = shown.filter((t) => !hidden.has(t));
  if (on.length === shown.length) return <>All</>;
  return <>{on.length ? on.map((t) => INFRA_META[t].plural).join(', ') : 'None'}</>;
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
  const [opened, setOpened] = useState<Set<string>>(() => new Set(['dry']));
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
      onClick={() => toggleRoute(r.id)}
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
  const keep = (key: string) => (e: Event) => {
    const isOpen = (e.currentTarget as HTMLDetailsElement).open;
    setOpened((prev) => {
      if (prev.has(key) === isOpen) return prev;
      const next = new Set(prev);
      if (isOpen) next.add(key);
      else next.delete(key);
      return next;
    });
  };
  return (
    <Section title="Baltic benchmarks">
      {SEGMENTS.map((seg) => {
        const items = visible.filter((r) => r.benchmark && segmentOf(r.vclass) === seg);
        if (!items.length) return null;
        return (
          <details class="route-group" key={seg} open={opened.has(seg) || vc.size > 0 || seg === selSeg} onToggle={keep(seg)}>
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
          <details class="route-group" open={opened.has('others') || vc.size > 0 || (selSeg != null && others.some((r) => r.id === selId))} onToggle={keep('others')}>
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
