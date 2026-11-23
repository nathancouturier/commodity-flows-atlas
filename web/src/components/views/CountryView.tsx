/** Country profile: ranked exports, imports, production shares, infrastructure, companies, lanes. */
import { useEffect, useMemo, useState } from 'preact/hooks';
import type { CaveatsFile, CountryProfile, Lane, LaneFile, ProfileEntry } from '../../types';
import { loadOptional, countryName, commodityMeta, countries, isCountry, sourceLabel } from '../../lib/data';
import { fmt, fmtEst, pct, FAMILY_COLOR } from '../../lib/format';
import { GROUP_LABEL, LANE_GROUPS, caveatFor, decodePairs, loadCaveats, loadLaneFile, loadPairs, vesselName, type Pair } from '../../lib/freight';
import { flyToCountry } from '../../map/controller';
import { loadInfra, type InfraFeature } from '../../map/modules/infrastructure';
import { commodity, select } from '../../lib/store';
import { Section, Placeholder, Skeleton, SourcesLine, SourceLine, Kpi, RowBtn, CompanyRows, AlertBanners, EstMark, ModeBadge, shortSource } from '../ui';
import { passagesText } from '../LaneTable';
import { publisher, useFreightCatalogue, useLoaded } from './shared';
import { InfraList } from './InfraList';
import '../../styles/lane-table.css';

/** Rows shown before "Show all N": the profile file holds every row that passes the relevance rule. */
const FIRST_ROWS = 8;

