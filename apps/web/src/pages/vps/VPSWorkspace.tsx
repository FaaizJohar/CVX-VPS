import { lazy, Suspense, useEffect } from "react";
import { Link, Navigate, Route, Routes, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { VPS } from "@/types";
import { PageLoader, Spinner } from "@/components/ui/Loading";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { ModeBadge } from "@/components/ui/ModeBadge";

const CommandTab = lazy(() => import("./tabs/CommandTab"));
const TerminalTab = lazy(() => import("./tabs/TerminalTab"));
const PerformanceTab = lazy(() => import("./tabs/PerformanceTab"));
const NetworkTab = lazy(() => import("./tabs/NetworkTab"));
const StorageTab = lazy(() => import("./tabs/StorageTab"));
const DevicesTab = lazy(() => import("./tabs/DevicesTab"));
const SecurityTab = lazy(() => import("./tabs/SecurityTab"));
const SnapshotsTab = lazy(() => import("./tabs/SnapshotsTab"));
const BackupsTab = lazy(() => import("./tabs/BackupsTab"));
const LogsTab = lazy(() => import("./tabs/LogsTab"));
const ConfigurationTab = lazy(() => import("./tabs/ConfigurationTab"));

const TABS = [
  { slug: "command", label: "Command" },
  { slug: "terminal", label: "Terminal" },
  { slug: "performance", label: "Performance" },
  { slug: "network", label: "Network" },
  { slug: "storage", label: "Storage" },
  { slug: "devices", label: "Devices" },
  { slug: "security", label: "Security" },
  { slug: "snapshots", label: "Snapshots" },
  { slug: "backups", label: "Backups" },
  { slug: "logs", label: "Logs" },
  { slug: "configuration", label: "Configuration" },
];

export default function VPSWorkspace() {
  const { id, "*": active = "command" } = useParams();

  const unlocked = sessionStorage.getItem(`cvx-unlock-${id}`) === "1";

  const { data: vps } = useQuery({
    queryKey: ["vps", id],
    queryFn: () => api.get<VPS>(`/api/v1/vps/${id}`),
    enabled: unlocked,
    refetchInterval: 15_000,
  });

  useEffect(() => {
    document.title = vps ? `${vps.name} — CVX` : "CVX";
    return () => {
      document.title = "CVX — VPS Infrastructure Control";
    };
  }, [vps]);

  if (!unlocked) return <Navigate to={`/app/vps/${id}/unlock`} replace />;

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* Header */}
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-cvx-border pb-3">
        <div className="flex min-w-0 items-center gap-3">
          <Link to="/app/vps" className="text-cvx-faint hover:text-cvx-muted">←</Link>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h1 className="truncate font-mono text-lg font-semibold">{vps?.name ?? "…"}</h1>
              {vps && <><StatusBadge status={vps.status} /><ModeBadge mode={vps.deployment_mode} /></>}
            </div>
            <p className="truncate font-mono text-xs text-cvx-faint">
              {vps?.ipv4 ?? vps?.hostname ?? ""}
            </p>
          </div>
        </div>
      </header>

      {/* Tabs */}
      <nav className="-mx-4 mt-3 overflow-x-auto px-4 scrollbar-thin md:-mx-6 md:px-6">
        <div className="flex min-w-max gap-1 border-b border-cvx-border pb-px">
          {TABS.map((t) => (
            <Link
              key={t.slug}
              to={`/app/vps/${id}/${t.slug}`}
              className={`rounded-t-md border-b-2 px-3 py-2 text-xs uppercase tracking-wider transition-colors ${
                active === t.slug
                  ? "border-cvx-accent text-cvx-text"
                  : "border-transparent text-cvx-faint hover:text-cvx-muted"
              }`}
            >
              {t.label}
            </Link>
          ))}
        </div>
      </nav>

      {/* Content */}
      <div className="mt-4 min-h-0 flex-1 overflow-y-auto pb-8 scrollbar-thin">
        {!vps ? (
          <PageLoader />
        ) : (
          <Suspense fallback={<div className="flex justify-center py-16"><Spinner /></div>}>
            <Routes>
              <Route index element={<Navigate to="command" replace />} />
              <Route path="command" element={<CommandTab vps={vps} />} />
              <Route path="terminal" element={<TerminalTab vps={vps} />} />
              <Route path="performance" element={<PerformanceTab vps={vps} />} />
              <Route path="network" element={<NetworkTab vps={vps} />} />
              <Route path="storage" element={<StorageTab vps={vps} />} />
              <Route path="devices" element={<DevicesTab vps={vps} />} />
              <Route path="security" element={<SecurityTab vps={vps} />} />
              <Route path="snapshots" element={<SnapshotsTab vps={vps} />} />
              <Route path="backups" element={<BackupsTab vps={vps} />} />
              <Route path="logs" element={<LogsTab vps={vps} />} />
              <Route path="configuration" element={<ConfigurationTab vps={vps} />} />
              <Route path="*" element={<Navigate to="command" replace />} />
            </Routes>
          </Suspense>
        )}
      </div>
    </div>
  );
}
