/**
 * The search field of the top bar (a button that opens it over the top of the screen on a phone). One list for the whole
 * atlas: commodities, countries, freight routes (by name and Baltic code), chokepoints, vessel classes, infrastructure
 * assets, the typical ports of the lanes, events and price series, grouped by kind. With nothing typed it lists the kinds
 * with their counts, and a kind opens its whole list: that is the way to every object of the map from the keyboard.
 * The matching and the index are in lib/search.ts, loaded the first time the field gets the focus.
 */
import { useEffect, useMemo, useRef, useState } from 'preact/hooks';
import { signal } from '@preact/signals';
import { TOUCH } from '../lib/format';
import { tokens } from '../lib/searchMatch';
import '../styles/search.css';

type Lib = typeof import('../lib/search');
type Item = import('../lib/search').Item;
type Kind = import('../lib/search').Kind;

let lib: Lib | null = null;
let libPromise: Promise<Lib> | null = null;
function loadLib(): Promise<Lib> {
  libPromise ??= import('../lib/search').then((m) => (lib = m));
  libPromise.catch(() => (libPromise = null));
  return libPromise;
}

/** The phone layout: a button in the top bar, the field over the top of the screen. */
const PHONE = '(max-width: 640px)';
function usePhone(): boolean {
  const [phone, setPhone] = useState(() => matchMedia(PHONE).matches);
  useEffect(() => {
    const mq = matchMedia(PHONE);
    const on = () => setPhone(mq.matches);
    mq.addEventListener('change', on);
    return () => mq.removeEventListener('change', on);
  }, []);
  return phone;
}

/** The phone's search button (in the top bar's tool group) asks the field to open. */
export const searchOverlay = signal(false);

const SearchIcon = () => (
  <svg viewBox="0 0 14 14" aria-hidden="true">
    <circle cx="6" cy="6" r="4.2" fill="none" stroke="currentColor" stroke-width="1.5" />
    <path d="M9.3 9.3l3.2 3.2" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
  </svg>
);

export function SearchButton() {
  return (
    <button class="tool-btn search-tool" aria-haspopup="dialog" aria-label="Search" title="Search the atlas" onClick={() => (searchOverlay.value = true)}>
      <SearchIcon />
    </button>
  );
}

/** One option of the list, in the order the keyboard walks them. */
interface Opt {
  id: string;
  run: () => void;
}

const isEditable = (el: EventTarget | null) => {
  const e = el as HTMLElement | null;
  return !!e && (e.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(e.tagName));
};

