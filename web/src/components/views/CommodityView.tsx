/// <reference types="vite/client" />
/** Global picture of one commodity: KPIs, ranked countries, main flows, lanes, companies, infrastructure. */
import { Fragment } from 'preact';
import { useEffect, useMemo, useState } from 'preact/hooks';
import type { CaveatsFile, Company, CommodityData, CommodityHistory, Fig, Flow, HistTable, LaneFile, Ranked } from '../../types';
import { loadOptional, loadHistory, commodityMeta, countryName, isCountry, sourceLabel } from '../../lib/data';
import { SMALL_BASE, largestChanges, rowName, tableAt, yearLabel, type Change } from '../../lib/tableYears';
import { FAMILY_COLOR, FAMILY_LABEL, atlasKind, fig as fmtFig, fmt, fmtEst, fmtFlow, pct } from '../../lib/format';
import { GROUP_LABEL, LANE_GROUPS, loadCaveats, loadLaneFile, loadPairs } from '../../lib/freight';
import { layers, select, toggleLayer, year } from '../../lib/store';
import { infraMatches, loadInfra, type InfraFeature } from '../../map/modules/infrastructure';
import { Section, Placeholder, Skeleton, Kpi, RankedBars, SourceLine, SourcesLine, RowBtn, ModeBadge, EstMark, FoldNote, AlertBanners, shortSource } from '../ui';
import { CompanyRows, linkedCompany } from '../Companies';
import LaneTable, { estimateBasis, estimatedShare, estimatedVolume, yearNote } from '../LaneTable';
import { EventList } from '../EventList';
import { openCommodity, useLoaded } from './shared';
import { InfraList } from './InfraList';
import { MetalFigures } from './MetalFigures';
import '../../styles/history-year.css';
import { PRICE_COVERAGE_NOTE, loadPriceFigures, lowerName, openPrices, priceFigures } from '../../lib/prices';
import { PriceFigure } from '../PriceFigure';
import { EnergyMonthly } from '../EnergyMonthly';
import AgriBlocks from '../AgriBlocks';
import { reportMonth } from '../CropBalance';
import { CsvAction } from '../CsvAction';
import { downloadFlows, flowSources } from '../../lib/blockCsv';
import { mixedShown } from '../../lib/mixedShown';
import { allCoalTag, flowDefinitions, hasSeveralSources, showsSourceTag } from '../../lib/flowSources';
import { KINDS, allTables, coverText, listText, pageTables, sectionTitle, shortName, type Table } from '../../lib/commodityTables';

/**
 * Opens the bottom price drawer on this commodity's series. `none` is true once the price catalogue is
 * loaded and holds no series for the commodity: the button then says so instead of opening a chart.
 */
function usePriceDrawer(id: string): { open: () => void; none: boolean } {
  useEffect(() => {
    loadPriceFigures().catch(() => undefined);
  }, []);
  // prices/figures.json has an entry for every commodity that has a price series: the page does not load the whole index
  const figures = priceFigures.value;
  return { open: () => openPrices({ commodity: id }), none: figures !== null && !figures[id] };
}

type CompanyMap = Record<string, { producers?: Company[]; processors?: Company[]; traders?: Company[] }>;


/**
 * Ranked table with a marketing-year caption under USDA PSD tables. The figures are PSD local marketing
 * years, which start in a different month in each country: no single month range describes them.
 */
function RankedBlock({ data, color, hist, at, above }: { id: string; data: Ranked; color?: string; hist?: HistTable; at?: number | null; above?: string[] }) {
  // the table's warning is written into its note too: it is shown once, as its own line under the table
  const cv = data.caveat;
  // a warning the key figure above already prints in full is not printed again (one rule for the page: see seenAbove)
  const cvText = cv && seenAbove(cv, above) ? 'See the note of the key figure above.' : cv;
  const n = cv && data.n ? data.n.replace(` · ${cv}`, '').replace(cv, '').replace(/ · $/, '') : data.n;
  const shown = useMemo(() => (cv ? { ...data, n: n || undefined } : data), [data, cv, n]);
  return (
    <>
      <RankedBars data={shown} color={color} hist={hist} at={at} />
      {cv && <FoldNote class="table-caveat" text={cvText} />}
      {/* notes on the series by year (a first year set by a rule, a change of membership or coverage, a country that split) */}
      {!!hist?.n?.length && <FoldNote class="src-line" style={{ marginTop: '2px' }} text={`Series by year: ${hist.n.join(' ')}`} />}
      {data.s === 'usda-psd' && (
        <div class="muted small my-cap">
          Marketing year {data.y}
          {data.yk ? `, USDA's ${data.yk}${data.rel ? ` (report of ${reportMonth(data.rel)})` : ''}` : ''}: USDA PSD local marketing years, which start in different months by country.
        </div>
      )}
    </>
  );
}

/**
 * A ranked table that follows the History year when its series by year holds that year (heading, source line, shares on
 * that year's world total); otherwise the latest table, with the words "2025: no series for 2010" next to the heading.
 */
