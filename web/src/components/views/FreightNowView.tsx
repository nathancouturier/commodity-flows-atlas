/** Freight market now: tankers and dry bulk carriers at the five passages with the most cargo of the type, the last four weeks against the same four weeks a year earlier (IMF PortWatch). */
import '../../styles/freight-now.css';
import type { Chokepoint, MarketNow, MarketNowRow } from '../../types';
import { load, sourceLabel, sources } from '../../lib/data';
import { FAMILY_COLOR, FAMILY_LABEL } from '../../lib/format';
import { loadChokepoints } from '../../lib/freight';
import { INDICATORS, LINK_ONLY, NOT_A_RATE, indicatorNote, percentOnYear, valueInMonth, yearEarlier, type LinkOnly } from '../../lib/freightIndicators';
import { MARKET_TYPES, readMarketNow, rowText } from '../../lib/marketNow';
import { fmtPct, fmtPrice, isLate, loadSeries, openPrices, type PriceMeta } from '../../lib/prices';
import { fmtDate } from '../../lib/status';
import { select } from '../../lib/store';
import { Section, SourceLine, Skeleton } from '../ui';
import { useLoaded } from './shared';

const LEAD = 'This page shows traffic at the main passages and two indicators, none of them a freight rate: the atlas shows no spot rate for tankers or gas carriers and no Baltic Exchange index value, since the sources it knows for them are proprietary or cannot be republished.';
const NO_FIGURES = 'No traffic figures are available.';
const NO_INDICATORS = 'No indicator figures are available.';
const CLASSES =
  'PortWatch lists five ship classes (container, dry bulk, general cargo, ro-ro and tanker) and defines none, so the atlas cannot say whether gas carriers are in its tanker class: the tanker figures above may include them or not. The atlas shows no separate gas carrier figure.';

/** The digest, and the atlas's name of each passage (data/freight/chokepoints.json: a passage that the catalogue lacks keeps its id and has no page to open). */
async function loadPage(): Promise<{ digest: MarketNow | null; names: Map<string, string> }> {
  const [digest, catalogue] = await Promise.all([
    load<unknown>('freight/market-now.json').then(readMarketNow, () => null),
    loadChokepoints().catch(() => [] as Chokepoint[]),
  ]);
  return { digest, names: new Map((Array.isArray(catalogue) ? catalogue : []).map((c) => [c.id, c.name])) };
}

/** An indicator of the price files, with the value of the same month a year earlier (found by its date). A series that fails to load has no row. */
interface Indicator {
  meta: PriceMeta;
  segment: string;
  ago: number | null;
}
async function loadIndicators(): Promise<Indicator[]> {
  const rows = await Promise.all(
    INDICATORS.map(async ({ id, segment }): Promise<Indicator | null> => {
      try {
        const s = await loadSeries(id);
        const last = s.meta.stats?.last;
        if (!last) return null;
        return { meta: s.meta, segment, ago: valueInMonth(s.x, s.v, yearEarlier(last.t)) };
      } catch {
        return null;
      }
    }),
  );
  return rows.filter((r): r is Indicator => r !== null);
}

function PassageRow({ row, name, src, y }: { row: MarketNowRow; name?: string; src: string; y: string }) {
  const t = rowText(row);
  const body = (
    <>
      <b class="fn-name">{name ?? row.id}</b>
      <span class="muted small num fn-fig">
        <span>
          Transits {t.transits.now} vs {t.transits.ago} a year earlier: <b title={t.transits.change === '—' ? 'No per cent to print: nothing a year earlier' : undefined}>{t.transits.change}</b>
        </span>
        <span>
          Cargo {t.cargo.now} vs {t.cargo.ago} a year earlier: <b title={t.cargo.change === '—' ? 'No per cent to print: nothing a year earlier' : undefined}>{t.cargo.change}</b>
        </span>
      </span>
    </>
  );
  // data-src and data-y: what "Copy citation" reads
  return name ? (
    <button class="list-btn fn-row" data-src={src} data-y={y} onClick={() => select({ kind: 'chokepoint', id: row.id })} title={`Open ${name}`}>
      {body}
    </button>
  ) : (
    <div class="fn-row" data-src={src} data-y={y}>
      {body}
    </div>
  );
}

