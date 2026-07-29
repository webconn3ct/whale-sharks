import type { ConsensusRowOut, HighlightsOut } from "../lib/types";
import { formatCompactCurrency, formatProbability, TIMEFRAME_LABEL } from "../lib/format";

// Only today's pick joins the top-picks/most-volume cards here — Weekly,
// Monthly, and All-Time are still filterable via the timeframe dropdown below.
const TIMEFRAME_KEYS: { key: string; label: string }[] = [{ key: "day", label: TIMEFRAME_LABEL.DAY }];

function HighlightCard({
  eyebrow,
  row,
  onSelect,
}: {
  eyebrow: string;
  row: ConsensusRowOut | null | undefined;
  onSelect: (row: ConsensusRowOut) => void;
}) {
  return (
    <button
      onClick={() => row && onSelect(row)}
      disabled={!row}
      className="flex w-56 shrink-0 flex-col items-start gap-1 rounded-lg border border-[var(--border-hairline)] bg-[var(--bg-surface)] px-4 py-3 text-left transition-colors hover:bg-[var(--bg-surface-raised)] disabled:cursor-default disabled:hover:bg-[var(--bg-surface)]"
    >
      <span className="text-xs font-medium uppercase tracking-wide text-[var(--accent)]">{eyebrow}</span>
      {row ? (
        <>
          <span className="truncate text-sm font-medium text-[var(--text-primary)]" title={row.market_title}>
            {row.market_title || "Untitled market"}
          </span>
          <span className="flex items-center gap-2 text-xs text-[var(--text-muted)]">
            <span className="text-[var(--accent)]">{row.whale_count} whales</span>
            <span>{formatCompactCurrency(row.combined_value)}</span>
            <span>{formatProbability(row.current_price)}</span>
          </span>
        </>
      ) : (
        <span className="text-sm text-[var(--text-muted)]">No data yet</span>
      )}
    </button>
  );
}

export function HighlightsStrip({
  highlights,
  onSelect,
}: {
  highlights: HighlightsOut | undefined;
  onSelect: (row: ConsensusRowOut) => void;
}) {
  if (!highlights) return null;

  return (
    <div className="mb-6">
      <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
        Whale spotlight
      </h2>
      <div className="flex flex-wrap gap-3">
        {highlights.top_picks.map((row, i) => (
          <HighlightCard key={row.id} eyebrow={`Top pick #${i + 1}`} row={row} onSelect={onSelect} />
        ))}
        <HighlightCard eyebrow="Most volume" row={highlights.most_volume} onSelect={onSelect} />
        {TIMEFRAME_KEYS.map(({ key, label }) => (
          <HighlightCard key={key} eyebrow={label} row={highlights.by_timeframe[key]} onSelect={onSelect} />
        ))}
      </div>
    </div>
  );
}
