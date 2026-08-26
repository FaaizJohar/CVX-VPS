import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { api, ApiError } from "@/lib/api";
import type { NodeInfo } from "@/types";
import { Button } from "@/components/ui/Button";
import { Card, CardHeader, Stat } from "@/components/ui/Card";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { Spinner } from "@/components/ui/Loading";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { fmtBytes, fmtDate, fmtRelative, fmtUptime } from "@/lib/format";

export default function NodeDetailPage() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const [token, setToken] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmAction, setConfirmAction] = useState<"rotate" | "disable" | "remove" | null>(null);

  const { data: node } = useQuery({
    queryKey: ["nodes", id],
    queryFn: () => api.get<NodeInfo>(`/api/v1/nodes/${id}`),
    refetchInterval: 10_000,
    enabled: !!id,
  });

  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ["nodes"] });
    setError(null);
  };

  const newToken = useMutation({
    mutationFn: () =>
      api.post<{ token: string; expires_at: string; install_command: string }>(
        `/api/v1/nodes/${id}/enrollment-token`,
      ),
    onSuccess: (d) => {
      setToken(d.token);
      refresh();
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : "Failed."),
  });

  const rotate = useMutation({
    mutationFn: () =>
      api.post<{ enrollment_token: string }>(`/api/v1/nodes/${id}/rotate-credentials`),
    onSuccess: (d) => {
      setToken(d.enrollment_token);
      refresh();
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : "Failed."),
  });

  const maintenance = useMutation({
    mutationFn: (enabled: boolean) =>
      api.post(`/api/v1/nodes/${id}/maintenance?enabled=${enabled}`),
    onSuccess: refresh,
    onError: (e) => setError(e instanceof ApiError ? e.message : "Failed."),
  });

  const disable = useMutation({
    mutationFn: () => api.post(`/api/v1/nodes/${id}/disable`),
    onSuccess: refresh,
    onError: (e) => setError(e instanceof ApiError ? e.message : "Failed."),
  });

  const remove = useMutation({
    mutationFn: () => api.delete(`/api/v1/nodes/${id}`),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["nodes"] });
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : "Failed to remove node."),
  });

  if (!node) return <div className="flex justify-center py-16"><Spinner /></div>;

  const ramPct =
    node.ram_used_mb != null && node.ram_total_mb
      ? (node.ram_used_mb / node.ram_total_mb) * 100
      : null;
  const storPct =
    node.storage_used_gb != null && node.storage_total_gb
      ? (node.storage_used_gb / node.storage_total_gb) * 100
      : null;

  return (
    <div className="animate-fade-up space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <Link to="/app/admin/nodes" className="text-cvx-faint hover:text-cvx-muted" aria-label="Back to nodes">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M19 12H5M12 19l-7-7 7-7" />
            </svg>
          </Link>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="font-mono text-lg font-semibold">{node.name}</h1>
              <StatusBadge status={node.status} />
            </div>
            <p className="text-xs text-cvx-faint">
              {node.location} · {node.public_ip} · heartbeat {fmtRelative(node.last_heartbeat_at)}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" onClick={() => newToken.mutate()} disabled={newToken.isPending}>
            New enrollment token
          </Button>
          <Button size="sm" onClick={() => setConfirmAction("rotate")} disabled={rotate.isPending}>
            Rotate credentials
          </Button>
          <Button size="sm" onClick={() => maintenance.mutate(node.status !== "maintenance")}>
            {node.status === "maintenance" ? "Exit maintenance" : "Maintenance mode"}
          </Button>
          <Button size="sm" variant="danger" onClick={() => setConfirmAction("disable")}>
            Disable
          </Button>
          <Button size="sm" variant="danger" onClick={() => setConfirmAction("remove")}>
            Remove
          </Button>
        </div>
      </div>

      {error && (
        <p className="rounded-md border border-cvx-danger/30 bg-cvx-danger/5 px-3 py-2 text-xs text-cvx-danger">
          {error}
        </p>
      )}
      {remove.isSuccess && (
        <p className="rounded-md border border-emerald-500/30 bg-emerald-500/5 px-3 py-2 text-xs text-emerald-400">
          Node removed.
        </p>
      )}

      {token && (
        <Card className="border-emerald-500/30">
          <CardHeader title="Enrollment token (shown once)" />
          <div className="space-y-2 p-4">
            <code className="block break-all rounded-md border border-cvx-border bg-cvx-bg p-3 font-mono text-xs text-emerald-300">
              {token}
            </code>
            <Button size="sm" onClick={() => navigator.clipboard.writeText(token)}>Copy</Button>
          </div>
        </Card>
      )}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="CPU" value={node.cpu_percent != null ? `${node.cpu_percent.toFixed(1)}%` : "—"} sub={`${node.cpu_cores ?? "?"} cores`} />
        <Stat
          label="Memory"
          value={ramPct != null ? `${ramPct.toFixed(0)}%` : "—"}
          sub={node.ram_used_mb != null ? `${(node.ram_used_mb / 1024).toFixed(1)} / ${((node.ram_total_mb ?? 0) / 1024).toFixed(1)} GB` : undefined}
        />
        <Stat
          label="Storage"
          value={storPct != null ? `${storPct.toFixed(0)}%` : "—"}
          sub={node.storage_used_gb != null ? `${fmtBytes(node.storage_used_gb * 1024 ** 3)} used` : undefined}
        />
        <Stat label="Load (1m)" value={node.load1?.toFixed(2) ?? "—"} sub={`uptime ${fmtUptime(node.uptime_seconds)}`} />
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader title="System facts" />
          <dl className="divide-y divide-cvx-border text-sm">
            {[
              ["Agent version", node.agent_version],
              ["LXD version", node.lxd_version],
              ["OS", node.os_name ? `${node.os_name} ${node.os_version ?? ""}` : null],
              ["Architecture", node.architecture],
              ["CPU model", node.cpu_model],
              ["Storage driver", node.storage_driver],
              ["Enrolled", fmtDate(node.enrolled_at)],
              ["Created", fmtDate(node.created_at)],
            ].map(([k, v]) => (
              <div key={k as string} className="flex justify-between gap-4 px-4 py-2.5">
                <dt className="text-cvx-faint">{k}</dt>
                <dd className="mono-data truncate text-right">{v ?? "—"}</dd>
              </div>
            ))}
          </dl>
        </Card>

        <Card>
          <CardHeader title="Operational notes" />
          <ul className="space-y-2 px-4 py-3 text-xs leading-relaxed text-cvx-muted">
            <li>• Nodes in <span className="font-mono">MAINTENANCE</span> or <span className="font-mono">DISABLED</span> state are excluded from new VPS placement.</li>
            <li>• Rotating credentials invalidates the agent's current credential — re-enroll using a fresh token.</li>
            <li>• A node is reported <span className="font-mono">OFFLINE</span> automatically when heartbeats stop.</li>
            <li>• Removal requires the node to host no active VPS.</li>
          </ul>
        </Card>
      </div>

      <ConfirmDialog
        open={confirmAction === "rotate"}
        title="Rotate credentials?"
        message="The agent must re-enroll with a new token. The current agent credential will be invalidated immediately."
        confirmLabel="Rotate"
        busy={rotate.isPending}
        onConfirm={() => { rotate.mutate(); setConfirmAction(null); }}
        onClose={() => setConfirmAction(null)}
      />
      <ConfirmDialog
        open={confirmAction === "disable"}
        title="Disable this node?"
        message="New VPS cannot be placed on a disabled node. Existing VPS on this node are not affected."
        confirmLabel="Disable"
        danger
        onConfirm={() => { disable.mutate(); setConfirmAction(null); }}
        onClose={() => setConfirmAction(null)}
      />
      <ConfirmDialog
        open={confirmAction === "remove"}
        title="Permanently remove this node?"
        message="This will unregister the node from the panel. The node must host no active VPS. This cannot be undone."
        confirmLabel="Remove"
        danger
        busy={remove.isPending}
        onConfirm={() => { remove.mutate(); setConfirmAction(null); }}
        onClose={() => setConfirmAction(null)}
      />
    </div>
  );
}