/** Row note and table warning (trade hubs, gross weight). Long text folds to three lines and opens on a tap. */
function RowNote({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  const style = { margin: '0 4px 3px 30px', width: 'auto' };
  if (text.length <= 110) return <div class="kpi-note" style={style}>{text}</div>;
  return (
    <button class={`kpi-note kpi-note-btn${open ? ' open' : ''}`} style={style} aria-expanded={open} onClick={() => setOpen(!open)} title={open ? 'Show less' : 'Show the full note'}>
      {text}
    </button>
  );
}

/** "CEPII BACI 2024": short publisher and year, as printed on a row. */
const srcYear = (s: string, y: number | string) => `${shortSource(s)} ${y}`;

/**
 * Ranked rows of a profile section. The source and year of the tonnage and of the USD value are printed
 * on each row, with what the tonnage measures and the warnings of its table: a hover tooltip cannot be
 * read on a touch screen.
 */
function EntryList(props: { rows: ProfileEntry[]; showUsd?: boolean }) {
  const [showAll, setShowAll] = useState(false);
  const shown = showAll ? props.rows : props.rows.slice(0, FIRST_ROWS);
  const usdOf = (e: ProfileEntry) => (props.showUsd && e.usd != null ? { s: e.usdS ?? e.s, y: e.usdY ?? e.y } : null);
  return (
    <div class="bars">
      {shown.map((e, i) => {
        const meta = commodityMeta(e.k);
        const color = meta ? FAMILY_COLOR[meta.family] : '#8892a0';
        const usd = usdOf(e);
        const vol = srcYear(e.s, e.y);
        const val = usd ? srcYear(usd.s, usd.y) : null;
        // one mention when tonnage and value share a source and year, else each figure names its own
        const sub = [
          e.rank ? `world #${e.rank}` : null,
          usd ? (val === vol ? `${fmt(e.usd)} bn USD` : `${fmt(e.usd)} bn USD (${val})`) : null,
          val && val !== vol ? `volume ${vol}` : vol,
        ]
          .filter(Boolean)
          .join(' · ');
        const note = [e.n, e.warn].filter(Boolean).join('. ');
        return (
          <div key={e.k + (e.label ?? '') + i}>
            <button
              class="bar-row"
              style={{ width: '100%' }}
              title={`${sourceLabel(e.s)} · ${e.y}${usd && val !== vol ? ` · value: ${sourceLabel(usd.s)} · ${usd.y}` : ''}${e.n ? ' · ' + e.n : ''}`}
              onClick={() => {
                if (!meta) return;
                commodity.value = e.k;
                select({ kind: 'commodity', id: e.k });
              }}
            >
              <span class="bar-rank">{i + 1}</span>
              <span>
                <span class="bar-label">
                  {e.label ?? meta?.name ?? e.k}
                  {e.est && <EstMark />}
                </span>
                <div class="bar-track">
                  <div class="bar-fill" style={{ width: `${Math.max(2, (e.share ?? 0) * 100)}%`, background: color }} />
                </div>
                <span class="bar-sub">{sub}</span>
                {e.basis && <span class="bar-sub">{e.basis}</span>}
              </span>
              <span class="bar-value">
                {fmtEst(e.v, e.est)} {e.u}
                {e.share != null && <small>{pct(e.share)} of world</small>}
              </span>
            </button>
            {note && <RowNote text={note} />}
          </div>
        );
      })}
      {props.rows.length > FIRST_ROWS && (
        <button class="act-btn" style={{ alignSelf: 'flex-start' }} onClick={() => setShowAll(!showAll)} aria-expanded={showAll}>
          {showAll ? 'Show fewer' : `Show all ${props.rows.length}`}
        </button>
      )}
      <SourcesLine
        items={shown.flatMap((e) => {
          const usd = usdOf(e);
          return usd ? [e, usd] : [e];
        })}
        n="shares are of the world total of the same source and year"
      />
    </div>
  );
}

const byUsd = (a: ProfileEntry, b: ProfileEntry) => (b.usd ?? -1) - (a.usd ?? -1);

/** Seaborne lanes touching a country, across the lane files of its profile commodities (or of the selected commodity). */
function CountryLanes({ id, p }: { id: string; p: CountryProfile }) {
  const sel = commodity.value;
  const groups = useMemo(() => {
    // with a commodity selected the list follows it; the lanes of its own groups are the only ones that make sense there
    if (sel && LANE_GROUPS[sel]) return LANE_GROUPS[sel];
    const ks = new Set([...p.exports, ...p.imports, ...p.production].map((e) => e.k));
    const gs = new Set<string>();
    for (const k of ks) (LANE_GROUPS[k] ?? []).forEach((g) => gs.add(g));
    return [...gs].slice(0, 14);
  }, [p, sel]);
  const lanes = useLoaded<{ lane: Lane; file: LaneFile }[]>(
    () =>
      Promise.all(groups.map((g) => loadLaneFile(g).catch(() => null))).then((files) => {
        const out: { lane: Lane; file: LaneFile }[] = [];
        for (const file of files) {
          if (!file) continue;
          // the main set only (a history lane is drawn only in a year when it was large); hide lanes that would display as 0.0 Mt
          for (const lane of file.lanes) if (lane.set !== 'history' && (lane.o === id || lane.d === id) && lane.flow.v >= (lane.flow.u === 'Mt' ? 0.05 : 1e-9)) out.push({ lane, file });
        }
        return out.sort((a, b) => b.lane.flow.v - a.lane.flow.v).slice(0, 6);
      }),
    [id, groups.join()],
  );
  if (!lanes || !lanes.length) return null;
  return (
    <Section title="Seaborne trade lanes">
      {lanes.map(({ lane, file }) => (
        <RowBtn
          key={lane.id}
          title={<>{countryName(lane.o)} <span class="arrow">→</span> {countryName(lane.d)}</>}
          sub={
            <>
              {lane.mode === 'mixed' && <ModeBadge mode="mixed" />}
              {file.label ?? commodityMeta(lane.k)?.name ?? file.group}
              {lane.flow.est && <EstMark />}
            </>
          }
          meta={<>{lane.flow.est ? fmtEst(lane.flow.v, true) : lane.flow.u === 'Mt' ? lane.flow.v.toFixed(1) : fmt(lane.flow.v)} {lane.flow.u}<small>{lane.flow.y}</small></>}
          tip={`${sourceLabel(lane.flow.s)} · ${lane.flow.y}${lane.mode === 'mixed' ? ' · by sea and overland, split not known' : ''}`}
          onClick={() => select({ kind: 'lane', id: lane.id })}
        />
      ))}
      <SourcesLine items={lanes.map((l) => l.lane.flow)} n={sel && LANE_GROUPS[sel] ? 'largest lanes of the selected commodity' : "largest lanes of this country's main commodities"} />
    </Section>
  );
}

/** Rows shown before "Show all N" in the supplier and customer tables. */
const PARTNER_ROWS = 8;

/**
 * Suppliers (importers' side) or customers (exporters' side) of the selected commodity, from the pairs table
 * of its customs groups: every recorded pair of the latest year, whatever its mode. A row with a lane opens
 * the lane; a partner that is not a country of the index (Gibraltar, "Asia, not specified") is plain text.
 */
function PartnerTable(props: { title: string; side: 'o' | 'd'; id: string; rows: Pair[]; caveats: CaveatsFile | null; twoGroups: boolean; src: { s: string; y: number } }) {
  const [all, setAll] = useState(false);
  const { side, id } = props;
  const mine = props.rows.filter((r) => r[side] === id).sort((a, b) => b.kt - a.kt);
  if (!mine.length) return null;
  // a commodity with two customs groups (concentrate and refined copper) has two products: a share is of its own product's total
  const totals = new Map<string, number>();
  for (const r of mine) totals.set(r.group, (totals.get(r.group) ?? 0) + r.kt);
  const shown = all ? mine : mine.slice(0, PARTNER_ROWS);
  const k = commodity.value;
  return (
    <Section title={props.title} aside={<span class="muted num">{commodityMeta(k ?? '')?.name ?? k} · {props.src.y}</span>}>
      <div class="pt-list">
        {shown.map((r, i) => {
          const partner = side === 'd' ? r.o : r.d;
          // the transit port is the end of the route that is not in the pair's own country
          const transit = r.kind === 'transit' ? [r.load, r.dis].filter((x) => x && x.c !== (x === r.load ? r.o : r.d)).map((x) => x!.name) : [];
          const via = transit.length ? transit.join(' and ') : null;
          const mt = r.kt / 1000;
          const cav = r.caveat ? caveatFor(props.caveats, r.group, r.o, r.d) : null;
          const lane = r.lane ? `${r.group}:${r.o}-${r.d}` : null;
          const open = lane ? () => select({ kind: 'lane', id: lane }) : isCountry(partner) ? () => select({ kind: 'country', id: partner }) : undefined;
          const passages = passagesText(r.via, r.viaAltLists);
          return (
            <div key={`${r.group}:${r.o}-${r.d}`}>
              <RowBtn
                lead={<span class="bar-rank">{i + 1}</span>}
                title={countryName(partner)}
                sub={
                  <>
                    <ModeBadge mode={r.kind === 'transit' ? 'sea' : r.kind} via={via ?? undefined} />
                    {r.kind === 'transit' && <span class="mode-via"> via {via ?? 'a foreign port'}</span>}{' '}
                    {[
                      props.twoGroups ? (GROUP_LABEL[r.group] ?? r.group) : null,
                      r.cls ? vesselName(r.cls) : null,
                      r.nm ? `${r.nm.toLocaleString('en-US')} nm` : r.kind === 'sea' || r.kind === 'transit' ? 'no route modelled' : null,
                      passages || null,
                    ]
                      .filter(Boolean)
                      .join(' · ')}
                    {r.est && <EstMark />}
                  </>
                }
                meta={<>{fmtEst(mt, r.est)} Mt<small>{pct(r.kt / totals.get(r.group)!, true)}</small></>}
                tip={lane ? 'Open this lane' : isCountry(partner) ? `Open ${countryName(partner)}` : undefined}
                onClick={open}
              />
              {cav && <RowNote text={cav.entry.text} />}
            </div>
          );
        })}
      </div>
      {mine.length > PARTNER_ROWS && (
        <button class="act-btn" style={{ alignSelf: 'flex-start' }} onClick={() => setAll(!all)} aria-expanded={all}>
          {all ? 'Show fewer' : `Show all ${mine.length}`}
        </button>
      )}
      <SourceLine s={props.src.s} y={props.src.y} n={`all transport modes; shares are of ${countryName(id)}'s recorded ${side === 'd' ? 'imports' : 'exports'} of ${props.twoGroups ? 'the same product (each product has its own total)' : 'this commodity'}`} />
    </Section>
  );
}

/** "Suppliers" and "Customers" of the selected commodity (A-001), above the country's other sections. */
function PartnerTables({ id }: { id: string }) {
  useFreightCatalogue();
  const k = commodity.value;
  const groups = k ? (LANE_GROUPS[k] ?? []) : [];
  const data = useLoaded<{ rows: Pair[]; caveats: CaveatsFile | null; src: { s: string; y: number } }>(
    () =>
      groups.length
        ? Promise.all([Promise.all(groups.map((g) => loadPairs(g).catch(() => null))), loadCaveats().catch(() => null)]).then(([files, caveats]) => {
            const ok = files.filter((f): f is NonNullable<typeof f> => !!f);
            return ok.length ? { rows: ok.flatMap(decodePairs), caveats, src: { s: ok[0].s, y: ok[0].y } } : null;
          })
        : Promise.resolve(null),
    [k],
  );
  if (!data) return null;
  const common = { id, rows: data.rows, caveats: data.caveats, twoGroups: groups.length > 1, src: data.src };
  return (
    <>
      <PartnerTable title="Suppliers" side="d" {...common} />
      <PartnerTable title="Customers" side="o" {...common} />
    </>
  );
}

function CountryInfra({ ids }: { ids: string[] }) {
  const all = useLoaded<InfraFeature[]>(() => loadInfra(), []);
  const items = useMemo(() => {
    if (!all) return [];
    const map = new Map(all.map((f) => [`${f.p.type}:${f.p.id}`, f]));
    return ids.map((k) => map.get(k)).filter((f): f is InfraFeature => !!f);
  }, [all, ids.join()]);
  if (!items.length) return null;
  return (
    <Section title="Main infrastructure" aside={<span class="muted num">{items.length}</span>}>
      <InfraList key={ids.join()} items={items} allStatus />
    </Section>
  );
}

export default function CountryView({ id }: { id: string }) {
  const p = useLoaded<CountryProfile>(
    () => loadOptional<Record<string, CountryProfile>>('countries/profiles.json').then((all) => all?.[id] ?? null),
    [id],
  );
  useEffect(() => {
    flyToCountry(id);
  }, [id]);
  const meta = countries.value[id];

  // KPIs
  let kpis: preact.ComponentChildren = null;
  if (p) {
    const all = [...p.exports, ...p.imports, ...p.production];
    const ents = all.filter((e) => (e.rank ?? 99) <= 10 && commodityMeta(e.k));
    // counted by the pipeline on every table row; the rows themselves are listed below
    const top10 = p.top10 ?? new Set(ents.map((e) => e.k)).size;
    const pubs = [...new Set(ents.map((e) => shortSource(e.s)))];
    const srcs = `${pubs.length > 1 ? 'Sources' : 'Source'}: ${pubs.join(', ')}`;
    const yrs = [...new Set(ents.map((e) => String(e.y)))].sort();
    const yr = yrs.length > 1 ? `${yrs[0]}–${yrs[yrs.length - 1]}` : (yrs[0] ?? '');
    const topExp = [...p.exports].filter((e) => e.usd != null).sort(byUsd)[0];
    kpis = (
      <div class="kpis">
        {top10 > 0 && (
          <Kpi
            label="World top-10 in"
            value={`${top10} commodit${top10 === 1 ? 'y' : 'ies'}`}
            sub={`${srcs} · ${yr}`}
            title="Atlas catalogue commodities where this country ranks in the top 10 of production, exports or imports"
          />
        )}
        {topExp && (
          <Kpi
            label={`Largest export`}
            value={`${fmt(topExp.usd)} bn USD`}
            sub={`${topExp.label ?? commodityMeta(topExp.k)?.name ?? topExp.k} · ${shortSource(topExp.usdS ?? topExp.s)} · ${topExp.usdY ?? topExp.y}`}
            title={`${sourceLabel(topExp.usdS ?? topExp.s)} · ${topExp.usdY ?? topExp.y}`}
            note={topExp.warn}
          />
        )}
      </div>
    );
  }

  // order set by the pipeline: by trade value, thermal and metallurgical coal under the all-coal row that carries their value
  const exports = p?.exports ?? [];
  const imports = p?.imports ?? [];
  return (
    <>
      <div class="detail-head">
        {/* the region is named as such: "Australia and New Zealand" above "Australia" read as a wrong title */}
        <div class="detail-kicker">Country profile{meta ? ` · Region: ${meta.region}` : ''}</div>
        <h2 class="detail-title">{countryName(id)}</h2>
        {kpis}
      </div>
      <div class="panel-scroll">
        <AlertBanners country={id} />
        <PartnerTables key={id} id={id} />
        {p === undefined ? (
          <Skeleton lines={6} />
        ) : p === null ? (
          <Placeholder>No commodity in the atlas catalogue is significant for this country yet.</Placeholder>
        ) : (
          <>
            {exports.length > 0 && (
              <Section title="Key exports" aside={<span class="muted num">{exports.length}</span>}>
                <EntryList key={id} rows={exports} showUsd />
              </Section>
            )}
            {imports.length > 0 && (
              <Section title="Key imports" aside={<span class="muted num">{imports.length}</span>}>
                <EntryList key={id} rows={imports} showUsd />
              </Section>
            )}
            {p.production.length > 0 && (
              <Section title="Production, share of world" aside={<span class="muted num">{p.production.length}</span>}>
                <EntryList key={id} rows={p.production} />
              </Section>
            )}
            {p.other && p.other.length > 0 && (
              <Section title="Other notable raw materials">
                {p.other.map((e, i) => (
                  <RowBtn
                    key={e.k + i}
                    title={e.label ?? e.k}
                    sub={e.n ? `${e.n} · ${publisher(e.s)} ${e.y}` : `${publisher(e.s)} ${e.y}`}
                    meta={<>{fmt(e.v)} {e.u}</>}
                    tip={`${sourceLabel(e.s)} · ${e.y}`}
                  />
                ))}
                <SourcesLine items={p.other} />
              </Section>
            )}
            {p.infra && p.infra.length > 0 && <CountryInfra ids={p.infra} />}
            {p.companies && p.companies.length > 0 && (
              <Section title="Main companies">
                <CompanyRows list={p.companies} showK />
              </Section>
            )}
            <CountryLanes id={id} p={p} />
          </>
        )}
      </div>
    </>
  );
}
