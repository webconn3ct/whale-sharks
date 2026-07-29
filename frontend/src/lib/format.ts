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
