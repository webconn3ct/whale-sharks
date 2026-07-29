import { useState } from "react";
import { OceanScene } from "./OceanScene";
import { unlock } from "../lib/api";

export function AccessGate({ onUnlocked }: { onUnlocked: () => void }) {
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!code.trim()) return;
    setLoading(true);
    setError(null);
    try {
      await unlock(code.trim());
      onUnlocked();
    } catch {
      setError("Incorrect access code");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="gate-background relative flex min-h-screen items-center justify-center overflow-hidden px-6">
      <OceanScene />
      <img
        src="/brand/shark-mark-800.png"
        alt=""
        className="gate-logo-mark -left-64 top-1/2 w-[1100px] -translate-y-1/2"
      />
      <img src="/brand/shark-mark-800.png" alt="" className="gate-logo-mark right-0 top-0 w-[500px] rotate-12" />

      <a
        href="/admin"
        className="absolute right-6 top-6 z-10 rounded-md border border-[var(--border-hairline)] px-3 py-1.5 text-xs text-[var(--text-muted)] transition-colors hover:border-[var(--accent)] hover:text-[var(--text-primary)]"
      >
        Admin
      </a>

      <div className="relative z-10 w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center gap-4 text-center">
          <img src="/brand/shark-mark-300.png" alt="Whale Sharkks" className="h-28 w-28 object-contain" />
          <div>
            <h1 className="brand-wordmark text-3xl text-[var(--text-primary)]">Whale Sharkks</h1>
            <p className="brand-tagline mt-1 text-xs text-[var(--text-muted)]">
              Where deep pockets swim in the same current.
            </p>
          </div>
        </div>

        <form
          onSubmit={submit}
          className="rounded-xl border border-[var(--border-hairline)] bg-[var(--bg-surface)] p-6 shadow-2xl"
        >
          <label className="mb-2 block text-xs font-medium uppercase tracking-wide text-[var(--text-muted)]">
            Access code
          </label>
          <input
            autoFocus
            type="password"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder="Enter code"
            className="w-full rounded-md border border-[var(--border-hairline)] bg-[var(--bg-page)] px-3 py-2.5 text-center tracking-[0.3em] text-[var(--text-primary)] placeholder:tracking-normal placeholder:text-[var(--text-muted)] focus:border-[var(--accent)] focus:outline-none"
          />
          {error && <p className="mt-2 text-center text-sm text-[var(--critical)]">{error}</p>}
          <button
            type="submit"
            disabled={loading}
            className="mt-4 w-full rounded-md bg-[var(--accent)] px-4 py-2.5 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50"
          >
            {loading ? "Checking…" : "Enter"}
          </button>
        </form>
      </div>
    </div>
  );
}
