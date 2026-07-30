import type { SummaryOut } from "../lib/types";
import { formatCompactCurrency, formatCompactNumber, formatRelativeTime } from "../lib/format";

interface Tile {
  label: string;
  value: string;
  accent?: boolean;
}

function StatTile({ label, value, accent }: Tile) {
  return (
    <div className="rounded-lg border border-[var(--border-hairline)] bg-[var(--bg-surface)] px-4 py-3">
      <div className="text-xs text-[var(--text-muted)]">{label}</div>
      <div className={`mt-1 text-2xl font-semibold ${accent ? "text-[var(--accent)]" : "text-[var(--text-primary)]"}`}>
        {value}
      </div>
    </div>
  );
}

export function SummaryMetrics({ summary, isLoading }: { summary: SummaryOut | undefined; isLoading: boolean }) {
  const tiles: Tile[] = [
    { label: "Tracked traders", value: summary ? formatCompactNumber(summary.tracked_traders) : "—" },
    { label: "Active positions", value: summary ? formatCompactNumber(summary.active_positions) : "—" },
    { label: "Consensus markets", value: summary ? formatCompactNumber(summary.consensus_markets) : "—", accent: true },
    { label: "Total whale exposure", value: summary ? formatCompactCurrency(summary.total_whale_exposure) : "—" },
    {
      label: "Last scan",
      value: summary ? formatRelativeTime(summary.last_refresh_at) : isLoading ? "loading…" : "—",
    },
  ];

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
      {tiles.map((tile) => (
        <StatTile key={tile.label} {...tile} />
      ))}
    </div>
  );
}
