import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { SummaryMetrics } from "./components/SummaryMetrics";
import { FiltersBar } from "./components/FiltersBar";
import { ConsensusTable } from "./components/ConsensusTable";
import { MarketDetailDrawer } from "./components/MarketDetailDrawer";
import { HighlightsStrip } from "./components/HighlightsStrip";
import { AccessGate } from "./components/AccessGate";
import { AdminLogin } from "./components/AdminLogin";
import { AdminPanel } from "./components/AdminPanel";
import { ChatWidget } from "./components/ChatWidget";
import { WhaleSharkLogo } from "./components/WhaleSharkLogo";
import { useAuthStatus, useCategories, useConsensus, useHighlights, useSummary } from "./hooks/useApi";
import type { ConsensusFilters, ConsensusRowOut } from "./lib/types";
import { ApiNotReadyError } from "./lib/api";

const DEFAULT_FILTERS: ConsensusFilters = {
  timeframe: "combined",
  top_n: 25,
  status: "active",
  category: null,
  min_whales: 2,
  min_value: 0,
  search: "",
};

function Dashboard() {
  const [filters, setFilters] = useState<ConsensusFilters>(DEFAULT_FILTERS);
  const [selectedRow, setSelectedRow] = useState<ConsensusRowOut | null>(null);

  const summaryQuery = useSummary();
  const categoriesQuery = useCategories();
  const consensusQuery = useConsensus(filters);
  const highlightsQuery = useHighlights();

  const notReady =
    summaryQuery.error instanceof ApiNotReadyError || consensusQuery.error instanceof ApiNotReadyError;

  return (
    <div className="mx-auto max-w-7xl px-6 py-8">
      <header className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <WhaleSharkLogo size={36} className="text-[var(--accent)]" />
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Whale Sharks</h1>
            <p className="text-sm text-[var(--text-muted)]">Where deep pockets swim in the same current.</p>
          </div>
        </div>
      </header>

      <div className="mb-6">
        <SummaryMetrics summary={summaryQuery.data} isLoading={summaryQuery.isLoading} />
      </div>

      {notReady ? (
        <div className="rounded-lg border border-[var(--border-hairline)] bg-[var(--bg-surface)] py-16 text-center text-sm text-[var(--text-secondary)]">
          Initial scan is still in progress — this page will populate automatically once it completes.
        </div>
      ) : (
        <>
          <HighlightsStrip highlights={highlightsQuery.data} onSelect={setSelectedRow} />

          <div className="mb-4">
            <FiltersBar filters={filters} onChange={setFilters} categories={categoriesQuery.data ?? []} />
          </div>

          <ConsensusTable
            rows={consensusQuery.data ?? []}
            isLoading={consensusQuery.isLoading}
            onSelectRow={setSelectedRow}
          />
        </>
      )}

      <MarketDetailDrawer row={selectedRow} onClose={() => setSelectedRow(null)} />
      <ChatWidget />

      <footer className="mt-10 text-center">
        <a href="/admin" className="text-xs text-[var(--text-muted)] hover:text-[var(--text-secondary)]">
          Admin
        </a>
      </footer>
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
  return <Dashboard />;
}

function AdminRoute() {
  const authQuery = useAuthStatus();
  const qc = useQueryClient();

  if (authQuery.isLoading) return null;
  if (!authQuery.data?.admin) {
    return <AdminLogin onLoggedIn={() => qc.invalidateQueries({ queryKey: ["auth-status"] })} />;
  }
  return <AdminPanel onLoggedOut={() => qc.invalidateQueries({ queryKey: ["auth-status"] })} />;
}

function App() {
  const isAdminRoute = window.location.pathname.startsWith("/admin");
  return isAdminRoute ? <AdminRoute /> : <DashboardRoute />;
}

export default App;