function TableSection(props: { id: string; title: string; data: Ranked; hist?: HistTable; color?: string; loading?: boolean; fold?: boolean; above?: string[] }) {
  const yr = year.value;
  const { table, i, note, past } = useMemo(() => tableAt(props.data, props.hist, yr), [props.data, props.hist, yr]);
  // with a History year, nothing is said of the year until the series by year is loaded: no latest table, no "no series" tag
  if (yr != null && props.loading)
    return (
      <Section title={props.title} fold={props.fold}>
        <Skeleton lines={4} />
      </Section>
    );
  // a title that names the latest year ("EIA 2024") names the year shown; a table dated otherwise (reserves "last revised
  // 2022", whose series runs to 2025) keeps its title, and the year shown goes next to it
  const dated = !!props.hist && String(props.data.y) === yearLabel(props.hist, props.hist.years.length - 1);
  const title = past && dated ? props.title.split(String(props.data.y)).join(String(table.y)) : props.title;
  // a USDA table says what its marketing year is in USDA's words: the forecast of the year in progress, or the estimate of the one before
  const aside = note ? <span class="year-tag">{note}</span> : table.yk ? <span class="year-tag">{table.y} {table.yk}</span> : past && title === props.title ? <span class="year-tag">{table.y}</span> : null;
  return (
    <Section title={title} aside={aside} fold={props.fold}>
      <RankedBlock id={props.id} data={table} color={props.color} hist={props.hist} at={i} above={props.above} />
    </Section>
  );
}

/** "+12.3" / "−4.1": a change with its sign. */
const signed = (v: number, est: boolean) => `${v > 0 ? '+' : '−'}${fmtEst(Math.abs(v), est)}`;

/**
 * The five largest increases and decreases of the exporters and of the importers from one year to the next, from the
 * series by year; the History year when the series holds it, else its latest year.
 */
function LargestChanges({ hist, data, color }: { hist: CommodityHistory; data: CommodityData; color?: string }) {
  const yr = year.value;
  const series = (['exports', 'imports'] as const).flatMap((k) => (hist.t[k] && hist.t[k].years.length >= 2 ? [{ k, h: hist.t[k] }] : []));
  if (!series.length) return null;
  // the History year is the first year of the series: there is no year before it to compare with
  const first = yr != null && series.every(({ h }) => h.years.indexOf(yr) === 0) ? yearLabel(series[0].h, 0) : null;
  if (first)
    return (
      <Section fold title="Largest changes" aside={<span class="year-tag">no year before {first}</span>}>
        <div class="muted small">The series by year start in {first}: there is no year before it to compare with.</div>
      </Section>
    );
  const sides = series.flatMap(({ k, h }) => {
    const at = yr != null && h.years.indexOf(yr) >= 1 ? h.years.indexOf(yr) : h.years.length - 1;
    const ch = largestChanges(h, at);
    return ch && (ch.up.length || ch.down.length) ? [{ k, h, at, ch }] : [];
  });
  if (!sides.length) return null;
  const { h, at } = sides[0];
  // a USDA marketing year says what it is: the change from an estimate to a forecast is not a change between two settled years
  const withKind = (i: number) => `${yearLabel(h, i)}${h.kinds?.[i] ? ` ${h.kinds[i]}` : ''}`;
  const from = yearLabel(h, at - 1);
  const to = yearLabel(h, at);
  const anyEst = sides.some((s) => [...s.ch.up, ...s.ch.down].some((c) => c.est));
  const note = yr != null && !h.years.includes(yr) ? <span class="year-tag">no series for {yr}</span> : null;
  // no percentage where one year has no figure or a very small one: the words say why
  const pctText = (c: Change) =>
    c.p != null
      ? `${c.p > 0 ? '+' : '−'}${pct(Math.abs(c.p))}`
      : c.why === 'none-before'
        ? `none in ${from}`
        : c.why === 'none-after'
          ? `none in ${to}`
          : `<0.1% in ${from}`;
  const pctTitle = (c: Change) =>
    c.why === 'small'
      ? `Under ${pct(SMALL_BASE)} of the world total in ${from}: no percentage change`
      : c.why
        ? `No figure in ${c.why === 'none-before' ? from : to}: the source gives none${h.s === 'baci' ? ', or the flows are under its reporting threshold (1,000 t and 1 million USD)' : ''}, or it rounds to 0; counted as 0`
        : '';
  return (
    <Section fold title={`Largest changes, ${withKind(at - 1)} to ${withKind(at)}`} aside={note}>
      {sides.map(({ k, h: s, ch }) => (
        <div class="chg-block" key={k} style={{ '--bar-color': color }}>
          <div class="chg-head">{k === 'exports' ? 'Exporters' : 'Importers'}{data[k]?.basis ? ` — ${data[k]!.basis}` : ''}</div>
          {[...ch.up, ...ch.down].map((c) => {
            // an aggregate that is not a country of the index (USDA's European Union) has no page: plain text
            const Row = isCountry(c.c) ? 'button' : 'div';
            const name = rowName(s, c.c, at);
            return (
              <Row
                class={`chg-row ${c.d > 0 ? 'chg-up' : 'chg-down'}`}
                key={c.c}
                onClick={Row === 'button' ? () => select({ kind: 'country', id: c.c }) : undefined}
                title={`${name}: ${fmt(s.c[c.c][at - 1])} ${s.u} in ${yearLabel(s, at - 1)}, ${fmt(s.c[c.c][at])} ${s.u} in ${yearLabel(s, at)}${c.est ? '; an Atlas estimate on one side' : ''}`}
              >
                <span class="chg-name">
                  {name}
                  {c.est && <EstMark />}
                </span>
                <span class="chg-d">
                  {signed(c.d, c.est)} {s.u}
                </span>
                <span class="chg-p" title={pctTitle(c) || undefined}>
                  {pctText(c)}
                </span>
              </Row>
            );
          })}
        </div>
      ))}
      <SourceLine
        s={h.s}
        y={`${from} and ${to}`}
        n={
          `change in ${h.u}, this year minus the year before, from the series by year; a country with no figure in one year counts as 0 there, with no percentage ` +
          `(the source gives none${h.s === 'baci' ? ', or its flows are under the reporting threshold of 1,000 t and 1 million USD' : ''}, or it rounds to 0); ` +
          `a figure out of line with the years around it, or a row that changes entity, gives no change${anyEst ? '; a change with an Atlas estimate on either side is marked' : ''}`
        }
      />
    </Section>
  );
}

