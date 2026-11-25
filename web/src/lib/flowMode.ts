import type { Flow } from '../types';

/** What a flow of mode `mixed` says of its split by mode: the share by sea where a source measures it for the year of the flow, else that it is not known. */
export const mixedModeText = (f: Pick<Flow, 'seaShare' | 'y'>): string =>
  f.seaShare != null ? `sea and overland, ${Math.round(f.seaShare * 100)}% by sea in ${f.y}` : 'sea and overland, split not known';
