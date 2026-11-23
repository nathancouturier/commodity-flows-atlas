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
  sheetSnap,
  layers,
  infraHidden,
  infraAvailable,
  rfOrigin,
  rfDest,
  rfGroup,
  rfCommodity,
  routeFinderOpen,
  setFamily,
  type FamilyFilter,
  type Metric,
  type SheetSnap,
} from '../lib/store';
import { FAMILY_COLOR, FAMILY_LABEL } from '../lib/format';
import { LANE_GROUPS, SEGMENT_COLOR, SEGMENT_LABEL, loadRoutes, openVesselClass, routeMatches, segmentOf, vesselClassList, vesselName, finderCommodity } from '../lib/freight';
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

/** A whole family (Freight, Energy, Metals, Softs or all): no commodity, no vessel-class filter. */
function pickFamily(f: FamilyFilter) {
  setFamily(f);
  commodity.value = null;
  vesselClasses.value = new Set();
  select(null);
}

/** A click on the open route closes it; any other route opens. */
function toggleRoute(id: string) {
  const s = selection.peek();
  select(s?.kind === 'route' && s.id === id ? null : { kind: 'route', id });
}

// the route finder follows the commodity picked in the panel (when it has sea lanes)
// (a finder question that came with the link is kept, and so is a question about coal when the panel switches between its two kinds)
let finderStarted = false;
commodity.subscribe((k) => {
  const linked = !finderStarted && !!(rfOrigin.peek() || rfDest.peek());
  finderStarted = true;
  if (linked || !k || !(k in LANE_GROUPS) || finderCommodity(rfCommodity.peek()) === finderCommodity(k)) return;
  rfCommodity.value = k;
  rfOrigin.value = null;
  rfDest.value = null;
  rfGroup.value = null;
});

