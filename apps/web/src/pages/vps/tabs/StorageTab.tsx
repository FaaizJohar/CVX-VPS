import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { MetricPoint, VPS } from "@/types";
import { Card, CardHeader, Stat } from "@/components/ui/Card";

export default function StorageTab({ vps }: { vps: VPS }) {
  const { data } = useQuery({
    queryKey: ["vps", vps.id, "metrics", "latest"],
    queryFn: () => api.get<{ series: MetricPoint[] }>(`/api/v1/metrics/vps/${vps.id}?range=1h`),
    refetchInterval: 15_000,
  });

  const last = data?.series[data.series.length - 1];
  const used = last?.disk_used_gb;
  const total = last?.disk_total_gb ?? vps.disk_gb;
  const pct = used != null && total ? Math.min(100, (used / total) * 100) : null;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Root disk size" value={`${vps.disk_gb} GB`} />
        <Stat label="Used" value={used != null ? `${used.toFixed(2)} GB` : "—"} />
        <Stat label="Available" value={used != null && total ? `${(total - used).toFixed(2)} GB` : "—"} />
        <Stat label="Utilization" value={pct != null ? `${pct.toFixed(0)}%` : "—"} />
      </div>

      <Card>
        <CardHeader title="Root disk" />
        <div className="px-4 py-4">
          <div className="h-2 overflow-hidden rounded-full bg-cvx-raised">
            <div
              className={`h-full rounded-full transition-all ${
                pct != null && pct > 90 ? "bg-red-400" : pct != null && pct > 75 ? "bg-amber-400" : "bg-cvx-accent"
              }`}
              style={{ width: `${pct ?? 0}%` }}
            />
          </div>
          <p className="mt-2 font-mono text-xs text-cvx-faint">
            {used?.toFixed(2) ?? "?"} GB / {total ?? "?"} GB
          </p>
        </div>
      </Card>

      <Card>
        <CardHeader title="Volumes" />
        <p className="px-4 py-3 text-xs leading-relaxed text-cvx-muted">
          Additional block volumes are not yet provisionable through CVX V1. The root disk is
          fully managed — resize it from the Configuration tab by adjusting the disk limit and
          applying it on the node.
        </p>
      </Card>
    </div>
  );
}
