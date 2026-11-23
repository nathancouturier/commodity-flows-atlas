/** "Copy link" and "Copy citation", in the header of the detail panel. */
import { useEffect, useRef, useState } from 'preact/hooks';
import { citationOf, copyText } from '../lib/cite';
import { selection } from '../lib/store';
import '../styles/share.css';

type Done = 'link' | 'citation' | 'failed' | null;

const LinkIcon = () => (
  <svg viewBox="0 0 14 14" aria-hidden="true">
    <path d="M6 8a2.4 2.4 0 0 0 3.4 0l2-2A2.4 2.4 0 0 0 8 2.6l-.7.7M8 6a2.4 2.4 0 0 0-3.4 0l-2 2A2.4 2.4 0 0 0 6 11.4l.7-.7" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" />
  </svg>
);
// two filled quotation marks: at 14 px two open strokes read as "ff"
const QuoteIcon = () => (
  <svg viewBox="0 0 14 14" aria-hidden="true">
    <path d="M1.8 10.6V6.5C1.8 4.5 2.9 3.2 4.9 2.8l.3 1.1C4.2 4.3 3.7 4.9 3.7 5.7h1.8v4.9zM7.8 10.6V6.5C7.8 4.5 8.9 3.2 10.9 2.8l.3 1.1c-1 .4-1.5 1-1.5 1.8h1.8v4.9z" fill="currentColor" />
  </svg>
);

const CheckIcon = () => (
  <svg viewBox="0 0 14 14" aria-hidden="true">
    <path d="M2.8 7.4l2.7 2.7 5.7-6" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" />
  </svg>
);

export function DetailActions({ panel }: { panel: { current: HTMLElement | null } }) {
  const [done, setDone] = useState<Done>(null);
  const timer = useRef(0);
  const sel = selection.value;
  const key = sel ? `${sel.kind}:${sel.id}` : '';
  // a new page starts without a "Copied" left from the last one
  useEffect(() => setDone(null), [key]);
  useEffect(() => () => clearTimeout(timer.current), []);
  const copy = async (what: 'link' | 'citation') => {
    const text = what === 'link' ? location.href : panel.current ? citationOf(panel.current) : location.href;
    const ok = await copyText(text);
    setDone(ok ? what : 'failed');
    clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setDone(null), 2200);
  };
  return (
    <div class="detail-actions" role="group" aria-label="Share this page">
      <button class="da-btn" onClick={() => copy('link')} aria-label="Copy link" title="Copy link: the address of this page">
        {done === 'link' ? <CheckIcon /> : <LinkIcon />}
      </button>
      <button class="da-btn" onClick={() => copy('citation')} aria-label="Copy citation" title="Copy citation (the sources of the blocks open on the page)">
        {done === 'citation' ? <CheckIcon /> : <QuoteIcon />}
      </button>
      <span class={`da-tip${done === 'failed' ? ' bad' : ''}`} role="status">
        {done === 'failed' ? 'Could not copy' : done === 'link' ? 'Link copied' : done === 'citation' ? 'Citation copied' : ''}
      </span>
    </div>
  );
}