export function SidePanel() {
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
        <FreightSection />
        <div class="panel-block">
          <Dropdown name="Route finder" stack value={<RouteFinderSummary />} open={routeFinderOpen.value} onToggle={(o) => (routeFinderOpen.value = o)}>
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
  /** long values (a commodity, a vessel class, a route question) go on their own line under the name */
  stack?: boolean;
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
      class={`cc-browse dd${props.stack ? ' dd-stack' : ''}`}
      open={open}
      onToggle={(e) => {
        const o = (e.currentTarget as HTMLDetailsElement).open;
        if (props.onToggle) props.onToggle(o);
        else setInner(o);
      }}
      onKeyDown={(e) => {
        // Escape folds the dropdown the focus is in and hands the focus back to its button;
        // a menu open inside it closes first (App's Escape handler)
        if (e.key !== 'Escape' || e.defaultPrevented || !open) return;
        const el = e.currentTarget as HTMLDetailsElement;
        if (el.querySelector('[aria-haspopup][aria-expanded="true"]')) return;
        e.preventDefault();
        if (props.onToggle) props.onToggle(false);
        else setInner(false);
        el.querySelector('summary')?.focus();
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
  const pick = (f: FamilyFilter) => {
    setBrowseOpen(false);
    pickFamily(f);
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
  // freight has its own dropdown (Routes by vessel class)
  const commodityFamily = fam !== 'all' && fam !== 'freight';
  const value = current ? (
    <>{dot(FAMILY_COLOR[current.family])} {current.name}</>
  ) : commodityFamily ? (
    <>{dot(FAMILY_COLOR[fam])} {FAMILY_LABEL[fam]}</>
  ) : null;
  return (
    <div class="panel-block">
      <Dropdown
        name="All commodities"
        stack
        value={value}
        onClear={current || commodityFamily ? () => pick('all') : undefined}
        open={browseOpen}
        onToggle={setBrowseOpen}
      >
        {FAMILIES.map((g) => (
          <div key={g} class="cc-group">
            <button
              class="vc-label fam-head"
              aria-pressed={!current && fam === g}
              style={{ color: FAMILY_COLOR[g] }}
              title={`Show all of ${FAMILY_LABEL[g]}`}
              onClick={() => pick(g)}
            >
              {FAMILY_LABEL[g]}
              <span class="fam-all">all</span>
            </button>
            {commodities.value.filter((c) => c.family === g).map((c, i, list) => (
              <>
                {c.sub && c.sub !== list[i - 1]?.sub && <div class="cc-sub">{c.sub}</div>}
                <button class="list-btn" aria-pressed={commodity.value === c.id} onClick={() => choose(commodity.value === c.id ? null : c.id)}>
                  <span class="dot" style={{ color: FAMILY_COLOR[c.family], width: '6px', height: '6px' }} />
                  {c.name}
                  <span class="meta">{c.unit}</span>
                </button>
              </>
            ))}
          </div>
        ))}
      </Dropdown>
    </div>
  );
}

// ---------------------------------------------------------------- freight tab

const SEGMENTS: Segment[] = ['dry', 'tanker', 'gas'];

const dot = (color: string) => <span class="dot" style={{ color, width: '6px', height: '6px' }} />;

/**
 * Freight, like a commodity family in All commodities: the FREIGHT header shows every route
 * (Freight view), each vessel class below shows its family's routes and opens its page. On the
 * Freight view the route list follows.
 */
function FreightSection() {
  const fam = family.value;
  const freight = fam === 'freight';
  const vc = vesselClasses.value;
  const sel = selection.value;
  const vessels = vesselClassList.value;
  const [open, setOpen] = useState(false);
  const [routes, setRoutes] = useState<Route[]>([]);
  useEffect(() => {
    loadRoutes().then(setRoutes).catch(() => undefined);
  }, []);
  const allFreight = () => {
    setOpen(false);
    pickFamily('freight');
  };
  const chooseVessel = (id: string) => {
    setOpen(false);
    if (sel?.kind === 'vessel' && sel.id === id) return pickFamily('freight'); // second click: every route
    openVesselClass(id);
  };
  // the class named in the summary: the open one, else the first class of the active filter
  const head = vc.size ? (vessels.find((v) => sel?.kind === 'vessel' && v.id === sel.id && vc.has(v.id)) ?? vessels.find((v) => vc.has(v.id))) : undefined;
  const matched = vc.size ? routes.filter((r) => !r.discontinued && routeMatches(r, vc)).length : 0;
  const value = head ? (
    <>{dot(SEGMENT_COLOR[head.segment])} {shortName(head.name)} ({matched})</>
  ) : freight ? (
    <>{dot(FAMILY_COLOR.freight)} All routes</>
  ) : null;
  return (
    <div class="panel-block">
      <Dropdown
        name="Routes by vessel class"
        stack
        value={value}
        onClear={freight || vc.size ? () => { setOpen(false); pickFamily('all'); } : undefined}
        open={open}
        onToggle={setOpen}
      >
        <div class="cc-group">
          <button
            class="vc-label fam-head"
            aria-pressed={freight && !vc.size}
            style={{ color: FAMILY_COLOR.freight }}
            title="Show every freight route"
            onClick={allFreight}
          >
            {FAMILY_LABEL.freight}
            <span class="fam-all">all routes</span>
          </button>
          {vessels.map((v) => (
            <button class="list-btn" key={v.id} aria-pressed={vc.has(v.id)} title={`${v.name}: its routes on the map and its page`} onClick={() => chooseVessel(v.id)}>
              {dot(SEGMENT_COLOR[v.segment])}
              {shortName(v.name)}
              <span class="meta">{vesselSize(v)}</span>
            </button>
          ))}
        </div>
        {freight && <RouteList />}
      </Dropdown>
    </div>
  );
}

/** "VLOC (Valemax/Guaibamax)" -> "VLOC" for the lists; the full name stays in the title. */
function shortName(name: string): string {
  return name.replace(/\s*\(.*\)$/, '');
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
    .filter((r) => routeMatches(r, vc))
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

  const others = visible.filter((r) => !r.benchmark && !r.generated);
  const atlas = visible.filter((r) => r.generated);
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
              {others.length} {others.length === 1 ? 'route' : 'routes'}<span class="meta">non-benchmark · typical class</span>
            </summary>
            {others.map(row)}
          </details>
        </>
      )}
      {atlas.length > 0 && (
        <>
          <h4 class="route-sub">Atlas corridors, by typical class</h4>
          {vesselClassList.value.map((v) => {
            const items = atlas.filter((r) => r.vclass === v.id);
            if (!items.length) return null;
            const key = `gen:${v.id}`;
            return (
              <details class="route-group" key={key} open={opened.has(key) || vc.size > 0 || items.some((r) => r.id === selId)} onToggle={keep(key)}>
                <summary>
                  {dot(SEGMENT_COLOR[v.segment])}
                  {shortName(v.name)}
                  <span class="meta">{items.length}</span>
                </summary>
                {items.map(row)}
              </details>
            );
          })}
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
