/** The CSV button of a table or a series, or, where the terms of a source are not known to allow a download, a line that says so. */
import type { ComponentChildren } from 'preact';
import { termsNotConfirmed } from '../lib/csv';

export function CsvAction(props: {
  /** the registry ids of every source the rows rest on */
  sources: string[];
  onClick: (e: MouseEvent & { currentTarget: HTMLButtonElement }) => void;
  title: string;
  children?: ComponentChildren;
  /** the button's classes (default: the one of the tables' action buttons) */
  class?: string;
  disabled?: boolean;
}) {
  const who = termsNotConfirmed(props.sources);
  if (who.length)
    return (
      <span class="muted small no-download" title="The licence of this source states no permission to reuse its data, so the atlas does not offer it as a file">
        No download: terms of {who.join(' and ')} not confirmed
      </span>
    );
  return (
    <button class={props.class ?? 'act-btn'} onClick={props.onClick} title={props.title} disabled={props.disabled}>
      {props.children ?? 'CSV'}
    </button>
  );
}
