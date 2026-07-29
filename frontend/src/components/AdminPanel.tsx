import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  acknowledgeAllWhaleAlerts,
  acknowledgeSupportRequest,
  acknowledgeWhaleAlert,
  adminLogout,
  changeAdminPassword,
  createAccessCode,
  excludeMarket,
  excludeTrader,
  fetchAccessCodes,
  fetchAdminScans,
  fetchExcludedMarkets,
  fetchExcludedTraders,
  fetchLoginStats,
  fetchScoringWeights,
  fetchSupportRequests,
  fetchWhaleAlerts,
  revokeAccessCode,
  triggerRescan,
  unexcludeMarket,
  unexcludeTrader,
  updateScoringWeights,
} from "../lib/api";
import { formatCompactCurrency, formatRelativeTime } from "../lib/format";
import { WhaleSharkLogo } from "./WhaleSharkLogo";

const inputClass =
  "rounded-md border border-[var(--border-hairline)] bg-[var(--bg-page)] px-3 py-2 text-sm text-[var(--text-primary)] focus:border-[var(--accent)] focus:outline-none";
const buttonClass =
  "rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50";
const cardClass = "rounded-lg border border-[var(--border-hairline)] bg-[var(--bg-surface)] p-5";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className={cardClass}>
      <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-[var(--text-muted)]">{title}</h2>
      {children}
    </section>
  );
}