/** The row opens the series in the price explorer; the source line under it carries the source and the month for "Copy citation". */
function IndicatorRow({ ind }: { ind: Indicator }) {
  const { meta: m, segment, ago } = ind;
  const last = m.stats!.last;
  const late = isLate(m);
  const pct = percentOnYear(m);
  const publisher = sources.value[m.s]?.publisher ?? m.s;
  return (
    <div class="fn-ind" data-src={m.s} data-y={last.t}>
      <button class="list-btn fn-row" onClick={() => openPrices({ series: [m.id] })} title={`Open ${m.name} in the price explorer · ${sourceLabel(m.s)}${m.basis ? ' · ' + m.basis : ''}`}>
        <b class="fn-name">{m.name}</b>
        <span class="muted small num fn-fig">
          <span>
            {segment} · {NOT_A_RATE}
          </span>
          <span title={late ? `No value since ${fmtDate(last.t)}: this series is late` : undefined}>
            {fmtPrice(last.v)} {m.unit} in {fmtDate(last.t)}
            {late ? ' · late' : ''}
          </span>
          {ago != null && (
            <span>
              A year earlier, {fmtDate(yearEarlier(last.t))}: {fmtPrice(ago)}
              {pct != null && <> · <b>{fmtPct(pct)}</b> on the year</>}
            </span>
          )}
          {ago == null && pct != null && (
            <span>
              Change on one year: <b>{fmtPct(pct)}</b>
            </span>
          )}
        </span>
      </button>
      <SourceLine s={m.s} y={last.t} n={indicatorNote(m.id, publisher, m.note)} />
    </div>
  );
}

/** A publisher the atlas links to and shows no value of: no source line, no data-src, so the citation never names it. */
function LinkRow({ l }: { l: LinkOnly }) {
  const src = sources.value[l.s];
  const href = l.href ?? src?.url;
  return (
    <div class="fn-link">
      {href ? (
        <a href={href} target="_blank" rel="noopener">
          {l.name}
        </a>
      ) : (
        <b>{l.name}</b>
      )}
      <span class="muted small fn-pub">
        {l.what} · {src?.publisher ?? l.s}
      </span>
    </div>
  );
}

export default function FreightNowView() {
  const page = useLoaded(loadPage, []);
  const indicators = useLoaded(loadIndicators, []);
  const head = (
    <div class="detail-head" style={{ '--kicker': FAMILY_COLOR.freight }}>
      <div class="detail-kicker">{FAMILY_LABEL.freight}</div>
      <h2 class="detail-title">Freight market now</h2>
    </div>
  );
  const digest = page?.digest ?? null;
  const dates = digest ? `${digest.weeks} weeks to ${digest.to}, against ${digest.weeks} weeks to ${digest.yearAgoTo}` : '';
  return (
    <>
      {head}
      <div class="panel-scroll">
        <p class="prose" style={{ margin: '8px 0 0' }}>{LEAD}</p>
        {page === undefined ? (
          <Skeleton lines={6} />
        ) : !digest ? (
          <p class="muted small fn-none">{NO_FIGURES}</p>
        ) : (
          <>
            <p class="muted small fn-window">
              Figures are {digest.unit} and {digest.mtUnit}: the {digest.weeks} weeks to {digest.to}, against the same {digest.weeks} weeks to {digest.yearAgoTo}. A ship that crosses several passages is counted at each, so the rows do not add up.
            </p>
            {MARKET_TYPES.map(({ type, title, noun }) => {
              const rows = digest.types[type];
              return (
                <Section key={type} title={title}>
                  {rows.length === 0 ? (
                    <p class="muted small fn-none">{NO_FIGURES}</p>
                  ) : (
                    <>
                      <p class="muted small fn-rule">
                        The five are the passages with the most cargo of {noun} over the {digest.rankWeeks} weeks to {digest.yearAgoTo}, by PortWatch's estimate: a rule of the atlas, not of PortWatch.
                      </p>
                      {rows.map((r) => (
                        <PassageRow key={r.id} row={r} name={page?.names.get(r.id)} src={digest.s} y={dates} />
                      ))}
                      <SourceLine
                        s={digest.s}
                        y={dates}
                        n={`${noun}; weekly averages of PortWatch's daily counts, times 7 and summed over the four weeks; the cargo is PortWatch's estimate of what the vessels carry, not a customs statistic; data adapted`}
                      />
                    </>
                  )}
                  {type === 'tanker' && <p class="muted small fn-classes">{CLASSES}</p>}
                </Section>
              );
            })}
          </>
        )}
        <Section title="Indicators that are not freight rates">
          {indicators === undefined ? (
            <Skeleton lines={3} />
          ) : indicators?.length ? (
            indicators.map((ind) => <IndicatorRow key={ind.meta.id} ind={ind} />)
          ) : (
            <p class="muted small fn-none">{NO_INDICATORS}</p>
          )}
        </Section>
        <Section title="Indices and rates published elsewhere">
          <p class="muted small fn-rule">The atlas links to these and shows no value of them.</p>
          {LINK_ONLY.map((l) => (
            <LinkRow key={l.name} l={l} />
          ))}
        </Section>
      </div>
    </>
  );
}
