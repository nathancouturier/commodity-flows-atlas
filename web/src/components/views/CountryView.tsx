/** Country profile: ranked exports, imports, production shares, infrastructure, companies, lanes. */
import { useEffect, useMemo, useState } from 'preact/hooks';
import type { CountryProfile, Lane, LaneFile, ProfileEntry } from '../../types';
import { loadOptional, countryName, commodityMeta, countries, sourceLabel } from '../../lib/data';
import { fmt, pct, FAMILY_COLOR } from '../../lib/format';
import { LANE_GROUPS, loadLaneFile } from '../../lib/freight';
import { flyToCountry } from '../../map/controller';
import { infraCapacity, infraColor, infraRef, loadInfra, type InfraFeature } from '../../map/modules/infrastructure';
import { commodity, select } from '../../lib/store';
import { Section, Placeholder, Skeleton, SourcesLine, Kpi, RowBtn, InfraIcon, INFRA_META, CompanyRows, AlertBanners, StatusBadge, shortSource } from '../ui';
import { publisher, useLoaded } from './shared';

function EntryList(props: { rows: ProfileEntry[]; showUsd?: boolean }) {
  return (
    <div class="bars">
      {props.rows.map((e, i) => {
        const meta = commodityMeta(e.k);
        const color = meta ? FAMILY_COLOR[meta.family] : '#8892a0';
        const sub = [e.rank ? `world #${e.rank}` : null, props.showUsd && e.usd != null ? `${fmt(e.usd)} bn USD` : null].filter(Boolean).join(' · ');
        return (
          <button
            class="bar-row"
            key={e.k + i}
            title={`${sourceLabel(e.s)} · ${e.y}${e.n ? ' · ' + e.n : ''}`}
            onClick={() => {
              if (!meta) return;
              commodity.value = e.k;
              select({ kind: 'commodity', id: e.k });
            }}
          >
            <span class="bar-rank">{i + 1}</span>
            <span>
              <span class="bar-label">{e.label ?? meta?.name ?? e.k}</span>
              <div class="bar-track">
                <div class="bar-fill" style={{ width: `${Math.max(2, (e.share ?? 0) * 100)}%`, background: color }} />
              </div>
              {sub && <span class="bar-sub">{sub}</span>}
            </span>
            <span class="bar-value">
              {fmt(e.v)} {e.u}
              {e.share != null && <small>{pct(e.share)} of world</small>}
            </span>
          </button>
        );
      })}
      <SourcesLine items={props.rows} />
    </div>
  );
}

const byUsd = (a: ProfileEntry, b: ProfileEntry) => (b.usd ?? -1) - (a.usd ?? -1);

/** Seaborne lanes touching a country, across the lane files of its profile commodities. */
function CountryLanes({ id, p }: { id: string; p: CountryProfile }) {
  const groups = useMemo(() => {
    const ks = new Set([...p.exports, ...p.imports, ...p.production].map((e) => e.k));
    const gs = new Set<string>();
    for (const k of ks) (LANE_GROUPS[k] ?? []).forEach((g) => gs.add(g));
    return [...gs].slice(0, 14);
  }, [p]);
  const lanes = useLoaded<{ lane: Lane; file: LaneFile }[]>(
    () =>
      Promise.all(groups.map((g) => loadLaneFile(g).catch(() => null))).then((files) => {
        const out: { lane: Lane; file: LaneFile }[] = [];
        for (const file of files) {
          if (!file) continue;
          // hide lanes that would display as 0.0 Mt
          for (const lane of file.lanes) if ((lane.o === id || lane.d === id) && lane.flow.v >= (lane.flow.u === 'Mt' ? 0.05 : 1e-9)) out.push({ lane, file });
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
          sub={file.label ?? commodityMeta(lane.k)?.name ?? file.group}
          meta={<>{lane.flow.u === 'Mt' ? lane.flow.v.toFixed(1) : fmt(lane.flow.v)} {lane.flow.u}<small>{lane.flow.y}</small></>}
          tip={`${sourceLabel(lane.flow.s)} · ${lane.flow.y}`}
          onClick={() => select({ kind: 'lane', id: lane.id })}
        />
      ))}
      <SourcesLine items={lanes.map((l) => l.lane.flow)} n="largest lanes of this country's main commodities" />
    </Section>
  );
}

