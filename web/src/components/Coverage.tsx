/**
 * The Quality tab of the About window: which blocks each commodity page holds (data/coverage.json). The file is requested when the tab
 * is opened, not at page load. Every count printed here is computed from it (lib/coverage.ts). Nothing is stored and nothing is written
 * to the address.
 */
import { Fragment } from 'preact';
import { useEffect, useRef, useState } from 'preact/hooks';
import { commodities, loadOptional } from '../lib/data';
import { FAMILY_LABEL } from '../lib/format';
import { STATE_NAME, allCells, coverageCounts, reasonCounts, type CellState, type CoverageFile } from '../lib/coverage';
import { RELEASE, fmtDate } from '../lib/status';
import type { Family } from '../types';
import { closeAbout } from './AboutHost';
import { Skeleton } from './ui';
import { openCommodity } from './views/shared';
import '../styles/coverage.css';

const FAMILIES: Family[] = ['energy', 'metals', 'softs'];

const LEGEND: Record<CellState, string> = {
  p: 'The block holds at least one entry.',
  na: 'The commodity cannot have this block.',
  nf: 'No free source offers it; the pages that say so were read.',
  m: 'Not in the atlas yet: nothing is loaded for it.',
};
const LEGEND_ORDER: CellState[] = ['p', 'na', 'nf', 'm'];

function Mark(props: { state: CellState }) {
  return <span class={`cov-mark cov-${props.state}`} aria-hidden="true" />;
}

/** The reason of a cell that is not applicable or not available for free, opened under its row. */
function ReasonRow(props: { id: string; page: string; block: string; state: CellState; reason: string }) {
  return (
    <tr class="cov-reason" id={props.id}>
      <td colSpan={12}>
        <div role="status">
          <b>
            {props.page} · {props.block} · {STATE_NAME[props.state]}:
          </b>{' '}
          {props.reason}
        </div>
      </td>
    </tr>
  );
}