/** "World exports (concentrate, gross wt)" when the figure counts ore or concentrate rather than metal. */
function exportsLabel(f: Fig, tbl?: Ranked): string {
  const n = `${f.n ?? ''} ${tbl?.n ?? ''}`;
  const parts: string[] = [];
  if (/concentrate/i.test(n)) parts.push('concentrate');
  else if (/\bores?\b/i.test(n)) parts.push('ore');
  if (/gross weight/i.test(n)) parts.push('gross wt');
  return parts.length ? `World exports (${parts.join(', ')})` : 'World exports';
}

/** Names of the ports that landlocked countries' sea cargo goes through, from the lane and pairs files of the commodity's groups. */
function useTransitPorts(id: string, flows: Flow[] | undefined): Record<string, string> | null | undefined {
  const need = !!flows?.some((f) => f.transit);
  return useLoaded<Record<string, string>>(async () => {
    const groups = LANE_GROUPS[id] ?? [];
    if (!need || !groups.length) return {};
    const out: Record<string, string> = {};
    await Promise.all(
      groups.map(async (g) => {
        const [lf, pf] = await Promise.all([loadLaneFile(g).catch(() => null), loadPairs(g).catch(() => null)]);
        for (const p of pf?.ports ?? []) out[p[0]] = p[1];
        for (const p of Object.values(lf?.ports ?? {})) out[p.id] = p.name;
      }),
    );
    return out;
  }, [id, need]);
}

/** The flows a Main flows block shows: the first ten, or all of them once "Show all" is pressed. */
const shownFlows = (flows: Flow[], all: boolean) => {
  const sorted = [...flows].sort((a, b) => b.v - a.v);
  return all ? sorted : sorted.slice(0, 10);
};

/**
 * One rule for the whole page: a text already printed above is not printed again. `above`: the texts printed higher on the
 * page; a text is seen when one of them holds it whole.
 */
function seenAbove(text: string, above: string[] | undefined): boolean {
  return !!above?.some((t) => t.includes(text));
}

