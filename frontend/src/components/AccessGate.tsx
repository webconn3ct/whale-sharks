import { useState } from "react";
import { OceanScene } from "./OceanScene";
import { InstagramIcon } from "./InstagramIcon";
import { submitSignup, unlock } from "../lib/api";

function StarIcon({ size = 14 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <path d="M12 2.5l2.6 6.3 6.8.5-5.2 4.4 1.7 6.6L12 16.9l-5.9 3.4 1.7-6.6-5.2-4.4 6.8-.5L12 2.5z" />
    </svg>
  );
}

function SignupBox() {
  const [contact, setContact] = useState("");
  const [status, setStatus] = useState<"idle" | "sending" | "sent" | "error">("idle");

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!contact.trim() || status === "sending") return;
    setStatus("sending");
    try {
      await submitSignup(contact.trim());
      setStatus("sent");
      setContact("");
    } catch {
      setStatus("error");
    }
  };

  return (
    <form
      onSubmit={submit}
      className="mt-4 rounded-xl border border-[var(--border-hairline)] bg-[var(--bg-surface)] p-6 shadow-2xl"
    >
      <label className="mb-2 block text-xs font-medium uppercase tracking-wide text-[var(--text-muted)]">
        Sign up:
      </label>
      <div className="flex gap-2">
        <input
          type="text"
          value={contact}
          onChange={(e) => setContact(e.target.value)}
          placeholder="Email or Instagram handle"
          className="w-full rounded-md border border-[var(--border-hairline)] bg-[var(--bg-page)] px-3 py-2.5 text-center text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:border-[var(--accent)] focus:outline-none"
        />
      </div>
      {status === "sent" && <p className="mt-2 text-center text-sm text-[var(--good)]">Thanks — we'll be in touch.</p>}
      {status === "error" && <p className="mt-2 text-center text-sm text-[var(--critical)]">Something went wrong — try again.</p>}
      <button
        type="submit"
        disabled={status === "sending"}
        className="mt-4 w-full rounded-md bg-[var(--accent)] px-4 py-2.5 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50"
      >
        {status === "sending" ? "Sending…" : "Submit"}
      </button>
    </form>
  );
}

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

      <div className="absolute left-6 top-6 z-10 hidden max-w-[260px] flex-col gap-2 sm:flex">
        <p className="flex items-start gap-1.5 text-xs text-[var(--text-muted)]">
          <span className="mt-0.5 shrink-0 text-[var(--accent)]">
            <StarIcon size={13} />
          </span>
          <span>We reveal where the smartest money on Polymarket is moving.</span>
        </p>
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

      <div className="relative z-10 w-full max-w-sm">
        <div className="mb-6 flex flex-col items-center gap-2 text-center sm:hidden">
          <p className="flex items-start gap-1.5 text-xs text-[var(--text-muted)]">
            <span className="mt-0.5 shrink-0 text-[var(--accent)]">
              <StarIcon size={13} />
            </span>
            <span>We reveal where the smartest money on Polymarket is moving.</span>
          </p>
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

        <SignupBox />
      </div>
    </div>
  );
}
