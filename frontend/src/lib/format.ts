const compactNumber = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 });
const compactCurrency = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  notation: "compact",
  maximumFractionDigits: 1,
});
const fullCurrency = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });

export function formatCompactNumber(value: number): string {
  return compactNumber.format(value);
}

export function formatCompactCurrency(value: number): string {
  return compactCurrency.format(value);
}

export function formatCurrency(value: number): string {
  return fullCurrency.format(value);
}

export function formatPercent(value: number, digits = 1): string {
  return `${value.toFixed(digits)}%`;
}

export function formatProbability(price: number): string {
  return `${Math.round(price * 100)}%`;
}

export function formatRelativeTime(iso: string | null): string {
  if (!iso) return "never";
  const diffMs = Date.now() - new Date(iso).getTime();
  const diffSec = Math.round(diffMs / 1000);
  if (diffSec < 5) return "just now";
  if (diffSec < 60) return `${diffSec}s ago`;
  const diffMin = Math.round(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.round(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  return `${Math.round(diffHr / 24)}d ago`;
}

export function truncateWallet(wallet: string): string {
  return `${wallet.slice(0, 6)}…${wallet.slice(-4)}`;
}

export const TIMEFRAME_LABEL: Record<string, string> = {
  DAY: "Daily",
  WEEK: "Weekly",
  MONTH: "Monthly",
  ALL: "All-Time",
};

// The raw consensus_score is an unbounded internal ranking key (real
// production values range from ~1 to 5000+), not something a visitor should
// have to interpret directly. This maps it onto a practical 0-1000 rating
// via a saturating curve — rating = 1000 * score / (score + K) — calibrated
// against the REAL score distribution of live markets (min_whales >= 2,
// queried directly from production): median score ~346, p90 ~868, p99 ~2049,
// max observed ~5034. With K=350 that lands the median at ~500 (a genuinely
// middling pick reads as middling), p90 at ~713, p99 at ~854, and even the
// most extreme real-world case only reaches ~935 — the curve approaches
// 1000 asymptotically and never reaches it, so a "perfect" rating is not
// something the scale can produce, by construction.
const WHALE_RATING_K = 350;

export function whaleRating(consensusScore: number): number {
  if (consensusScore <= 0) return 0;
  const rating = (1000 * consensusScore) / (consensusScore + WHALE_RATING_K);
  return Math.min(999, Math.round(rating));
}
