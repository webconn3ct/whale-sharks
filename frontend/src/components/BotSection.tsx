import { useState } from "react";
import type { BotPositionOut, BotStateOut, BotTimeframe } from "../lib/types";
import { formatCurrency, formatPercent, formatProbability } from "../lib/format";
import { useBotPositions, useBotState } from "../hooks/useApi";
import { KrillIcon } from "./KrillIcon";
import { PageControl } from "./PageControl";

const TIMEFRAME_OPTIONS: { value: BotTimeframe; label: string }[] = [
  { value: "day", label: "Daily" },
  { value: "week", label: "Weekly" },
  { value: "all_time", label: "All time" },
];

function StatTile({ label, value, tone }: { label: string; value: string; tone?: "good" | "critical" | "accent" }) {
  const color =
    tone === "good"
      ? "text-[var(--good)]"
      : tone === "critical"
        ? "text-[var(--critical)]"
        : tone === "accent"
          ? "text-[var(--accent)]"
          : "text-[var(--text-primary)]";
  return (
    <div className="rounded-lg border border-[var(--border-hairline)] bg-[var(--bg-surface)] px-4 py-3">
      <div className="text-xs text-[var(--text-muted)]">{label}</div>
      <div className={`mt-1 text-2xl font-semibold ${color}`}>{value}</div>
    </div>
  );
}

function PositionRow({ position }: { position: BotPositionOut }) {
  const isOpen = position.status === "open";
  const markPrice = isOpen ? position.current_price ?? position.entry_price : position.exit_price ?? position.entry_price;
  const pnl = isOpen ? position.shares * markPrice - position.stake : position.realized_pnl ?? 0;
  const isPositive = pnl >= 0;

  return (
    <tr className="border-b border-[var(--border-hairline)] last:border-b-0">
      <td className="px-3 py-2.5">
        <div className="max-w-xs truncate font-medium text-[var(--text-primary)]" title={position.market_title}>
          {position.market_title || "Untitled market"}
        </div>
        <div className="text-xs text-[var(--text-muted)]">{position.outcome_label}</div>
      </td>
      <td className="px-3 py-2.5 text-right tabular-nums">{formatCurrency(position.stake)}</td>
      <td className="px-3 py-2.5 text-right tabular-nums text-[var(--text-secondary)]">
        {formatProbability(position.entry_price)}
        {!isOpen && `/${formatProbability(position.exit_price ?? position.entry_price)}`}
      </td>
      <td className="px-3 py-2.5 text-right" style={{ color: isPositive ? "var(--good)" : "var(--critical)" }}>
        <div className="tabular-nums font-medium">
          {isPositive ? "+" : ""}
          {formatCurrency(pnl)}
        </div>
      </td>
      <td className="px-3 py-2.5 text-right text-xs text-[var(--text-muted)]">
        {isOpen ? (
          <span className="rounded border border-[var(--accent)] px-1.5 py-0.5 text-[var(--accent)]">open</span>
        ) : (
          <span className="rounded border border-[var(--border-hairline)] px-1.5 py-0.5">
            {position.exit_reason?.replace("_", " ") ?? "closed"}
          </span>
        )}
      </td>
    </tr>
  );
}

function BotSummary({ state }: { state: BotStateOut | undefined }) {
  if (!state) {
    return <div className="py-8 text-center text-sm text-[var(--text-muted)]">Loading bot status…</div>;
  }
  const returnPct = state.percent_return * 100;
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      <StatTile label="Total value" value={formatCurrency(state.total_value)} tone="accent" />
      <StatTile
        label={`Return since $${Math.round(state.starting_balance)} start`}
        value={`${returnPct >= 0 ? "+" : ""}${formatPercent(returnPct)}`}
        tone={returnPct >= 0 ? "good" : "critical"}
      />
      <StatTile label="Cash on hand" value={formatCurrency(state.cash_balance)} />
      <StatTile label="Open positions" value={String(state.open_positions_count)} />
    </div>
  );
}

