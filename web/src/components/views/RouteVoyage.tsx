/**
 * The "Voyage calculator" block of a route page: a calculation on figures the visitor types, with the speed and fuel of the
 * standard vessel and the distance of the route as the starting values (web/src/lib/voyage.ts has the formulas and the
 * defaults). It is a calculation, not a market rate: hire, freight, bunker price, port costs, canal tolls and port days have no
 * default.
 *
 * What was typed lives in `typed`, in memory, by route id: a folded block is unmounted and a route page is rebuilt for each
 * route, so the component could not keep it. Nothing is written to the URL hash or to any storage of the browser: a typed
 * hire or bunker price in a copied link would pass for a figure the atlas published.
 */
import { Fragment } from 'preact';
import { useMemo, useState } from 'preact/hooks';
import type { Route } from '../../types';
import { vesselClassList } from '../../lib/freight';
import {
  FIELD_LABEL, OPTIONAL_FIELDS, emptyInputs, formatDays, formatUsd, parseField, routingOptions, voyage, voyageDefaults, voyageEligible,
  type Field, type Trace,
} from '../../lib/voyage';
import { Kpi, MethodLink, Section, SourceLine } from '../ui';
import '../../styles/infra.css';
import '../../styles/voyage.css';

/** The authorities' own pages: the atlas holds no toll figure and copies none. */
const SUEZ_URL = 'https://www.suezcanal.gov.eg/English/Navigation/Tolls/Pages/TollsTable.aspx';
const PANAMA_URL = 'https://pancanal.com/en/maritime-services/maritime-tariff/';

interface Typed {
  /** index into `routingOptions(r)`; null for the main routing */
  alt: number | null;
  /** the text of each field the visitor touched; a field that is not here shows its default */
  text: Partial<Record<Field, string>>;
}
const typed = new Map<string, Typed>();

/** Fields that must be above zero: a typed 0 takes the warning border like a letter does. */
const POSITIVE = new Set<Field>(['cargoT', 'ladenKn', 'ballastKn', 'ladenFuel', 'ballastFuel', 'bunkerUsdPerT', 'hireUsdPerDay', 'freightUsdPerT']);

/** The form in reading order, two to a row. The laden distance is the routing's, shown as a value. */
const FORM: Field[] = [
  'cargoT', 'portDays', 'ladenNm', 'ballastNm', 'ladenKn', 'ballastKn', 'ladenFuel', 'ballastFuel',
  'bunkerUsdPerT', 'portFuelT', 'portCostsUsd', 'tollsUsd', 'hireUsdPerDay', 'freightUsdPerT',
];

const NOT_ENTERED: Partial<Record<Field, string>> = { portDays: 'port and canal days', portFuelT: 'port fuel', tollsUsd: 'canal tolls', portCostsUsd: 'port costs' };

const numText = (v: number) => v.toLocaleString('en-US', { maximumFractionDigits: 6 });
const t0 = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 });

export function RouteVoyage({ r }: { r: Route }) {
  const classes = vesselClassList.value;
  if (!voyageEligible(r) || !classes.length) return null;
  return (
    <Section fold title="Voyage calculator">
      <Calculator r={r} classes={classes} />
    </Section>
  );
}

