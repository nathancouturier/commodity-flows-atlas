/** The ports of a route on the route page, each a link to its asset page when the route names the asset. */
import { Fragment } from 'preact';
import type { InfraType } from '../../types';
import { select } from '../../lib/store';
import '../../styles/infra.css';

/**
 * The ports of a route, each a link to its asset page when the route names the asset (`assets`, written by
 * pipeline/infrastructure/route_assets.py): "Primorsk, Ust-Luga".
 */
export function RoutePorts({ ports, assets }: { ports: string[]; assets?: (string | null)[] }) {
  return (
    <>
      {ports.map((name, i) => {
        const a = assets?.[i];
        const at = a ? a.indexOf(':') : -1;
        return (
          <Fragment key={`${name}${i}`}>
            {i > 0 && ', '}
            {a && at > 0 ? (
              <button class="port-link" title={`Open the asset page of ${name}`} onClick={() => select({ kind: 'infra', id: a.slice(at + 1), layer: a.slice(0, at) as InfraType })}>
                {name}
              </button>
            ) : (
              name
            )}
          </Fragment>
        );
      })}
    </>
  );
}
