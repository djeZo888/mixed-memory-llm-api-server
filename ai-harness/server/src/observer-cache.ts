/** Passive, independent observers. A timed-out observer retains its slot until
 * its underlying work settles: an abort-ignoring probe cannot spawn replacements. */
export interface Observation<T> {
  state: "fresh" | "stale" | "unknown";
  value?: T;
  observedAt: number | null;
  ageMs: number | null;
  error: "timeout" | "transport_error" | null;
  inflight: boolean;
}
export class ObserverCache<T> {
  private value?: T;
  private observedAt: number | null = null;
  private failure: Observation<T>["error"] = null;
  private running = false;
  private stopped = false;
  private controller?: AbortController;
  private interval?: NodeJS.Timeout;
  constructor(
    private readonly probe: (signal: AbortSignal) => Promise<T>,
    private readonly options: {
      now?: () => number;
      deadlineMs?: number;
      staleMs?: number;
      pollMs?: number;
      changed?: () => void;
    } = {},
  ) {}
  snapshot(): Observation<T> {
    const ageMs =
      this.observedAt === null
        ? null
        : Math.max(0, this.now() - this.observedAt);
    return {
      state:
        this.observedAt === null
          ? "unknown"
          : ageMs! >= (this.options.staleMs ?? 15000)
            ? "stale"
            : "fresh",
      value: this.value,
      observedAt: this.observedAt,
      ageMs,
      error: this.failure,
      inflight: this.running,
    };
  }
  private now() {
    return (this.options.now ?? performance.now.bind(performance))();
  }
  async poll(): Promise<void> {
    if (this.running || this.stopped) return;
    this.running = true;
    const controller = (this.controller = new AbortController());
    let timedOut = false;
    let finish!: () => void;
    const bounded = new Promise<void>((resolve) => {
      finish = resolve;
    });
    const timer = setTimeout(() => {
      timedOut = true;
      this.failure = "timeout";
      controller.abort();
      this.options.changed?.();
      finish();
    }, this.options.deadlineMs ?? 2000);
    // The scheduler timer is unref'd; this individual deadline intentionally
    // remains referenced so an awaited offline/one-shot poll always terminates.
    void Promise.resolve()
      .then(() => this.probe(controller.signal))
      .then(
        (value) => {
          if (!timedOut && !this.stopped) {
            this.value = value;
            this.observedAt = this.now();
            this.failure = null;
          }
        },
        () => {
          if (!timedOut && !this.stopped) this.failure = "transport_error";
        },
      )
      .finally(() => {
        clearTimeout(timer);
        this.running = false;
        if (!this.stopped) this.options.changed?.();
        finish();
      });
    await bounded;
  }
  start() {
    if (this.interval || this.stopped) return;
    void this.poll();
    this.interval = setInterval(() => {
      void this.poll();
    }, this.options.pollMs ?? 5000);
    this.interval.unref();
  }
  stop() {
    this.stopped = true;
    clearInterval(this.interval);
    this.controller?.abort();
  }
}
