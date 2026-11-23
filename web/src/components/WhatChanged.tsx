/** "What changed" at the top of the About window: the digest of the weekly update jobs (data/_status/changes.json). */
import type { Changes, PriceMove } from '../lib/status';
import { fmtDate } from '../lib/status';
import { fmtPct } from '../lib/prices';
import { shortSource } from './ui';
import '../styles/changes.css';

const price = (v: number) => (Math.abs(v) >= 1000 ? Math.round(v).toLocaleString('en-US') : Math.abs(v) >= 100 ? v.toFixed(1) : v.toFixed(2));

function Move({ m, when }: { m: PriceMove; when: string }) {
  return (
    <li>
      <b>{m.name}</b>{' '}
      <b class={`num ${m.pct < 0 ? 'chg-dn' : 'chg-up'}`}>{fmtPct(m.pct)}</b>{' '}
      <span class="chg-when num">
        {when} · {price(m.v0)} to {price(m.v1)} {m.unit} · {shortSource(m.s)}
      </span>
    </li>
  );
}

export function WhatChanged({ changes }: { changes: Changes | null | undefined }) {
  return (
    <section class="chg-sec" aria-labelledby="what-changed">
      <h3 id="what-changed">What changed</h3>
      {changes === undefined ? (
        <p class="about-empty">Loading…</p>
      ) : changes === null ? (
        <p class="about-empty">No digest yet: the weekly updates write it.</p>
      ) : (
        <>
          <p class="muted small">
            Made by the update jobs from the data on this site
            {changes.generated && <> · last news {fmtDate(changes.generated)}</>} ·{' '}
            <a href="changes.atom" type="application/atom+xml">
              Atom feed
            </a>
          </p>
          {changes.weekly.moves.length > 0 && (
            <>
              <h4>Largest price moves, week to {fmtDate(changes.weekly.to)}</h4>
              <ul class="chg-list">
                {changes.weekly.moves.map((m) => (
                  <Move key={m.id} m={m} when={`${fmtDate(m.from)} to ${fmtDate(m.to)}`} />
                ))}
              </ul>
            </>
          )}
          {changes.monthly.moves.length > 0 && (
            <>
              <h4>Monthly prices, {fmtDate(changes.monthly.to)}</h4>
              <ul class="chg-list">
                {changes.monthly.moves.slice(0, 3).map((m) => (
                  <Move key={m.id} m={m} when={`${fmtDate(m.from)} to ${fmtDate(m.to)}`} />
                ))}
              </ul>
            </>
          )}
          {changes.passages.moves.length > 0 && (
            <>
              <h4>Passages furthest from their averages, to {fmtDate(changes.passages.to)}</h4>
              <ul class="chg-list">
                {changes.passages.moves.map((m) => (
                  <li key={m.id}>
                    <b>{m.name}</b> <span class="num">{m.week.toFixed(1)} vessels a day in the last week</span>{' '}
                    <span class="chg-when num">
                      {fmtPct(m.gap28)} on the 4 weeks before · {fmtPct(m.gap365)} on the 365 days before · IMF PortWatch
                    </span>
                  </li>
                ))}
              </ul>
            </>
          )}
          <h4>New data</h4>
          {changes.sources.length ? (
            <ul class="chg-list">
              {changes.sources.map((s) => (
                <li key={s.id}>
                  <b>{s.name}</b>{' '}
                  <span class="chg-when num">
                    {s.data_to ? `data to ${fmtDate(s.data_to)}` : 'new release'} · checked {fmtDate(s.t)}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p class="muted small">No source has published new data since the previous update.</p>
          )}
        </>
      )}
    </section>
  );
}
