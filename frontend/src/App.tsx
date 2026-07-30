import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { SummaryMetrics } from "./components/SummaryMetrics";
import { FiltersBar } from "./components/FiltersBar";
import { ConsensusTable } from "./components/ConsensusTable";
import { PageControl } from "./components/PageControl";
import { MarketDetailDrawer } from "./components/MarketDetailDrawer";
import { HighlightsStrip } from "./components/HighlightsStrip";
import { MissionSection } from "./components/MissionSection";
import { BotSection } from "./components/BotSection";
import { AccessGate } from "./components/AccessGate";
import { AdminLogin } from "./components/AdminLogin";
import { AdminPanel } from "./components/AdminPanel";
import { ChatWidget } from "./components/ChatWidget";
import { InstagramIcon } from "./components/InstagramIcon";
import { useAuthStatus, useCategories, useConsensus, useHighlights, useSummary } from "./hooks/useApi";
import type { ConsensusFilters, ConsensusRowOut, Variant } from "./lib/types";
import { ApiNotReadyError, logout } from "./lib/api";

export interface SelectedRow {
  row: ConsensusRowOut;
  timeframe: Variant;
  topN: number;
}

const DEFAULT_FILTERS: ConsensusFilters = {
  timeframe: "combined",
  top_n: 25,
  status: "active",
  category: null,
  min_whales: 2,
  min_value: 0,
  search: "",
  page: 1,
};

// A deep link (e.g. from an admin notification) can arrive with ?search= —
// in that case relax the default whale/status filters so the target market
// is actually visible regardless of whale count or active/finished status.
function initialFilters(): ConsensusFilters {
  const search = new URLSearchParams(window.location.search).get("search");
  if (!search) return DEFAULT_FILTERS;
  return { ...DEFAULT_FILTERS, search, min_whales: 0, status: "all" };
}

function Dashboard({ onLoggedOut }: { onLoggedOut: () => void }) {
  const [filters, setFilters] = useState<ConsensusFilters>(initialFilters);
  const [selectedRow, setSelectedRow] = useState<SelectedRow | null>(null);

  const selectFromTable = (row: ConsensusRowOut) =>
    setSelectedRow({ row, timeframe: filters.timeframe, topN: filters.top_n });

  const summaryQuery = useSummary();
  const categoriesQuery = useCategories();
  const consensusQuery = useConsensus(filters);
  const highlightsQuery = useHighlights();

  const notReady =
    summaryQuery.error instanceof ApiNotReadyError || consensusQuery.error instanceof ApiNotReadyError;

  const handleLogout = () => {
    // Flip the UI immediately — don't wait on the network round-trip.
    // The actual cookie-clearing call fires in the background.
    onLoggedOut();
    void logout();
  };

  // Any filter change other than the page itself invalidates the current
  // page of results, so it resets back to page 1.
  const handleFiltersChange = (next: ConsensusFilters) => setFilters({ ...next, page: 1 });
  const handlePageChange = (page: number) => setFilters((f) => ({ ...f, page }));

  return (
    <div className="mx-auto max-w-7xl px-6 py-8">
      {/* Single space-y rhythm controls spacing BETWEEN sections — each
          section's own internal spacing (headings, grids, card gaps) is
          untouched and lives inside that section's own component. */}
      <div className="space-y-8">
        <div className="flex justify-end">
          <a
            href="https://www.instagram.com/whalesharkks"
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-1.5 text-xs text-[var(--text-muted)] transition-colors hover:text-[var(--accent)]"
          >
            <InstagramIcon size={15} />
            @whalesharkks
          </a>
        </div>

        <header className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <img src="/brand/shark-mark-120.png" alt="Whale Sharkks" className="h-10 w-10 object-contain" />
            <div>
              <h1 className="brand-wordmark text-xl text-[var(--text-primary)]">Whale Sharkks</h1>
              <p className="brand-tagline text-[11px] text-[var(--text-muted)]">Where deep pockets swim in the same current.</p>
            </div>
          </div>
          <button
            onClick={handleLogout}
            className="rounded-md border border-[var(--border-hairline)] px-3 py-1.5 text-xs text-[var(--text-muted)] transition-colors hover:border-[var(--accent)] hover:text-[var(--text-primary)]"
          >
            Logout
          </button>
        </header>

        <SummaryMetrics summary={summaryQuery.data} isLoading={summaryQuery.isLoading} />

        <MissionSection />

        {notReady ? (
          <div className="rounded-lg border border-[var(--border-hairline)] bg-[var(--bg-surface)] py-16 text-center text-sm text-[var(--text-secondary)]">
            Initial scan is still in progress — this page will populate automatically once it completes.
          </div>
        ) : (
          <>
            <HighlightsStrip
              highlights={highlightsQuery.data}
              onSelect={(row, timeframe, topN) => setSelectedRow({ row, timeframe, topN })}
            />

            <BotSection />

            <FiltersBar filters={filters} onChange={handleFiltersChange} categories={categoriesQuery.data ?? []} />

            <ConsensusTable
              rows={consensusQuery.data?.items ?? []}
              isLoading={consensusQuery.isLoading}
              onSelectRow={selectFromTable}
            />

            <PageControl
              page={consensusQuery.data?.page ?? 1}
              totalPages={consensusQuery.data?.total_pages ?? 1}
              onChange={handlePageChange}
            />
          </>
        )}

        <footer className="text-center">
          <a href="/admin" className="text-xs text-[var(--text-muted)] hover:text-[var(--text-secondary)]">
            Admin
          </a>
          <p className="mx-auto mt-4 max-w-2xl text-[11px] leading-relaxed text-[var(--text-muted)] opacity-70">
            Whale ratings, consensus scores, "Data-backed lean" text, and all other picks, labels, and commentary
            on this site are Whale Sharkks' own methodology applied to public data, offered for informational and
            entertainment purposes only. They are opinions open to interpretation, not statements of fact, not
            predictions of any market's or event's real-world outcome, and not financial or investment advice.
            Nothing on this site, including KrillBot's simulated trades, should be relied upon to make trading or
            wagering decisions.
          </p>
        </footer>
      </div>

      <MarketDetailDrawer selected={selectedRow} onClose={() => setSelectedRow(null)} />
      <ChatWidget />
    </div>
  );
}

function DashboardRoute() {
  const authQuery = useAuthStatus();
  const qc = useQueryClient();

  if (authQuery.isLoading) return null;
  if (!authQuery.data?.visitor) {
    return <AccessGate onUnlocked={() => qc.invalidateQueries({ queryKey: ["auth-status"] })} />;
  }
  return (
    <Dashboard
      onLoggedOut={() => qc.setQueryData(["auth-status"], { visitor: false, admin: false })}
    />
  );
}

function AdminRoute() {
  const authQuery = useAuthStatus();
  const qc = useQueryClient();

  if (authQuery.isLoading) return null;
  if (!authQuery.data?.admin) {
    return <AdminLogin onLoggedIn={() => qc.invalidateQueries({ queryKey: ["auth-status"] })} />;
  }
  return (
    <AdminPanel
      onLoggedOut={() => qc.setQueryData(["auth-status"], (prev: { visitor: boolean; admin: boolean } | undefined) => ({ visitor: prev?.visitor ?? false, admin: false }))}
    />
  );
}

function App() {
  const isAdminRoute = window.location.pathname.startsWith("/admin");
  return isAdminRoute ? <AdminRoute /> : <DashboardRoute />;
}

export default App;
