interface Props {
  page: number;
  totalPages: number;
  onChange: (page: number) => void;
}

export function PageControl({ page, totalPages, onChange }: Props) {
  if (totalPages <= 1) return null;

  const btnClass =
    "rounded-md border border-[var(--border-hairline)] px-3 py-1.5 text-sm text-[var(--text-secondary)] transition-colors hover:border-[var(--accent)] hover:text-[var(--text-primary)] disabled:cursor-default disabled:opacity-40 disabled:hover:border-[var(--border-hairline)] disabled:hover:text-[var(--text-secondary)]";

  return (
    <div className="mt-4 flex items-center justify-center gap-3">
      <button className={btnClass} disabled={page <= 1} onClick={() => onChange(page - 1)}>
        Prev
      </button>
      <span className="tabular-nums text-sm text-[var(--text-muted)]">
        {page}/{totalPages}
      </span>
      <button className={btnClass} disabled={page >= totalPages} onClick={() => onChange(page + 1)}>
        Next
      </button>
    </div>
  );
}
