import { useState } from "react";
import { OceanScene } from "./OceanScene";
import { InstagramIcon } from "./InstagramIcon";
import { XIcon } from "./XIcon";
import { submitSignup, unlock } from "../lib/api";
import { useTeaser } from "../hooks/useApi";
import { formatCompactCurrency } from "../lib/format";

function StarIcon({ size = 14 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <path d="M12 2.5l2.6 6.3 6.8.5-5.2 4.4 1.7 6.6L12 16.9l-5.9 3.4 1.7-6.6-5.2-4.4 6.8-.5L12 2.5z" />
    </svg>
  );
}

// A small, deliberately non-specific proof point — real aggregate numbers
// and KrillBot's real equity-curve shape, no market names or picks. Fails
// silently (renders nothing) rather than blocking or cluttering the login
// flow if the teaser endpoint isn't ready yet.
function TeaserCard() {
  const teaserQuery = useTeaser();
  const teaser = teaserQuery.data;
  if (!teaser || teaser.bot_equity_curve.length < 2) return null;

  const curve = teaser.bot_equity_curve;
  const min = Math.min(...curve);
  const max = Math.max(...curve);
  const range = max - min || 1;
  const points = curve
    .map((v, i) => {
      const x = (i / (curve.length - 1)) * 100;
      const y = 26 - ((v - min) / range) * 26;
      return `${x},${y}`;
    })
    .join(" ");
  const isPositive = teaser.bot_return_pct >= 0;
  const lineColor = isPositive ? "var(--good)" : "var(--critical)";

  const totalTrades = teaser.bot_win_count + teaser.bot_loss_count;

  return (
    <div className="rounded-xl border border-[var(--border-hairline)] bg-[var(--bg-surface)] p-4 shadow-2xl">
      <div className="flex items-center justify-between gap-4">
        <div>
          <div className="text-xs font-medium uppercase tracking-wide text-[var(--text-muted)]">KrillBot, live</div>
          <div className="flex items-baseline gap-2">
            <span className="text-lg font-semibold tabular-nums" style={{ color: lineColor }}>
              {isPositive ? "+" : ""}
              {teaser.bot_return_pct.toFixed(1)}%
            </span>
            {totalTrades > 0 && (
              <span className="text-xs tabular-nums text-[var(--text-muted)]">
                {teaser.bot_win_count}W-{teaser.bot_loss_count}L
              </span>
            )}
          </div>
        </div>
        <svg viewBox="0 0 100 26" preserveAspectRatio="none" className="h-8 w-28" aria-hidden="true">
          <polyline points={points} fill="none" stroke={lineColor} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </div>
      <div className="mt-3 grid grid-cols-3 gap-2 border-t border-[var(--border-hairline)] pt-3 text-center text-[11px] text-[var(--text-muted)]">
        <div>
          <div className="font-medium tabular-nums text-[var(--text-secondary)]">{teaser.tracked_traders.toLocaleString()}</div>
          whales tracked
        </div>
        <div>
          <div className="font-medium tabular-nums text-[var(--text-secondary)]">{teaser.active_markets.toLocaleString()}</div>
          live markets
        </div>
        <div>
          <div className="font-medium tabular-nums text-[var(--text-secondary)]">{formatCompactCurrency(teaser.total_whale_exposure)}</div>
          tracked
        </div>
      </div>
    </div>
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
    <div className="gate-background relative flex min-h-screen items-center justify-center px-6 py-10">
      {/* Decorative background only — its own clipped layer, so oversized
          art never constrains or clips the actual page content below. A
          tall stack (form + teaser + signup) needs to be free to scroll on
          short viewports instead of getting cut off. */}
      <div className="absolute inset-0 overflow-hidden">
        <OceanScene />
        <img
          src="/brand/shark-mark-800.png"
          alt=""
          className="gate-logo-mark -left-64 top-1/2 w-[1100px] -translate-y-1/2"
        />
        <img src="/brand/shark-mark-800.png" alt="" className="gate-logo-mark right-0 top-0 w-[500px] rotate-12" />
      </div>

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
        <a
          href="https://x.com/WhaleSharkksX?ct=b25ib2FyZGluZ193ZWxjb21l&ppid=email-push-service"
          target="_blank"
          rel="noreferrer"
          className="flex items-center gap-1.5 text-xs text-[var(--text-muted)] transition-colors hover:text-[var(--accent)]"
        >
          <XIcon size={13} />
          @WhaleSharkksX
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
          <a
            href="https://x.com/WhaleSharkksX?ct=b25ib2FyZGluZ193ZWxjb21l&ppid=email-push-service"
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-1.5 text-xs text-[var(--text-muted)] transition-colors hover:text-[var(--accent)]"
          >
            <XIcon size={13} />
            @WhaleSharkksX
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

        <div className="mb-4">
          <TeaserCard />
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
