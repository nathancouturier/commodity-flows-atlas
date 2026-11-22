/** Country profile: ranked exports, imports, production shares, infrastructure, companies. */
import { useEffect, useState } from 'preact/hooks';
import type { CountryProfile, ProfileEntry } from '../../types';
import { loadOptional, countryName, commodityMeta, countries } from '../../lib/data';
import { fmt, pct, FAMILY_COLOR } from '../../lib/format';
import { flyToCountry } from '../../map/controller';
import { commodity, select } from '../../lib/store';
import { Section, Placeholder, Skeleton, SourceLine } from '../ui';

function EntryList(props: { rows: ProfileEntry[] }) {
  return (
    <div class="bars">
      {props.rows.map((e, i) => {
        const meta = commodityMeta(e.k);
        const color = meta ? FAMILY_COLOR[meta.family] : '#8892a0';
        return (
          <button
            class="bar-row"
            key={e.k + i}
            title={`${e.s} · ${e.y}${e.n ? ' · ' + e.n : ''}`}
            onClick={() => {
              if (!meta) return;
              commodity.value = e.k;
              select({ kind: 'commodity', id: e.k });
            }}
          >
            <span class="bar-rank">{e.rank ? `#${e.rank}` : i + 1}</span>
            <span>
              <span class="bar-label">{meta?.name ?? e.label ?? e.k}</span>
              <div class="bar-track">
                <div class="bar-fill" style={{ width: `${Math.max(2, (e.share ?? 0) * 100)}%`, background: color }} />
              </div>
            </span>
            <span class="bar-value">
              {fmt(e.v)} {e.u}
              {e.share != null && <small>{pct(e.share)} of world</small>}
            </span>
          </button>
        );
      })}
    </div>
  );
}

export default function CountryView({ id }: { id: string }) {
  const [p, setP] = useState<CountryProfile | null | undefined>(undefined);
  useEffect(() => {
    setP(undefined);
    flyToCountry(id);
    loadOptional<Record<string, CountryProfile>>('countries/profiles.json').then((all) => setP(all?.[id] ?? null));
  }, [id]);
  const meta = countries.value[id];
  return (
    <>
      <div class="detail-head">
        <div class="detail-kicker">Country profile{meta ? ` · ${meta.region}` : ''}</div>
        <h2 class="detail-title">{countryName(id)}</h2>
      </div>
      <div class="panel-scroll">
        {p === undefined ? (
          <Skeleton lines={6} />
        ) : p === null ? (
          <Placeholder>No commodity in the atlas catalogue is significant for this country yet.</Placeholder>
        ) : (
          <>
            {p.exports.length > 0 && (
              <Section title="Key exports">
                <EntryList rows={p.exports} />
              </Section>
            )}
            {p.imports.length > 0 && (
              <Section title="Key imports">
                <EntryList rows={p.imports} />
              </Section>
            )}
            {p.production.length > 0 && (
              <Section title="Production, share of world">
                <EntryList rows={p.production} />
              </Section>
            )}
            {p.other && p.other.length > 0 && (
              <Section title="Other notable raw materials">
                <EntryList rows={p.other} />
              </Section>
            )}
            {p.companies && p.companies.length > 0 && (
              <Section title="Main companies">
                {p.companies.map((c) => (
                  <div class="list-btn" key={c.name} style={{ cursor: 'default' }}>
                    {c.name}
                    <span class="meta">{c.role}</span>
                  </div>
                ))}
                <SourceLine s={p.companies[0].s} y={p.companies[0].y} />
              </Section>
            )}
          </>
        )}
      </div>
    </>
  );
}
