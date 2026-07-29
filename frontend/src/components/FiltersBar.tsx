import { useEffect, useState } from "react";
import type { ConsensusFilters, TradeStatus, Variant } from "../lib/types";
import { TOP_N_OPTIONS } from "../lib/types";
import { TIMEFRAME_LABEL } from "../lib/format";

const TIMEFRAME_OPTIONS: { value: Variant; label: string }[] = [
  { value: "combined", label: "All leaderboards" },
  { value: "day", label: TIMEFRAME_LABEL.DAY },
  { value: "week", label: TIMEFRAME_LABEL.WEEK },
  { value: "month", label: TIMEFRAME_LABEL.MONTH },
  { value: "all_time", label: TIMEFRAME_LABEL.ALL },
];

const STATUS_OPTIONS: { value: TradeStatus; label: string }[] = [
  { value: "active", label: "Active trades" },
  { value: "finished", label: "Finished trades" },
  { value: "all", label: "All trades" },
];

const selectClass =
  "rounded-md border border-[var(--border-hairline)] bg-[var(--bg-surface)] px-3 py-2 text-sm text-[var(--text-primary)] focus:border-[var(--accent)] focus:outline-none";
const inputClass = selectClass + " placeholder:text-[var(--text-muted)]";

interface Props {
  filters: ConsensusFilters;
  onChange: (filters: ConsensusFilters) => void;
  categories: string[];
}

export function FiltersBar({ filters, onChange, categories }: Props) {
  const [searchDraft, setSearchDraft] = useState(filters.search);

  useEffect(() => {
    const id = setTimeout(() => {
      if (searchDraft !== filters.search) onChange({ ...filters, search: searchDraft });
    }, 300);
    return () => clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchDraft]);

  return (
    <div className="flex flex-wrap items-center gap-2">
      <input
        type="search"
        placeholder="Search markets by keyword or phrase…"
        className={inputClass + " w-64"}
        value={searchDraft}
        onChange={(e) => setSearchDraft(e.target.value)}
      />

      <select
        className={selectClass}
        value={filters.timeframe}
        onChange={(e) => onChange({ ...filters, timeframe: e.target.value as Variant })}
      >
        {TIMEFRAME_OPTIONS.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>

      <label className="flex items-center gap-1.5 text-sm text-[var(--text-secondary)]">
        Top
        <select
          className={selectClass}
          value={filters.top_n}
          onChange={(e) => onChange({ ...filters, top_n: Number(e.target.value) as ConsensusFilters["top_n"] })}
        >
          {TOP_N_OPTIONS.map((n) => (
            <option key={n} value={n}>
              Top {n}
            </option>
          ))}
        </select>
      </label>

      <select
        className={selectClass}
        value={filters.status}
        onChange={(e) => onChange({ ...filters, status: e.target.value as TradeStatus })}
      >
        {STATUS_OPTIONS.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>

      <select
        className={selectClass}
        value={filters.category ?? ""}
        onChange={(e) => onChange({ ...filters, category: e.target.value || null })}
      >
        <option value="">All categories</option>
        {categories.map((c) => (
          <option key={c} value={c}>
            {c}
          </option>
        ))}
      </select>

      <label className="flex items-center gap-1.5 text-sm text-[var(--text-secondary)]">
        Min whales
        <input
          type="number"
          min={0}
          className={inputClass + " w-20"}
          value={filters.min_whales}
          onChange={(e) => onChange({ ...filters, min_whales: Math.max(0, Number(e.target.value) || 0) })}
        />
      </label>

      <label className="flex items-center gap-1.5 text-sm text-[var(--text-secondary)]">
        Min value ($)
        <input
          type="number"
          min={0}
          step={1000}
          className={inputClass + " w-28"}
          value={filters.min_value}
          onChange={(e) => onChange({ ...filters, min_value: Math.max(0, Number(e.target.value) || 0) })}
        />
      </label>
    </div>
  );
}
