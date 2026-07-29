import type { HolderOut } from "../lib/types";
import { formatCurrency, formatPercent, formatProbability, truncateWallet, TIMEFRAME_LABEL } from "../lib/format";
import { useConsensusLean } from "../hooks/useApi";
import type { SelectedRow } from "../App";

function HolderRow({ holder }: { holder: HolderOut }) {
  const isPositive = holder.cash_pnl >= 0;
  return (
    <tr className="border-b border-[var(--border-hairline)] last:border-b-0">
      <td className="px-3 py-2.5">
        <div className="font-medium text-[var(--text-primary)]">{holder.username || truncateWallet(holder.wallet)}</div>
        <div className="text-xs text-[var(--text-muted)]">{truncateWallet(holder.wallet)}</div>
      </td>
      <td className="px-3 py-2.5">
        <span className="rounded border border-[var(--border-hairline)] px-1.5 py-0.5 text-xs text-[var(--text-secondary)]">
          {TIMEFRAME_LABEL[holder.best_timeframe]} #{holder.best_rank}
        </span>
      </td>
      <td className="px-3 py-2.5 text-right tabular-nums">{formatCurrency(holder.position_value)}</td>
      <td className="px-3 py-2.5 text-right tabular-nums text-[var(--text-secondary)]">
        {formatProbability(holder.avg_entry_price)}
      </td>
      <td className="px-3 py-2.5 text-right tabular-nums text-[var(--text-secondary)]">
        {formatProbability(holder.current_price)}
      </td>
      <td className="px-3 py-2.5 text-right" style={{ color: isPositive ? "var(--good)" : "var(--critical)" }}>
        <div className="tabular-nums font-medium">
          {isPositive ? "+" : ""}
          {formatCurrency(holder.cash_pnl)}
        </div>
        <div className="tabular-nums text-xs opacity-80">{formatPercent(holder.percent_pnl)}</div>
      </td>
    </tr>
  );
}

function LeanBanner({ selected }: { selected: SelectedRow }) {
  const leanQuery = useConsensusLean(selected.row.id, selected.timeframe, selected.topN);

  return (
    <div className="mt-4 rounded-lg border border-[var(--accent)]/40 bg-[var(--accent)]/10 px-4 py-3">
      <div className="text-xs font-medium uppercase tracking-wide text-[var(--accent)]">Data-backed lean</div>
      {leanQuery.isLoading ? (
        <p className="mt-1 text-sm text-[var(--text-muted)]">Computing…</p>
      ) : (
        <p className="mt-1 text-sm text-[var(--text-primary)]">
          {leanQuery.data?.reasoning ?? "No recommendation available for this market."}
        </p>
      )}
    </div>
  );
}

export function MarketDetailDrawer({
  selected,
  onClose,
}: {
  selected: SelectedRow | null;
  onClose: () => void;
}) {
  if (!selected) return null;
  const row = selected.row;

  const sortedHolders = [...row.holders].sort((a, b) => b.position_value - a.position_value);

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />
      <div className="relative flex h-full w-full max-w-3xl flex-col overflow-y-auto border-l border-[var(--border-hairline)] bg-[var(--bg-page)] p-6 shadow-2xl">
        <button
          onClick={onClose}
          className="absolute right-4 top-4 rounded-md border border-[var(--border-hairline)] px-2 py-1 text-sm text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
        >
          Close
        </button>

        <div className="pr-16">
          <div className="text-xs text-[var(--text-muted)]">{row.category || "Uncategorized"}</div>
          <h2 className="mt-1 text-xl font-semibold text-[var(--text-primary)]">
            {row.market_title || "Untitled market"}
          </h2>
          <div className="mt-2 flex flex-wrap items-center gap-3 text-sm text-[var(--text-secondary)]">
            <span className="rounded border border-[var(--border-hairline)] px-2 py-0.5">{row.outcome_label}</span>
            <span>Probability {formatProbability(row.current_price)}</span>
            <span className="text-[var(--accent)]">{row.whale_count} whales</span>
            <span>{formatCurrency(row.combined_value)} combined</span>
            <span>Score {row.consensus_score.toFixed(0)}</span>
          </div>
          {row.market_slug && (
            <a
              href={`https://polymarket.com/event/${row.event_slug || row.market_slug}`}
              target="_blank"
              rel="noreferrer"
              className="mt-2 inline-block text-sm text-[var(--accent)] hover:underline"
            >
              View on Polymarket ↗
            </a>
          )}

          <LeanBanner selected={selected} />
        </div>

        <div className="mt-6 overflow-x-auto rounded-lg border border-[var(--border-hairline)]">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-[var(--border-hairline)] bg-[var(--bg-surface)] text-left text-xs uppercase tracking-wide text-[var(--text-muted)]">
                <th className="px-3 py-2.5">Trader</th>
                <th className="px-3 py-2.5">Leaderboard</th>
                <th className="px-3 py-2.5 text-right">Position value</th>
                <th className="px-3 py-2.5 text-right">Entry</th>
                <th className="px-3 py-2.5 text-right">Current</th>
                <th className="px-3 py-2.5 text-right">P/L</th>
              </tr>
            </thead>
            <tbody className="bg-[var(--bg-surface)]">
              {sortedHolders.map((h) => (
                <HolderRow key={h.wallet} holder={h} />
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
