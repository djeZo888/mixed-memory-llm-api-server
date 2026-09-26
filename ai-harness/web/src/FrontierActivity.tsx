import { useEffect, useState } from 'react';
type Snapshot = {
  model: string;
  configured: boolean;
  state: string;
  availability?: { state: 'available' | 'unavailable' | 'unknown' };
  contextWindow: number | null;
  queued: number;
  requests: { state: string; promptTokens?: number; reservedOutput?: number; updatedAt: string }[];
};
export function FrontierActivity({ sessionId }: { sessionId: string }) {
  const [value, setValue] = useState<Snapshot | null>(null);
  useEffect(() => {
    let alive = true;
    const controller = new AbortController();
    setValue(null);
    const refresh = async () => {
      try {
        const r = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}/frontier`, {
          signal: controller.signal,
        });
        if (!r.ok) throw Error();
        const v = await r.json();
        if (alive) setValue(v);
      } catch {
        if (alive) setValue(null);
      }
    };
    void refresh();
    const timer = setInterval(() => void refresh(), 3000);
    return () => {
      alive = false;
      clearInterval(timer);
      controller.abort();
    };
  }, [sessionId]);
  if (!value || !value.configured) return null;
  const latest = value.requests[0];
  return (
    <aside className="frontier-activity" aria-label="Frontier child activity">
      <small>
        {value.model} child · backend {value.availability?.state ?? 'unknown'} · lane{' '}
        {value.state} · queue {value.queued}/8 · context{' '}
        {value.contextWindow?.toLocaleString() ?? 'unknown'}
        {latest && (
          <>
            {' '}
            · this chat: {latest.state}
            {latest.promptTokens !== undefined && (
              <>
                {' '}
                · rendered input {latest.promptTokens.toLocaleString()} + output reserve{' '}
                {latest.reservedOutput?.toLocaleString()}
              </>
            )}
          </>
        )}
      </small>
    </aside>
  );
}
