/** The blocks of the agriculture pages that sit beside the flows: the balance of a USDA crop, and the gap between customs flows and USDA. */
import type { CommodityData } from '../types';
import { commodityMeta, countryName } from '../lib/data';
import { Section, SourceLine } from './ui';
import CropBalanceSection from './CropBalance';

/**
 * Where the customs record of an exporter is far below USDA's figure (Russian grain: Russia has not published its customs data
 * since 2022, so its flows rest on what importers declare): said once, in full, above the flows and the lanes they feed.
 */
function GapNote({ gaps }: { gaps: NonNullable<CommodityData['gaps']> }) {
  return (
    <Section title="Gap in the customs record">
      {gaps.map((g) => (
        <div class="alert alert-medium" role="note" key={g.o}>
          <div class="alert-head">
            <b>{countryName(g.o)}: customs flows and lanes are below USDA</b>
          </div>
          <p>{g.text}</p>
        </div>
      ))}
      <SourceLine s={gaps[0].s} y={gaps[0].y} n="the flows and lanes below are customs records; the figures of USDA PSD are in the tables above" />
    </Section>
  );
}

/** `part`: the balance sits with the secondary blocks of the page, the gap note just above the flows it is about. */
export default function AgriBlocks({ d, color, part }: { d: CommodityData; color?: string; part: 'balance' | 'gaps' }) {
  return (
    <>
      {part === 'balance' && d.balance && <CropBalanceSection bal={d.balance} color={color} commodity={commodityMeta(d.id)?.name ?? d.id} />}
      {part === 'gaps' && !!d.gaps?.length && <GapNote gaps={d.gaps} />}
    </>
  );
}
