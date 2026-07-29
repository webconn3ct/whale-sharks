import { useState } from "react";
import { WhaleSharkLogo } from "./WhaleSharkLogo";
import { adminLogin } from "../lib/api";

export function AdminLogin({ onLoggedIn }: { onLoggedIn: () => void }) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!password.trim()) return;
    setLoading(true);
    setError(null);
    try {
      await adminLogin(password.trim());
      onLoggedIn();
    } catch {
      setError("Incorrect admin password");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="gate-background flex min-h-screen items-center justify-center px-6">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center gap-3 text-center">
          <WhaleSharkLogo size={56} className="text-[var(--accent)]" />
          <h1 className="text-xl font-semibold tracking-tight">Admin Login</h1>
        </div>
        <form
          onSubmit={submit}
          className="rounded-xl border border-[var(--border-hairline)] bg-[var(--bg-surface)] p-6 shadow-2xl"
        >
          <label className="mb-2 block text-xs font-medium uppercase tracking-wide text-[var(--text-muted)]">
            Admin password
          </label>
          <input
            autoFocus
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full rounded-md border border-[var(--border-hairline)] bg-[var(--bg-page)] px-3 py-2.5 text-[var(--text-primary)] focus:border-[var(--accent)] focus:outline-none"
          />
          {error && <p className="mt-2 text-sm text-[var(--critical)]">{error}</p>}
          <button
            type="submit"
            disabled={loading}
            className="mt-4 w-full rounded-md bg-[var(--accent)] px-4 py-2.5 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50"
          >
            {loading ? "Checking…" : "Log in"}
          </button>
        </form>
        <a href="/" className="mt-4 block text-center text-sm text-[var(--text-muted)] hover:text-[var(--text-secondary)]">
          ← Back to dashboard
        </a>
      </div>
    </div>
  );
}
