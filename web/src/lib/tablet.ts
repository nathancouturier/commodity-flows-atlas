import { effect } from '@preact/signals';
import { panelCollapsed, selection } from './store';
import { foldStep, isTabletLayout } from './layoutQueries';

let before: boolean | null = null; // whether the controls were folded before a page folded them

/**
 * On a tablet (761 to 1024 px) the controls column (276 px) and the page column (353 to 372 px) leave 100 to 350 px of
 * map, so a page folds the controls into their Controls button and its closing gives them back. Nothing is stored in
 * the browser: the fold is a signal in memory.
 */
export function startTabletFold() {
  return effect(() => {
    const next = foldStep({
      open: selection.value !== null,
      isTablet: isTabletLayout(),
      before,
      collapsed: panelCollapsed.peek(),
    });
    before = next.before;
    if (next.collapsed !== panelCollapsed.peek()) panelCollapsed.value = next.collapsed;
  });
}