function FlowRows(props: { id: string; flows: Flow[]; tag?: string; all: boolean; setAll: (v: boolean) => void; gaps: string[]; defs?: string[] }) {
  const { all, setAll } = props;
  const sorted = [...props.flows].sort((a, b) => b.v - a.v);
  const rows = shownFlows(props.flows, all);
  const ports = useTransitPorts(props.id, sorted);
  // the text of the reporting gaps that apply to the listed flows (freight/caveats.json)
  const needCaveats = rows.some((f) => f.caveat);
  const caveats = useLoaded<CaveatsFile>(() => (needCaveats ? loadCaveats() : Promise.resolve(null)), [props.id, needCaveats]);
  // the footer names the customs source; flows re-based by the atlas say so on their own row
  const first = rows.find((f) => f.s !== 'atlas') ?? rows[0];
  // a list whose rows come from more than one source (the Metallurgical coal page: two exporters' own statistics) names the source of each row
  // and every source in the footer; a list with one source is drawn as before
  const several = hasSeveralSources(props.flows);
  const anyEst = rows.some((f) => f.est);
  // the two bases of an Atlas estimate are told apart: a volume in the United States' own export statistics, the declared value
  const estBases = [rows.some((f) => f.est && f.estBy === 'volume') && "a volume in the United States' own export statistics", rows.some((f) => f.est && f.estBy !== 'volume') && 'the declared value'].filter(Boolean).join(' or ');
  // a reporting gap printed in full above (Gap in the customs record) or under an earlier row gets a pointer, not the text again
  const caveatText = (i: number): string | undefined => {
    const t = caveats?.[rows[i].caveat!]?.text;
    if (!t) return t;
    if (seenAbove(t, props.gaps)) return "See 'Gap in the customs record' above.";
    const j = rows.findIndex((f) => f.caveat && caveats?.[f.caveat]?.text === t);
    return j < i ? `See the note under row ${j + 1} above.` : t;
  };
  return (
    <>
      {rows.map((f, i) => {
        // the port's name when a lane or pairs file of the commodity has it, else the country it is in
        const via = f.transit ? (ports === undefined ? '…' : (ports?.[f.transit.port] ?? `a port in ${countryName(f.transit.c)}`)) : null;
        // a code that is not a country of the index (Gibraltar, "Asia, not specified") is plain text
        const open = f.lane ? () => select({ kind: 'lane', id: f.lane! }) : isCountry(f.o) ? () => select({ kind: 'country', id: f.o }) : undefined;
        // a row with no lane page opens the page of its origin: it says so, in its title and to a screen reader
        const opens = !f.lane && open ? `Opens the page of ${countryName(f.o)}` : null;
        return (
          <div key={`${f.o}-${f.d}-${i}`}>
            <RowBtn
              lead={<span class="bar-rank">{i + 1}</span>}
              title={<>{countryName(f.o)} <span class="arrow">→</span> {countryName(f.d)}</>}
              sub={
                <>
                  {/* a flow with no mode is not modelled (precious metals): say so rather than leave the badge out */}
                  {f.mode ? <ModeBadge mode={f.mode} via={via ?? undefined} /> : <span class="muted-cap">mode not modelled</span>}
                  {f.transit && <span class="mode-via"> via {via}</span>}
                  {props.tag && <span class="muted-cap"> {props.tag}</span>}
                  {f.est ? <EstMark /> : showsSourceTag(f, props.flows, rows) && <span class="muted-cap"> {shortSource(f.s)}</span>}
                  {opens && <span class="sr-only"> · {opens}</span>}
                </>
              }
              meta={<>{fmtFlow(f.v, f.u, f.est && !f.cap)} {f.u}</>}
              tip={`${opens ? `${opens} · ` : ''}${sourceLabel(f.s)} · ${f.y}${f.n ? ' · ' + f.n : ''}${f.mode === 'mixed' ? ' · by sea and overland, split not known' : f.mode && f.mode !== 'sea' ? ' · ' + f.mode : ''}${f.transit ? ' · sea via ' + via : ''}`}
              onClick={open}
            />
            {/* the method of an Atlas estimate is written out under the row, not only in its tooltip */}
            {f.est && <FoldNote text={f.n} style={{ margin: '0 4px 3px 30px', width: 'auto' }} />}
            {f.caveat && <FoldNote text={caveatText(i)} style={{ margin: '0 4px 3px 30px', width: 'auto' }} />}
          </div>
        );
      })}
      <div class="lt-foot" style={{ marginTop: '6px' }}>
        {sorted.length > 10 && (
          <button class="act-btn" onClick={() => setAll(!all)} aria-expanded={all}>
            {all ? 'Show fewer' : `Show all (${sorted.length})`}
          </button>
        )}
        <CsvAction
          sources={flowSources(props.flows)}
          onClick={() => downloadFlows(commodityMeta(props.id)?.name ?? props.id, 'Main flows', props.flows)}
          title="Every flow of this table with its year, source and licence, as a CSV file"
        />
      </div>
      {!!flowDefinitions(props.flows, props.defs) && <div class="src-line">{flowDefinitions(props.flows, props.defs)}</div>}
      {several && <SourcesLine items={props.flows} n="bilateral flows, each exporter's own statistics; the sources are not added to one another" />}
      {!several && first && <SourceLine s={first.s} y={first.y} n={`bilateral flows, all transport modes${anyEst ? `; an Atlas estimate is a tonnage computed from ${estBases}, shown to two significant digits` : ''}`} />}
    </>
  );
}

/** History timeline on another year: the year a block really shows, next to its title. */
function YearTag({ y }: { y?: number | string }) {
  const yr = year.value;
  if (yr == null || y == null || String(y) === String(yr)) return null;
  return <span class="year-tag">latest: {y}</span>;
}

/**
 * Value, source line and note of a KPI. The second unit of an Atlas conversion goes in brackets, its factor after the source's own note.
 * An estimated figure (`est`) is printed to two significant digits and says "Atlas estimate"; a figure the atlas only converted
 * (source `atlas`, no `est`) is printed as the file gives it and says "Atlas conversion".
 */
function altKpi(f: Fig): { value?: string; sub?: string; note?: string } {
  const kind = atlasKind(f);
  const g = kind === 'est' ? { ...f, est: true } : f;
  const sub = kind ? `${kind === 'est' ? 'Atlas estimate' : 'Atlas conversion'} · ${f.y}` : undefined;
  // the History year can replace the seaborne figure by another year's: the conversion belongs to the latest year only
  if (!f.alt || String(f.alt.y) !== String(f.y)) return { value: kind === 'est' ? fmtFig(g) : undefined, sub, note: f.n };
  // no break inside a figure: a narrow card wraps before the bracket, not inside "3,140 Mt LNG"
  const nb = (t: string) => t.replace(/ /g, '\u00a0');
  return { value: `${nb(fmtFig(g))} (${nb(`${fmt(f.alt.v)} ${f.alt.u}`)})`, sub, note: f.n ? `${f.n} · ${f.alt.n}` : f.alt.n };
}

