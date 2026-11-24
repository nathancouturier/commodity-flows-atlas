/**
 * The label of a cargo chip that stands for one product of a commodity page (package FNCE, review of FNCC): a lane or a generated
 * route of ammonia, UAN, phosphoric acid or coke carries the page's id ("urea", "met-coal"), and the chip would read "Urea & nitrogen"
 * for a cargo of ammonia. The chip is labelled with the group's own name when the cargo is one group and that group is not the
 * main group of the page (the first group of its lanes: `laneGroups[page][0]`); it still opens the page. Pure: the tables are
 * passed in, so that a node test can run the same function on the real tables (src/lib/freight.ts: LANE_GROUPS, GROUP_LABEL).
 */
export type ChipLabels = Record<string, string>;

/** Labels for the chip of `page` when its cargo is the customs group `group` only, or undefined when the page's own name is right. */
export function groupChipLabels(
  page: string,
  group: string | undefined | null,
  laneGroups: Record<string, string[]>,
  groupLabel: Record<string, string>,
): ChipLabels | undefined {
  if (!group || group === laneGroups[page]?.[0] || !groupLabel[group]) return undefined;
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
