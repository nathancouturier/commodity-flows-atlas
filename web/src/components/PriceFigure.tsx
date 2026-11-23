/**
 * The last price of a commodity and its change over one year, as two key figures on the commodity page.
 * It reads the board figures of the first price series of the commodity from prices/figures.json (a small file with one
 * entry per commodity: the page does not load the whole index); the change is arithmetic on the two published values,
 * not an estimate. An annual series (USGS) is never shown as a current price: the figure says "annual average <year>",
 * with the decimals of the source, and its change is the change on the previous year. Renders nothing for a commodity
 * with no price series.
 */
import { useEffect } from 'preact/hooks';
import { sourceLabel } from '../lib/data';
import { annualWord, fmtPct, fmtSeriesValue, inEstimate, isAnnualSeries, isLate, loadPriceFigures, priceFigures } from '../lib/prices';
import { fmtDate } from '../lib/status';
import { shortSource } from './ui';
import '../styles/price-board.css';

/** "2025" or "2026-10" -> seconds of its first day. */
const lastStamp = (t: string): number => {
  const [y, mo = '1'] = t.split('-');
  return Date.UTC(Number(y), Number(mo) - 1, 1) / 1000;
};

export function PriceFigure({ commodity }: { commodity: string }) {
  useEffect(() => {
    loadPriceFigures().catch(() => undefined);
  }, []);
  const m = priceFigures.value?.[commodity];
  const st = m?.stats;
  if (!m || !st) return null;
  const annual = isAnnualSeries(m);
  const when = annual ? st.last.t.slice(0, 4) : fmtDate(st.last.t);
  const late = isLate(m);
  const y = st.chg?.y;
  const what = m.freq === 'D' ? 'daily spot' : annual ? `${annualWord(m)} ${when}` : 'monthly average';
  const est = m.freq !== 'D' && inEstimate(m, lastStamp(st.last.t));
  // the name of an annual series already says "annual average": the label says it once
  const name = annual ? m.name.replace(/,? annual average$/, '') : m.name;
  return (
    <div class="kpis pf">
      <div class="kpi" title={`${m.name} · ${sourceLabel(m.s)} · ${what}${annual ? '' : ` · ${when}`}${m.basis ? ' · ' + m.basis : ''}`}>
        <div class="kpi-label">
          {annual ? `Annual average ${when}` : 'Latest price'} · {name}
        </div>
        <div class="kpi-value num">
          {fmtSeriesValue(m, st.last.v)}
          <small>{m.unit}</small>
        </div>
        <div class="kpi-src">
          {annual ? (
            <>
              {shortSource(m.s)} · calendar-year average
              {est ? ' · estimated' : ''}
            </>
          ) : (
            <>
              {shortSource(m.s)} · {when} · {what}
              {est ? ' · estimated' : ''}
            </>
          )}
          {late ? ' · late' : ''}
        </div>
      </div>
      {y != null && (
        <div
          class="kpi"
          title={
            annual
              ? `Change of ${m.name} between ${when} and the year before: arithmetic on the published figures`
              : `Change of ${m.name} between the last value (${when}) and the value one year earlier: arithmetic on the published figures`
          }
        >
          <div class="kpi-label">{annual ? 'Change on previous year' : 'Change on one year'}</div>
          <div class={`kpi-value num ${y > 0 ? 'pf-up' : y < 0 ? 'pf-dn' : ''}`}>{fmtPct(y)}</div>
          <div class="kpi-src">
            {annual ? `${when} on ${Number(when) - 1}` : `to ${when}`} · {shortSource(m.s)}
          </div>
        </div>
      )}
    </div>
  );
}