/** KPI label with the figure's own year when the History timeline is on another year. */
function kpiLabel(label: string, f: Fig): string {
  const yr = year.value;
  return yr != null && String(f.y) !== String(yr) ? `${label} · ${f.y}` : label;
}

/**
 * Seaborne trade of the History year. The summary figure is the latest value of the yearly series of the
 * commodity's first lane group; the year replaces it only when that link holds (same source, unit and value).
 */
function seaborneAt(f: Fig | undefined, file: LaneFile | null | undefined, yr: number | null): Fig | undefined {
  if (!f || !file || yr == null || String(f.y) === String(yr)) return f;
  const i = file.years.indexOf(yr);
  const latest = file.seaborne[file.years.indexOf(Number(f.y))];
  if (i < 0 || file.seaborne[i] == null || latest == null) return f;
  if (file.s !== f.s || file.unit !== f.u || Math.abs(latest - f.v) > 0.005 * Math.abs(f.v)) return f;
  // the clauses of the note that are figures of the latest year (the tonnage that also moves overland, the share estimated from
  // value) are said again for the year shown, from the same lane file
  const mixed = file.mixed?.[i] ?? 0;
  const est = estimatedShare(file, yr);
  const bare = (f.n ?? '')
    .replace(/; [\d.,]+ \S+ that move both by sea and overland \(split not known\) are not in it/, '')
    .replace(/; [\d.]+% of this tonnage (?:estimated from value|is an Atlas estimate: [^;]*)/, '')
    .replace(/; \d{4} includes [^;]*\(split by mode known for \d{4} only[^)]*\)/, '');
  // each clause is added for the year shown, whether or not the note of the latest year had one
  const add = (base: string, clause: string) => (!clause ? base : base ? base.replace(/(\.?)$/, `; ${clause}$1`) : clause);
  const withMixed = add(bare, mixedShown(mixed, file.unit) ? `${fmt(mixed)} ${file.unit} that move both by sea and overland (split not known) are not in it` : '');
  const estVol = est ? estimatedVolume(file, est.year) : 0;
  const withEst = add(withMixed, est ? (estVol > 0 ? `${pct(est.share)} of this tonnage is ${estimateBasis(est.share, estVol)}` : `${pct(est.share)} of this tonnage estimated from value`) : '');
  return { ...f, v: file.seaborne[i], y: yr, n: withEst || undefined };
}

function LaneSummary({ id, color }: { id: string; color?: string }) {
  const groups = LANE_GROUPS[id];
  const files = useLoaded<LaneFile[]>(
    () => (groups?.length ? Promise.all(groups.map((g) => loadLaneFile(g).catch(() => null))).then((r) => r.filter((x): x is LaneFile => !!x)) : Promise.resolve([])),
    [id],
  );
  if (!files || !files.length) return null;
  const on = layers.value.flows;
  const hy = year.value;
  // the main set is what the map draws with no year chosen; sea-and-overland lanes belong to it (drawn dashed)
  const main = (f: LaneFile) => f.lanes.filter((l) => l.set !== 'history');
  const mixedN = files.reduce((n, f) => n + main(f).filter((l) => l.mode === 'mixed').length, 0);
  // in a past year: the lanes that have a figure that year, as on the map
  const pastAt = (f: LaneFile) => (hy != null && hy !== f.y ? f.years.indexOf(hy) : -1);
  const total = files.reduce((n, f) => {
    const at = pastAt(f);
    return n + (at >= 0 ? f.lanes.filter((l) => (l.hist[at] ?? 0) > 0).length : main(f).length);
  }, 0);
  const past = files.some((f) => pastAt(f) >= 0);
  const shownY = hy != null && files[0].years.includes(hy) ? hy : files[0].y;
  return (
    <Section title="Seaborne lanes">
      <div class="lane-sum">
        <div class="lane-sum-n num" style={{ color }}>{total}</div>
        <div class="lane-sum-t">
          {past ? `lane${total === 1 ? '' : 's'} with a flow in ${shownY}` : `mapped lane${total === 1 ? '' : 's'}`}
          {!past && mixedN > 0 && <span class="muted"> · {mixedN} by sea and overland</span>}
        </div>
      </div>
      <div class="ft" style={{ marginTop: '8px' }}>
        {files.map((f) => {
          // the History year when the series has it, else the latest year
          const at = hy != null ? f.years.indexOf(hy) : -1;
          const i = at >= 0 ? at : f.years.length - 1;
          const last = f.seaborne[i];
          const yr = f.years[i];
          const active = pastAt(f) >= 0 ? f.lanes.filter((l) => (l.hist[i] ?? 0) > 0).length : main(f).length;
          const mixed = f.mixed?.[i] ?? 0;
          const note = yearNote(f, hy);
          return (
            <div key={f.group}>
              <div class="ft-row ft-wide" title={`${sourceLabel(f.s)} · ${yr}`}>
                <span class="ft-k">{f.label ?? GROUP_LABEL[f.group] ?? commodityMeta(f.group)?.name ?? commodityMeta(id)?.name ?? f.group}</span>
                <span class="num">
                  {last != null ? `${fmt(last)} ${f.unit} seaborne` : '—'} <span class="muted">· {yr} · {active} lanes{at >= 0 ? ' with a flow' : ''}</span>
                </span>
              </div>
              {(mixedShown(mixed, f.unit) || note) && (
                <div class="lt-note" style={{ margin: '2px 0 0 0' }}>
                  {mixedShown(mixed, f.unit) && <div>Plus {fmt(mixed)} {f.unit} by sea and overland, split not known: not in the seaborne figure.</div>}
                  {note && <div>{note}</div>}
                </div>
              )}
            </div>
          );
        })}
      </div>
      <LaneTable files={files} yr={hy} name={id} />
      <SourceLine s={files[0].s} y={shownY} n="Atlas lane method, seaborne subset of customs flows" />
      <button class="act-btn" disabled={on} onClick={() => toggleLayer('flows', true)}>
        {on ? 'Lanes shown on the map' : 'Show lanes on the map'}
      </button>
    </Section>
  );
}

