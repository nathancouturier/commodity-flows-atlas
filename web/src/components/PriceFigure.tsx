/**
 * The last price of a commodity and its change over one year, as two key figures on the commodity page.
 * It reads the board figures of the first price series of the commodity (daily before monthly) from
 * prices/index.json; the change is arithmetic on the two published values, not an estimate. Renders nothing for a
 * commodity with no price series.
 */
import { useEffect } from 'preact/hooks';
import { sourceLabel } from '../lib/data';
import { fmtPct, fmtPrice, inEstimate, isLate, loadPriceIndex, priceIndex, seriesForCommodity } from '../lib/prices';
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
    loadPriceIndex().catch(() => undefined);
  }, []);
  const m = seriesForCommodity(commodity, priceIndex.value).find((x) => x.stats);
  const st = m?.stats;
  if (!m || !st) return null;
  const when = fmtDate(st.last.t);
  const late = isLate(m);
  const y = st.chg?.y;
  const what = m.freq === 'D' ? 'daily spot' : m.freq === 'A' ? 'annual average' : 'monthly average';
  return (
    <div class="kpis pf">
      <div class="kpi" title={`${m.name} · ${sourceLabel(m.s)} · ${what} · ${when}${m.basis ? ' · ' + m.basis : ''}`}>
        <div class="kpi-label">Latest price · {m.name}</div>
        <div class="kpi-value num">
          {fmtPrice(st.last.v)}
          <small>{m.unit}</small>
        </div>
        <div class="kpi-src">
          {shortSource(m.s)} · {when} · {what}
          {m.freq !== 'D' && inEstimate(m, lastStamp(st.last.t)) ? ' · estimated' : ''}
          {late ? ' · late' : ''}
        </div>
      </div>
      {y != null && (
        <div class="kpi" title={`Change of ${m.name} between the last value (${when}) and the value one year earlier: arithmetic on the published figures`}>
          <div class="kpi-label">Change on one year</div>
          <div class={`kpi-value num ${y > 0 ? 'pf-up' : y < 0 ? 'pf-dn' : ''}`}>{fmtPct(y)}</div>
          <div class="kpi-src">to {when} · {shortSource(m.s)}</div>
        </div>
      )}
    </div>
  );
}