function Grid(props: { file: CoverageFile }) {
  const { file } = props;
  const [open, setOpen] = useState<string | null>(null);
  // whether the open reason was opened by the keyboard: only that one closes when the focus moves on (a tap that opens a reason closes
  // nothing by blurring, since the reason row under the tapped cell would shift the layout between the touch and the click)
  const byKey = useRef(false);
  const cells = new Map<string, ReturnType<typeof allCells>[number]>();
  for (const c of allCells(file)) cells.set(`${c.page}|${c.block.id}`, c);
  const meta = commodities.value;
  const byId = new Map(meta.map((m) => [m.id, m]));
  const rows = file.pages.map((p) => ({ id: p.id, name: byId.get(p.id)?.name ?? p.id, family: byId.get(p.id)?.family }));
  const nCols = file.blocks.length;
  return (
    <table class="cov-grid">
      <caption class="sr-only">Blocks held by each commodity page</caption>
      <colgroup>
        <col class="cov-col-name" />
        {file.blocks.map((b) => (
          <col key={b.id} />
        ))}
      </colgroup>
      <thead>
        <tr>
          <th scope="col" class="cov-name">
            <span class="sr-only">Commodity page</span>
          </th>
          {file.blocks.map((b) => (
            <th scope="col" class="cov-head" key={b.id} title={b.text}>
              <span>{b.label}</span>
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {FAMILIES.map((fam) => {
          const list = rows.filter((r) => r.family === fam);
          if (!list.length) return null;
          return (
            <Fragment key={fam}>
              <tr class="cov-fam">
                <th scope="colgroup" colSpan={nCols + 1}>
                  {FAMILY_LABEL[fam]}
                </th>
              </tr>
              {list.map((r) => {
                const openHere = open?.startsWith(`${r.id}|`) ? cells.get(open) : undefined;
                return (
                  <Fragment key={r.id}>
                    <tr>
                      <th scope="row" class="cov-name">
                        <button
                          class="cov-page"
                          title={`Open the page ${r.name}`}
                          onClick={() => {
                            openCommodity(r.id);
                            closeAbout();
                          }}
                        >
                          {r.name}
                        </button>
                      </th>
                      {file.blocks.map((b) => {
                        const c = cells.get(`${r.id}|${b.id}`);
                        if (!c) return <td class="cov-cell cov-none" key={b.id} />;
                        const label = `${r.name}, ${b.label}: ${STATE_NAME[c.state]}`;
                        if (c.reason == null)
                          return (
                            <td class="cov-cell" key={b.id}>
                              <span role="img" aria-label={label} title={label}>
                                <Mark state={c.state} />
                              </span>
                            </td>
                          );
                        const key = `${r.id}|${b.id}`;
                        return (
                          <td class="cov-cell" key={b.id}>
                            <button
                              class={`cov-btn${open === key ? ' cov-on' : ''}`}
                              aria-label={`${label}. ${c.reason}`}
                              aria-expanded={open === key}
                              aria-controls={open === key ? `cov-reason-${r.id}` : undefined}
                              onFocus={(e) => {
                                // the keyboard gets the reason on focus; a tap or a click opens it with the click below
                                if (e.currentTarget.matches(':focus-visible')) {
                                  byKey.current = true;
                                  setOpen(key);
                                }
                              }}
                              onBlur={(e) => {
                                const to = e.relatedTarget;
                                if (!byKey.current || (to instanceof Element && to.classList.contains('cov-btn'))) return;
                                byKey.current = false;
                                setOpen((o) => (o === key ? null : o));
                              }}
                              onClick={(e) => {
                                if (e.detail !== 0) byKey.current = false;
                                setOpen(open === key && e.detail !== 0 ? null : key);
                              }}
                              onKeyDown={(e) => {
                                if (e.key === 'Escape' && open) {
                                  // the first Escape closes the reason, not the window
                                  e.preventDefault();
                                  e.stopPropagation();
                                  setOpen(null);
                                }
                              }}
                            >
                              <Mark state={c.state} />
                            </button>
                          </td>
                        );
                      })}
                    </tr>
                    {openHere && openHere.reason != null && (
                      <ReasonRow id={`cov-reason-${r.id}`} page={r.name} block={openHere.block.label} state={openHere.state} reason={openHere.reason} />
                    )}
                  </Fragment>
                );
              })}
            </Fragment>
          );
        })}
      </tbody>
    </table>
  );
}

export function QualityTabView() {
  const [file, setFile] = useState<CoverageFile | null | undefined>(undefined);
  useEffect(() => {
    let live = true;
    loadOptional<CoverageFile>('coverage.json').then((f) => live && setFile(f));
    return () => {
      live = false;
    };
  }, []);
  if (file === undefined || commodities.value.length === 0) return <Skeleton lines={8} />;
  if (file === null) return <p class="about-empty">The coverage of the commodity pages could not be loaded.</p>;
  const n = coverageCounts(file);
  const asOf = `as of release ${file.release}${String(file.release) === RELEASE.number && RELEASE.date ? `, ${fmtDate(RELEASE.date)}` : ''}`;
  const reasons = reasonCounts(file);
  return (
    <>
      <h3>Coverage of the commodity pages</h3>
      <p class="cov-headline">
        <b class="num">{n.p}</b> of <b class="num">{n.applicable}</b> blocks present, {asOf}.
        {n.na > 0 && <> The {n.na} that are not applicable are not counted.</>}
      </p>
      <p>
        Which blocks each commodity page holds, counted from the files the atlas is built from. Present means at least one entry, not how many.
      </p>
      <ul class="cov-legend">
        {LEGEND_ORDER.map((s) => (
          <li key={s}>
            <Mark state={s} />
            <span>
              <b>{STATE_NAME[s][0].toUpperCase() + STATE_NAME[s].slice(1)}</b> <span class="num">{n[s]}</span> · {LEGEND[s]}
            </span>
          </li>
        ))}
      </ul>
      <Grid file={file} />
      <h3>What each column counts</h3>
      <dl class="cov-defs">
        {file.blocks.map((b) => (
          <Fragment key={b.id}>
            <dt>{b.label}</dt>
            <dd>
              {b.text}
              {b.families && <> Only for {b.families.map((f) => FAMILY_LABEL[f as Family] ?? f).join(', ')} pages.</>}
            </dd>
          </Fragment>
        ))}
      </dl>
      {reasons.length > 0 && (
        <>
          <h3>Reasons given</h3>
          <ul class="cov-reasons">
            {reasons.map((r) => (
              <li key={r.id}>
                <b>{STATE_NAME[r.st === 'na' ? 'na' : 'nf']}</b> · {r.t} <span class="num">{r.cells}</span> {r.cells === 1 ? 'cell' : 'cells'}
              </li>
            ))}
          </ul>
        </>
      )}
    </>
  );
}
