/**
 * Infrastructure rows of a commodity page ("Key infrastructure") and of a country page ("Main
 * infrastructure"): grouped by asset type and ranked among comparable figures only. A capacity in kb/d,
 * in Mt of ore or in Mt of all port cargo is never ranked against another kind of figure.
 */
import { useMemo, useState } from 'preact/hooks';
import type { InfraType } from '../../types';
import { commodityMeta, countryName, sourceLabel } from '../../lib/data';
import { fmt } from '../../lib/format';
import { readCapacity, type CapacityRead, type Form } from '../../lib/capacity';
import { figureText, isOperating, OUTPUT_LABEL, yearText } from '../../lib/infra';
import { lowerName } from '../../lib/prices';
import { select } from '../../lib/store';
import { infraColor, infraRef, type InfraFeature } from '../../map/modules/infrastructure';
import { InfraIcon, INFRA_ORDER, RowBtn, SourcesLine, StatusBadge, shortSource } from '../ui';
import '../../styles/infra.css';

/** Rows shown before "Show all N". */
const FIRST_ROWS = 8;

const GROUP_LABEL: Record<InfraType, string> = {
  field: 'Oil & gas fields',
  refinery: 'Refineries',
  'lng-export': 'LNG export terminals',
  'lng-import': 'LNG import terminals',
  pipeline: 'Pipelines',
  mine: 'Mines',
  smelter: 'Smelters / refineries',
  port: 'Ports',
};

const FORM_ORDER: Form[] = ['product', 'concentrate', 'ore', 'feed'];
const FORM_LABEL: Record<Form, string> = { product: '', concentrate: 'concentrate', ore: 'ore processed', feed: 'concentrate feed' };

interface Row {
  f: InfraFeature;
  cap: CapacityRead;
}
/** Rows whose figures are comparable (same unit family, same commodity, same form), largest first. */
interface Block {
  key: string;
  cap: CapacityRead;
  rows: Row[];
}
interface Group {
  type: InfraType;
  blocks: Block[];
  n: number;
}

const subjectName = (s: string) => (s === 'coal' ? 'Coal' : s === 'cereal' ? 'Cereals' : (commodityMeta(s)?.name ?? s));
const cap1 = (s: string) => s[0].toUpperCase() + s.slice(1);

function buildGroups(items: InfraFeature[], commodity?: string): Group[] {
  const byType = new Map<InfraType, Map<string, Block>>();
  for (const f of items) {
    const cap = readCapacity(f.p, commodity);
    // a figure for another commodity is not printed: the asset joins those without a figure
    const key = cap.kind === 'own' || cap.kind === 'cargo' ? cap.key : 'none';
    const blocks = byType.get(f.p.type) ?? new Map<string, Block>();
    const b = blocks.get(key) ?? { key, cap, rows: [] };
    b.rows.push({ f, cap });
    blocks.set(key, b);
    byType.set(f.p.type, blocks);
  }
  // operating figures first, then planned and under-construction ones, then closed assets, then the assets without a figure
  const kindOrder = (b: Block) => (b.cap.kind === 'none' ? 4 : b.cap.basis === 'closed' ? 3 : b.cap.basis === 'planned' ? 2 : b.cap.kind === 'own' ? 0 : 1);
  const groups: Group[] = [];
  for (const type of INFRA_ORDER) {
    const blocks = byType.get(type);
    if (!blocks) continue;
    const list = [...blocks.values()];
    for (const b of list) b.rows.sort((x, y) => y.cap.rank - x.cap.rank || x.f.p.name.localeCompare(y.f.p.name));
    // the page's commodity as a product first, then other forms; on a country page the fullest block first
    list.sort(
      (x, y) =>
        kindOrder(x) - kindOrder(y) ||
        (commodity ? FORM_ORDER.indexOf(x.cap.form) - FORM_ORDER.indexOf(y.cap.form) : 0) ||
        y.rows.length - x.rows.length,
    );
    groups.push({ type, blocks: list, n: list.reduce((n, b) => n + b.rows.length, 0) });
  }
  return groups;
}

/** The first rows: one asset per type in turn, so that every type is represented. */
function preview(groups: Group[], commodity: string | undefined, max: number): Set<InfraFeature> {
  const queues = groups.map((g) => {
    if (commodity) return g.blocks.flatMap((b) => b.rows);
    // country page: the leader of each commodity in turn, assets without a figure last
    const turns = (bs: Block[]) => {
      const out: Row[] = [];
      for (let i = 0; bs.some((b) => i < b.rows.length); i++) for (const b of bs) if (b.rows[i]) out.push(b.rows[i]);
      return out;
    };
    const fig = g.blocks.filter((b) => b.key !== 'none');
    return [
      ...turns(fig.filter((b) => b.cap.basis === 'operating')),
      ...turns(fig.filter((b) => b.cap.basis === 'planned')),
      ...turns(fig.filter((b) => b.cap.basis === 'closed')),
      ...g.blocks.filter((b) => b.key === 'none').flatMap((b) => b.rows),
    ];
  });
  const picked = new Set<InfraFeature>();
  for (let i = 0; picked.size < max && queues.some((q) => i < q.length); i++) {
    for (const q of queues) if (q[i] && picked.size < max) picked.add(q[i].f);
  }
  return picked;
}

