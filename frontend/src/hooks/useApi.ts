import { useQuery } from "@tanstack/react-query";
import {
  fetchAuthStatus,
  fetchBotPositions,
  fetchBotState,
  fetchCategories,
  fetchConsensus,
  fetchConsensusLean,
  fetchHighlights,
  fetchSummary,
} from "../lib/api";
import type { ConsensusFilters } from "../lib/types";

const SUMMARY_POLL_MS = 60_000;
const CONSENSUS_POLL_MS = 60_000;

function shouldRetry(failureCount: number, error: Error): boolean {
  return error.name !== "ApiNotReadyError" && error.name !== "UnauthorizedError" && failureCount < 3;
}

export function useSummary() {
  return useQuery({
    queryKey: ["summary"],
    queryFn: fetchSummary,
    refetchInterval: SUMMARY_POLL_MS,
    retry: shouldRetry,
  });
}

export function useCategories() {
  return useQuery({
    queryKey: ["categories"],
    queryFn: fetchCategories,
    staleTime: SUMMARY_POLL_MS,
    retry: shouldRetry,
  });
}

export function useAuthStatus() {
  return useQuery({
    queryKey: ["auth-status"],
    queryFn: fetchAuthStatus,
    staleTime: 10_000,
  });
}

export function useHighlights() {
  return useQuery({
    queryKey: ["highlights"],
    queryFn: fetchHighlights,
    refetchInterval: CONSENSUS_POLL_MS,
    retry: shouldRetry,
  });
}

export function useConsensus(filters: ConsensusFilters) {
  return useQuery({
    queryKey: ["consensus", filters],
    queryFn: () => fetchConsensus(filters),
    refetchInterval: CONSENSUS_POLL_MS,
    retry: shouldRetry,
  });
}

export function useConsensusLean(rowId: string | null, timeframe: string, topN: number) {
  return useQuery({
    queryKey: ["consensus-lean", rowId, timeframe, topN],
    queryFn: () => fetchConsensusLean(rowId as string, timeframe, topN),
    enabled: rowId !== null,
    staleTime: CONSENSUS_POLL_MS,
    retry: shouldRetry,
  });
}

export function useBotState() {
  return useQuery({
    queryKey: ["bot-state"],
    queryFn: fetchBotState,
    refetchInterval: CONSENSUS_POLL_MS,
    retry: shouldRetry,
  });
}

export function useBotPositions(status: "open" | "closed" | "all" = "all") {
  return useQuery({
    queryKey: ["bot-positions", status],
    queryFn: () => fetchBotPositions(status),
    refetchInterval: CONSENSUS_POLL_MS,
    retry: shouldRetry,
  });
}
