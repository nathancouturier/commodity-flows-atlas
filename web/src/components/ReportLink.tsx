/**
 * A link to GitHub's "Report an error" form, filled in with the page the visitor is on (lib/report.ts).
 * Nothing is requested from GitHub before the click. The address is built again when the visitor acts (pointer, focus,
 * context menu, click), so "Copy link address" gives the page that is shown.
 */
import type { ComponentChildren } from 'preact';
import { selection } from '../lib/store';
import { reportUrl } from '../lib/report';
import { REPO } from '../lib/links';
import { BUILD, RELEASE } from '../lib/status';
import { detailTitle } from '../lib/view';

/** The heading of the open page, else the tab's title without the site's name. */
function pageTitle(): string {
  return detailTitle.peek() ?? document.title.replace(/ · [^·]*$/, '');
}

/** The form's address for the page shown now; `about` is the About window, which names no object. */
export function reportHref(about: boolean): string {
  return reportUrl({
    repo: REPO,
    release: RELEASE,
    build: BUILD.commit,
    href: location.href,
    selection: about ? null : selection.peek(),
    title: about ? 'About window' : pageTitle(),
  });
}

export function ReportLink(props: { about?: boolean; class?: string; label?: string; tip?: string; children: ComponentChildren }) {
  const about = !!props.about;
  const refresh = (e: Event) => {
    (e.currentTarget as HTMLAnchorElement).href = reportHref(about);
  };
  return (
    <a
      class={props.class}
      href={reportHref(about)}
      target="_blank"
      rel="noopener noreferrer"
      aria-label={props.label}
      title={props.tip}
      onPointerEnter={refresh}
      onFocus={refresh}
      onContextMenu={refresh}
      onAuxClick={refresh}
      onClick={refresh}
    >
      {props.children}
    </a>
  );
}
