import { useQuery } from "@tanstack/react-query";
import { fetchAuthStatus, fetchCategories, fetchConsensus, fetchHighlights, fetchSummary } from "../lib/api";
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