export function BotSection() {
  const [tab, setTab] = useState<"open" | "closed">("open");
  const [timeframe, setTimeframe] = useState<BotTimeframe>("day");
  const [page, setPage] = useState(1);
  const stateQuery = useBotState();
  const positionsQuery = useBotPositions(tab, timeframe, page);

  const changeTab = (next: "open" | "closed") => {
    setTab(next);
    setPage(1);
  };
  const changeTimeframe = (next: BotTimeframe) => {
    setTimeframe(next);
    setPage(1);
  };

  return (
    <div className="rounded-lg border border-[var(--border-hairline)] bg-[var(--bg-page)] p-4">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <h2 className="flex items-center gap-1.5 text-sm font-semibold text-[var(--text-primary)]">
            <KrillIcon size={18} />
            KrillBot
          </h2>
          <p className="text-xs text-[var(--text-muted)]">
            Our simulated trading bot — testing the whale-consensus strategy live with a hypothetical $
            {stateQuery.data ? Math.round(stateQuery.data.starting_balance) : 1000}. Not real money, not investment
            advice.
          </p>
        </div>
      </div>

      <BotSummary state={stateQuery.data} />

      <div className="mt-4">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <div className="flex gap-2">
            <button
              onClick={() => changeTab("open")}
              className={`rounded-md px-3 py-1 text-xs font-medium ${
                tab === "open"
                  ? "bg-[var(--accent)] text-white"
                  : "border border-[var(--border-hairline)] text-[var(--text-secondary)]"
              }`}
            >
              Open positions
            </button>
            <button
              onClick={() => changeTab("closed")}
              className={`rounded-md px-3 py-1 text-xs font-medium ${
                tab === "closed"
                  ? "bg-[var(--accent)] text-white"
                  : "border border-[var(--border-hairline)] text-[var(--text-secondary)]"
              }`}
            >
              Trade history
            </button>
          </div>
          {tab === "closed" && (
            <select
              value={timeframe}
              onChange={(e) => changeTimeframe(e.target.value as BotTimeframe)}
              className="rounded-md border border-[var(--border-hairline)] bg-[var(--bg-surface)] px-2 py-1 text-xs text-[var(--text-secondary)] focus:border-[var(--accent)] focus:outline-none"
            >
              {TIMEFRAME_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          )}
        </div>

        {positionsQuery.isLoading ? (
          <div className="py-8 text-center text-sm text-[var(--text-muted)]">Loading…</div>
        ) : (positionsQuery.data?.items ?? []).length === 0 ? (
          <div className="py-8 text-center text-sm text-[var(--text-muted)]">
            {tab === "open" ? "No open positions right now." : "No closed trades in this window."}
          </div>
        ) : (
          <>
            <div className="overflow-x-auto rounded-lg border border-[var(--border-hairline)]">
              <table className="w-full border-collapse text-sm">
                <thead>
                  <tr className="border-b border-[var(--border-hairline)] bg-[var(--bg-surface)] text-left text-xs uppercase tracking-wide text-[var(--text-muted)]">
                    <th className="px-3 py-2.5">Market</th>
                    <th className="px-3 py-2.5 text-right">Stake</th>
                    <th className="px-3 py-2.5 text-right">Entry/Exit</th>
                    <th className="px-3 py-2.5 text-right">P/L</th>
                    <th className="px-3 py-2.5 text-right">Status</th>
                  </tr>
                </thead>
                <tbody className="bg-[var(--bg-surface)]">
                  {(positionsQuery.data?.items ?? []).map((p) => (
                    <PositionRow key={p.id} position={p} />
                  ))}
                </tbody>
              </table>
            </div>
            <PageControl
              page={positionsQuery.data?.page ?? 1}
              totalPages={positionsQuery.data?.total_pages ?? 1}
              onChange={setPage}
            />
          </>
        )}
      </div>
    </div>
  );
}
