import { useMemo, useState } from "react";
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type SortingState,
} from "@tanstack/react-table";
import type { ConsensusRowOut } from "../lib/types";
import { formatCompactCurrency, formatProbability, whaleRating } from "../lib/format";

const columnHelper = createColumnHelper<ConsensusRowOut>();

function SortIcon({ direction }: { direction: false | "asc" | "desc" }) {
  if (!direction) return <span className="text-[var(--text-muted)]">↕</span>;
  return <span className="text-[var(--accent)]">{direction === "asc" ? "↑" : "↓"}</span>;
}

export function ConsensusTable({
  rows,
  isLoading,
  onSelectRow,
}: {
  rows: ConsensusRowOut[];
  isLoading: boolean;
  onSelectRow: (row: ConsensusRowOut) => void;
}) {
  const [sorting, setSorting] = useState<SortingState>([{ id: "consensus_score", desc: true }]);

  const columns = useMemo(
    () => [
      columnHelper.accessor("market_title", {
        header: "Market",
        cell: (info) => (
          <div className="max-w-md">
            <div className="truncate font-medium text-[var(--text-primary)]">
              {info.getValue() || "Untitled market"}
            </div>
            {info.row.original.category && (
              <div className="text-xs text-[var(--text-muted)]">{info.row.original.category}</div>
            )}
          </div>
        ),
      }),
      columnHelper.accessor("outcome_label", {
        header: "Outcome",
        cell: (info) => (
          <span className="rounded border border-[var(--border-hairline)] px-2 py-0.5 text-xs text-[var(--text-secondary)]">
            {info.getValue()}
          </span>
        ),
      }),
      columnHelper.accessor("current_price", {
        header: "Probability",
        cell: (info) => <span className="tabular-nums">{formatProbability(info.getValue())}</span>,
      }),
      columnHelper.accessor("whale_count", {
        header: "Whales",
        cell: (info) => <span className="tabular-nums font-medium text-[var(--accent)]">{info.getValue()}</span>,
      }),
      columnHelper.accessor("combined_value", {
        header: "Combined value",
        cell: (info) => <span className="tabular-nums">{formatCompactCurrency(info.getValue())}</span>,
      }),
      columnHelper.accessor("consensus_score", {
        header: "Whale rating",
        cell: (info) => (
          <span className="tabular-nums font-medium">
            {whaleRating(info.getValue())}
            <span className="text-[var(--text-muted)]">/1000</span>
          </span>
        ),
      }),
    ],
    [],
  );

  const table = useReactTable({
    data: rows,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  if (isLoading) {
    return <div className="py-16 text-center text-sm text-[var(--text-muted)]">Loading consensus data…</div>;
  }

  if (rows.length === 0) {
    return (
      <div className="py-16 text-center text-sm text-[var(--text-muted)]">
        No consensus positions match these filters.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-[var(--border-hairline)]">
      <table className="w-full border-collapse text-sm">
        <thead>
          {table.getHeaderGroups().map((headerGroup) => (
            <tr key={headerGroup.id} className="border-b border-[var(--border-hairline)] bg-[var(--bg-surface)]">
              {headerGroup.headers.map((header) => (
                <th
                  key={header.id}
                  className="cursor-pointer select-none whitespace-nowrap px-4 py-2.5 text-left text-xs font-medium uppercase tracking-wide text-[var(--text-muted)]"
                  onClick={header.column.getToggleSortingHandler()}
                >
                  <span className="inline-flex items-center gap-1">
                    {flexRender(header.column.columnDef.header, header.getContext())}
                    <SortIcon direction={header.column.getIsSorted()} />
                  </span>
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row) => (
            <tr
              key={row.id}
              onClick={() => onSelectRow(row.original)}
              className="cursor-pointer border-b border-[var(--border-hairline)] bg-[var(--bg-surface)] last:border-b-0 hover:bg-[var(--bg-surface-raised)]"
            >
              {row.getVisibleCells().map((cell) => (
                <td key={cell.id} className="px-4 py-2.5">
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
