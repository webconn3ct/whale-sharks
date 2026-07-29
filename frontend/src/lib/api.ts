import type {
  AccessCodeOut,
  AuthStatusOut,
  BotPositionOut,
  BotStateOut,
  ChatMessage,
  ConsensusFilters,
  ExcludedMarketOut,
  ExcludedTraderOut,
  HealthOut,
  HighlightsOut,
  LeanOut,
  LoginStatsOut,
  PaginatedConsensusOut,
  ScanOut,
  ScoringWeights,
  SummaryOut,
  SupportRequestOut,
  WhaleAlertOut,
} from "./types";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";

class ApiNotReadyError extends Error {
  constructor() {
    super("Initial scan still in progress");
    this.name = "ApiNotReadyError";
  }
}

class UnauthorizedError extends Error {
  constructor() {
    super("Locked");
    this.name = "UnauthorizedError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { credentials: "include", ...init });
  if (res.status === 503) throw new ApiNotReadyError();
  if (res.status === 401) throw new UnauthorizedError();
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail || `${path} failed: ${res.status}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

function getJson<T>(path: string): Promise<T> {
  return request<T>(path);
}

function postJson<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
}

function putJson<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
}

function del<T>(path: string): Promise<T> {
  return request<T>(path, { method: "DELETE" });
}

export function fetchSummary(): Promise<SummaryOut> {
  return getJson<SummaryOut>("/api/summary");
}

export function fetchHealth(): Promise<HealthOut> {
  return getJson<HealthOut>("/api/health");
}

export function fetchCategories(): Promise<string[]> {
  return getJson<string[]>("/api/categories");
}

export function fetchHighlights(): Promise<HighlightsOut> {
  return getJson<HighlightsOut>("/api/highlights");
}

export function fetchConsensus(filters: ConsensusFilters): Promise<PaginatedConsensusOut> {
  const params = new URLSearchParams({
    timeframe: filters.timeframe,
    top_n: String(filters.top_n),
    status: filters.status,
    page: String(filters.page),
  });
  if (filters.category) params.set("category", filters.category);
  if (filters.min_whales > 0) params.set("min_whales", String(filters.min_whales));
  if (filters.min_value > 0) params.set("min_value", String(filters.min_value));
  if (filters.search.trim()) params.set("search", filters.search.trim());
  return getJson<PaginatedConsensusOut>(`/api/consensus?${params.toString()}`);
}

export function fetchConsensusLean(rowId: string, timeframe: string, topN: number): Promise<LeanOut> {
  const params = new URLSearchParams({ timeframe, top_n: String(topN) });
  return getJson<LeanOut>(`/api/consensus/${encodeURIComponent(rowId)}/lean?${params.toString()}`);
}

// ---- auth -------------------------------------------------------------

export function unlock(code: string): Promise<{ ok: boolean }> {
  return postJson("/api/auth/unlock", { code });
}

export function adminLogin(password: string): Promise<{ ok: boolean }> {
  return postJson("/api/auth/admin-login", { password });
}

export function adminLogout(): Promise<{ ok: boolean }> {
  return postJson("/api/auth/admin-logout", {});
}

export function logout(): Promise<{ ok: boolean }> {
  return postJson("/api/auth/logout", {});
}

export function fetchAuthStatus(): Promise<AuthStatusOut> {
  return getJson<AuthStatusOut>("/api/auth/status");
}

// ---- chat ---------------------------------------------------------------

export function sendChatMessage(message: string, history: ChatMessage[]): Promise<{ reply: string }> {
  return postJson("/api/chat", { message, history });
}

// ---- admin --------------------------------------------------------------

export function fetchAdminScans(): Promise<ScanOut[]> {
  return getJson<ScanOut[]>("/api/admin/scans");
}

export function triggerRescan(): Promise<{ ok: boolean; detail: string }> {
  return postJson("/api/admin/rescan", {});
}

export function fetchScoringWeights(): Promise<ScoringWeights> {
  return getJson<ScoringWeights>("/api/admin/config");
}

export function updateScoringWeights(weights: ScoringWeights): Promise<ScoringWeights> {
  return putJson<ScoringWeights>("/api/admin/config", weights);
}

export function fetchExcludedMarkets(): Promise<ExcludedMarketOut[]> {
  return getJson<ExcludedMarketOut[]>("/api/admin/moderation/markets");
}

export function excludeMarket(conditionId: string, reason: string): Promise<ExcludedMarketOut> {
  return postJson("/api/admin/moderation/markets", { condition_id: conditionId, reason });
}

export function unexcludeMarket(conditionId: string): Promise<{ ok: boolean }> {
  return del(`/api/admin/moderation/markets/${encodeURIComponent(conditionId)}`);
}

export function fetchExcludedTraders(): Promise<ExcludedTraderOut[]> {
  return getJson<ExcludedTraderOut[]>("/api/admin/moderation/traders");
}

export function excludeTrader(walletAddress: string, reason: string): Promise<ExcludedTraderOut> {
  return postJson("/api/admin/moderation/traders", { wallet_address: walletAddress, reason });
}

export function unexcludeTrader(walletAddress: string): Promise<{ ok: boolean }> {
  return del(`/api/admin/moderation/traders/${encodeURIComponent(walletAddress)}`);
}

export function fetchAccessCodes(): Promise<AccessCodeOut[]> {
  return getJson<AccessCodeOut[]>("/api/admin/access-codes");
}

export function createAccessCode(name: string, code: string): Promise<AccessCodeOut> {
  return postJson("/api/admin/access-codes", { name, code });
}

export function revokeAccessCode(id: number): Promise<{ ok: boolean }> {
  return postJson(`/api/admin/access-codes/${id}/revoke`, {});
}

export function changeAdminPassword(newPassword: string): Promise<{ ok: boolean }> {
  return postJson("/api/admin/admin-password", { new_password: newPassword });
}

export function fetchSupportRequests(): Promise<SupportRequestOut[]> {
  return getJson<SupportRequestOut[]>("/api/admin/support-requests");
}

export function acknowledgeSupportRequest(id: number): Promise<{ ok: boolean }> {
  return postJson(`/api/admin/support-requests/${id}/acknowledge`, {});
}

export function fetchLoginStats(): Promise<LoginStatsOut> {
  return getJson<LoginStatsOut>("/api/admin/login-stats");
}

export function fetchWhaleAlerts(): Promise<WhaleAlertOut[]> {
  return getJson<WhaleAlertOut[]>("/api/admin/whale-alerts");
}

export function acknowledgeWhaleAlert(id: number): Promise<{ ok: boolean }> {
  return postJson(`/api/admin/whale-alerts/${id}/acknowledge`, {});
}

export function acknowledgeAllWhaleAlerts(): Promise<{ ok: boolean }> {
  return postJson("/api/admin/whale-alerts/acknowledge-all", {});
}

// ---- mini whale bot ------------------------------------------------------

export function fetchBotState(): Promise<BotStateOut> {
  return getJson<BotStateOut>("/api/bot/state");
}

export function fetchBotPositions(status: "open" | "closed" | "all" = "all"): Promise<BotPositionOut[]> {
  return getJson<BotPositionOut[]>(`/api/bot/positions?status=${status}`);
}

export { ApiNotReadyError, UnauthorizedError };