function blockLabel(b: Block, commodity: string | undefined, first: boolean, alone: boolean): string | null {
  const c = b.cap;
  if (b.key === 'none') {
    if (alone && !commodity) return null;
    return commodity ? `No ${lowerName(commodityMeta(commodity)?.name ?? commodity)} figure` : 'No capacity figure';
  }
  const form = FORM_LABEL[c.form];
  // an output block says what the figure is: production, exports or port throughput are not capacities
  const out = c.fig && c.fig.kind !== 'capacity' ? OUTPUT_LABEL[c.fig.kind] : '';
  if (c.basis !== 'operating') {
    const what = c.kind === 'cargo' ? 'all cargo' : commodity ? '' : subjectName(c.subject ?? '');
    const head = c.basis === 'closed' ? 'Closed' : 'Planned or under construction';
    return `${head}${what ? `: ${what}` : ''}${form && c.kind !== 'cargo' ? `, ${form}` : ''}`;
  }
  if (c.kind === 'cargo') return out ? `${out}: all cargo of the port` : 'All cargo of the port';
  if (commodity) return out ? (form ? `${out}, ${form}` : out) : form ? cap1(form) : first ? null : 'Other unit';
  if (alone && !out) return null;
  const name = subjectName(c.subject ?? '');
  const sub = form ? `${name}, ${form}` : name;
  return out ? `${out}: ${sub}` : sub;
}

export function InfraList(props: { items: InfraFeature[]; commodity?: string; showCountry?: boolean; allStatus?: boolean }) {
  const { items, commodity } = props;
  const [showAll, setShowAll] = useState(false);
  const groups = useMemo(() => buildGroups(items, commodity), [items, commodity]);
  const first = useMemo(() => preview(groups, commodity, FIRST_ROWS), [groups, commodity]);
  const visible = (r: Row) => showAll || first.has(r.f);
  const shown = groups.flatMap((g) => g.blocks.flatMap((b) => b.rows.filter(visible)));
  if (!items.length) return <p class="infra-empty">No infrastructure asset recorded for this commodity yet.</p>;
  return (
    <>
      {groups.map((g) => {
        const blocks = g.blocks.map((b, i) => ({ b, i, rows: b.rows.filter(visible) })).filter((x) => x.rows.length);
        if (!blocks.length) return null;
        return (
          <div class="co-group" key={g.type}>
            <h4 class="route-sub infra-group">
              {GROUP_LABEL[g.type]} <span class="muted num">{g.n}</span>
            </h4>
            {blocks.map(({ b, i, rows }) => {
              const label = blockLabel(b, commodity, i === 0, g.blocks.length === 1);
              return [
                label && <div class="infra-block" key={b.key}>{label}</div>,
                ...rows.map(({ f, cap }) => {
                  const p = f.p;
                  const fig = cap.kind === 'own' || cap.kind === 'cargo' ? cap.fig : null;
                  const figure = fig ? figureText(fig, fmt) : '';
                  const badge = p.status && p.status !== 'not-stated' && (props.allStatus || !isOperating(p.status));
                  const line = [props.showCountry ? countryName(p.c) : null, figure || null].filter(Boolean).join(' · ');
                  return (
                    <RowBtn
                      key={p.type + p.id}
                      lead={<InfraIcon type={p.type} color={infraColor(f)} size={22} />}
                      title={p.name}
                      sub={
                        line || badge ? (
                          <>
                            {line}
                            {badge && (
                              <>
                                {' '}
                                <StatusBadge status={p.status} />
                              </>
                            )}
                            {fig && <span class="row-detail">{fig.kind === 'capacity' ? '' : `${OUTPUT_LABEL[fig.kind].toLowerCase()} `}{yearText(fig)} · {shortSource(p.s)}</span>}
                          </>
                        ) : undefined
                      }
                      tip={`${sourceLabel(p.s)}${fig ? ` · ${yearText(fig)}` : ''}${fig?.n ? ` · ${fig.n}` : ''}${fig?.orig ? ` · source: ${fig.orig}` : ''}`}
                      onClick={() => select(infraRef(f))}
                    />
                  );
                }),
              ];
            })}
          </div>
        );
      })}
      {items.length > first.size && (
        <button class="act-btn" onClick={() => setShowAll(!showAll)} aria-expanded={showAll}>
          {showAll ? 'Show fewer' : `Show all ${items.length}`}
        </button>
      )}
      {/* each figure carries its own source and year on its row: the foot names and links the sources */}
      <SourcesLine items={shown.map((r) => ({ s: r.f.p.s }))} n="ranked within each type among figures of the same kind, each in its source's unit" />
    </>
  );
}
