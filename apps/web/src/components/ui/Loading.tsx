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

export function EmptyState({ title, hint, action }: { title: string; hint?: string; action?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-cvx-border py-16">
      <p className="text-sm font-medium text-cvx-muted">{title}</p>
      {hint && <p className="max-w-sm text-center text-xs text-cvx-faint">{hint}</p>}
      {action && <div className="mt-3">{action}</div>}
    </div>
  );
}