function KeyInfra({ id }: { id: string }) {
  const all = useLoaded<InfraFeature[]>(() => loadInfra(), []);
  const on = layers.value.infrastructure;
  const mine = useMemo(() => (all ?? []).filter((f) => infraMatches(f.p.k, id)), [all, id]);
  if (!all || !mine.length) return null;
  return (
    <Section fold title="Key infrastructure" aside={<span class="muted num">{mine.length}</span>}>
      <InfraList key={id} items={mine} commodity={id} showCountry />
      {mine.length > 0 && (
        <button class="act-btn" disabled={on} onClick={() => toggleLayer('infrastructure', true)}>
          {on ? `${mine.length} asset${mine.length === 1 ? '' : 's'} shown on the map` : `Show ${mine.length} asset${mine.length === 1 ? '' : 's'} on the map`}
        </button>
      )}
    </Section>
  );
}

/** A table note without the warning the page prints apart (RankedBlock does the same). */
function ownNote(t: Ranked): string {
  const cv = t.caveat;
  return (cv && t.n ? t.n.replace(` · ${cv}`, '').replace(cv, '').replace(/ · $/, '') : (t.n ?? '')).trim();
}

/**
 * Notes that repeat under several tables of the page are printed once, in the Notes section: the notes on a table's series by year
 * (a country that split), and the clauses of the table notes after the first one, which says what the table counts (the method of
 * the customs extract, "world = sum of reporting countries"). Each table keeps the notes that are its own, and every clause about an
 * estimate. The note of an Atlas estimate or conversion is kept whole: it is the method of the figure.
 */
function sharedNotes(tables: Table[], hist: CommodityHistory | null | undefined) {
  const count = (m: Map<string, Table[]>, k: string, t: Table) => m.set(k, [...(m.get(k) ?? []), t]);
  const series = new Map<string, Table[]>();
  const clauses = new Map<string, Table[]>();
  for (const t of tables) {
    for (const n of new Set(hist?.t[t.key]?.n ?? [])) count(series, n, t);
    // a clause about an estimate stays with the figures it qualifies
    if (!atlasKind(t.data)) for (const c of new Set(ownNote(t.data).split('; ').slice(1))) if (!/estimat/i.test(c)) count(clauses, c, t);
  }
  const many = (m: Map<string, Table[]>) => new Set([...m].filter(([, ts]) => ts.length > 1).map(([k]) => k));
  const seriesOut = many(series);
  const clauseOut = many(clauses);
  const data: Record<string, Ranked> = {};
  const hists: Record<string, HistTable> = {};
  for (const t of tables) {
    const h = hist?.t[t.key];
    if (h?.n?.some((n) => seriesOut.has(n))) hists[t.key] = { ...h, n: h.n.filter((n) => !seriesOut.has(n)) };
    if (atlasKind(t.data)) continue;
    const parts = ownNote(t.data).split('; ');
    const kept = [parts[0], ...parts.slice(1).filter((c) => !clauseOut.has(c))];
    if (kept.length < parts.length) data[t.key] = { ...t.data, n: [kept.join('; '), t.data.caveat].filter(Boolean).join(' · ') };
  }
  // a note that stands under many tables is said once for the tables it covers, not as a list of their titles (the pulses page has ten): see coverText
  const notes = [
    ...[...clauseOut].map((c) => `${coverText(clauses.get(c)!, 'In the tables of', 'Tables of')}: ${c}`),
    ...[...seriesOut].map((n) => `${coverText(series.get(n)!, 'Series by year of', 'Series by year of')}: ${n}`),
  ];
  return { data, hists, notes };
}

