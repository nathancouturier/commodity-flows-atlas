/**
 * Opens and closes the About window. The window itself (AboutDialog: about, sources and licences,
 * data freshness, quality, method, third-party notices) is a separate chunk, loaded the first time it opens.
 */
import type { ComponentType } from 'preact';
import { useEffect, useState } from 'preact/hooks';
import { signal } from '@preact/signals';

export type AboutTab = 'about' | 'sources' | 'freshness' | 'quality' | 'method' | 'notices';

/** Tab shown in the About window; null = window closed. */
export const aboutTab = signal<AboutTab | null>(null);

let opener: HTMLElement | null = null;

/** Open the window on a tab. `from` is the control that gets the focus back on close. */
export function openAbout(tab: AboutTab = 'about', from?: HTMLElement | null) {
  const el = from ?? document.activeElement;
  opener = el instanceof HTMLElement && el !== document.body ? el : null;
  aboutTab.value = tab;
}

export function closeAbout() {
  if (aboutTab.value === null) return;
  aboutTab.value = null;
  const el = opener;
  opener = null;
  if (el && el.isConnected) requestAnimationFrame(() => el.focus());
}

export function AboutHost() {
  const [Dialog, setDialog] = useState<ComponentType | null>(null);
  const open = aboutTab.value !== null;
  useEffect(() => {
    if (!open || Dialog) return;
    import('./AboutDialog').then(
      (m) => setDialog(() => m.default),
      // the chunk could not be fetched (offline): leave the window closed so the button can try again
      () => (aboutTab.value = null),
    );
  }, [open, Dialog]);
  return open && Dialog ? <Dialog /> : null;
}
