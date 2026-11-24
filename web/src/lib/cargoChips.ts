/**
 * The label of a cargo chip that stands for one product of a commodity page (package FNCE, review of FNCC; GV7B.4): a lane or a generated
 * route of ammonia, UAN, phosphoric acid or coke carries the page's id ("urea", "met-coal"), and the chip would read "Urea & nitrogen"
 * for a cargo of ammonia. The chip is labelled with the group's own name when the cargo is one group and the page has more than one
 * group, and it still opens the page: the first group of a page is labelled like its siblings (a ferro-chromium route read "Ferro-alloys"
 * where ferro-silicon read "Ferro-silicon"). Pure: the tables are passed in, so that a node test can run the same function on the real
 * tables (src/lib/freight.ts: LANE_GROUPS, GROUP_LABEL).
 */
export type ChipLabels = Record<string, string>;

/**
 * The group that stands for the whole of its page, which keeps the page's name: the coal of the two coal pages (the page is named by the
 * grade, the group is all coal) and the crop of "Rapeseed & canola" (canola is the same seed). Any other group of a page that has several
 * is named: "Urea" on "Urea & nitrogen", "Pig iron" on "Pig iron & DRI", "Bauxite" on "Bauxite & alumina", "Potassium chloride" on "Potash"
 * (the page holds the sulphate too). Decided by reading the groups of the pages of data/commodities/index.json (FNCG).
 */
export const WHOLE_PAGE: Record<string, string> = { 'thermal-coal': 'coal', 'met-coal': 'coal', rapeseed: 'rapeseed' };

/** Labels for the chip of `page` when its cargo is the customs group `group` only, or undefined when the page's own name is right. */
export function groupChipLabels(
  page: string,
  group: string | undefined | null,
  laneGroups: Record<string, string[]>,
  groupLabel: Record<string, string>,
): ChipLabels | undefined {
  if (!group || !groupLabel[group] || (laneGroups[page]?.length ?? 0) < 2 || WHOLE_PAGE[page] === group) return undefined;
  return { [page]: groupLabel[group] };
}

/** The same for a route: its corridor entries all name the same page and the same group (a generated corridor does; a hand-written
 * route that lists several groups or none keeps the page's name). */
export function routeChipLabels(
  corridor: { k: string; g?: string }[] | undefined,
  laneGroups: Record<string, string[]>,
  groupLabel: Record<string, string>,
): ChipLabels | undefined {
  const first = corridor?.[0];
  if (!first || !corridor!.every((c) => c.g && c.g === first.g && c.k === first.k)) return undefined;
  return groupChipLabels(first.k, first.g, laneGroups, groupLabel);
}
