export type Timeframe = "DAY" | "WEEK" | "MONTH" | "ALL";
export type Variant = "combined" | "day" | "week" | "month" | "all_time";
export type TradeStatus = "active" | "finished" | "all";
export const TOP_N_OPTIONS = [5, 10, 25, 50, 100] as const;
export type TopN = (typeof TOP_N_OPTIONS)[number];

export interface HolderOut {
  wallet: string;
  username: string | null;
  profile_image: string | null;
  verified: boolean;
  best_timeframe: Timeframe;
  best_rank: number;
  position_value: number;
  size: number;
  avg_entry_price: number;
  current_price: number;
  cash_pnl: number;
  percent_pnl: number;
}

export interface ConsensusRowOut {
  id: string;
  condition_id: string;
  outcome_index: number;
  outcome_label: string;
  market_title: string;
  market_slug: string;
  event_slug: string;
  category: string | null;
  image_url: string | null;
  end_date: string | null;
  is_active: boolean;
  current_price: number;
  whale_count: number;
  combined_value: number;
  consensus_score: number;
  holders: HolderOut[];
}

export interface SummaryOut {
  tracked_traders: number;
  active_positions: number;
  consensus_markets: number;
  total_whale_exposure: number;
  last_refresh_at: string | null;
}

export interface HealthOut {
  status: string;
  ready: boolean;
  last_refresh_at: string | null;
}

export interface MatchupOut {
  leader: ConsensusRowOut;
  other: ConsensusRowOut;
  reasoning: string;
}

export interface TopPickOut {
  kind: "single" | "matchup";
  single: ConsensusRowOut | null;
  matchup: MatchupOut | null;
}

export interface HighlightsOut {
  top_picks: TopPickOut[];
  most_volume: ConsensusRowOut | null;
  by_timeframe: Record<string, ConsensusRowOut | null>;
}

export interface LeanOut {
  facts: Record<string, unknown>;
  reasoning: string;
}

export interface PaginatedConsensusOut {
  items: ConsensusRowOut[];
  page: number;
  page_size: number;
  total_items: number;
  total_pages: number;
}

export interface ConsensusFilters {
  timeframe: Variant;
  top_n: TopN;
  status: TradeStatus;
  category: string | null;
  min_whales: number;
  min_value: number;
  search: string;
  page: number;
}

export interface AuthStatusOut {
  visitor: boolean;
  admin: boolean;
}

export interface ScanOut {
  id: number;
  started_at: string;
  completed_at: string | null;
  status: string;
  traders_count: number;
  positions_count: number;
  total_value: number;
  error: string | null;
}

export interface ScoringWeights {
  value_normalizer: number;
  max_value_boost: number;
}

export interface ExcludedMarketOut {
  condition_id: string;
  title: string | null;
  reason: string | null;
  excluded_at: string;
}

export interface ExcludedTraderOut {
  wallet_address: string;
  username: string | null;
  reason: string | null;
  excluded_at: string;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface LoginStatsOut {
  total_logins: number;
  unique_visitors: number;
  logins_last_24h: number;
  unique_visitors_last_24h: number;
}

export interface WhaleAlertOut {
  id: number;
  wallet_address: string;
  username: string | null;
  condition_id: string;
  outcome_label: string;
  market_title: string;
  position_value: number;
  detected_at: string;
  acknowledged: boolean;
}

export interface AccessCodeOut {
  id: number;
  name: string;
  created_at: string;
  active: boolean;
}

export interface SupportRequestOut {
  id: number;
  summary: string;
  contact: string;
  created_at: string;
  acknowledged: boolean;
}

export interface BotStateOut {
  cash_balance: number;
  starting_balance: number;
  open_positions_value: number;
  total_value: number;
  percent_return: number;
  open_positions_count: number;
  entry_min_whales: number;
  entry_score_threshold: number;
  last_recalibrated_at: string | null;
}

export interface BotPositionOut {
  id: number;
  condition_id: string;
  outcome_index: number;
  outcome_label: string;
  market_title: string;
  category: string | null;
  status: "open" | "closed";
  stake: number;
  shares: number;
  entry_price: number;
  entry_at: string;
  entry_consensus_score: number;
  entry_whale_count: number;
  entry_reasoning: string | null;
  current_price: number | null;
  exit_price: number | null;
  exit_at: string | null;
  exit_reason: string | null;
  realized_pnl: number | null;
}

export interface PaginatedBotPositionsOut {
  items: BotPositionOut[];
  page: number;
  page_size: number;
  total_items: number;
  total_pages: number;
}

export type BotTimeframe = "day" | "week" | "all_time";
