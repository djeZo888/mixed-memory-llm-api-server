import { useEffect, useState } from 'react';
type Snapshot = {
  model: string;
  provider?: string;
  capacity?: { configured: number | null; allocated: number | null; occupiedTested: number | null };
  configured: boolean;
  state: string;
  availability?: { state: 'available' | 'unavailable' | 'unknown' };
  contextWindow: number | null;
  queued: number;
  requests: { model?: string; state: string; promptTokens?: number; reservedOutput?: number; updatedAt: string }[];
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
  const active = latest && ['active', 'queued', 'running', 'pending'].includes(latest.state);
  if (!active && value.queued === 0) return null;
  return (
    <aside className="frontier-activity" aria-label="Research activity" role="status">
      <small>{latest?.state === 'queued' ? 'Research queued' : 'Research in progress'}
        {value.queued > 0 && ` · ${value.queued} waiting`}
      </small>
    </aside>
  );
}
