import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, ApiError } from "@/lib/api";
import type { LocalStatus, NodeInfo } from "@/types";
import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/Loading";
import { Input } from "@/components/ui/Input";
import { Field } from "@/components/ui/Input";
import { ModeBadge } from "@/components/ui/ModeBadge";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { fmtRelative } from "@/lib/format";

interface CreateResult {
  node: NodeInfo;
  enrollment: { node_id: string; token: string; expires_at: string; install_command: string };
}

export default function AdminNodesPage() {
  const qc = useQueryClient();
  const [showAdd, setShowAdd] = useState(false);
  const [result, setResult] = useState<CreateResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({ name: "", location: "", hostname: "", public_ip: "", description: "" });

  const { data: nodes, isLoading } = useQuery({
    queryKey: ["nodes"],
    queryFn: () => api.get<NodeInfo[]>("/api/v1/nodes"),
    refetchInterval: 15_000,
  });
  const { data: localStatus } = useQuery({
    queryKey: ["nodes", "local", "status"],
    queryFn: () => api.get<LocalStatus>("/api/v1/nodes/local/status"),
    refetchInterval: 30_000,
  });

  const refreshLocal = useMutation({
    mutationFn: () => api.post("/api/v1/nodes/local/refresh"),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["nodes"] }),
  });

  const create = useMutation({
    mutationFn: () => api.post<CreateResult>("/api/v1/nodes", form),
    onSuccess: (data) => {
      setResult(data);
      setShowAdd(false);
      setError(null);
      setForm({ name: "", location: "", hostname: "", public_ip: "", description: "" });
      void qc.invalidateQueries({ queryKey: ["nodes"] });
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : "Failed to create node."),
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold">Nodes</h1>
          <p className="text-xs text-cvx-faint">Compute nodes running LXD and the CVX agent.</p>
        </div>
        <Button variant="primary" onClick={() => { setShowAdd(!showAdd); setResult(null); }}>
          {showAdd ? "Cancel" : "Add node"}
        </Button>
      </div>

      {showAdd && (
        <Card>
          <CardHeader title="Register a new node" />
          <form
            className="grid gap-3 p-4 md:grid-cols-2"
            onSubmit={(e) => {
              e.preventDefault();
              create.mutate();
            }}
          >
            <Field label="Name" hint="Unique identifier, e.g. fra1-node01">
              <Input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </Field>
            <Field label="Location" hint="e.g. Frankfurt, DE">
              <Input required value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} />
            </Field>
            <Field label="Hostname">
              <Input required value={form.hostname} onChange={(e) => setForm({ ...form, hostname: e.target.value })} />
            </Field>
            <Field label="Public IP">
              <Input required value={form.public_ip} onChange={(e) => setForm({ ...form, public_ip: e.target.value })} placeholder="203.0.113.10" />
            </Field>
            <div className="md:col-span-2">
              <Field label="Description (optional)">
                <Input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
              </Field>
            </div>
            <div className="flex items-center gap-3 md:col-span-2">
              <Button type="submit" variant="primary" disabled={create.isPending}>
                {create.isPending ? "Creating…" : "Create & generate enrollment token"}
              </Button>
              {error && <span className="text-xs text-cvx-danger">{error}</span>}
            </div>
          </form>
        </Card>
      )}

      {result && (
        <Card className="border-emerald-500/30">
          <CardHeader title="Node created — enroll the agent (shown once)" />
          <div className="space-y-3 p-4">
            <div>
              <p className="stat-label mb-1">One-time enrollment token</p>
              <code className="block break-all rounded-md border border-cvx-border bg-cvx-bg p-3 font-mono text-xs text-emerald-300">
                {result.enrollment.token}
              </code>
              <p className="mt-1 text-[11px] text-cvx-faint">
                Expires {new Date(result.enrollment.expires_at).toLocaleString()} · single use
              </p>
            </div>
            <div>
              <p className="stat-label mb-1">Run on the node</p>
              <pre className="overflow-x-auto rounded-md border border-cvx-border bg-cvx-bg p-3 font-mono text-xs text-cvx-muted">
                {result.enrollment.install_command}
              </pre>
            </div>
            <Button size="sm" onClick={() => navigator.clipboard.writeText(result.enrollment.token)}>
              Copy token
            </Button>
          </div>
        </Card>
      )}

      {/* Local machine (control plane host) */}
      {localStatus && (
        <Card className={localStatus.available ? "border-violet-500/30" : ""}>
          <CardHeader
            title="Local machine"
            action={
              localStatus.available ? (
                <Button size="sm" onClick={() => refreshLocal.mutate()} disabled={refreshLocal.isPending}>
                  {refreshLocal.isPending ? "Refreshing…" : "Re-detect"}
                </Button>
              ) : undefined
            }
          />
          <div className="p-4 text-sm">
            {localStatus.available ? (
              <div className="grid gap-3 sm:grid-cols-4">
                <div>
                  <p className="stat-label">Status</p>
                  <p className="mt-1"><ModeBadge mode="local" /> <span className="ml-1 text-emerald-400">Available</span></p>
                </div>
                <div>
                  <p className="stat-label">CPU</p>
                  <p className="mono-data mt-1">{localStatus.cpu_cores} cores</p>
                </div>
                <div>
                  <p className="stat-label">Memory</p>
                  <p className="mono-data mt-1">
                    {localStatus.ram_total_mb != null
                      ? `${(localStatus.ram_total_mb / 1024).toFixed(0)} GB`
                      : "?"}
                  </p>
                </div>
                <div>
                  <p className="stat-label">Storage</p>
                  <p className="mono-data mt-1">
                    {localStatus.storage_used_gb ?? 0} / {localStatus.storage_total_gb ?? "?"} GB used
                  </p>
                </div>
                {localStatus.lxd_version && (
                  <p className="text-xs text-cvx-faint sm:col-span-4">
                    LXD {localStatus.lxd_version} · socket{" "}
                    <code className="font-mono">{localStatus.socket_path}</code>
                  </p>
                )}
              </div>
            ) : (
              <p className="text-xs text-cvx-faint">
                Local deployment unavailable
                {localStatus.reason === "disabled" && " — set CVX_ENABLE_LOCAL_DEPLOYMENT=true."}
                {localStatus.reason === "no_lxd_socket" && " — LXD is not installed or the socket is not mounted."}
                {localStatus.reason === "lxd_unreachable" && " — LXD did not answer on its unix socket."}
              </p>
            )}
          </div>
        </Card>
      )}

      {isLoading ? (
        <p className="py-8 text-center text-sm text-cvx-faint">Loading…</p>
      ) : !nodes || nodes.length === 0 ? (
        <EmptyState title="No nodes registered" hint="Add your first compute node to start provisioning VPS." />
      ) : (
        <Card>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-cvx-border text-left text-[11px] uppercase tracking-wider text-cvx-faint">
                <th className="px-4 py-2.5 font-medium">Node</th>
                <th className="px-4 py-2.5 font-medium">Location</th>
                <th className="px-4 py-2.5 font-medium">Address</th>
                <th className="px-4 py-2.5 font-medium">CPU / RAM</th>
                <th className="px-4 py-2.5 font-medium">Heartbeat</th>
                <th className="px-4 py-2.5 font-medium">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-cvx-border">
              {nodes.map((n) => (
                <tr key={n.id} className="hover:bg-cvx-raised/40">
                  <td className="px-4 py-2.5">
                    <div className="flex items-center gap-2">
                      <Link to={`/app/admin/nodes/${n.id}`} className="font-mono text-cvx-accent hover:underline">
                        {n.name}
                      </Link>
                      {n.kind === "local" && <ModeBadge mode="local" />}
                    </div>
                  </td>
                  <td className="px-4 py-2.5 text-cvx-muted">{n.location}</td>
                  <td className="mono-data px-4 py-2.5">{n.public_ip}</td>
                  <td className="mono-data px-4 py-2.5 text-cvx-muted">
                    {n.cpu_cores ?? "?"} cores · {n.ram_total_mb != null ? `${(n.ram_total_mb / 1024).toFixed(0)} GB` : "?"}
                  </td>
                  <td className="px-4 py-2.5 text-xs text-cvx-faint">{fmtRelative(n.last_heartbeat_at)}</td>
                  <td className="px-4 py-2.5"><StatusBadge status={n.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
