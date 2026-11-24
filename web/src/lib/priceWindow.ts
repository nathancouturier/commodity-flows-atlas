/** The window of years of the price drawer when a series is swapped for another (nominal and real prices): kept or opened afresh. */
export type PriceWin = { min: number; max: number };

/** The series (first and last time, in seconds) covers the window in view, to a day: the visitor's window stays. */
export const seriesCovers = (w: PriceWin, xMin: number, xMax: number, day = 86400): boolean => w.min >= xMin - day && w.max <= xMax + day;
