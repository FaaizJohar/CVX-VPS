import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { api, ApiError } from "@/lib/api";
import type { NodeInfo, VPS } from "@/types";
import { Button } from "@/components/ui/Button";
import { Input, Select } from "@/components/ui/Input";
import { ModeBadge } from "@/components/ui/ModeBadge";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { EmptyState, TableSkeleton } from "@/components/ui/Loading";
import { ErrorState } from "@/components/ui/ErrorState";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { DropdownMenu } from "@/components/ui/DropdownMenu";
import type { DropdownAction } from "@/components/ui/DropdownMenu";
import { useToast } from "@/components/ui/Toast";
import { fmtDate } from "@/lib/format";

type SortKey = "name" | "status" | "cpu" | "ram" | "disk" | "ip" | "created";
type SortDir = "asc" | "desc";

export default function VPSListPage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const toast = useToast();
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [pendingDelete, setPendingDelete] = useState<VPS | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>("name");
  const [sortDir, setSortDir] = useState<SortDir>("asc");

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["vps", "list", search, statusFilter],
    queryFn: () =>
      api.get<{ items: VPS[]; total: number }>(
        `/api/v1/vps?page=1&page_size=200${search ? `&search=${encodeURIComponent(search)}` : ""}${statusFilter ? `&status=${statusFilter}` : ""}`,
      ),
    placeholderData: (prev) => prev,
  });

  const { data: nodes } = useQuery({
    queryKey: ["nodes"],
    queryFn: () => api.get<NodeInfo[]>("/api/v1/nodes"),
    staleTime: 30_000,
  });

  const nodeMap = useMemo(() => {
    const m = new Map<string, NodeInfo>();
    for (const n of nodes ?? []) m.set(n.id, n);
    return m;
  }, [nodes]);

  const sorted = useMemo(() => {
    const items = data?.items ?? [];
    const copy = [...items];
    copy.sort((a, b) => {
      let cmp = 0;
      switch (sortKey) {
        case "name":
          cmp = a.name.localeCompare(b.name);
          break;
        case "status":
          cmp = a.status.localeCompare(b.status);
          break;
        case "cpu":
          cmp = a.cpu_limit - b.cpu_limit;
          break;
        case "ram":
          cmp = a.ram_mb - b.ram_mb;
          break;
        case "disk":
          cmp = a.disk_gb - b.disk_gb;
          break;
        case "ip":
          cmp = (a.ipv4 ?? "").localeCompare(b.ipv4 ?? "");
          break;
        case "created":
          cmp = new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
          break;
      }
      return sortDir === "asc" ? cmp : -cmp;
    });
    return copy;
  }, [data, sortKey, sortDir]);

  function toggleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  }

  const deleteVps = useMutation({
    mutationFn: (id: string) => api.delete(`/api/v1/vps/${id}`),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["vps"] });
      toast.success(`${pendingDelete?.name ?? "VPS"} deleted.`);
      setPendingDelete(null);
    },
    onError: (err) => {
      toast.error(err instanceof ApiError ? err.message : "Delete failed.");
    },
  });

  const lifecycleAction = useMutation({
    mutationFn: ({ id, action }: { id: string; action: string }) =>
      api.post(`/api/v1/vps/${id}/${action}`),
    onSuccess: (_data, vars) => {
      void qc.invalidateQueries({ queryKey: ["vps"] });
      toast.success(`VPS ${vars.action} succeeded.`);
    },
    onError: (err) => {
      toast.error(err instanceof ApiError ? err.message : "Action failed.");
    },
  });

  function getActions(v: VPS): DropdownAction[] {
    const isRunning = v.status === "running";
    const isStopped = v.status === "stopped";
    return [
      {
        label: "Open",
        icon: (
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><rect x="2" y="3" width="20" height="14" rx="2" /><path d="M8 21h8M12 18v3" /></svg>
        ),
        onClick: () => navigate(`/app/vps/${v.id}`),
      },
      {
        label: "Restart",
        icon: (
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M1 4v6h6M23 20v-6h-6" /><path d="M20.49 9A9 9 0 005.64 5.64L1 10m22 4l-4.64 4.36A9 9 0 013.51 15" /></svg>
        ),
        disabled: !isRunning || lifecycleAction.isPending,
        onClick: () => lifecycleAction.mutate({ id: v.id, action: "restart" }),
      },
      {
        label: isRunning ? "Stop" : "Start",
        icon: isRunning ? (
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><rect x="6" y="4" width="4" height="16" /><rect x="14" y="4" width="4" height="16" /></svg>
        ) : (
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><polygon points="5 3 19 12 5 21 5 3" /></svg>
        ),
        disabled: (!isRunning && !isStopped) || lifecycleAction.isPending,
        onClick: () =>
          lifecycleAction.mutate({
            id: v.id,
            action: isRunning ? "stop" : "start",
          }),
      },
      { separator: true, label: "" },
      {
        label: "Delete",
        danger: true,
        icon: (
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" /></svg>
        ),
        onClick: () => setPendingDelete(v),
      },
    ];
  }

  function SortHeader({ k, children, className = "" }: { k: SortKey; children: React.ReactNode; className?: string }) {
    const active = sortKey === k;
    return (
      <th className={`px-4 py-2.5 font-medium ${className}`}>
        <button
          type="button"
          onClick={() => toggleSort(k)}
          className={`flex items-center gap-1 transition-colors ${active ? "text-cvx-text" : "hover:text-cvx-text"}`}
        >
          {children}
          <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1.5"
            className={`shrink-0 transition-transform ${active ? "text-cvx-accent" : "text-cvx-faint/50"} ${sortDir === "desc" && active ? "rotate-180" : ""}`}
          >
            <path d="M2 6l3-3 3 3" />
          </svg>
        </button>
      </th>
    );
  }

  if (error && !data) {
    return <ErrorState message="Failed to load virtual servers." onRetry={() => void refetch()} />;
  }

  return (
    <div className="animate-fade-up space-y-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="font-display text-xl font-semibold tracking-tight">Virtual Servers</h1>
          <p className="mt-0.5 text-sm text-cvx-muted">{data?.total ?? 0} total</p>
        </div>
        <Button variant="primary" onClick={() => navigate("/app/vps/new")}>
          Create VPS
        </Button>
      </header>

      <div className="flex flex-wrap gap-2">
        <Input
          placeholder="Search by name…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-xs"
          aria-label="Search virtual servers"
        />
        <Select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="w-40"
          aria-label="Filter by status"
        >
          <option value="">All statuses</option>
          <option value="running">Running</option>
          <option value="stopped">Stopped</option>
          <option value="error">Error</option>
        </Select>
      </div>

      {!data && isLoading ? (
        <TableSkeleton rows={5} cols={7} />
      ) : sorted.length === 0 ? (
        <EmptyState
          title={search || statusFilter ? "No matches" : "No virtual servers"}
          hint={
            search || statusFilter
              ? "Try a different search or clear the filters."
              : "Provision your first VPS from the node pool."
          }
          action={
            search || statusFilter ? undefined : (
              <Button variant="primary" onClick={() => navigate("/app/vps/new")}>
                Create VPS
              </Button>
            )
          }
        />
      ) : (
        <>
          {/* ── Desktop table ── */}
          <div className="panel animate-fade-in overflow-hidden hidden md:block">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-cvx-border text-left text-[11px] uppercase tracking-wider text-cvx-faint">
                  <SortHeader k="name">Name</SortHeader>
                  <SortHeader k="status">Status</SortHeader>
                  <th className="hidden px-4 py-2.5 font-medium lg:table-cell">Location</th>
                  <SortHeader k="cpu" className="hidden lg:table-cell">CPU</SortHeader>
                  <SortHeader k="ram" className="hidden lg:table-cell">RAM</SortHeader>
                  <SortHeader k="disk" className="hidden xl:table-cell">Storage</SortHeader>
                  <SortHeader k="ip" className="hidden xl:table-cell">IP</SortHeader>
                  <SortHeader k="created" className="hidden xl:table-cell">Created</SortHeader>
                  <th className="px-4 py-2.5" />
                </tr>
              </thead>
              <tbody className="divide-y divide-cvx-border">
                {sorted.map((v) => {
                  const node = nodeMap.get(v.node_id);
                  return (
                    <tr key={v.id} className="group transition-colors hover:bg-cvx-raised/40">
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <Link
                            to={`/app/vps/${v.id}`}
                            className="font-mono font-medium transition-colors group-hover:text-cvx-accent-hover"
                          >
                            {v.name}
                          </Link>
                          <ModeBadge mode={v.deployment_mode} />
                        </div>
                        <p className="text-xs text-cvx-faint truncate max-w-[200px]">{v.hostname}</p>
                      </td>
                      <td className="px-4 py-3">
                        <StatusBadge status={v.status} />
                      </td>
                      <td className="hidden px-4 py-3 text-xs text-cvx-muted lg:table-cell">
                        {node?.location ?? "—"}
                      </td>
                      <td className="hidden px-4 py-3 lg:table-cell">
                        <span className="mono-data text-xs text-cvx-muted">{v.cpu_limit}</span>
                      </td>
                      <td className="hidden px-4 py-3 lg:table-cell">
                        <span className="mono-data text-xs text-cvx-muted">{(v.ram_mb / 1024).toFixed(1)} GB</span>
                      </td>
                      <td className="hidden px-4 py-3 xl:table-cell">
                        <span className="mono-data text-xs text-cvx-muted">{v.disk_gb} GB</span>
                      </td>
                      <td className="hidden px-4 py-3 xl:table-cell">
                        <span className="mono-data text-xs text-cvx-muted">{v.ipv4 ?? "—"}</span>
                      </td>
                      <td className="hidden px-4 py-3 text-xs text-cvx-faint xl:table-cell">
                        {fmtDate(v.created_at)}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <div className="flex justify-end opacity-0 transition-opacity group-hover:opacity-100">
                          <DropdownMenu
                            trigger={
                              <button type="button" className="icon-btn-sm" aria-label={`Actions for ${v.name}`}>
                                <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
                                  <circle cx="8" cy="3" r="1.5" /><circle cx="8" cy="8" r="1.5" /><circle cx="8" cy="13" r="1.5" />
                                </svg>
                              </button>
                            }
                            actions={getActions(v)}
                          />
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* ── Mobile cards ── */}
          <div className="space-y-2 md:hidden">
            {sorted.map((v) => {
              const node = nodeMap.get(v.node_id);
              return (
                <div key={v.id} className="panel p-3 space-y-2">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 min-w-0">
                      <Link to={`/app/vps/${v.id}`} className="font-mono font-medium text-cvx-accent truncate">
                        {v.name}
                      </Link>
                      <ModeBadge mode={v.deployment_mode} />
                    </div>
                    <StatusBadge status={v.status} />
                  </div>
                  <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-cvx-muted">
                    {v.ipv4 && <span className="mono-data">{v.ipv4}</span>}
                    <span>{v.cpu_limit} vCPU · {(v.ram_mb / 1024).toFixed(1)} GB · {v.disk_gb} GB</span>
                    {node && <span>{node.location}</span>}
                  </div>
                  <div className="flex gap-2 pt-1">
                    <Link to={`/app/vps/${v.id}`}>
                      <Button size="sm">Open</Button>
                    </Link>
                    <DropdownMenu
                      trigger={
                        <button type="button" className="icon-btn-sm" aria-label={`Actions for ${v.name}`}>
                          <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
                            <circle cx="8" cy="3" r="1.5" /><circle cx="8" cy="8" r="1.5" /><circle cx="8" cy="13" r="1.5" />
                          </svg>
                        </button>
                      }
                      actions={getActions(v)}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </>
      )}

      <ConfirmDialog
        open={pendingDelete !== null}
        title={`Delete ${pendingDelete?.name ?? ""}?`}
        message="The instance will be destroyed on its node and its IP address released. This cannot be undone."
        confirmLabel="Delete"
        danger
        busy={deleteVps.isPending}
        onConfirm={() => pendingDelete && deleteVps.mutate(pendingDelete.id)}
        onClose={() => !deleteVps.isPending && setPendingDelete(null)}
      />
    </div>
  );
}