export function Search() {
  const phone = usePhone();
  const over = phone && searchOverlay.value;
  const shown = !phone || over;
  const root = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const back = useRef<HTMLElement | null>(null);
  const [items, setItems] = useState<Item[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [query, setQuery] = useState('');
  const [scope, setScope] = useState<Kind | null>(null);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [pairs, setPairs] = useState<{ title: string; items: Item[] } | null>(null);
  const enterWhenReady = useRef(false);

  const start = () => {
    if (items || failed) return;
    loadLib()
      .then((m) => m.loadIndex())
      .then(setItems)
      .catch(() => setFailed(true));
  };

  const close = (giveBack: boolean) => {
    setOpen(false);
    setQuery('');
    setScope(null);
    setActive(0);
    searchOverlay.value = false;
    enterWhenReady.current = false;
    // read before the blur: the field forgets where the focus came from when it loses it
    const to = back.current;
    const el = input.current;
    if (el && document.activeElement === el) el.blur();
    if (giveBack && to?.isConnected) to.focus();
    back.current = null;
  };

  // "/" focuses the field (or opens it over the screen on a phone), unless a field already has the keys
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== '/' || e.ctrlKey || e.metaKey || e.altKey || isEditable(e.target) || document.querySelector('dialog[open]')) return;
      e.preventDefault();
      if (phone) searchOverlay.value = true;
      else {
        back.current = document.activeElement as HTMLElement | null;
        input.current?.focus();
        input.current?.select();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [phone]);

  // the phone's overlay: focus the field as it opens; leaving the phone layout closes it
  useEffect(() => {
    if (!over) return;
    back.current = document.querySelector<HTMLElement>('.search-tool');
    input.current?.focus();
    setOpen(true);
    start();
  }, [over]);
  useEffect(() => {
    if (!phone) searchOverlay.value = false;
  }, [phone]);

  // a country and a commodity typed together: their pages, and the Route finder questions between them
  const combo = useMemo(() => (lib && items && scope === null ? lib.countryAndCommodity(tokens(query), items) : null), [query, items, scope]);
  useEffect(() => {
    setPairs(null);
    if (!combo || !lib) return;
    let live = true;
    const title = `${combo.country.label} and ${combo.commodity.label}`;
    setPairs({ title, items: [combo.country, combo.commodity] });
    lib.finderQuestions(combo.country, combo.commodity).then((q) => live && setPairs({ title, items: [...q, combo.country, combo.commodity] })).catch(() => undefined);
    return () => {
      live = false;
    };
  }, [combo]);

  const groups = useMemo(() => (lib && items ? lib.search(query, items, scope) : []), [query, items, scope]);
  const kinds = useMemo(() => (lib && items && !query.trim() && !scope ? lib.counts(items) : []), [query, items, scope]);
  const scopeInfo = scope && lib ? lib.KINDS.find((k) => k.kind === scope) : null;

  // the options in the order the keyboard walks them
  const { opts, view } = useMemo(() => {
    const opts: Opt[] = [];
    /** One option: its place in the walk is its place in the list, which is what the id and the active index share. */
    const option = (run: () => void, cls: string, body: preact.ComponentChildren, key: string, kind?: string) => {
      const n = opts.length;
      const id = `sr-opt-${n}`;
      opts.push({ id, run });
      return (
        <div key={key} id={id} role="option" class={`sr-opt ${cls}`} aria-selected={n === active} data-k={kind} onClick={run} onMouseMove={(e) => (e.movementX || e.movementY) && setActive(n)}>
          {body}
        </div>
      );
    };
    const row = (it: Item) =>
      option(
        () => {
          it.open();
          close(false);
        },
        '',
        <>
          <span class="sr-main">
            <span class="sr-label">{it.label}</span>
            {it.sub && <span class="sr-sub">{it.sub}</span>}
          </span>
          {it.badge && <span class="sr-badge num">{it.badge}</span>}
        </>,
        it.key,
        it.kind,
      );
    const enter = (k: Kind) => () => {
      setScope(k);
      setActive(0);
      input.current?.focus();
    };
    const rows: preact.ComponentChildren[] = [];
    if (kinds.length) {
      rows.push(
        <div key="kinds" role="group" aria-label="Kinds">
          <div class="sr-head">Browse by kind</div>
          {kinds.map((k) =>
            option(enter(k.kind), 'sr-kind', <><span class="sr-main"><span class="sr-label">{k.label}</span></span><span class="sr-badge num">{k.n}</span></>, k.kind),
          )}
        </div>,
      );
    }
    if (pairs) {
      rows.push(
        <div key="pair" role="group" aria-label={pairs.title}>
          <div class="sr-head">{pairs.title}</div>
          {pairs.items.map(row)}
        </div>,
      );
    }
    for (const g of groups) {
      rows.push(
        <div key={g.kind} role="group" aria-label={g.label}>
          <div class="sr-head">
            {g.label}
            <span class="num">{g.total}</span>
          </div>
          {g.items.map(row)}
          {!scope && g.total > g.items.length && option(enter(g.kind as Kind), 'sr-more', <span class="sr-main"><span class="sr-label">Show all {g.total} in {g.label.toLowerCase()}</span></span>, 'more')}
        </div>,
      );
    }
    return { opts, view: rows };
    // `close` only touches state setters and refs
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [groups, kinds, pairs, scope, active]);

  useEffect(() => {
    if (!enterWhenReady.current || !items) return;
    enterWhenReady.current = false;
    if (opts.length) opts[0].run();
  }, [opts, items]);

  // the active option stays inside the scrolled list
  useEffect(() => {
    const o = opts[active];
    if (o) document.getElementById(o.id)?.scrollIntoView({ block: 'nearest' });
  }, [active, opts.length]);
  useEffect(() => setActive(0), [query, scope, pairs?.items.length]);

  const typing = query.trim().length > 0;
  const message = !items
    ? failed
      ? 'Search could not load its index. Reload the page to try again.'
      : 'Loading the search index…'
    : typing && !groups.length && !pairs
      ? `Nothing matches “${query.trim()}”. Try a country, a port, a route code such as TD3C or a commodity.`
      : scope && !groups.length
        ? 'Nothing in this list matches.'
        : '';
  const status = message || (scope ? `${groups[0]?.total ?? 0} ${scopeInfo?.label.toLowerCase() ?? ''}` : typing ? `${groups.reduce((a, g) => a + g.total, 0)} results` : '');

  const onKey = (e: KeyboardEvent) => {
    if (e.key === 'Escape') {
      e.preventDefault();
      e.stopPropagation();
      close(true);
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (!open) setOpen(true);
      else setActive((a) => Math.min(opts.length - 1, a + 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActive((a) => Math.max(0, a - 1));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      // the index is still loading: the first result opens as soon as there is one
      if (opts[active]) opts[active].run();
      else if (!items && !failed) enterWhenReady.current = true;
    } else if (e.key === 'Backspace' && !query && scope) {
      e.preventDefault();
      setScope(null);
    }
  };

  const listId = 'sr-list';
  return (
    <div class={`search${over ? ' over' : ''}`} ref={root} role="search" onFocusOut={(e) => !root.current?.contains(e.relatedTarget as Node | null) && !over && setOpen(false)}>
      {shown && (
        <>
          {over && <div class="search-backdrop" onClick={() => close(true)} />}
          <div class="search-box glass">
            <SearchIcon />
            {scopeInfo && (
              <button class="sr-chip" onClick={() => { setScope(null); input.current?.focus(); }} aria-label={`${scopeInfo.label}: show all kinds`} title="Back to all kinds">
                {scopeInfo.label}
                <span aria-hidden="true">×</span>
              </button>
            )}
            <input
              ref={input}
              type="text"
              role="combobox"
              aria-label="Search the atlas"
              aria-expanded={open}
              aria-controls={listId}
              aria-autocomplete="list"
              aria-activedescendant={open && opts[active] ? opts[active].id : undefined}
              placeholder={scopeInfo ? `Filter ${scopeInfo.label.toLowerCase()}` : 'Search the atlas'}
              autocomplete="off"
              autocapitalize="off"
              spellcheck={false}
              enterkeyhint="go"
              value={query}
              onFocus={(e) => {
                const from = e.relatedTarget as HTMLElement | null;
                if (!back.current && from && !root.current?.contains(from)) back.current = from;
                setOpen(true);
                start();
              }}
              onBlur={() => {
                if (!over) back.current = null;
              }}
              onInput={(e) => {
                setQuery((e.target as HTMLInputElement).value);
                setOpen(true);
              }}
              onKeyDown={onKey}
            />
            {!TOUCH && !query && !scope && !open && <kbd class="sr-key" aria-hidden="true">/</kbd>}
            {over && (
              <button class="sr-cancel" onClick={() => close(true)}>
                Cancel
              </button>
            )}
          </div>
          <div class={`sr-pop${open ? ' on' : ''}`} onMouseDown={(e) => e.preventDefault()}>
            <div id={listId} role="listbox" aria-label="Search results">
              {view}
            </div>
            {message && <div class="sr-msg">{message}</div>}
            {scope && items && (
              <div class="sr-note">{typing ? 'Matches in this list. ' : 'Type to filter. '}Backspace or × goes back to all kinds.</div>
            )}
          </div>
          <div class="sr-only" role="status" aria-live="polite">
            {open ? status : ''}
          </div>
        </>
      )}
    </div>
  );
}
