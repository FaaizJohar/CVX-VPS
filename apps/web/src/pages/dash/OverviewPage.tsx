import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { LogItem, VPS } from "@/types";
import { useAuth, useIsAdmin } from "@/lib/auth";
import { StatGridSkeleton } from "@/components/ui/Loading";
import { ErrorState } from "@/components/ui/ErrorState";
import { fmtRelative } from "@/lib/format";

interface DashboardData {
  vps: { total: number; running: number };
  nodes: {
    total: number;
    online: number;
    items: {
      id: string;
      name: string;
      location: string;
      status: string;
      cpu_percent: number | null;
      ram_used_mb: number | null;
      ram_total_mb: number | null;
    }[];
  };
  allocation: {
    cpu_allocated: number;
    cpu_capacity: number;
    ram_allocated_mb: number;
    ram_capacity_mb: number;
    storage_used_gb: number;
    storage_total_gb: number;
  };
  security_alerts: {
    id: string;
    severity: string;
    category: string;
    message: string;
    created_at: string;
  }[];
}

function ResourceBar({ used, total, label }: { used: number; total: number; label: string }) {
  const pct = total > 0 ? Math.min((used / total) * 100, 100) : 0;
  const color =
    pct > 90 ? "bg-cvx-danger" : pct > 70 ? "bg-cvx-warn" : "bg-cvx-accent";
  return (
    <div className="space-y-1">
      <div className="flex items-baseline justify-between text-xs">
        <span className="text-cvx-muted">{label}</span>
        <span className="mono-data text-[11px]">
          {used} / {total}
        </span>
      </div>
      <div className="resource-track">
        <div className={`resource-fill ${color}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function SeverityDot({ severity }: { severity: string }) {
  const cls =
    severity === "critical"
      ? "bg-cvx-danger"
      : severity === "warning"
        ? "bg-cvx-warn"
        : "bg-cvx-muted";
  return <span className={`inline-block h-1.5 w-1.5 rounded-full ${cls}`} />;
}

export default function OverviewPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const isAdmin = useIsAdmin();

  useEffect(() => {
    document.title = "Overview — CVX";
    return () => { document.title = "CVX — VPS Infrastructure Control"; };
  }, []);

  const { data: dash, isLoading: dashLoading, error: dashError, refetch: dashRefetch } = useQuery({
    queryKey: ["admin", "dashboard"],
    queryFn: () => api.get<DashboardData>("/api/v1/admin/dashboard"),
    enabled: isAdmin,
    staleTime: 15_000,
  });

  const { data: vpsList } = useQuery({
    queryKey: ["vps", "list"],
    queryFn: () => api.get<{ items: VPS[]; total: number }>("/api/v1/vps?page=1&page_size=100"),
    staleTime: 15_000,
  });

  const { data: logsData } = useQuery({
    queryKey: ["logs", "recent"],
    queryFn: () => api.get<{ items: LogItem[] }>("/api/v1/logs?page=1&page_size=8"),
    staleTime: 10_000,
  });

  const vpsItems = vpsList?.items ?? [];
  const totalVps = vpsList?.total ?? 0;
  const runningVps = vpsItems.filter((v) => v.status === "running").length;
  const stoppedVps = vpsItems.filter((v) => v.status === "stopped").length;
  const errorVps = vpsItems.filter((v) => v.status === "error").length;
  const recentLogs = logsData?.items ?? [];
  const alloc = dash?.allocation;
  const nodes = dash?.nodes;

  if (dashLoading) {
    return (
      <div className="space-y-6">
        <div className="space-y-2">
          <div className="skeleton h-8 w-64" />
          <div className="skeleton h-4 w-96" />
        </div>
        <StatGridSkeleton count={4} />
        <div className="skeleton h-48 w-full" />
      </div>
    );
  }

  if (dashError && isAdmin) {
    return <ErrorState message="Failed to load dashboard data." onRetry={() => void dashRefetch()} />;
  }

  /* ── Non-admin fallback: just show VPS summary ── */
  if (!isAdmin) {
    return (
      <div className="animate-fade-up space-y-6">
        <header className="space-y-1">
          <h1 className="font-display text-2xl font-semibold tracking-tight text-cvx-text">
            Welcome back, {user?.name || user?.email}
          </h1>
          <p className="text-sm text-cvx-muted">
            {totalVps} virtual {totalVps === 1 ? "server" : "servers"} total, {runningVps} running.
          </p>
        </header>
        <div className="grid grid-cols-3 gap-3">
          {[
            { label: "Running", value: runningVps, color: "text-cvx-ok" },
            { label: "Stopped", value: stoppedVps, color: "text-cvx-muted" },
            { label: "Error", value: errorVps, color: "text-cvx-danger" },
          ].map((s) => (
            <div key={s.label} className="panel px-4 py-3">
              <p className="stat-label">{s.label}</p>
              <p className={`mt-1 font-display text-2xl font-semibold ${s.color}`}>{s.value}</p>
            </div>
          ))}
        </div>
      </div>
    );
  }

  /* ── Admin dashboard ── */
  const ramUsedGB = alloc ? alloc.ram_allocated_mb / 1024 : 0;
  const ramTotalGB = alloc ? alloc.ram_capacity_mb / 1024 : 0;
  const cpuPct = alloc && alloc.cpu_capacity > 0
    ? Math.round((alloc.cpu_allocated / alloc.cpu_capacity) * 100)
    : 0;

  return (
    <div className="animate-fade-up space-y-6">
      {/* ── Headline ── */}
      <header className="space-y-1">
        <h1 className="font-display text-2xl font-semibold tracking-tight text-cvx-text">
          Infrastructure overview
        </h1>
        <p className="text-sm text-cvx-muted">
          {totalVps} virtual {totalVps === 1 ? "server" : "servers"}
          {nodes ? ` across ${nodes.total} ${nodes.total === 1 ? "node" : "nodes"}` : ""}
          {nodes && nodes.online > 0 ? ` · ${nodes.online} online` : ""}
        </p>
      </header>

      {/* ── Dense summary row ── */}
      <div className="panel divide-y divide-cvx-border">
        <div className="grid grid-cols-2 gap-px bg-cvx-border sm:grid-cols-4">
          {[
            { label: "VPS total", value: String(totalVps), accent: false },
            { label: "Running", value: String(runningVps), accent: true },
            { label: "Nodes online", value: nodes ? `${nodes.online}/${nodes.total}` : "—", accent: false },
            { label: "CPU alloc", value: `${cpuPct}%`, accent: cpuPct > 90 },
          ].map((s) => (
            <div key={s.label} className="bg-cvx-panel px-4 py-3">
              <p className="stat-label">{s.label}</p>
              <p className={`mt-1 font-display text-xl font-semibold ${s.accent ? "text-cvx-ok" : "text-cvx-text"}`}>
                {s.value}
              </p>
            </div>
          ))}
        </div>
      </div>

      {/* ── Compute control surface ── */}
      <div className="panel p-4 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-cvx-text">Resource allocation</h2>
          <span className="stat-label">across all nodes</span>
        </div>
        <div className="grid gap-4 sm:grid-cols-3">
          <ResourceBar
            label="CPU cores"
            used={alloc?.cpu_allocated ?? 0}
            total={alloc?.cpu_capacity ?? 0}
          />
          <ResourceBar
            label="RAM"
            used={Math.round(ramUsedGB)}
            total={Math.round(ramTotalGB)}
          />
          <ResourceBar
            label="Storage (GB)"
            used={alloc?.storage_used_gb ?? 0}
            total={alloc?.storage_total_gb ?? 0}
          />
        </div>
      </div>

      {/* ── Node list ── */}
      {nodes && nodes.items.length > 0 && (
        <div className="panel overflow-hidden">
          <div className="flex items-center justify-between border-b border-cvx-border px-4 py-2.5">
            <h2 className="text-sm font-semibold text-cvx-text">Nodes</h2>
            <button
              type="button"
              onClick={() => navigate("/app/admin/nodes")}
              className="text-xs text-cvx-accent hover:underline"
            >
              View all →
            </button>
          </div>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[11px] uppercase tracking-wider text-cvx-faint">
                <th className="px-4 py-2 font-medium">Node</th>
                <th className="px-4 py-2 font-medium">Location</th>
                <th className="hidden px-4 py-2 font-medium sm:table-cell">CPU</th>
                <th className="hidden px-4 py-2 font-medium sm:table-cell">RAM</th>
                <th className="px-4 py-2 font-medium">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-cvx-border">
              {nodes.items.map((n) => {
                const ramPctN = n.ram_total_mb && n.ram_used_mb != null
                  ? Math.round((n.ram_used_mb / n.ram_total_mb) * 100)
                  : null;
                return (
                  <tr key={n.id} className="hover:bg-cvx-raised/30 transition-colors">
                    <td className="px-4 py-2.5">
                      <button
                        type="button"
                        onClick={() => navigate(`/app/admin/nodes/${n.id}`)}
                        className="font-medium text-cvx-accent hover:underline"
                      >
                        {n.name}
                      </button>
                    </td>
                    <td className="px-4 py-2.5 text-cvx-muted">{n.location}</td>
                    <td className="hidden px-4 py-2.5 sm:table-cell">
                      <div className="flex items-center gap-2">
                        <div className="resource-track w-16">
                          <div
                            className="resource-fill bg-cvx-accent"
                            style={{ width: `${n.cpu_percent ?? 0}%` }}
                          />
                        </div>
                        <span className="mono-data text-[11px] text-cvx-muted">
                          {n.cpu_percent != null ? `${Math.round(n.cpu_percent)}%` : "—"}
                        </span>
                      </div>
                    </td>
                    <td className="hidden px-4 py-2.5 sm:table-cell">
                      <div className="flex items-center gap-2">
                        <div className="resource-track w-16">
                          <div
                            className="resource-fill bg-cvx-ok"
                            style={{ width: `${ramPctN ?? 0}%` }}
                          />
                        </div>
                        <span className="mono-data text-[11px] text-cvx-muted">
                          {ramPctN != null ? `${ramPctN}%` : "—"}
                        </span>
                      </div>
                    </td>
                    <td className="px-4 py-2.5">
                      <span className={`inline-flex items-center gap-1.5 text-xs ${
                        n.status === "online" ? "text-cvx-ok" : "text-cvx-faint"
                      }`}>
                        <span className={`inline-block h-1.5 w-1.5 rounded-full ${
                          n.status === "online" ? "bg-cvx-ok" : "bg-cvx-faint"
                        }`} />
                        {n.status}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        {/* ── Recent activity ── */}
        {recentLogs.length > 0 && (
          <div className="panel overflow-hidden">
            <div className="flex items-center justify-between border-b border-cvx-border px-4 py-2.5">
              <h2 className="text-sm font-semibold text-cvx-text">Recent activity</h2>
              <button
                type="button"
                onClick={() => navigate("/app/admin/logs")}
                className="text-xs text-cvx-accent hover:underline"
              >
                View all →
              </button>
            </div>
            <ul className="divide-y divide-cvx-border">
              {recentLogs.map((log) => (
                <li key={log.id} className="flex items-start gap-3 px-4 py-2.5">
                  <span className={`mt-1 inline-block h-1.5 w-1.5 shrink-0 rounded-full ${
                    log.severity === "error" ? "bg-cvx-danger"
                      : log.severity === "warning" ? "bg-cvx-warn"
                        : log.severity === "info" ? "bg-cvx-accent"
                          : "bg-cvx-faint"
                  }`} />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-xs text-cvx-text">{log.message}</p>
                    <p className="mt-0.5 text-[11px] text-cvx-faint">
                      {log.source} · {fmtRelative(log.created_at)}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* ── Security alerts ── */}
        {dash && dash.security_alerts.length > 0 && (
          <div className="panel overflow-hidden">
            <div className="border-b border-cvx-border px-4 py-2.5">
              <h2 className="text-sm font-semibold text-cvx-text">Security alerts</h2>
            </div>
            <ul className="divide-y divide-cvx-border">
              {dash.security_alerts.map((alert) => (
                <li key={alert.id} className="flex items-start gap-3 px-4 py-2.5">
                  <SeverityDot severity={alert.severity} />
                  <div className="min-w-0 flex-1">
                    <p className="text-xs text-cvx-text">{alert.message}</p>
                    <p className="mt-0.5 text-[11px] text-cvx-faint">
                      {alert.category} · {fmtRelative(alert.created_at)}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}
