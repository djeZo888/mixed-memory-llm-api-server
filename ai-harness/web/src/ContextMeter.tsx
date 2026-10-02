import { CONTEXT_LIMIT, type Context } from './types';
const number = new Intl.NumberFormat('en-US');
export function ContextMeter({ context }: { context?: Context }) {
  const known =
    typeof context?.used === 'number' && Number.isFinite(context.used) && context.used >= 0;
  const percent = known ? (context!.used! / CONTEXT_LIMIT) * 100 : null;
  const fresh = known && context?.used === 0 && context.source === 'empty' && !context.stale;
  const kind = fresh ? 'New conversation' : context?.estimated ? 'Estimated' : 'Measured';
  const percentText = percent === 0 ? '0' : percent?.toFixed(1);
  return (
    <div
      className={`context-meter ${context?.stale ? 'is-stale' : ''}`}
      aria-label="Context occupancy"
    >
      <details className="context-details">
        <summary className="context-label">
          <span>
            {known ? (fresh ? kind : `${kind} context`) : 'Context unavailable'}
            {context?.stale ? ' · stale' : ''}
          </span>
        </summary>
        <span className="context-numbers">
          {known
            ? `${number.format(context!.used!)} / ${number.format(CONTEXT_LIMIT)} tokens · ${percentText}%`
            : `Unknown used / ${number.format(CONTEXT_LIMIT)} tokens`}
        </span>
        <span className="context-note">
          {fresh
            ? 'No turns yet. '
            : context?.estimated && known
              ? 'Approximate server estimate. '
              : ''}
          Input and output share this window.
          {context?.stale
            ? known
              ? ' Last reported value; awaiting an update.'
              : ' Awaiting an update.'
            : ''}
        </span>
      </details>
      {known ? (
        <div
          className="meter"
          role="meter"
          aria-label={`${kind} context${context?.stale ? ', stale' : ''}`}
          aria-valuenow={Math.min(context!.used!, CONTEXT_LIMIT)}
          aria-valuemin={0}
          aria-valuemax={CONTEXT_LIMIT}
          aria-valuetext={`${number.format(context!.used!)} tokens, ${percentText} percent${context?.stale ? ', stale' : ''}`}
        >
          <span style={{ width: `${Math.min(percent!, 100)}%` }} />
        </div>
      ) : (
        <div className="meter unknown" />
      )}
    </div>
  );
}