export default function CommodityView({ id }: { id: string }) {
  const meta = commodityMeta(id);
  const [d, setD] = useState<CommodityData | null | undefined>(undefined);
  const [co, setCo] = useState<CompanyMap | null>(null);
  const prices = usePriceDrawer(id);
  const seaFile = useLoaded<LaneFile>(() => (LANE_GROUPS[id]?.[0] ? loadLaneFile(LANE_GROUPS[id][0]) : Promise.resolve(null)), [id]);
  const yr = year.value;
  useEffect(() => {
    let live = true;
    setD(undefined);
    loadOptional<CommodityData>(`commodities/${id}.json`).then((x) => live && setD(x));
    return () => {
      live = false;
    };
  }, [id]);
  useEffect(() => {
    loadOptional<CompanyMap>('commodities/companies.json').then(setCo);
  }, []);
  const color = meta ? FAMILY_COLOR[meta.family] : undefined;
  const companies = d?.companies ?? co?.[id];
  const hasCo = !!companies && (companies.producers?.length || companies.processors?.length || companies.traders?.length);
  const seaborne = seaborneAt(d?.summary.seaborne, seaFile, yr);
  const seaFollows = !!seaborne && String(seaborne.y) === String(yr);
  const hist = useLoaded<CommodityHistory>(() => loadHistory(id), [id]);
  const ht = (key: string): HistTable | undefined => hist?.t[key];
  const tables = useMemo(() => (d ? pageTables(d, id) : null), [d, id]);
  const shared = useMemo(
    () => (tables ? sharedNotes(allTables(tables), hist) : null),
    [tables, hist],
  );
  // the texts printed above the Notes, in page order: key figures, the open table of each kind, the gap in the customs record,
  // the rows of Main flows shown; a later place does not print them again (seenAbove)
  const [flowsAll, setFlowsAll] = useState(false);
  useEffect(() => setFlowsAll(false), [id]);
  const kpiNotes = d?.summary ? [d.summary.production, d.summary.exports, d.summary.reserves, d.summary.consumption, seaborne].flatMap((f) => (f ? [altKpi(f).note ?? ''] : [])).filter(Boolean) : [];
  const gapTexts = d?.gaps?.map((g) => g.text) ?? [];
  const needCaveats = !!d?.flows?.some((f) => f.caveat);
  const caveats = useLoaded<CaveatsFile>(() => (needCaveats ? loadCaveats() : Promise.resolve(null)), [id, needCaveats]);
  const printed = [
    ...kpiNotes,
    ...(tables ? KINDS.flatMap((k) => tables.kinds[k].slice(0, 1).map((t) => t.data.caveat ?? '')) : []),
    ...gapTexts,
    ...shownFlows(d?.flows ?? [], flowsAll).flatMap((f) => (f.caveat && caveats?.[f.caveat] ? [caveats[f.caveat].text] : [])),
  ].filter(Boolean);
  const notes = (d?.notes ?? []).filter((n) => !seenAbove(n, printed));
  const discrepancies = (d?.discrepancies ?? []).filter((n) => !seenAbove(n, printed));
  const tableEl = (t: Table, fold?: boolean) => (
    <TableSection id={id} key={t.key} title={t.title} data={shared?.data[t.key] ?? t.data} hist={shared?.hists[t.key] ?? ht(t.key)} loading={hist === undefined} color={color} fold={fold} above={kpiNotes} />
  );
  // the first table of a kind is open; the others are folded under one line that names them
  const kindEl = (ts: Table[]) =>
    ts.length > 0 && (
      <>
        {tableEl(ts[0])}
        {ts.length > 1 && (
          <Section fold latest={!ts.slice(1).some((t) => yr != null && ht(t.key)?.years.includes(yr))} title={ts.slice(1).map((t) => shortName(t.title)).join(' · ')}>
            {ts.slice(1).map((t) => tableEl(t))}
          </Section>
        )}
      </>
    );
  const coCount = (companies?.producers?.length ?? 0) + (companies?.processors?.length ?? 0) + (companies?.traders?.length ?? 0);
  const noteCount = notes.length + (shared?.notes.length ?? 0) + discrepancies.length;
  // what follows the History year on this page
  const following = [
    yr != null && hist && Object.values(hist.t).some((h) => h.years.includes(yr)) ? 'the tables that have a series by year' : null,
    seaFollows ? 'the seaborne trade figure' : null,
    LANE_GROUPS[id]?.length ? 'the seaborne lanes' : null,
  ].filter((x): x is string => !!x);
  return (
    <>
      <div class="detail-head" style={{ '--kicker': color }}>
        <div class="detail-kicker">{meta ? FAMILY_LABEL[meta.family] : 'Commodity'}</div>
        <h2 class="detail-title">{meta?.name ?? id}</h2>
        {meta?.blurb && <p class="muted" style={{ margin: '4px 0 0', fontSize: '13px' }}>{meta.blurb}</p>}
      </div>
      <div class="panel-scroll">
        {yr != null && d && hist !== undefined && (
          <div class="year-note">
            History year <b class="num">{yr}</b>:{' '}
            {following.length
              ? `${following.length > 1 ? `${following.slice(0, -1).join(', ')} and ${following[following.length - 1]}` : `only ${following[0]}`} follow it. Every other figure and table`
              : 'no yearly series for this commodity. Every figure and table'}{' '}
            is the latest published and shows its own year.
            {d.balance && d.balance.years.length >= 2 && (
              <> The USDA tables follow the History year; the {d.balance.years.map((b) => `${b.y}${b.yk ? ` ${b.yk}` : ''}`).join(' and ')} are shown when History is closed.</>
            )}
          </div>
        )}
        {d?.summary && (
          <div class="kpis">
            {d.summary.production && <Kpi label={kpiLabel(d.kpis?.production ?? 'World production', d.summary.production)} f={d.summary.production} {...altKpi(d.summary.production)} />}
            {d.summary.exports && <Kpi label={kpiLabel(d.kpis?.exports ?? exportsLabel(d.summary.exports, d.exports), d.summary.exports)} f={d.summary.exports} {...altKpi(d.summary.exports)} />}
            {d.summary.reserves && <Kpi label={kpiLabel(d.kpis?.reserves ?? 'World reserves', d.summary.reserves)} f={d.summary.reserves} {...altKpi(d.summary.reserves)} />}
            {d.summary.consumption && <Kpi label={kpiLabel(d.kpis?.consumption ?? 'World consumption', d.summary.consumption)} f={d.summary.consumption} {...altKpi(d.summary.consumption)} />}
            {seaborne && <Kpi label={`${d.kpis?.seaborne ?? 'Seaborne trade'}${yr != null ? ` · ${seaborne.y}` : ''}`} f={seaborne} {...altKpi(seaborne)} />}
          </div>
        )}
        {d?.see?.map((s) => (
          <div class="muted small my-cap" key={s.k}>
            See{' '}
            <button class="link-btn link-inline" onClick={() => openCommodity(s.k)} disabled={!commodityMeta(s.k)}>
              {commodityMeta(s.k)?.name ?? s.k}
            </button>{' '}
            for {s.text}.
          </div>
        ))}
        <PriceFigure commodity={id} />
        <AlertBanners commodity={id} />
        {prices.none ? (
          <button class="act-btn act-prices" disabled title="The atlas only charts prices from free sources; none is available for this commodity yet.">
            No free price series for {lowerName(meta?.name ?? id)} yet
          </button>
        ) : (
          <button class="act-btn act-prices" onClick={prices.open}>
            Price history
          </button>
        )}
        {!prices.none && PRICE_COVERAGE_NOTE[id] && <div class="muted small my-cap">{PRICE_COVERAGE_NOTE[id]}</div>}
        {d === undefined ? (
          <Skeleton lines={8} />
        ) : d === null ? (
          <Placeholder>Data for this commodity is being compiled and will appear in a later release.</Placeholder>
        ) : (
          <Fragment key={id}>
            {kindEl(tables!.kinds.production)}
            {kindEl(tables!.kinds.consumption)}
            {kindEl(tables!.kinds.exports)}
            {kindEl(tables!.kinds.imports)}
            {kindEl(tables!.kinds.reserves)}
            {tables!.other.map((t) => tableEl(t, true))}
            <AgriBlocks d={d} color={color} part="gaps" />
            {d.flows && d.flows.length > 0 && (
              <Section title={sectionTitle(d, 'flows', 'Main flows')} aside={<YearTag y={d.flows[0].y} />}>
                <FlowRows id={id} flows={d.flows} tag={allCoalTag(id)} all={flowsAll} setAll={setFlowsAll} gaps={gapTexts} defs={d.flowDefs} />
              </Section>
            )}
            <LaneSummary id={id} color={color} />
            {/* the secondary blocks, folded to their title: the commodity's family first */}
            <EnergyMonthly id={id} />
            <AgriBlocks d={d} color={color} part="balance" />
            {tables!.stocks.map((t) => tableEl(t, true))}
            {tables!.eu.length > 0 && (
              <Section fold latest={!tables!.eu.some((t) => yr != null && ht(t.key)?.years.includes(yr))} title={`EU member states: ${listText(tables!.eu.map((t) => t.key.replace(/^eu-/, '')))}`}>
                {tables!.eu.map((t) => tableEl(t))}
              </Section>
            )}
            <MetalFigures id={id} d={d} hist={hist} color={color} />
            {hist && <LargestChanges hist={hist} data={d} color={color} />}
            <KeyInfra id={id} />
            {hasCo && (
              <Section key={linkedCompany(companies!.producers, companies!.processors, companies!.traders) ?? ''} fold latest
                open={!!linkedCompany(companies!.producers, companies!.processors, companies!.traders)} title="Main companies" aside={<span class="muted num">{coCount}</span>}>
                <CompanyRows title="Producers" list={companies!.producers ?? []} />
                <CompanyRows title="Processors" list={companies!.processors ?? []} />
                <CompanyRows title="Traders" list={companies!.traders ?? []} />
              </Section>
            )}
            <EventList commodity={id} fold />
            {noteCount > 0 && (
              <Section fold title="Notes" aside={<span class="muted num">{noteCount}</span>}>
                <ul class="bullets small-print">
                  {notes.map((n, i) => <li key={'n' + i}>{n}</li>)}
                  {shared?.notes.map((n, i) => <li key={'s' + i}>{n}</li>)}
                  {discrepancies.map((n, i) => <li key={'d' + i} class="disc">Discrepancy: {n}</li>)}
                </ul>
              </Section>
            )}
          </Fragment>
        )}
      </div>
    </>
  );
}
