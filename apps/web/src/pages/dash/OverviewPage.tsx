import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "@/lib/api";
import type { VPS } from "@/types";
import { Stat, Card, CardHeader } from "@/components/ui/Card";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { PageLoader } from "@/components/ui/Loading";
import { fmtRelative } from "@/lib/format";

interface DashboardData {
  vps: { total: number; running: number };
  nodes: {
    total: number;
    online: number;
    items: Array<{
      id: string;
      name: string;
      location: string;
      status: string;
      cpu_percent: number | null;
      ram_used_mb: number | null;
      ram_total_mb: number | null;
    }>;
  };
  allocation: {
    cpu_allocated: number;
    cpu_capacity: number;
    ram_allocated_mb: number;
    ram_capacity_mb: number;
    storage_used_gb: number;
    storage_total_gb: number;
  };
  security_alerts: Array<{
    id: string;
    severity: string;
    category: string;
    message: string;
    created_at: string;
  }>;
}

export default function OverviewPage() {
  const { data } = useQuery({
    queryKey: ["dashboard"],
    queryFn: () => api.get<DashboardData>("/api/v1/admin/dashboard"),
    refetchInterval: 30_000,
  });
  const { data: recentVps } = useQuery({
    queryKey: ["vps", "recent"],
    queryFn: () => api.get<{ items: VPS[] }>("/api/v1/vps?page=1&page_size=6"),
  });

  if (!data) return <PageLoader />;

  const alloc = data.allocation;

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-xl font-semibold">Overview</h1>
        <p className="mt-0.5 text-sm text-cvx-muted">Infrastructure at a glance</p>
      </header>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Total VPS" value={data.vps.total} sub={`${data.vps.running} running`} />
        <Stat label="Nodes" value={data.nodes.total} sub={`${data.nodes.online} online`} />
        <Stat
          label="CPU allocated"
          value={alloc.cpu_allocated}
          sub={alloc.cpu_capacity ? `of ${alloc.cpu_capacity} cores` : "no capacity detected"}
        />
        <Stat
          label="RAM allocated"
          value={`${(alloc.ram_allocated_mb / 1024).toFixed(1)} GB`}
          sub={alloc.ram_capacity_mb ? `of ${(alloc.ram_capacity_mb / 1024).toFixed(0)} GB` : undefined}
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader title="Nodes" action={<Link to="/app/admin/nodes" className="text-xs text-cvx-accent hover:underline">Manage</Link>} />
          <div className="divide-y divide-cvx-border">
            {data.nodes.items.length === 0 && (
              <p className="px-4 py-8 text-center text-sm text-cvx-faint">No nodes registered yet.</p>
            )}
            {data.nodes.items.map((n) => (
              <Link
                key={n.id}
                to={`/app/admin/nodes/${n.id}`}
                className="flex items-center justify-between px-4 py-3 hover:bg-cvx-raised/50"
              >
                <div>
                  <p className="font-mono text-sm">{n.name}</p>
                  <p className="text-xs text-cvx-faint">{n.location}</p>
                </div>
                <div className="flex items-center gap-3">
                  <span className="mono-data text-xs text-cvx-muted">
                    {n.cpu_percent != null ? `${n.cpu_percent.toFixed(0)}% CPU` : ""}
                  </span>
                  <StatusBadge status={n.status} />
                </div>
              </Link>
            ))}
          </div>
        </Card>

        <Card>
          <CardHeader title="Recent VPS" action={<Link to="/app/vps" className="text-xs text-cvx-accent hover:underline">View all</Link>} />
          <div className="divide-y divide-cvx-border">
            {(recentVps?.items.length ?? 0) === 0 && (
              <p className="px-4 py-8 text-center text-sm text-cvx-faint">No VPS provisioned yet.</p>
            )}
            {recentVps?.items.map((v) => (
              <Link
                key={v.id}
                to={`/app/vps/${v.id}`}
                className="flex items-center justify-between px-4 py-3 hover:bg-cvx-raised/50"
              >
                <div>
                  <p className="font-mono text-sm">{v.name}</p>
                  <p className="text-xs text-cvx-faint">{v.ipv4 ?? v.hostname}</p>
                </div>
                <StatusBadge status={v.status} />
              </Link>
            ))}
          </div>
        </Card>

        <Card className="xl:col-span-2">
          <CardHeader title="Security alerts" />
          <div className="divide-y divide-cvx-border">
            {data.security_alerts.length === 0 && (
              <p className="px-4 py-8 text-center text-sm text-cvx-faint">No recent alerts.</p>
            )}
            {data.security_alerts.map((a) => (
              <div key={a.id} className="flex items-start justify-between gap-4 px-4 py-3">
                <div className="min-w-0">
                  <p className="truncate text-sm text-cvx-text">{a.message}</p>
                  <p className="text-xs text-cvx-faint">{a.category}</p>
                </div>
                <div className="shrink-0 text-right">
                  <StatusBadge status={a.severity} />
                  <p className="mt-1 text-[11px] text-cvx-faint">{fmtRelative(a.created_at)}</p>
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}
