/** The tonnage that moves by sea and overland (split not known) is said beside the seaborne figure from this size (Mt): the lane panel and the year note share it. */
export const MIXED_MIN_MT = 0.005;
/** `v` is in the unit of the lane file ("Mt", or "kt" for a group under 1 Mt a year). */
export const mixedShown = (v: number, unit: string): boolean => v >= MIXED_MIN_MT * (unit === 'kt' ? 1000 : 1);
