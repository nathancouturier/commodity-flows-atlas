/**
 * Left parameters panel: commodity picker, layer toggles, map colouring, filters.
 * Everything beyond the default "flows" layer is one click away here.
 */
import { useEffect, useRef, useState } from 'preact/hooks';
import { commodities } from '../lib/data';
import {
  family,
  commodity,
  layers,
  toggleLayer,
  metric,
  select,
  panelCollapsed,
  selection,
  vesselClasses,
  infraTypes,
  infraAvailable,
  toggleInSet,
  sheetSnap,
  type Metric,
  type SheetSnap,
} from '../lib/store';
import { FAMILY_COLOR, FAMILY_LABEL } from '../lib/format';
import { SEGMENT_COLOR, SEGMENT_LABEL, loadRoutes, segmentOf, vesselClassList, vesselFamily, vesselMatches, vesselName } from '../lib/freight';
import { RouteFinderSlot } from './RouteFinder';
import { flyToWorld } from '../map/controller';
import { Section, Switch, InfraIcon, INFRA_META, INFRA_ORDER } from './ui';
import type { Family, Route, Segment } from '../types';

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
  const list = commodities.value.filter((c) => c.family !== 'freight' && (fam === 'all' || fam === 'freight' || c.family === fam));
  const groups = FAMILIES.filter((f) => fam === 'all' || fam === 'freight' || f === fam);
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
        <Section title="Map layers">
          <Switch
            label="Physical flows"
            desc="What is traded: country-to-country volumes (customs data); width = tonnage"
            checked={layers.value.flows}
            onChange={(v) => toggleLayer('flows', v)}
          />
          <Switch
            label="Freight routes"
            desc="How it ships: Baltic benchmark and main routes, by vessel class"
            checked={layers.value.routes}
            onChange={(v) => toggleLayer('routes', v)}
          />
          <Switch
            label="Chokepoints"
            desc="Straits and canals, with current traffic"
            checked={layers.value.chokepoints}
            onChange={(v) => toggleLayer('chokepoints', v)}
          />
          <Switch
            label="Infrastructure"
            desc="Mines, fields, refineries, LNG terminals, pipelines, ports"
            checked={layers.value.infrastructure}
            onChange={(v) => toggleLayer('infrastructure', v)}
          />
          {layers.value.infrastructure && <InfraTypeChips />}
        </Section>

        {freight ? (
          <>
            <Section title="Route finder">
              <RouteFinderSlot always />
            </Section>
            <VesselFilter />
            <RouteList />
          </>
        ) : (
          <>
            <div class="rf-top">
              <RouteFinderSlot />
            </div>
        <VesselQuick />
        <Section title="Colour countries by">
          <label class="cc-pick">
            <span class="sr-only">Commodity to colour the map by</span>
            <select
              value={commodity.value ?? ''}
              onChange={(e) => {
                const v = (e.currentTarget as HTMLSelectElement).value || null;
                commodity.value = v;
                if (v) flyToWorld();
              }}
            >
              <option value="">Choose a commodity…</option>
              {FAMILIES.map((f) => (
                <optgroup key={f} label={FAMILY_LABEL[f]}>
                  {commodities.value.filter((c) => c.family === f).map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
          </label>
          <div class="chips" role="radiogroup">
            {METRICS.map((m) => {
              const noData = m.id !== 'none' && !!current && !current.has.includes(m.id);
              const off = m.id !== 'none' && (!current || noData);
              return (
                <button
                  class="chip"
                  role="radio"
                  aria-checked={metric.value === m.id}
                  aria-pressed={metric.value === m.id}
                  disabled={off}
                  title={noData ? 'No free country-level data' : undefined}
                  style={{ opacity: off ? 0.4 : 1 }}
                  onClick={() => (metric.value = m.id)}
                >
                  {m.label}
                </button>
              );
            })}
          </div>
          {!current && <p class="muted" style={{ fontSize: '12px', margin: '8px 0 0' }}>Choose a commodity: its producing countries are coloured in its family colour.</p>}
          {current && METRICS.some((m) => m.id !== 'none' && !current.has.includes(m.id)) && (
            <p class="muted" style={{ fontSize: '12px', margin: '8px 0 0' }}>Greyed-out options have no free country-level data for {current.name}.</p>
          )}
        </Section>

        {groups.map((g) => {
          const items = list.filter((c) => c.family === g);
          if (!items.length) return null;
          return (
            <Section key={g} title={<span style={{ color: FAMILY_COLOR[g] }}>{FAMILY_LABEL[g]}</span>}>
              {items.map((c) => (
                <button
                  class="list-btn"
                  aria-pressed={commodity.value === c.id}
                  onClick={() => {
                    const same = commodity.value === c.id;
                    commodity.value = same ? null : c.id;
                    select(same ? null : { kind: 'commodity', id: c.id });
                    if (!same) flyToWorld();
                  }}
                >
                  <span class="dot" style={{ color: FAMILY_COLOR[c.family], width: '6px', height: '6px' }} />
                  {c.name}
                  <span class="meta">{c.unit}</span>
                </button>
              ))}
            </Section>
          );
        })}
          </>
        )}
      </div>
    </aside>
  );
}

/** Infrastructure type filter: empty selection = all types. */
function InfraTypeChips() {
  const sel = infraTypes.value;
  const avail = infraAvailable.value;
  const shown = INFRA_ORDER.filter((t) => !avail || avail.has(t));
  const cur = commodities.value.find((c) => c.id === commodity.value);
  const scope = cur ? cur.name : family.value !== 'all' ? (family.value === 'freight' ? 'Freight' : FAMILY_LABEL[family.value as Family]) : null;
  return (
    <div class="infra-filter">
      {scope && <div class="infra-scope">Showing assets for {scope}</div>}
      <div class="chips">
        {shown.map((t) => (
          <button class="chip chip-infra" key={t} aria-pressed={sel.has(t)} onClick={() => toggleInSet(infraTypes, t)} title={INFRA_META[t].label}>
            <InfraIcon type={t} size={18} color={sel.has(t) ? '#3ee6ff' : '#b9c4d0'} />
            {INFRA_META[t].plural}
          </button>
        ))}
      </div>
      <div class="infra-hint">
        {sel.size ? (
          <button class="link-btn" onClick={() => (infraTypes.value = new Set())}>Show all types</button>
        ) : (
          <span>All types shown. Pick one or more to filter.</span>
        )}
      </div>
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
    if (sel.size && !routes.length) loadRoutes().then(setRoutes).catch(() => undefined);
  }, [sel.size]);
  const active = (id: string) => vesselFamily(id).some((m) => sel.has(m));
  const pick = (id: string) => {
    // single family at a time here: clicking the active one clears it
    vesselClasses.value = active(id) ? new Set() : new Set(vesselFamily(id));
  };
  const matched = sel.size ? routes.filter((r) => !r.discontinued && vesselMatches(r.vclass, sel)) : [];
  return (
    <Section
      title="Routes by vessel class"
      aside={sel.size > 0 ? <button class="link-btn" onClick={() => (vesselClasses.value = new Set())}>Clear</button> : null}
    >
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
    </Section>
  );
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
