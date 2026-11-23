/**
 * The "Freight rate" block of a route page: where the rates of the route are published, and why the atlas shows none.
 * Baltic Exchange assessments are proprietary. The free USDA tables of grain ocean rates credit a private consultancy or
 * a foreign institute for the rates, so the atlas links to them and does not copy them (METHODOLOGY.md, freight prices).
 */
import type { Route } from '../../types';
import { segmentOf } from '../../lib/freight';
import { openPrices } from '../../lib/prices';
import { Section } from '../ui';
import '../../styles/infra.css';

const BALTIC_URL = 'https://www.balticexchange.com/en/data-services/market-information0/indices.html';
/** Bank of Japan services producer price index (2020 base): its time-series site asks every service that uses its API to notify the Bank, so it is linked. */
const BOJ_URL = 'https://www.boj.or.jp/en/statistics/pi/sppi_2020/index.htm';

/** The USDA table that covers a route of the atlas: what the reader finds there. */
const USDA: Record<string, { text: string; href: string; label: string }> = {
  'usgulf-china-grain': {
    text: 'USDA publishes monthly ocean rates for bulk grain from the US Gulf to Japan (not China), in USD per tonne, assessed by O’Neil Commodity Consulting.',
    href: 'https://agtransport.usda.gov/d/ehs5-yac3',
    label: 'USDA vessel rates, US Gulf and PNW to Japan',
  },
  'uspnw-asia-grain': {
    text: 'USDA publishes monthly ocean rates for bulk grain from the US Pacific Northwest to Japan, in USD per tonne, assessed by O’Neil Commodity Consulting.',
    href: 'https://agtransport.usda.gov/d/ehs5-yac3',
    label: 'USDA vessel rates, US Gulf and PNW to Japan',
  },
  'brazil-china-soybeans': {
    text: 'USDA publishes quarterly ocean rates for soybeans from six Brazilian ports to Shanghai and Hamburg, in USD per tonne (University of São Paulo, ESALQ, and USDA).',
    href: 'https://agtransport.usda.gov/d/j6ns-hzra',
    label: 'USDA ocean rates, Brazilian ports to China and Germany',
  },
  'blacksea-egypt-wheat': {
    text: 'USDA publishes quarterly ocean rates for grain from Ukrainian ports to Egypt and other buyers, by vessel size, in USD per tonne (Centre for Transport Strategies, Kyiv, and USDA).',
    href: 'https://agtransport.usda.gov/d/2n8s-739j',
    label: 'USDA ocean rates from Ukrainian ports',
  },
};

export function RouteRates({ r }: { r: Route }) {
  const usda = USDA[r.id];
  const seg = segmentOf(r.vclass);
  const dry = seg === 'dry';
  return (
    <Section title="Freight rate">
      <p class="prose">
        {r.benchmark ? 'The Baltic Exchange assessment of this route is proprietary: the atlas does not show it.' : 'Baltic Exchange rate assessments are proprietary: the atlas shows none.'}{' '}
        <a class="port-link" href={BALTIC_URL} target="_blank" rel="noopener">Baltic Exchange indices</a>
      </p>
      {usda && (
        <p class="prose">
          {usda.text} The atlas links to the table and does not copy it.{' '}
          <a class="port-link" href={usda.href} target="_blank" rel="noopener">{usda.label}</a>
        </p>
      )}
      {dry && (
        <p class="prose">
          A free long-run indicator of dry bulk rates, deflated and detrended, is in Prices:{' '}
          <button class="port-link" onClick={() => openPrices({ series: ['igrea-m'] })}>Dallas Fed index of global real economic activity</button>.
        </p>
      )}
      {(dry || seg === 'tanker') && (
        <p class="prose">
          The Bank of Japan publishes a monthly services producer price index for {dry ? 'ocean freight transportation except tankers' : 'ocean tankers'} (2020 = 100); the atlas links to it.{' '}
          <a class="port-link" href={BOJ_URL} target="_blank" rel="noopener">Bank of Japan SPPI</a>
        </p>
      )}
    </Section>
  );
}
