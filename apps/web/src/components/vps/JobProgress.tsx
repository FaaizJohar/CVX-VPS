import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { ProvisioningJob } from "@/types";

const STAGE_LABELS: Record<string, string> = {
  preparing: "Preparing",
  creating_instance: "Creating instance",
  finalizing: "Finalizing",
  done: "Done",
  failed: "Failed",
};

interface JobProgressProps {
  vpsId: string;
  onFinished?: (job: ProvisioningJob | null) => void;
}

/**
 * Live provisioning progress for a VPS. Streams the active job via SSE with a
 * polling fallback; renders nothing once no job is in flight.
 */
export function JobProgress({ vpsId, onFinished }: JobProgressProps) {
  const { data: job, refetch } = useQuery({
    queryKey: ["jobs", "by-vps", vpsId],
    // The API answers 200 + null when no active job exists; errors mean the
    // VPS itself is inaccessible, which we treat the same way.
    queryFn: () =>
      api
        .get<ProvisioningJob | null>(`/api/v1/jobs/by-vps/${vpsId}`)
        .catch(() => null),
    refetchInterval: (query) =>
      query.state.data && ["queued", "running"].includes(query.state.data.status)
        ? 2_000
        : false,
  });

  if (!job || !["queued", "running"].includes(job.status)) {
    if (job && onFinished) onFinished(job);
    return null;
  }

  const stageLabel =
    STAGE_LABELS[job.stage] ?? (job.status === "queued" ? "Queued" : "Working");

  return (
    <div
      role="status"
      aria-live="polite"
      className="rounded-md border border-cvx-accent/25 bg-cvx-accent/5 px-3 py-2.5"
    >
      <div className="flex items-center justify-between text-xs">
        <span className="flex items-center gap-2 text-cvx-muted">
          <span
            aria-hidden
            className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-cvx-accent"
          />
          Provisioning · {stageLabel}
        </span>
        <button
          type="button"
          onClick={() => void refetch()}
          className="mono-data text-cvx-faint hover:text-cvx-text"
        >
          {job.progress}%
        </button>
      </div>
      <div className="mt-2 h-1 overflow-hidden rounded-full bg-cvx-border">
        <div
          className="h-full rounded-full bg-cvx-accent transition-all duration-500 ease-out"
          style={{ width: `${Math.max(6, Math.min(100, job.progress))}%` }}
        />
      </div>
    </div>
  );
}