function OperationalControls() {
  const qc = useQueryClient();
  const scansQuery = useQuery({ queryKey: ["admin", "scans"], queryFn: fetchAdminScans, refetchInterval: 15_000 });
  const rescanMutation = useMutation({
    mutationFn: triggerRescan,
    onSuccess: () => setTimeout(() => qc.invalidateQueries({ queryKey: ["admin", "scans"] }), 3000),
  });

  return (
    <Section title="Operational controls">
      <button
        onClick={() => rescanMutation.mutate()}
        disabled={rescanMutation.isPending}
        className={buttonClass}
      >
        {rescanMutation.isPending ? "Starting…" : "Trigger rescan now"}
      </button>
      {rescanMutation.isSuccess && (
        <p className="mt-2 text-sm text-[var(--good)]">Scan started — refreshes below in ~30-60s.</p>
      )}

      <div className="mt-4 overflow-x-auto">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-[var(--border-hairline)] text-left text-xs uppercase text-[var(--text-muted)]">
              <th className="py-2 pr-4">ID</th>
              <th className="py-2 pr-4">Started</th>
              <th className="py-2 pr-4">Status</th>
              <th className="py-2 pr-4">Traders</th>
              <th className="py-2 pr-4">Positions</th>
              <th className="py-2 pr-4">Total value</th>
            </tr>
          </thead>
          <tbody>
            {(scansQuery.data ?? []).map((s) => (
              <tr key={s.id} className="border-b border-[var(--border-hairline)] last:border-b-0">
                <td className="py-2 pr-4 text-[var(--text-muted)]">{s.id}</td>
                <td className="py-2 pr-4">{formatRelativeTime(s.started_at)}</td>
                <td className="py-2 pr-4">
                  <span
                    style={{
                      color:
                        s.status === "completed" ? "var(--good)" : s.status === "failed" ? "var(--critical)" : "var(--warning)",
                    }}
                  >
                    {s.status}
                  </span>
                </td>
                <td className="py-2 pr-4 tabular-nums">{s.traders_count}</td>
                <td className="py-2 pr-4 tabular-nums">{s.positions_count}</td>
                <td className="py-2 pr-4 tabular-nums">{formatCompactCurrency(s.total_value)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Section>
  );
}

function StatTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-[var(--border-hairline)] bg-[var(--bg-page)] px-4 py-3">
      <div className="text-xs text-[var(--text-muted)]">{label}</div>
      <div className="mt-1 text-xl font-semibold text-[var(--text-primary)]">{value}</div>
    </div>
  );
}

function LoginStatsSection() {
  const statsQuery = useQuery({ queryKey: ["admin", "login-stats"], queryFn: fetchLoginStats, refetchInterval: 60_000 });
  const s = statsQuery.data;

  return (
    <Section title="Logins">
      {!s ? (
        <p className="text-sm text-[var(--text-muted)]">Loading…</p>
      ) : (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatTile label="Unique visitors (all time)" value={String(s.unique_visitors)} />
          <StatTile label="Total logins (all time)" value={String(s.total_logins)} />
          <StatTile label="Unique visitors (24h)" value={String(s.unique_visitors_last_24h)} />
          <StatTile label="Logins (24h)" value={String(s.logins_last_24h)} />
        </div>
      )}
      <p className="mt-3 text-xs text-[var(--text-muted)]">
        "Unique" is approximated from a salted hash of the requester's IP — no raw IPs are stored.
      </p>
    </Section>
  );
}

function WhaleAlertsList() {
  const qc = useQueryClient();
  const alertsQuery = useQuery({ queryKey: ["admin", "whale-alerts"], queryFn: fetchWhaleAlerts, refetchInterval: 30_000 });
  const ackMutation = useMutation({
    mutationFn: acknowledgeWhaleAlert,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin", "whale-alerts"] }),
  });
  const ackAllMutation = useMutation({
    mutationFn: acknowledgeAllWhaleAlerts,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin", "whale-alerts"] }),
  });

  const alerts = alertsQuery.data ?? [];
  const unread = alerts.filter((a) => !a.acknowledged).length;

  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-sm font-medium text-[var(--text-secondary)]">
          Whale trades ($500k+) {unread > 0 && <span className="text-[var(--accent)]">· {unread} unread</span>}
        </h3>
        {unread > 0 && (
          <button
            onClick={() => ackAllMutation.mutate()}
            disabled={ackAllMutation.isPending}
            className="text-xs text-[var(--accent)] hover:underline"
          >
            Mark all read
          </button>
        )}
      </div>
      <ul className="space-y-2">
        {alerts.map((a) => (
          <li
            key={a.id}
            className={`flex items-center justify-between gap-3 rounded-lg border px-3 py-2.5 text-sm ${
              a.acknowledged ? "border-[var(--border-hairline)]" : "border-[var(--accent)] bg-[var(--bg-page)]"
            }`}
          >
            <div className="min-w-0">
              <div className="truncate font-medium text-[var(--text-primary)]" title={a.market_title}>
                {a.market_title || "Untitled market"} <span className="text-[var(--text-muted)]">· {a.outcome_label}</span>
              </div>
              <div className="text-xs text-[var(--text-muted)]">
                {a.username || `${a.wallet_address.slice(0, 6)}…${a.wallet_address.slice(-4)}`} —{" "}
                {formatCompactCurrency(a.position_value)} · {formatRelativeTime(a.detected_at)}
              </div>
            </div>
            {!a.acknowledged && (
              <button
                onClick={() => ackMutation.mutate(a.id)}
                className="shrink-0 text-xs text-[var(--text-muted)] hover:text-[var(--text-primary)]"
              >
                Dismiss
              </button>
            )}
          </li>
        ))}
        {alerts.length === 0 && <li className="text-sm text-[var(--text-muted)]">No large trades flagged yet.</li>}
      </ul>
    </div>
  );
}

function SupportRequestsList() {
  const qc = useQueryClient();
  const requestsQuery = useQuery({
    queryKey: ["admin", "support-requests"],
    queryFn: fetchSupportRequests,
    refetchInterval: 30_000,
  });
  const ackMutation = useMutation({
    mutationFn: acknowledgeSupportRequest,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin", "support-requests"] }),
  });

  const requests = requestsQuery.data ?? [];
  const unread = requests.filter((r) => !r.acknowledged).length;

  return (
    <div>
      <h3 className="mb-2 text-sm font-medium text-[var(--text-secondary)]">
        KrillBot escalations {unread > 0 && <span className="text-[var(--accent)]">· {unread} unread</span>}
      </h3>
      <ul className="space-y-2">
        {requests.map((r) => (
          <li
            key={r.id}
            className={`flex items-center justify-between gap-3 rounded-lg border px-3 py-2.5 text-sm ${
              r.acknowledged ? "border-[var(--border-hairline)]" : "border-[var(--accent)] bg-[var(--bg-page)]"
            }`}
          >
            <div className="min-w-0">
              <div className="truncate font-medium text-[var(--text-primary)]" title={r.summary}>
                {r.summary}
              </div>
              <div className="text-xs text-[var(--text-muted)]">
                Contact: {r.contact} · {formatRelativeTime(r.created_at)}
              </div>
            </div>
            {!r.acknowledged && (
              <button
                onClick={() => ackMutation.mutate(r.id)}
                className="shrink-0 text-xs text-[var(--text-muted)] hover:text-[var(--text-primary)]"
              >
                Dismiss
              </button>
            )}
          </li>
        ))}
        {requests.length === 0 && <li className="text-sm text-[var(--text-muted)]">No escalations from KrillBot yet.</li>}
      </ul>
    </div>
  );
}

function NotificationsSection() {
  return (
    <Section title="Notifications">
      <div className="flex flex-col gap-5">
        <SupportRequestsList />
        <WhaleAlertsList />
      </div>
    </Section>
  );
}

function ScoringWeightsForm() {
  const qc = useQueryClient();
  const weightsQuery = useQuery({ queryKey: ["admin", "weights"], queryFn: fetchScoringWeights });
  const [valueNormalizer, setValueNormalizer] = useState<string>("");
  const [maxValueBoost, setMaxValueBoost] = useState<string>("");

  const current = weightsQuery.data;
  const normalizer = valueNormalizer || String(current?.value_normalizer ?? "");
  const boost = maxValueBoost || String(current?.max_value_boost ?? "");

  const mutation = useMutation({
    mutationFn: () =>
      updateScoringWeights({ value_normalizer: Number(normalizer), max_value_boost: Number(boost) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin", "weights"] }),
  });

  return (
    <Section title="Consensus scoring weights">
      <p className="mb-3 text-sm text-[var(--text-secondary)]">
        Controls how much combined dollar value can boost a market's consensus score (capped multiplier — never
        additive, so whale count still wins). Takes effect on the next scan.
      </p>
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-sm">
          Value normalizer
          <input className={inputClass} value={normalizer} onChange={(e) => setValueNormalizer(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Max value boost
          <input className={inputClass} value={boost} onChange={(e) => setMaxValueBoost(e.target.value)} />
        </label>
        <button onClick={() => mutation.mutate()} disabled={mutation.isPending} className={buttonClass}>
          Save
        </button>
      </div>
      {mutation.isSuccess && <p className="mt-2 text-sm text-[var(--good)]">Saved.</p>}
    </Section>
  );
}

function ModerationSection() {
  const qc = useQueryClient();
  const marketsQuery = useQuery({ queryKey: ["admin", "excluded-markets"], queryFn: fetchExcludedMarkets });
  const tradersQuery = useQuery({ queryKey: ["admin", "excluded-traders"], queryFn: fetchExcludedTraders });
  const [marketId, setMarketId] = useState("");
  const [marketReason, setMarketReason] = useState("");
  const [wallet, setWallet] = useState("");
  const [walletReason, setWalletReason] = useState("");

  const addMarket = useMutation({
    mutationFn: () => excludeMarket(marketId.trim(), marketReason.trim()),
    onSuccess: () => {
      setMarketId("");
      setMarketReason("");
      qc.invalidateQueries({ queryKey: ["admin", "excluded-markets"] });
    },
  });
  const removeMarket = useMutation({
    mutationFn: (id: string) => unexcludeMarket(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin", "excluded-markets"] }),
  });
  const addTrader = useMutation({
    mutationFn: () => excludeTrader(wallet.trim(), walletReason.trim()),
    onSuccess: () => {
      setWallet("");
      setWalletReason("");
      qc.invalidateQueries({ queryKey: ["admin", "excluded-traders"] });
    },
  });
  const removeTrader = useMutation({
    mutationFn: (addr: string) => unexcludeTrader(addr),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin", "excluded-traders"] }),
  });

  return (
    <Section title="Content moderation">
      <div className="grid gap-6 md:grid-cols-2">
        <div>
          <h3 className="mb-2 text-sm font-medium text-[var(--text-secondary)]">Hidden markets</h3>
          <div className="mb-3 flex flex-wrap gap-2">
            <input
              placeholder="condition_id (0x…)"
              className={inputClass + " flex-1 min-w-0"}
              value={marketId}
              onChange={(e) => setMarketId(e.target.value)}
            />
            <input
              placeholder="reason (optional)"
              className={inputClass + " w-32"}
              value={marketReason}
              onChange={(e) => setMarketReason(e.target.value)}
            />
            <button
              onClick={() => addMarket.mutate()}
              disabled={!marketId.trim() || addMarket.isPending}
              className={buttonClass}
            >
              Hide
            </button>
          </div>
          <ul className="space-y-1 text-sm">
            {(marketsQuery.data ?? []).map((m) => (
              <li key={m.condition_id} className="flex items-center justify-between gap-2 rounded border border-[var(--border-hairline)] px-2 py-1.5">
                <span className="truncate text-[var(--text-secondary)]">{m.title || m.condition_id}</span>
                <button
                  onClick={() => removeMarket.mutate(m.condition_id)}
                  className="shrink-0 text-xs text-[var(--critical)] hover:underline"
                >
                  Unhide
                </button>
              </li>
            ))}
            {(marketsQuery.data ?? []).length === 0 && (
              <li className="text-[var(--text-muted)]">No hidden markets.</li>
            )}
          </ul>
        </div>

        <div>
          <h3 className="mb-2 text-sm font-medium text-[var(--text-secondary)]">Hidden traders</h3>
          <div className="mb-3 flex flex-wrap gap-2">
            <input
              placeholder="wallet address (0x…)"
              className={inputClass + " flex-1 min-w-0"}
              value={wallet}
              onChange={(e) => setWallet(e.target.value)}
            />
            <input
              placeholder="reason (optional)"
              className={inputClass + " w-32"}
              value={walletReason}
              onChange={(e) => setWalletReason(e.target.value)}
            />
            <button
              onClick={() => addTrader.mutate()}
              disabled={!wallet.trim() || addTrader.isPending}
              className={buttonClass}
            >
              Hide
            </button>
          </div>
          <ul className="space-y-1 text-sm">
            {(tradersQuery.data ?? []).map((t) => (
              <li key={t.wallet_address} className="flex items-center justify-between gap-2 rounded border border-[var(--border-hairline)] px-2 py-1.5">
                <span className="truncate text-[var(--text-secondary)]">{t.username || t.wallet_address}</span>
                <button
                  onClick={() => removeTrader.mutate(t.wallet_address)}
                  className="shrink-0 text-xs text-[var(--critical)] hover:underline"
                >
                  Unhide
                </button>
              </li>
            ))}
            {(tradersQuery.data ?? []).length === 0 && (
              <li className="text-[var(--text-muted)]">No hidden traders.</li>
            )}
          </ul>
        </div>
      </div>
      <p className="mt-3 text-xs text-[var(--text-muted)]">
        Changes apply on the next scan — trigger a rescan above to see them reflected immediately.
      </p>
    </Section>
  );
}

function AccessCodesLog() {
  const qc = useQueryClient();
  const codesQuery = useQuery({ queryKey: ["admin", "access-codes"], queryFn: fetchAccessCodes });
  const [name, setName] = useState("");
  const [code, setCode] = useState("");

  const createMutation = useMutation({
    mutationFn: () => createAccessCode(name.trim(), code.trim()),
    onSuccess: () => {
      setName("");
      setCode("");
      qc.invalidateQueries({ queryKey: ["admin", "access-codes"] });
    },
  });
  const revokeMutation = useMutation({
    mutationFn: (id: number) => revokeAccessCode(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin", "access-codes"] }),
  });

  const codes = codesQuery.data ?? [];

  return (
    <div className="flex flex-col gap-2">
      <label className="text-sm text-[var(--text-secondary)]">Create a new visitor access code</label>
      <p className="text-xs text-[var(--text-muted)]">
        Every active code works to unlock the dashboard — this adds a new one, it doesn't replace existing codes.
      </p>
      <div className="flex flex-wrap gap-2">
        <input placeholder="name (e.g. reddit promo)" className={inputClass + " w-40"} value={name} onChange={(e) => setName(e.target.value)} />
        <input placeholder="code" className={inputClass + " flex-1 min-w-0"} value={code} onChange={(e) => setCode(e.target.value)} />
        <button
          onClick={() => createMutation.mutate()}
          disabled={!name.trim() || code.trim().length < 4 || createMutation.isPending}
          className={buttonClass}
        >
          Create
        </button>
      </div>
      {createMutation.isSuccess && <p className="text-sm text-[var(--good)]">Code created.</p>}

      <ul className="mt-3 space-y-1 text-sm">
        {codes.map((c) => (
          <li
            key={c.id}
            className="flex items-center justify-between gap-2 rounded border border-[var(--border-hairline)] px-2 py-1.5"
          >
            <div className="min-w-0">
              <span className={c.active ? "text-[var(--text-primary)]" : "text-[var(--text-muted)] line-through"}>
                {c.name}
              </span>
              <span className="ml-2 text-xs text-[var(--text-muted)]">{formatRelativeTime(c.created_at)}</span>
            </div>
            {c.active && (
              <button
                onClick={() => revokeMutation.mutate(c.id)}
                className="shrink-0 text-xs text-[var(--critical)] hover:underline"
              >
                Revoke
              </button>
            )}
          </li>
        ))}
        {codes.length === 0 && <li className="text-[var(--text-muted)]">No codes yet.</li>}
      </ul>
    </div>
  );
}

function AccessManagement({ onLoggedOut }: { onLoggedOut: () => void }) {
  const [newPassword, setNewPassword] = useState("");
  const passwordMutation = useMutation({
    mutationFn: () => changeAdminPassword(newPassword.trim()),
    onSuccess: () => setNewPassword(""),
  });
  const handleLogout = () => {
    onLoggedOut();
    void adminLogout();
  };

  return (
    <Section title="Access management">
      <div className="grid gap-6 md:grid-cols-2">
        <AccessCodesLog />
        <div className="flex flex-col gap-2">
          <label className="text-sm text-[var(--text-secondary)]">New admin password</label>
          <div className="flex gap-2">
            <input
              className={inputClass + " flex-1"}
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
            />
            <button
              onClick={() => passwordMutation.mutate()}
              disabled={newPassword.trim().length < 8 || passwordMutation.isPending}
              className={buttonClass}
            >
              Update
            </button>
          </div>
          {passwordMutation.isSuccess && <p className="text-sm text-[var(--good)]">Admin password updated.</p>}
        </div>
      </div>
      <button
        onClick={handleLogout}
        className="mt-5 rounded-md border border-[var(--border-hairline)] px-4 py-2 text-sm text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
      >
        Log out of admin
      </button>
    </Section>
  );
}

export function AdminPanel({ onLoggedOut }: { onLoggedOut: () => void }) {
  return (
    <div className="mx-auto max-w-5xl px-6 py-8">
      <header className="mb-6 flex items-center gap-3">
        <WhaleSharkLogo size={32} />
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Admin panel</h1>
          <a href="/" className="text-sm text-[var(--text-muted)] hover:text-[var(--text-secondary)]">
            ← Back to dashboard
          </a>
        </div>
      </header>
      <div className="flex flex-col gap-6">
        <NotificationsSection />
        <LoginStatsSection />
        <OperationalControls />
        <ScoringWeightsForm />
        <ModerationSection />
        <AccessManagement onLoggedOut={onLoggedOut} />
      </div>
    </div>
  );
}
