/** The row of a ranked table that holds what the table's total has beyond the rows listed (page, tooltip and CSV). */
type GapTable = { shareOf?: string; norank?: boolean; scope?: string };

/** A table with its own total (`shareOf`: "Australia's exports") has one name for the row on the page and in the CSV; a world table keeps the two it had. */
export const gapLabel = (data: GapTable, csv = false): string =>
  data.shareOf ? 'Countries not listed' : !csv && data.norank && data.scope !== 'EU' ? 'Countries not listed' : 'Not given by country';

/** The tooltip of the row: the reason of a world table is places and regions the source does not give as a country; a table with its own total lists rows only. */
export const gapTitle = (data: GapTable, totalWord: string, other: boolean): string => {
  const minus = `${other ? ' and the source\'s "Other countries" line' : ''}`;
  return data.shareOf
    ? `The total minus the rows listed${minus}: the part of it that the table does not list by country, and rounding`
    : `The ${totalWord} minus the countries listed${minus}: places and regions the source does not give as a country of the atlas, and rounding`;
};
