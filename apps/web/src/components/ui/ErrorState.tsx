import { Button } from "@/components/ui/Button";

interface Props {
  title?: string;
  message: string;
  onRetry?: () => void;
}

export function ErrorState({ title = "Something went wrong", message, onRetry }: Props) {
  return (
    <div className="animate-fade-in flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-cvx-danger/30 bg-cvx-danger/5 py-16 px-6">
      <div className="flex h-10 w-10 items-center justify-center rounded-full bg-cvx-danger/10">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-cvx-danger">
          <circle cx="12" cy="12" r="10" />
          <path d="M12 8v4M12 16h.01" />
        </svg>
      </div>
      <p className="text-sm font-medium text-cvx-text">{title}</p>
      <p className="max-w-sm text-center text-xs leading-relaxed text-cvx-muted">{message}</p>
      {onRetry && (
        <Button size="sm" variant="outline" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}
