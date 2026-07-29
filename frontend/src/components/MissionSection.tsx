export function MissionSection() {
  return (
    <div className="mb-6 rounded-lg border border-[var(--border-hairline)] bg-[var(--bg-surface)] px-5 py-4">
      <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">Our mission</h2>
      <p className="text-sm leading-relaxed text-[var(--text-secondary)]">
        Whale Sharks tracks Polymarket's highest-performing traders in real time and surfaces the markets where
        several of them independently hold the same position — a signal we call whale consensus. Every position
        is weighted by leaderboard rank, trading history, and position size, then re-scored on a fixed 15-minute
        cycle so the dashboard never lags the market. We don't predict outcomes — we quantify where informed
        capital is currently concentrated, and let the data speak for itself. KrillBot, our simulated trading
        bot, exists to test that signal against real results, transparently and without exaggeration.
      </p>
    </div>
  );
}
