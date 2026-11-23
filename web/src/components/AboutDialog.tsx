/**
 * About window: what the atlas is, its sources and their licences, how fresh the data are,
 * the method in short, and the third-party notices. Credits live here because the map carries
 * no attribution box.
 */
import type { ComponentChildren } from 'preact';
import { useEffect, useRef, useState } from 'preact/hooks';
import { sources } from '../lib/data';
import { ESTIMATE_DEFINITION } from '../lib/freight';
import { BUILD, fmtDate, loadStatus, loadVintages, type Freshness, type StatusView } from '../lib/status';
import { aboutTab, closeAbout, type AboutTab } from './AboutHost';
import { CloseIcon, Skeleton } from './ui';

const REPO = 'https://github.com/nathancouturier/commodity-flows-atlas';
const DOC = `${REPO}/blob/main/`;

const TABS: { id: AboutTab; label: string }[] = [
  { id: 'about', label: 'About' },
  { id: 'sources', label: 'Sources' },
  { id: 'freshness', label: 'Data freshness' },
  { id: 'method', label: 'Method' },
  { id: 'notices', label: 'Notices' },
];

function Ext(props: { href: string; children: ComponentChildren }) {
  return (
    <a href={props.href} target="_blank" rel="noopener">
      {props.children}
      <span aria-hidden="true"> ↗</span>
    </a>
  );
}

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
/** "2026-11-22T12:04:55Z" -> "22 November 2026" (the form FAO asks for in its citation). */
function longDate(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  return m ? `${Number(m[3])} ${MONTHS[Number(m[2]) - 1]} ${m[1]}` : iso;
}

// ---------------------------------------------------------------- about

function AboutTabView() {
  // the registry also lists the atlas's own figures (id `atlas`), which are not a third-party source
  const n = Object.keys(sources.value).filter((id) => id !== 'atlas').length;
  return (
    <>
      <h3>What the atlas is</h3>
      <p>
        Commodity Flows Atlas is an interactive map of the world's raw material trade: who produces, exports and imports energy, metals and
        minerals, agricultural goods and fertilisers, and the ships, routes and chokepoints that carry them. Every figure shows its source and
        its year.
      </p>
      <h3>Who it is for</h3>
      <p>Analysts, traders, shipbrokers, students and journalists who need a quick, sourced picture of a commodity, a country, a route or a chokepoint.</p>
      <h3>What it does not do</h3>
      <ul>
        <li>No live vessel positions and no AIS tracking.</li>
        <li>No Baltic Exchange index values and no other paid data: the atlas uses free, public sources only.</li>
        <li>No real-time prices. Price series are daily or monthly and are checked every week. Trade statistics are annual and are published a year or more after the fact.</li>
      </ul>
      <h3>Before you rely on it</h3>
      <ul class="about-terms">
        <li>
          <b>Not investment advice.</b> The atlas is general information. Nothing on it is a recommendation to buy, sell or hold anything, or a
          basis for a trading decision.
        </li>
        <li>
          <b>Not for navigation.</b> Routes, lanes and distances are schematic. They are computed on a simplified sea network and must not be
          used to plan a voyage.
        </li>
        <li>
          <b>No warranty.</b> The data come from third parties and from the atlas's own estimates. They may contain errors or be out of date,
          and are provided as is, without warranty of any kind.
        </li>
        <li>Boundaries and names on the map come from Natural Earth and do not imply any opinion on the status of a territory.</li>
      </ul>
      <h3>Credits</h3>
      <p>
        Basemap: made with <Ext href="https://www.naturalearthdata.com/">Natural Earth</Ext>. Sea routes: Eurostat SeaRoute network, through the{' '}
        <Ext href="https://github.com/genthalili/searoute-py">searoute</Ext> package. Data: {n > 0 ? `${n} public sources` : 'public sources'}, listed
        with their licences under{' '}
        <button class="about-link" onClick={() => (aboutTab.value = 'sources')}>
          Sources
        </button>
        . The licences of the atlas itself are under{' '}
        <button class="about-link" onClick={() => (aboutTab.value = 'notices')}>
          Notices
        </button>
        .
      </p>
    </>
  );
}

