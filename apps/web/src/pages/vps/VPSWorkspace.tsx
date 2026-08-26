import { lazy, Suspense, useEffect } from "react";
import { Link, Navigate, Route, Routes, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api";
import type { VPS } from "@/types";
import { PageLoader, Spinner } from "@/components/ui/Loading";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { ModeBadge } from "@/components/ui/ModeBadge";
import { JobProgress } from "@/components/vps/JobProgress";
import { DropdownMenu } from "@/components/ui/DropdownMenu";
import type { DropdownAction } from "@/components/ui/DropdownMenu";
import { useToast } from "@/components/ui/Toast";

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
  const qc = useQueryClient();
  const toast = useToast();
  const unlocked = sessionStorage.getItem(`cvx-unlock-${id}`) === "1";

  const { data: vps } = useQuery({
    queryKey: ["vps", id],
    queryFn: () => api.get<VPS>(`/api/v1/vps/${id}`),
    enabled: unlocked,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "creating" || status === "provisioning" ? 3_000 : 15_000;
    },
  });

  const lifecycle = useMutation({
    mutationFn: (action: string) => api.post(`/api/v1/vps/${id}/${action}`),
    onSuccess: (_data, action) => {
      void qc.invalidateQueries({ queryKey: ["vps", id] });
      toast.success(`VPS ${action} succeeded.`);
    },
    onError: (err) => {
      toast.error(err instanceof ApiError ? err.message : "Action failed.");
    },
  });

  useEffect(() => {
    document.title = vps ? `${vps.name} — CVX` : "CVX";
    return () => {
      document.title = "CVX — VPS Infrastructure Control";
    };
  }, [vps]);

  if (!unlocked) return <Navigate to={`/app/vps/${id}/unlock`} replace />;

  const isRunning = vps?.status === "running";
  const isStopped = vps?.status === "stopped";
  const canLifecycle = (isRunning || isStopped) && !lifecycle.isPending;

  const actions: DropdownAction[] = [
    {
      label: "Open terminal",
      icon: <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><rect x="2" y="3" width="20" height="14" rx="2" /><path d="M8 21h8M12 18v3" /></svg>,
      onClick: () => {
        /* Navigate to terminal tab — handled by caller */
      },
    },
    { separator: true, label: "" },
    {
      label: "Restart",
      icon: <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M1 4v6h6M23 20v-6h-6" /><path d="M20.49 9A9 9 0 005.64 5.64L1 10m22 4l-4.64 4.36A9 9 0 013.51 15" /></svg>,
      disabled: !canLifecycle,
      onClick: () => lifecycle.mutate("restart"),
    },
    {
      label: isRunning ? "Stop" : "Start",
      icon: isRunning
        ? <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><rect x="6" y="4" width="4" height="16" /><rect x="14" y="4" width="4" height="16" /></svg>
        : <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><polygon points="5 3 19 12 5 21 5 3" /></svg>,
      disabled: !canLifecycle,
      onClick: () => lifecycle.mutate(isRunning ? "stop" : "start"),
    },
  ];

  return (
    <div className="animate-fade-up flex h-full min-h-0 flex-col">
      {/* Header */}
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-cvx-border pb-3">
        <div className="flex min-w-0 items-center gap-3">
          <Link to="/app/vps" className="text-cvx-faint hover:text-cvx-muted" aria-label="Back to VPS list">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M19 12H5M12 19l-7-7 7-7" />
            </svg>
          </Link>
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
        {vps && (
          <DropdownMenu
            trigger={
              <button type="button" className="icon-btn" aria-label="VPS actions">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
                  <circle cx="12" cy="5" r="1.5" fill="currentColor" />
                  <circle cx="12" cy="12" r="1.5" fill="currentColor" />
                  <circle cx="12" cy="19" r="1.5" fill="currentColor" />
                </svg>
              </button>
            }
            actions={actions}
          />
        )}
      </header>

      {vps && ["creating", "provisioning"].includes(vps.status) && id && (
        <div className="mt-3">
          <JobProgress vpsId={id} />
        </div>
      )}
      {vps?.status === "error" && vps.provision_error && (
        <div
          role="alert"
          className="mt-3 rounded-md border border-cvx-danger/30 bg-cvx-danger/5 px-3 py-2.5 text-xs text-cvx-danger"
        >
          <p className="font-medium">Provisioning failed</p>
          <p className="mt-1 font-mono text-[11px] text-cvx-muted">{vps.provision_error}</p>
        </div>
      )}

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