function CountryInfra({ ids }: { ids: string[] }) {
  const all = useLoaded<InfraFeature[]>(() => loadInfra(), []);
  const [showAll, setShowAll] = useState(false);
  const items = useMemo(() => {
    if (!all) return [];
    const map = new Map(all.map((f) => [`${f.p.type}:${f.p.id}`, f]));
    return ids.map((k) => map.get(k)).filter((f): f is InfraFeature => !!f);
  }, [all, ids.join()]);
  if (!items.length) return null;
  const shown = showAll ? items : items.slice(0, 8);
  return (
    <Section title="Main infrastructure" aside={<span class="muted num">{items.length}</span>}>
      {shown.map((f) => (
        <RowBtn
          key={f.p.type + f.p.id}
          lead={<InfraIcon type={f.p.type} color={infraColor(f)} size={22} />}
          title={f.p.name}
          sub={
            <>
              {[INFRA_META[f.p.type].label, f.p.capacity ? infraCapacity(f.p) : null].filter(Boolean).join(' · ')}
              {f.p.status && (
                <>
                  {' '}
                  <StatusBadge status={f.p.status} />
                </>
              )}
            </>
          }
          tip={`${sourceLabel(f.p.s)} · ${f.p.y}`}
          onClick={() => select(infraRef(f))}
        />
      ))}
      {items.length > 8 && (
        <button class="act-btn" onClick={() => setShowAll(!showAll)} aria-expanded={showAll}>
          {showAll ? 'Show fewer' : `Show all ${items.length}`}
        </button>
      )}
      <SourcesLine items={shown.map((f) => f.p)} n="capacity per asset in its own panel" />
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
    const top10 = new Set(all.filter((e) => (e.rank ?? 99) <= 10 && commodityMeta(e.k)).map((e) => e.k));
    const ents = all.filter((e) => (e.rank ?? 99) <= 10 && commodityMeta(e.k));
    const pubs = [...new Set(ents.map((e) => shortSource(e.s)))];
    const srcs = `${pubs.length > 1 ? 'Sources' : 'Source'}: ${pubs.join(', ')}`;
    const yrs = [...new Set(ents.map((e) => String(e.y)))].sort();
    const yr = yrs.length > 1 ? `${yrs[0]}–${yrs[yrs.length - 1]}` : (yrs[0] ?? '');
    const topExp = [...p.exports].filter((e) => e.usd != null).sort(byUsd)[0];
    kpis = (
      <div class="kpis">
        {top10.size > 0 && (
          <Kpi
            label="World top-10 in"
            value={`${top10.size} commodit${top10.size === 1 ? 'y' : 'ies'}`}
            sub={`${srcs} · ${yr}`}
            title="Atlas catalogue commodities where this country ranks in the top 10 of production, exports or imports"
          />
        )}
        {topExp && (
          <Kpi
            label={`Largest export`}
            value={`${fmt(topExp.usd)} bn USD`}
            sub={`${topExp.label ?? commodityMeta(topExp.k)?.name ?? topExp.k} · ${shortSource(topExp.s)} · ${topExp.y}`}
            title={`${sourceLabel(topExp.s)} · ${topExp.y}`}
          />
        )}
      </div>
    );
  }

  const exports = p ? [...p.exports].sort((a, b) => (a.usd != null || b.usd != null ? byUsd(a, b) : 0)) : [];
  const imports = p ? [...p.imports].sort((a, b) => (a.usd != null || b.usd != null ? byUsd(a, b) : 0)) : [];
  return (
    <>
      <div class="detail-head">
        <div class="detail-kicker">Country profile{meta ? ` · ${meta.region}` : ''}</div>
        <h2 class="detail-title">{countryName(id)}</h2>
        {kpis}
      </div>
      <div class="panel-scroll">
        <AlertBanners country={id} />
        {p === undefined ? (
          <Skeleton lines={6} />
        ) : p === null ? (
          <Placeholder>No commodity in the atlas catalogue is significant for this country yet.</Placeholder>
        ) : (
          <>
            {exports.length > 0 && (
              <Section title="Key exports">
                <EntryList rows={exports} showUsd />
              </Section>
            )}
            {imports.length > 0 && (
              <Section title="Key imports">
                <EntryList rows={imports} showUsd />
              </Section>
            )}
            {p.production.length > 0 && (
              <Section title="Production, share of world">
                <EntryList rows={p.production} />
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
