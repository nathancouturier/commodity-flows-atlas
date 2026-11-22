/**
 * Left parameters panel: commodity picker, layer toggles, map colouring, filters.
 * Everything beyond the default "flows" layer is one click away here.
 */
import { commodities } from '../lib/data';
import {
  family,
  commodity,
  layers,
  toggleLayer,
  metric,
  select,
  panelCollapsed,
  type Metric,
} from '../lib/store';
import { FAMILY_COLOR, FAMILY_LABEL } from '../lib/format';
import { Section, Switch } from './ui';
import type { Family } from '../types';

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
  const current = commodities.value.find((c) => c.id === commodity.value);

  return (
    <aside class={`side-panel glass ${panelCollapsed.value ? 'collapsed' : ''}`} aria-label="Map parameters">
      <div class="panel-scroll">
        <Section title="Map layers">
          <Switch label="Physical flows" checked={layers.value.flows} onChange={(v) => toggleLayer('flows', v)} />
          <Switch label="Freight routes" checked={layers.value.routes} onChange={(v) => toggleLayer('routes', v)} />
          <Switch label="Chokepoints" checked={layers.value.chokepoints} onChange={(v) => toggleLayer('chokepoints', v)} />
          <Switch
            label="Infrastructure"
            checked={layers.value.infrastructure}
            onChange={(v) => toggleLayer('infrastructure', v)}
          />
        </Section>

        <Section title="Colour countries by" aside={current ? <span class="muted">{current.name}</span> : null}>
          <div class="chips" role="radiogroup">
            {METRICS.map((m) => (
              <button
                class="chip"
                role="radio"
                aria-checked={metric.value === m.id}
                aria-pressed={metric.value === m.id}
                disabled={m.id !== 'none' && !current}
                style={{ opacity: m.id !== 'none' && !current ? 0.4 : 1 }}
                onClick={() => (metric.value = m.id)}
              >
                {m.label}
              </button>
            ))}
          </div>
          {!current && <p class="muted" style={{ fontSize: '12px', margin: '8px 0 0' }}>Pick a commodity to colour the map.</p>}
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
      </div>
    </aside>
  );
}
