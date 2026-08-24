import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import type { LocalStatus, VPS } from "@/types";
import { Stat, Card, CardHeader } from "@/components/ui/Card";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { ModeBadge } from "@/components/ui/ModeBadge";
import { Skeleton, StatGridSkeleton } from "@/components/ui/Loading";
import { Button } from "@/components/ui/Button";
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
  const navigate = useNavigate();
  const { data } = useQuery({
    queryKey: ["dashboard"],
    queryFn: () => api.get<DashboardData>("/api/v1/admin/dashboard"),
    refetchInterval: 30_000,
  });
  const { data: recentVps } = useQuery({
    queryKey: ["vps", "recent"],
    queryFn: () => api.get<{ items: VPS[] }>("/api/v1/vps?page=1&page_size=6"),
  });
  const { data: localStatus } = useQuery({
    queryKey: ["nodes", "local", "status"],
    queryFn: () => api.get<LocalStatus>("/api/v1/nodes/local/status"),
    staleTime: 30_000,
  });

  if (!data) {
    return (
      <div className="animate-fade-up space-y-6">
        <header className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold">Overview</h1>
            <p className="mt-0.5 text-sm text-cvx-muted">Infrastructure at a glance</p>
          </div>
        </header>
        <StatGridSkeleton />
        <div className="grid gap-4 xl:grid-cols-2">
          {[0, 1].map((i) => (
            <div key={i} className="panel space-y-3 p-4" role="status" aria-label="Loading">
              <Skeleton className="h-8 w-full" />
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-2/3" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  const alloc = data.allocation;
  const computeTargets: Array<{
    key: string;
    name: string;
    location: string;
    online: boolean;
    statusLabel: string;
    cpuPercent: number | null;
    ramUsedMb: number | null;
    ramTotalMb: number | null;
    href?: string;
    badge?: "local";
  }> = [];

  if (localStatus) {
    computeTargets.push({
      key: "local",
      name: "LOCAL",
      location: localStatus.hostname ?? "This machine",
      online: localStatus.state === "ready",
      statusLabel:
        (localStatus.state ?? "not_configured").replace("_", " "),
      cpuPercent: null,
      ramUsedMb: null,
      ramTotalMb: localStatus.resources?.ram_total_mb ?? null,
      badge: "local",
    });
  }
  for (const n of data.nodes.items) {
    if (n.status === "removed") continue;
    computeTargets.push({
      key: n.id,
      name: n.name.toUpperCase(),
      location: n.location,
      online: n.status === "online" || n.status === "maintenance",
      statusLabel: n.status,
      cpuPercent: n.cpu_percent,
      ramUsedMb: n.ram_used_mb,
      ramTotalMb: n.ram_total_mb,
      href: `/app/admin/nodes/${n.id}`,
    });
  }

  return (
    <div className="animate-fade-up space-y-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Overview</h1>
          <p className="mt-0.5 text-sm text-cvx-muted">Infrastructure at a glance</p>
        </div>
        <Button variant="primary" onClick={() => navigate("/app/vps/new")}>
          Create VPS
        </Button>
      </header>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {[
          <Stat key="vps" label="VPS" value={data.vps.total} sub={`${data.vps.running} running`} />,
          <Stat key="nodes" label="Nodes" value={data.nodes.total} sub={`${data.nodes.online} online`} />,
          <Stat
            key="cpu"
            label="CPU allocated"
            value={alloc.cpu_allocated}
            sub={alloc.cpu_capacity ? `of ${alloc.cpu_capacity} cores` : "no capacity detected"}
          />,
          <Stat
            key="ram"
            label="RAM allocated"
            value={`${(alloc.ram_allocated_mb / 1024).toFixed(1)} GB`}
            sub={alloc.ram_capacity_mb ? `of ${(alloc.ram_capacity_mb / 1024).toFixed(0)} GB` : undefined}
          />,
        ].map((stat, i) => (
          <div key={i} className="animate-fade-up" style={{ animationDelay: `${i * 50}ms` }}>
            {stat}
          </div>
        ))}
      </div>

      {/* Compute — where does capacity live? */}
      <section aria-labelledby="compute-heading">
        <h2 id="compute-heading" className="stat-label mb-2">Compute</h2>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {computeTargets.map((t) => {
            const inner = (
              <>
                <div className="flex items-center justify-between">
                  <span className="flex items-center gap-2">
                    <span
                      aria-hidden
                      className={`inline-block h-1.5 w-1.5 rounded-full ${
                        t.online ? "bg-emerald-400" : "bg-zinc-600"
                      }`}
                    />
                    <span className="font-mono text-sm font-medium">{t.name}</span>
                    {t.badge === "local" && <ModeBadge mode="local" />}
                  </span>
                  <span
                    className={`text-[10px] uppercase tracking-wider ${
                      t.online ? "text-emerald-400" : "text-cvx-faint"
                    }`}
                  >
                    ● {t.statusLabel}
                  </span>
                </div>
                <p className="mt-1 text-xs text-cvx-faint">{t.location}</p>
                {(t.cpuPercent != null || (t.ramTotalMb != null && t.ramTotalMb > 0)) && (
                  <div className="mt-3 space-y-1.5">
                    {t.cpuPercent != null && (
                      <div>
                        <div className="flex justify-between text-[10px] uppercase tracking-wider text-cvx-faint">
                          <span>CPU</span>
                          <span className="mono-data">{t.cpuPercent.toFixed(0)}%</span>
                        </div>
                        <div className="resource-track mt-1">
                          <div
                            className="resource-fill bg-cvx-accent"
                            style={{ width: `${Math.min(100, t.cpuPercent)}%` }}
                          />
                        </div>
                      </div>
                    )}
                    {t.ramTotalMb != null && t.ramTotalMb > 0 && t.ramUsedMb != null && (
                      <div>
                        <div className="flex justify-between text-[10px] uppercase tracking-wider text-cvx-faint">
                          <span>Memory</span>
                          <span className="mono-data">
                            {(t.ramUsedMb / 1024).toFixed(1)} / {(t.ramTotalMb / 1024).toFixed(0)} GB
                          </span>
                        </div>
                        <div className="resource-track mt-1">
                          <div
                            className="resource-fill bg-cvx-accent"
                            style={{ width: `${Math.min(100, (t.ramUsedMb / t.ramTotalMb) * 100)}%` }}
                          />
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </>
            );
            const cls =
              "panel block p-4 transition-colors duration-200 hover:border-cvx-border-strong";
            return t.href ? (
              <Link key={t.key} to={t.href} className={cls}>{inner}</Link>
            ) : (
              <div key={t.key} className={cls.replace(" hover:", " ")}>{inner}</div>
            );
          })}
          {computeTargets.length === 0 && (
            <div className="panel p-6 text-center text-sm text-cvx-faint sm:col-span-2 xl:col-span-3">
              No compute targets yet — enable local deployment or connect a node.
            </div>
          )}
        </div>
      </section>

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
                  <p className="font-mono text-sm">{v.name} <ModeBadge mode={v.deployment_mode} className="ml-1" /></p>
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