function Calculator({ r, classes }: { r: Route; classes: ReturnType<typeof vesselClassList.peek> }) {
  const [state, setState] = useState<Typed>(() => typed.get(r.id) ?? { alt: null, text: {} });
  const update = (next: Typed) => {
    typed.set(r.id, next);
    setState(next);
  };
  const options = routingOptions(r);
  const d = useMemo(() => voyageDefaults(r, state.alt, classes), [r, state.alt, classes]);
  const tolls = d.canals.length > 0;
  const visible = FORM.filter((f) => f !== 'tollsUsd' || tolls);

  const text = (f: Field) => state.text[f] ?? (d.values[f] != null ? numText(d.values[f]!) : '');
  const inputs = emptyInputs();
  const bad: Partial<Record<Field, boolean>> = {};
  for (const f of visible) {
    if (f === 'ladenNm') {
      inputs.ladenNm = d.values.ladenNm;
      continue;
    }
    const p = parseField(text(f));
    inputs[f] = p.value;
    bad[f] = p.invalid || (POSITIVE.has(f) && p.value === 0);
  }
  const anyBad = Object.values(bad).some(Boolean);
  const shown = OPTIONAL_FIELDS.filter((f) => f !== 'tollsUsd' || tolls);
  const res = anyBad ? null : voyage(inputs, shown);

  const lines: Trace[] = [];
  const seen = new Set<string>();
  for (const f of ['cargoT', 'ladenNm', 'ballastNm', 'ladenKn', 'ballastKn', 'ladenFuel', 'ballastFuel'] as Field[]) {
    const t = d.traces[f];
    if (!t || state.text[f] !== undefined) continue;
    const key = `${t.s}|${t.y ?? ''}|${t.n ?? ''}`;
    if (seen.has(key)) continue;
    seen.add(key);
    lines.push(t);
  }

  const field = (f: Field) => {
    if (f === 'ladenNm')
      return (
        <div key={f} class="rf-field vy-f">
          <span>{FIELD_LABEL[f]}</span>
          <div class="vy-val">{text(f) || '—'}</div>
        </div>
      );
    return (
      <label key={f} class={`rf-field vy-f${f === 'portCostsUsd' && !tolls ? ' vy-wide' : ''}`}>
        <span>{FIELD_LABEL[f]}</span>
        <input
          class={`rf-select vy-in${bad[f] ? ' vy-bad' : ''}`}
          type="text"
          inputMode="decimal"
          autocomplete="off"
          spellcheck={false}
          value={text(f)}
          aria-invalid={bad[f] ? true : undefined}
          onInput={(e) => update({ ...state, text: { ...state.text, [f]: (e.target as HTMLInputElement).value } })}
        />
      </label>
    );
  };

  const notEntered = res?.excluded.map((f) => NOT_ENTERED[f]).filter(Boolean) ?? [];
  const fr = res?.freight;
  return (
    <div class="vy">
      <div class="vy-grid">
        {options.length > 0 && (
          <label class="rf-field vy-f vy-wide">
            <span>Routing</span>
            <select class="rf-select vy-in" value={state.alt == null ? '' : String(state.alt)} onChange={(e) => {
              const v = (e.target as HTMLSelectElement).value;
              update({ ...state, alt: v === '' ? null : Number(v) });
            }}>
              <option value="">Main routing</option>
              {options.map((a, i) => (
                <option key={a.label} value={String(i)}>{a.label}</option>
              ))}
            </select>
          </label>
        )}
        {visible.map((f) =>
          f === 'hireUsdPerDay' && tolls ? (
            <Fragment key={f}>
              <div class="vy-wide vy-links muted small">
                {d.canals.map((c, i) => (
                  <span key={c}>
                    {i > 0 && ' · '}
                    <a class="port-link" href={c === 'suez' ? SUEZ_URL : PANAMA_URL} target="_blank" rel="noopener">{c === 'suez' ? 'Suez Canal Authority tolls' : 'Panama Canal Authority tariff'}</a>
                  </span>
                ))}
              </div>
              {field(f)}
            </Fragment>
          ) : (
            field(f)
          ),
        )}
      </div>
      <div class="kpis vy-kpis">
        <Kpi label="Freight to cover the hire" value={formatUsd(fr?.usdPerT, true)} sub="USD/t" />
        <Kpi label="Time-charter equivalent" value={formatUsd(res?.tce?.usdPerDay)} sub="USD/day" />
      </div>
      {res && (res.days != null || res.fuelT != null) && (
        <div class="ft vy-ft">
          {res.days != null && (
            <div class="ft-row ft-wide">
              <span class="ft-k">Round voyage, days</span>
              <span>
                <b>{formatDays(res.days)}</b>
                <span class="muted"> ({formatDays(res.ladenDays)} laden, {formatDays(res.ballastDays)} ballast{res.portDays ? `, ${formatDays(res.portDays)} port and canal` : ''})</span>
              </span>
            </div>
          )}
          {res.fuelT != null && (
            <div class="ft-row ft-wide">
              <span class="ft-k">Fuel, t</span>
              <span>
                <b>{t0.format(res.fuelT)}</b>
                {res.portFuelT ? <span class="muted"> ({t0.format(res.seaFuelT!)} at sea, {t0.format(res.portFuelT)} in port)</span> : null}
              </span>
            </div>
          )}
          {res.bunkersUsd != null && (
            <div class="ft-row ft-wide">
              <span class="ft-k">Bunkers, USD</span>
              <span><b>{formatUsd(res.bunkersUsd)}</b></span>
            </div>
          )}
          {fr && (
            <div class="ft-row ft-wide">
              <span class="ft-k">Freight parts, USD/t</span>
              <span>
                hire {formatUsd(fr.parts.hire, true)} · bunkers {formatUsd(fr.parts.bunkers, true)}
                {tolls && ` · canal tolls ${formatUsd(fr.parts.tolls, true)}`} · port costs {formatUsd(fr.parts.portCosts, true)}
              </span>
            </div>
          )}
          {res.tce && (
            <div class="ft-row ft-wide">
              <span class="ft-k">Revenue, USD</span>
              <span><b>{formatUsd(res.tce.revenueUsd)}</b></span>
            </div>
          )}
        </div>
      )}
      {notEntered.length > 0 && <div class="muted small vy-note">Not entered, counted as zero: {notEntered.join(', ')}</div>}
      {lines.map((t) => (
        <SourceLine key={`${t.s}|${t.y ?? ''}|${t.n ?? ''}`} s={t.s} y={t.y} n={t.n} />
      ))}
      <div class="muted small vy-note">
        A calculation on the figures above, not a market rate or a quote, and not a Baltic Exchange assessment. <MethodLink label="Method" />
      </div>
    </div>
  );
}