// ---------------------------------------------------------------- sources

/** A registry licence that points to NOTICE.md: the file name becomes a link. */
function LicenceText(props: { text: string }) {
  const i = props.text.indexOf('NOTICE.md');
  if (i < 0) return <>{props.text}</>;
  return (
    <>
      {props.text.slice(0, i)}
      <Ext href={`${DOC}NOTICE.md`}>NOTICE.md</Ext>
      {props.text.slice(i + 'NOTICE.md'.length)}
    </>
  );
}

function SourcesTabView(props: { status: StatusView | null; vintages: Record<string, string> }) {
  const list = Object.values(sources.value);
  const dated = new Map<string, string>();
  for (const r of props.status?.rows ?? []) if (r.dataTo) for (const s of r.sources) dated.set(s, r.dataTo);
  const vintage = (id: string) => dated.get(id) ?? (props.vintages[id] ? fmtDate(props.vintages[id]) : null);
  const lic = (id: string) => sources.value[id]?.licence;
  const st = props.status;
  return (
    <>
      <p>
        The atlas uses free, public sources only. Each figure on the site names its source and its year; this table lists every source with its
        licence. "Atlas estimate" marks a figure computed by the atlas.
      </p>
      {list.length === 0 ? (
        <Skeleton lines={5} />
      ) : (
        <table class="about-table about-sources">
          <thead>
            <tr>
              <th scope="col">Source</th>
              <th scope="col">Licence</th>
              <th scope="col">Vintage and updates</th>
            </tr>
          </thead>
          <tbody>
            {list.map((s) => {
              const v = vintage(s.id);
              return (
                <tr key={s.id}>
                  <th scope="row">
                    <Ext href={s.url}>{s.name}</Ext>
                    <small>{s.publisher}</small>
                  </th>
                  <td data-label="Licence">
                    <LicenceText text={s.licence} />
                  </td>
                  <td data-label="Vintage and updates">
                    {v && <span class="about-vintage">Data to <span class="num">{v}</span></span>}
                    <small>{s.update === 'n/a' ? 'No regular update' : `Updates: ${s.update}`}</small>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
      <h3>Attribution and notices</h3>
      <ul class="about-notices">
        <li>
          <b>Basemap.</b> Made with Natural Earth. Free vector and raster map data @ <Ext href="https://www.naturalearthdata.com/">naturalearthdata.com</Ext>.
        </li>
        <li>
          <b>Sea routes.</b> Routes, lanes and distances are computed on the SeaRoute maritime network of Eurostat with the{' '}
          <Ext href="https://github.com/genthalili/searoute-py">searoute</Ext> package.{lic('eurostat-searoute') ? ` Licences: ${lic('eurostat-searoute')}.` : ''}
        </li>
        <li>
          <b>Trade flows.</b> BACI, CEPII{st?.baciVersion ? `, version ${st.baciVersion}` : ''}. Reference: Gaulier, G. and Zignago, S. (2010) BACI:
          International Trade Database at the Product-Level. The 1994-2007 Version. CEPII Working Paper, N°2010-23. Licence: Etalab Open Licence 2.0.
        </li>
        <li>
          <b>Cocoa production.</b> FAO. FAOSTAT: Crops and livestock products.{st?.faoChecked ? ` Last checked on ${longDate(st.faoChecked)}.` : ''}{' '}
          <Ext href={sources.value.faostat?.url ?? 'https://www.fao.org/faostat/en/data/QCL'}>{sources.value.faostat?.url ?? 'https://www.fao.org/faostat/en/data/QCL'}</Ext>.
          Licence: CC BY 4.0.
        </li>
        <li>
          <b>Monthly prices.</b> World Bank Commodity Price Data (The Pink Sheet), World Bank{lic('wb-pink') ? `, ${lic('wb-pink')}` : ''}.
        </li>
        <li>
          <b>Chokepoint traffic.</b> IMF PortWatch, <Ext href="https://portwatch.imf.org/">portwatch.imf.org</Ext>
          {lic('portwatch') ? `. ${lic('portwatch')}` : ''}.
        </li>
        <li>
          <b>Wikipedia.</b> Figures and notes credited to Wikipedia (infrastructure assets, companies, events, vessel classes and chokepoint
          limits) are adapted from English Wikipedia articles, written by Wikipedia contributors and licensed{' '}
          <Ext href="https://creativecommons.org/licenses/by-sa/4.0/">CC BY-SA 4.0</Ext>. Changes were made: passages were shortened and
          rewritten, figures converted to the atlas's units, and entries combined with other sources. Each entry links its article, and the files
          that contain this material are shared under the same licence (see <Ext href={`${DOC}NOTICE.md`}>NOTICE.md</Ext>).
        </li>
        <li>
          <b>OpenStreetMap.</b> © <Ext href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</Ext>. The coordinates of a
          few infrastructure assets are taken from OpenStreetMap, available under the{' '}
          <Ext href="https://opendatacommons.org/licenses/odbl/1-0/">Open Database License 1.0</Ext> (the assets are listed in{' '}
          <Ext href={`${DOC}NOTICE.md`}>NOTICE.md</Ext>).
        </li>
        <li>
          <b>Baltic Exchange.</b> Commodity Flows Atlas is not affiliated with, sponsored by or endorsed by the Baltic Exchange. Benchmark routes
          are described from public route definitions. No Baltic Exchange index value or rate assessment is shown.
        </li>
        <li>
          <b>FRED.</b> This product uses the FRED® API but is not endorsed or certified by the Federal Reserve Bank of St. Louis. The deep-sea
          freight producer price index it provides is a U.S. Bureau of Labor Statistics series.
        </li>
        <li>
          <b>No endorsement.</b> The use of data from the U.S. Bureau of Labor Statistics, the International Monetary Fund, the Food and
          Agriculture Organization of the United Nations or any other publisher listed here does not mean that they endorse, sponsor or approve
          the atlas.
        </li>
      </ul>
    </>
  );
}

// ---------------------------------------------------------------- data freshness

const HEALTH_LABEL: Record<Freshness['health'], string> = {
  ok: 'On time',
  stale: 'Stale',
  failing: 'Check failing',
  manual: 'Checked by hand',
  unconfigured: 'Not configured',
};
const HEALTH_BADGE: Record<Freshness['health'], string> = { ok: 'badge-ok', stale: 'badge-warn', failing: 'badge-warn', manual: '', unconfigured: '' };

function FreshnessTabView(props: { status: StatusView | null; failed: boolean; vintages: Record<string, string> }) {
  const st = props.status;
  const name = (id: string) => sources.value[id]?.name ?? id;
  return (
    <>
      <p>
        Scheduled jobs check each source and rebuild the data: prices and chokepoint traffic every week, the annual statistics every month (FAOSTAT and WNA about every 80 days). A
        source is marked stale when its last check, or its latest data, is later than that rhythm allows.
      </p>
      {props.failed ? (
        <p class="about-empty">The update status could not be loaded. Try again later.</p>
      ) : !st ? (
        <Skeleton lines={5} />
      ) : st.rows.length === 0 ? (
        <p class="about-empty">No scheduled job has reported yet.</p>
      ) : (
        <>
          <table class="about-table about-fresh">
            <thead>
              <tr>
                <th scope="col">Source</th>
                <th scope="col">Data to</th>
                <th scope="col">Last checked</th>
                <th scope="col">Status</th>
              </tr>
            </thead>
            <tbody>
              {st.rows.map((r) => {
                const shown = r.sources.map((s) => props.vintages[s]).filter(Boolean);
                // annual sources: the year the published figures carry, read from the figures themselves
                const to = r.dataTo ?? (shown.length ? [...new Set(shown.map((v) => fmtDate(v)))].join(', ') : null);
                return (
                  <tr key={r.key} data-source={r.key} data-health={r.health}>
                    <th scope="row">
                      {r.sources.map((s) => (
                        <span class="about-src-name" key={s}>
                          {name(s)}
                        </span>
                      ))}
                    </th>
                    <td data-label="Data to">
                      <span class="num">{to ?? 'Not dated'}</span>
                      {r.release && <small>{r.release}</small>}
                    </td>
                    <td data-label="Last checked">
                      <span class="num">{r.checked ? fmtDate(r.checked) : 'Never'}</span>
                    </td>
                    <td data-label="Status">
                      <span class={`badge ${HEALTH_BADGE[r.health]}`}>{HEALTH_LABEL[r.health]}</span>
                      {r.why && <small>{r.why}</small>}
                      {r.retrying && <small>The last check did not complete. The site keeps the last good data.</small>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p class="about-foot-note">
            {st.rebuilt && <>Commodity pages and country profiles rebuilt on {fmtDate(st.rebuilt)}. </>}
            {st.updated && <>Status recorded on {fmtDate(st.updated)}. </>}
            Sources without a scheduled job (infrastructure, companies, vessel classes, events) are entered by hand: their year is shown with each
            figure.
          </p>
        </>
      )}
      {(BUILD.commit || BUILD.date) && (
        <p class="about-foot-note">
          Site build:{' '}
          {BUILD.commit && (
            <>
              commit{' '}
              <Ext href={`${REPO}/commit/${BUILD.commit}`}>
                <span class="num">{BUILD.commit}</span>
              </Ext>
            </>
          )}
          {BUILD.commit && BUILD.date && ', '}
          {BUILD.date && fmtDate(BUILD.date)}.
        </p>
      )}
    </>
  );
}

// ---------------------------------------------------------------- method

function MethodTabView() {
  return (
    <>
      <h3>How the figures are made</h3>
      <ul>
        <li>Trade flows between countries come from CEPII BACI, which reconciles the customs declarations of exporters and importers. Quantities are in tonnes.</li>
        <li>
          Each flow is classed from coastlines, land borders and lists of exceptions given in the methodology: by sea, by sea through a foreign port
          (for a landlocked country), by sea and overland when the split is not known, or overland. Only the first two count as seaborne.
        </li>
        <li>
          Sea lanes and benchmark routes follow the shortest path on Eurostat's SeaRoute network between typical ports, an Atlas assumption, and keep
          a vessel class out of the canals and straits it cannot use. Where nothing decides between several coasts or passages, the lane lists them.
          Distances and laden days are computed, not measured.
        </li>
        <li>The vessel classes shown on a lane are the typical ones for the cargo and the ports. They are not measured shares.</li>
        <li>
          Figures computed by the atlas, such as route and chokepoint shares, are labelled "Atlas estimate". So is a tonnage that customs data lack and
          the atlas computed from the declared value; it is shown to two significant digits.
        </li>
        <li>When sources disagree, the official or primary source is shown and the difference is noted.</li>
      </ul>
      <h3>Known limits</h3>
      <ul>
        <li>Customs codes do not separate thermal from metallurgical coal, and the trade series has a single code for all refined petroleum products.</li>
        <li>Origins are as declared. Crude from sanctioned origins may appear under another origin or not be recorded; see the note on each lane.</li>
        <li>Pipeline gas tonnage in customs data is often estimated from value and can be far too low.</li>
        <li>Chokepoint shares computed by the atlas are an Atlas estimate in two figures. {ESTIMATE_DEFINITION}</li>
        <li>Infrastructure is a selection of major mines, fields, refineries, terminals, pipelines and ports, not a complete register.</li>
      </ul>
      <h3>Read more</h3>
      <ul class="about-links">
        <li>
          <Ext href={`${DOC}METHODOLOGY.md`}>Methodology</Ext>
          <small>Every rule and assumption, in full</small>
        </li>
        <li>
          <Ext href={`${DOC}DATA_SOURCES.md`}>Data sources</Ext>
          <small>How each source is fetched and what it is used for</small>
        </li>
        <li>
          <Ext href={REPO}>Source code and data</Ext>
          <small>The repository on GitHub</small>
        </li>
        <li>
          <Ext href={`${REPO}/issues`}>Report an error</Ext>
          <small>Open an issue on GitHub</small>
        </li>
      </ul>
    </>
  );
}

// ---------------------------------------------------------------- third-party notices

// Licence and copyright line of each bundled package, as stated in its own LICENSE file.
const THIRD_PARTY: { name: string; url: string; licence: string; holder: string }[] = [
  { name: 'MapLibre GL JS', url: 'https://github.com/maplibre/maplibre-gl-js', licence: 'BSD 3-Clause', holder: 'MapLibre contributors' },
  { name: 'Preact', url: 'https://github.com/preactjs/preact', licence: 'MIT', holder: 'Jason Miller' },
  { name: 'Preact Signals', url: 'https://github.com/preactjs/signals', licence: 'MIT', holder: 'Preact Team' },
  { name: 'uPlot', url: 'https://github.com/leeoniya/uPlot', licence: 'MIT', holder: 'Leon Sorokin' },
  { name: 'topojson-client', url: 'https://github.com/topojson/topojson-client', licence: 'ISC', holder: 'Michael Bostock' },
  { name: 'Inter Tight (font)', url: 'https://github.com/rsms/inter-tight', licence: 'SIL Open Font License 1.1', holder: 'The Inter Project Authors' },
  { name: 'IBM Plex Mono (font)', url: 'https://github.com/IBM/plex', licence: 'SIL Open Font License 1.1', holder: 'IBM Corp.' },
];

function NoticesTabView() {
  return (
    <>
      <h3>Licences of the atlas</h3>
      <ul class="about-terms">
        <li>
          <b>Code:</b> MIT. It covers the source code, not the data files.
        </li>
        <li>
          <b>The atlas's own derived figures</b> (source id <code>atlas</code>, "Atlas estimate"): CC BY 4.0. Credit: "Commodity Flows Atlas".
        </li>
        <li>
          <b>Third-party data:</b> each dataset keeps the licence of its source, listed under Sources.
        </li>
        <li>
          <b>Material adapted from Wikipedia:</b> CC BY-SA 4.0, shared under the same licence.
        </li>
      </ul>
      <p>
        Full terms, credits and the list of files each licence covers: <Ext href={`${DOC}LICENSE`}>LICENSE</Ext> and{' '}
        <Ext href={`${DOC}NOTICE.md`}>NOTICE.md</Ext> in the repository.
      </p>
      <h3>Libraries and fonts</h3>
      <p>The site is built with these open-source libraries and fonts. The fonts are served from this site through the Fontsource packages.</p>
      <table class="about-table about-third">
        <thead>
          <tr>
            <th scope="col">Component</th>
            <th scope="col">Licence</th>
            <th scope="col">Copyright</th>
          </tr>
        </thead>
        <tbody>
          {THIRD_PARTY.map((t) => (
            <tr key={t.name}>
              <th scope="row">
                <Ext href={t.url}>{t.name}</Ext>
              </th>
              <td data-label="Licence">{t.licence}</td>
              <td data-label="Copyright">{t.holder}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p>
        Full licence texts: <Ext href={`${DOC}THIRD-PARTY-NOTICES.md`}>THIRD-PARTY-NOTICES.md</Ext> in the repository.
      </p>
    </>
  );
}

// ---------------------------------------------------------------- window

export default function AboutDialog() {
  const ref = useRef<HTMLDialogElement>(null);
  const body = useRef<HTMLDivElement>(null);
  const tab = aboutTab.value ?? 'about';
  const [status, setStatus] = useState<StatusView | null>(null);
  const [failed, setFailed] = useState(false);
  const [vintages, setVintages] = useState<Record<string, string>>({});

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    // a modal <dialog> keeps the focus inside and makes the page behind it inert
    if (!d.open) d.showModal();
    d.querySelector<HTMLElement>('[role="tab"][aria-selected="true"]')?.focus();
    let live = true;
    loadStatus().then(
      (s) => live && setStatus(s),
      () => live && setFailed(true),
    );
    loadVintages().then((v) => live && setVintages(v));
    return () => {
      live = false;
      if (d.open) d.close();
    };
  }, []);

  useEffect(() => {
    body.current?.scrollTo(0, 0);
  }, [tab]);

  const onKey = (e: KeyboardEvent) => {
    if (e.key === 'Tab') {
      // wrap at both ends, so the focus never leaves for the browser's own controls
      const stops = [...(ref.current?.querySelectorAll<HTMLElement>('a[href], button, [tabindex="0"]') ?? [])];
      const edge = e.shiftKey ? stops[0] : stops[stops.length - 1];
      if (stops.length && document.activeElement === edge) {
        e.preventDefault();
        (e.shiftKey ? stops[stops.length - 1] : stops[0]).focus();
      }
      return;
    }
    if (e.key !== 'Escape') return;
    // handled here so the panels behind the window stay as they are
    e.preventDefault();
    e.stopPropagation();
    closeAbout();
  };

  const onTabKey = (e: KeyboardEvent) => {
    const i = TABS.findIndex((t) => t.id === tab);
    const to =
      e.key === 'ArrowRight' ? (i + 1) % TABS.length : e.key === 'ArrowLeft' ? (i + TABS.length - 1) % TABS.length : e.key === 'Home' ? 0 : e.key === 'End' ? TABS.length - 1 : -1;
    if (to < 0) return;
    e.preventDefault();
    aboutTab.value = TABS[to].id;
    document.getElementById(`about-tab-${TABS[to].id}`)?.focus();
  };

  return (
    <dialog
      ref={ref}
      class="about"
      aria-labelledby="about-title"
      onKeyDown={onKey}
      onCancel={(e) => {
        e.preventDefault();
        closeAbout();
      }}
      onClose={closeAbout}
      onClick={(e) => {
        // a click on the backdrop lands on the dialog element itself
        if (e.target === ref.current) closeAbout();
      }}
    >
      <div class="about-box">
        <header class="about-head">
          <h2 id="about-title">About Commodity Flows Atlas</h2>
          <button class="about-close" onClick={closeAbout} aria-label="Close">
            <CloseIcon />
          </button>
        </header>
        <div class="about-tabs" role="tablist" aria-label="Sections" onKeyDown={onTabKey}>
          {TABS.map((t) => (
            <button
              key={t.id}
              id={`about-tab-${t.id}`}
              role="tab"
              class="about-tab"
              aria-selected={t.id === tab}
              aria-controls="about-panel"
              tabIndex={t.id === tab ? 0 : -1}
              onClick={() => (aboutTab.value = t.id)}
            >
              {t.label}
            </button>
          ))}
        </div>
        <div class="about-body" id="about-panel" role="tabpanel" aria-labelledby={`about-tab-${tab}`} tabIndex={0} ref={body}>
          {tab === 'about' ? (
            <AboutTabView />
          ) : tab === 'sources' ? (
            <SourcesTabView status={status} vintages={vintages} />
          ) : tab === 'freshness' ? (
            <FreshnessTabView status={status} failed={failed} vintages={vintages} />
          ) : tab === 'method' ? (
            <MethodTabView />
          ) : (
            <NoticesTabView />
          )}
        </div>
        <footer class="about-foot">
          <Ext href={`${REPO}/issues`}>Report an error</Ext>
          <Ext href={`${DOC}METHODOLOGY.md`}>Methodology</Ext>
          <Ext href={REPO}>Source code</Ext>
        </footer>
      </div>
    </dialog>
  );
}
