import { useState } from "react";
import type { ConsensusRowOut, HighlightsOut, MatchupOut, TopPickOut, Variant } from "../lib/types";
import { formatCompactCurrency, formatProbability } from "../lib/format";
import { useConsensusLean } from "../hooks/useApi";

type SelectFn = (row: ConsensusRowOut, timeframe: Variant, topN: number) => void;

// Only today's pick joins the top-picks/most-volume cards here — Weekly,
// Monthly, and All-Time are still filterable via the timeframe dropdown below.
const TIMEFRAME_KEYS: { key: Variant; label: string }[] = [{ key: "day", label: "Daily Catch" }];
const HIGHLIGHTS_TOP_N = 25;

// All highlight boxes are grid cells, not fixed-width flex items, so they
// stay evenly sized whether there are 3 top picks or 5 (grid col count
// steps down on narrower screens instead of any box changing width).
const CARD_SIZE = "w-full min-h-[112px]";

function HighlightCard({
  eyebrow,
  row,
  timeframe,
  onSelect,
  emptyLabel = "No data yet",
}: {
  eyebrow: string;
  row: ConsensusRowOut | null | undefined;
  timeframe: Variant;
  onSelect: SelectFn;
  emptyLabel?: string;
}) {
  return (
    <button
      onClick={() => row && onSelect(row, timeframe, HIGHLIGHTS_TOP_N)}
      disabled={!row}
      className={`flex ${CARD_SIZE} flex-col items-start justify-center gap-1 rounded-lg border border-[var(--border-hairline)] bg-[var(--bg-surface)] px-4 py-3 text-left transition-colors hover:bg-[var(--bg-surface-raised)] disabled:cursor-default disabled:hover:bg-[var(--bg-surface)]`}
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
        <span className="text-sm text-[var(--text-muted)]">{emptyLabel}</span>
      )}
    </button>
  );
}

function MatchupSideButton({
  row,
  isLeader,
  onSelect,
}: {
  row: ConsensusRowOut;
  isLeader: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      onClick={onSelect}
      className={
        "flex-1 rounded border px-2 py-1.5 text-left transition-colors hover:bg-[var(--bg-surface-raised)] " +
        (isLeader ? "border-[var(--accent)]" : "border-[var(--border-hairline)]")
      }
    >
      <div className={"text-xs font-medium " + (isLeader ? "text-[var(--accent)]" : "text-[var(--text-secondary)]")}>
        {row.outcome_label}
      </div>
      <div className="text-xs text-[var(--text-muted)]">{row.whale_count} whales</div>
    </button>
  );
}

function MatchupCard({
  eyebrow,
  matchup,
  onSelect,
}: {
  eyebrow: string;
  matchup: MatchupOut;
  onSelect: SelectFn;
}) {
  const [reasoningRequested, setReasoningRequested] = useState(false);
  // Only fires once the visitor actually asks for it — the lean used to be
  // generated for every top-pick card on every scan cycle regardless of
  // whether anyone looked, which burned API calls for nothing.
  const leanQuery = useConsensusLean(reasoningRequested ? matchup.leader.id : null, "combined", HIGHLIGHTS_TOP_N);

  return (
    <div className={`flex ${CARD_SIZE} flex-col justify-center gap-2 rounded-lg border border-[var(--border-hairline)] bg-[var(--bg-surface)] px-4 py-3 text-left`}>
      <span className="text-xs font-medium uppercase tracking-wide text-[var(--accent)]">{eyebrow} · Matchup</span>
      <span className="truncate text-sm font-medium text-[var(--text-primary)]" title={matchup.leader.market_title}>
        {matchup.leader.market_title || "Untitled market"}
      </span>
      <div className="flex gap-2">
        <MatchupSideButton
          row={matchup.leader}
          isLeader
          onSelect={() => onSelect(matchup.leader, "combined", HIGHLIGHTS_TOP_N)}
        />
        <MatchupSideButton
          row={matchup.other}
          isLeader={false}
          onSelect={() => onSelect(matchup.other, "combined", HIGHLIGHTS_TOP_N)}
        />
      </div>
      {reasoningRequested && (
        <p className="text-xs leading-relaxed text-[var(--text-secondary)]">
          {leanQuery.isLoading ? "Computing…" : leanQuery.data?.reasoning ?? "No insight available for this market."}
        </p>
      )}
      <button
        type="button"
        onClick={() => setReasoningRequested((v) => !v)}
        className="text-left text-xs text-[var(--text-muted)] underline decoration-dotted underline-offset-2 hover:text-[var(--text-secondary)]"
      >
        {reasoningRequested ? "Hide insight" : "What does the data show?"}
      </button>
    </div>
  );
}

function TopPickCard({ pick, index, onSelect }: { pick: TopPickOut; index: number; onSelect: SelectFn }) {
  const eyebrow = `Market #${index + 1}`;
  if (pick.kind === "matchup" && pick.matchup) {
    return <MatchupCard eyebrow={eyebrow} matchup={pick.matchup} onSelect={onSelect} />;
  }
  return <HighlightCard eyebrow={eyebrow} row={pick.single} timeframe="combined" onSelect={onSelect} />;
}

export function HighlightsStrip({
  highlights,
  onSelect,
}: {
  highlights: HighlightsOut | undefined;
  onSelect: SelectFn;
}) {
  if (!highlights) return null;

  return (
    <div>
      <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
        Whale spotlight
      </h2>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-5">
        {highlights.top_picks.map((pick, i) => (
          <TopPickCard key={i} pick={pick} index={i} onSelect={onSelect} />
        ))}
        <HighlightCard eyebrow="Most volume" row={highlights.most_volume} timeframe="combined" onSelect={onSelect} />
        {TIMEFRAME_KEYS.map(({ key, label }) => (
          <HighlightCard
            key={key}
            eyebrow={label}
            row={highlights.by_timeframe[key]}
            timeframe={key}
            onSelect={onSelect}
            emptyLabel="Picking today's catch…"
          />
        ))}
      </div>
    </div>
  );
}
