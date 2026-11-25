/** What the two PortWatch charts share (a chokepoint's weekly transits, a port's weekly traffic): the range buttons and the ship-type colours. */
import { YEAR } from './TimeChart';

export const RANGES = [
  { label: '1Y', seconds: YEAR },
  { label: '3Y', seconds: 3 * YEAR },
  { label: 'All', seconds: null },
];
export const PW_COLORS = { tanker: '#ffb547', dry: '#9db7ff', container: '#c7a3ff', other: '#7d8a99' };
