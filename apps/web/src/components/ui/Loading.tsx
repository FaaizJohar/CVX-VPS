export function Spinner({ className = "" }: { className?: string }) {
  return (
    <span
      className={`inline-block h-4 w-4 animate-spin rounded-full border-2 border-cvx-border-strong border-t-cvx-accent ${className}`}
    />
  );
}

export function PageLoader() {
  return (
    <div className="flex h-full min-h-[40vh] items-center justify-center">
      <Spinner className="h-6 w-6" />
    </div>
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <div aria-hidden className={`skeleton ${className}`} />;
}

export function TableSkeleton({ rows = 5, cols = 4 }: { rows?: number; cols?: number }) {
  return (
    <div className="panel overflow-hidden" role="status" aria-label="Loading">
      <div className="border-b border-cvx-border px-4 py-3">
        <Skeleton className="h-3 w-40" />
      </div>
      <div className="divide-y divide-cvx-border">
        {Array.from({ length: rows }, (_, r) => (
          <div key={r} className="flex items-center gap-4 px-4 py-3.5">
            {Array.from({ length: cols }, (_, c) => (
              <Skeleton
                key={c}
                className={`h-3 ${c === 0 ? "w-1/4" : c === cols - 1 ? "ml-auto w-16" : "hidden w-24 md:block"}`}
              />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

export function StatGridSkeleton({ count = 4 }: { count?: number }) {
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4" role="status" aria-label="Loading">
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="panel space-y-2 px-4 py-3">
          <Skeleton className="h-2.5 w-20" />
          <Skeleton className="h-5 w-12" />
          <Skeleton className="h-2.5 w-24" />
        </div>
      ))}
    </div>
  );
}

export function EmptyState({ title, hint, action }: { title: string; hint?: string; action?: React.ReactNode }) {
  return (
    <div className="animate-fade-in flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-cvx-border py-16">
      <svg
        aria-hidden
        width="28"
        height="28"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.25"
        className="mb-1 text-cvx-faint/60"
      >
        <rect x="3" y="4" width="18" height="14" rx="2" />
        <path d="M8 21h8M12 18v3" />
      </svg>
      <p className="text-sm font-medium text-cvx-muted">{title}</p>
      {hint && <p className="max-w-sm text-center text-xs text-cvx-faint">{hint}</p>}
      {action && <div className="mt-3">{action}</div>}
    </div>
  );
}
