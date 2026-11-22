/** Fallback view for selection kinds whose dedicated view is not built yet. */
import type { Selection } from '../../lib/store';
import { Placeholder } from '../ui';

export default function GenericView({ sel }: { sel: Selection }) {
  return (
    <>
      <div class="detail-head">
        <div class="detail-kicker">{sel.kind}</div>
        <h2 class="detail-title">{sel.id}</h2>
      </div>
      <div class="panel-scroll">
        <Placeholder>Details for this item arrive in a later release.</Placeholder>
      </div>
    </>
  );
}
