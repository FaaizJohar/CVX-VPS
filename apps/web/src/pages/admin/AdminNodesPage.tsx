import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, ApiError } from "@/lib/api";
import type { LocalStatus, NodeInfo } from "@/types";
import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/Loading";
import { ErrorState } from "@/components/ui/ErrorState";
import { Input } from "@/components/ui/Input";
import { Field } from "@/components/ui/Input";
import { ModeBadge } from "@/components/ui/ModeBadge";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { CommandBlock } from "@/components/ui/CommandBlock";
import { fmtRelative } from "@/lib/format";

interface CreateResult {
  node: NodeInfo;
  enrollment: { node_id: string; token: string; expires_at: string; install_command: string };
}

const LOCATION_PRESETS = ["Mumbai, IN", "Frankfurt, DE", "Singapore, SG", "Ashburn, US"];

function CheckIcon({ done, active }: { done: boolean; active: boolean }) {
  if (done) {
    return (
      <span className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-cvx-ok/15 text-cvx-ok">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M20 6L9 17l-5-5" />
        </svg>
      </span>
    );
  }
  if (active) {
    return (
      <span className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-cvx-accent/15">
        <span className="h-2 w-2 animate-pulse rounded-full bg-cvx-accent" />
      </span>
    );
  }
  return (
    <span className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-cvx-border-strong">
      <span className="h-1.5 w-1.5 rounded-full bg-cvx-faint" />
    </span>
  );
}

export default function AdminNodesPage() {
  const qc = useQueryClient();
  const [showAdd, setShowAdd] = useState(false);
  const [result, setResult] = useState<CreateResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({ name: "", location: "", description: "" });

  const pendingEnrollment = result !== null;
  const { data: nodes, isLoading, error: nodesError, refetch } = useQuery({
    queryKey: ["nodes"],
    queryFn: () => api.get<NodeInfo[]>("/api/v1/nodes"),
    refetchInterval: pendingEnrollment ? 3_000 : 15_000,
  });
  const { data: localStatus } = useQuery({
    queryKey: ["nodes", "local", "status"],
    queryFn: () => api.get<LocalStatus>("/api/v1/nodes/local/status"),
    refetchInterval: 30_000,
  });

  const enrolledNode = pendingEnrollment
    ? (nodes ?? []).find((n) => n.id === result.node.id)
    : undefined;
  const isEnrolled =
    enrolledNode != null &&
    enrolledNode.enrolled_at != null &&
    !["pending", "disabled", "removed"].includes(enrolledNode.status);

  useEffect(() => {
    if (isEnrolled) void qc.invalidateQueries({ queryKey: ["nodes"] });
  }, [isEnrolled, qc]);

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
      setForm({ name: "", location: "", description: "" });
      void qc.invalidateQueries({ queryKey: ["nodes"] });
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : "Failed to create node."),
  });

  function closeWizard() {
    setResult(null);
    setError(null);
  }

  if (nodesError) {
    return <ErrorState message="Failed to load nodes." onRetry={() => void refetch()} />;
  }

  return (
    <div className="animate-fade-up space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-lg font-semibold tracking-tight">Nodes</h1>
          <p className="text-xs text-cvx-faint">Compute nodes running LXD and the CVX agent.</p>
        </div>
        <Button variant="primary" onClick={() => { setShowAdd(true); setResult(null); }}>
          Add Node
        </Button>
      </div>

      {showAdd && !result && (
        <Card>
          <CardHeader title="Add a Node" />
          <p className="px-4 pt-0 text-xs text-cvx-faint">
            Connect any Linux server in one command. Hardware facts — CPU, memory,
            storage, addresses, LXD — are detected automatically.
          </p>
          <form
            className="grid gap-3 p-4 md:grid-cols-2"
            onSubmit={(e) => {
              e.preventDefault();
              create.mutate();
            }}
          >
            <Field label="Node name" hint="Optional — detected from the host when empty">
              <Input
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="Automatically detected"
                minLength={2}
                maxLength={64}
                pattern="[a-zA-Z0-9][a-zA-Z0-9._-]*"
              />
            </Field>
            <Field label="Location" hint="e.g. Frankfurt, DE">
              <Input
                required
                list="location-presets"
                value={form.location}
                onChange={(e) => setForm({ ...form, location: e.target.value })}
                placeholder="Mumbai, IN"
                minLength={2}
                maxLength={120}
              />
              <datalist id="location-presets">
                {LOCATION_PRESETS.map((l) => (
                  <option key={l} value={l} />
                ))}
              </datalist>
            </Field>
            <div className="md:col-span-2">
              <Field label="Description (optional)">
                <Input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} maxLength={2000} />
              </Field>
            </div>
            <div className="flex items-center gap-3 md:col-span-2">
              <Button type="submit" variant="primary" disabled={create.isPending}>
                {create.isPending ? "Generating…" : "Generate enrollment command"}
              </Button>
              <Button type="button" variant="ghost" onClick={() => setShowAdd(false)}>
                Cancel
              </Button>
              {error && <span className="text-xs text-cvx-danger">{error}</span>}
            </div>
          </form>
        </Card>
      )}

      {result && (
        <Card className="border-cvx-accent/30">
          {isEnrolled && enrolledNode ? (
            <>
              <CardHeader
                title="Node ready"
                action={<Button size="sm" variant="ghost" onClick={closeWizard}>Close</Button>}
              />
              <div className="space-y-4 p-4">
                <div className="flex items-center gap-2.5 text-sm text-emerald-400">
                  <CheckIcon done active={false} />
                  Agent connected — system detected and enrolled.
                </div>
                <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm sm:grid-cols-3">
                  {([
                    ["Name", enrolledNode.name],
                    ["Hostname", enrolledNode.hostname],
                    ["OS", `${enrolledNode.os_name ?? "?"} ${enrolledNode.os_version ?? ""}`.trim()],
                    ["Architecture", enrolledNode.architecture],
                    ["CPU", enrolledNode.cpu_cores != null ? `${enrolledNode.cpu_cores} cores` : null],
                    ["Memory", enrolledNode.ram_total_mb != null ? `${(enrolledNode.ram_total_mb / 1024).toFixed(0)} GB` : null],
                    ["Storage", enrolledNode.storage_total_gb != null ? `${enrolledNode.storage_total_gb} GB` : null],
                    ["LXD", enrolledNode.lxd_version],
                    ["Public IP", enrolledNode.public_ip],
                  ] as const).map(([k, v]) =>
                    v ? (
                      <div key={k}>
                        <dt className="stat-label">{k}</dt>
                        <dd className="mono-data mt-0.5 break-all">{v}</dd>
                      </div>
                    ) : null,
                  )}
                </dl>
                <Link
                  to={`/app/admin/nodes/${enrolledNode.id}`}
                  className="inline-flex items-center gap-1 text-xs text-cvx-accent hover:underline"
                >
                  Open node detail
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
                </Link>
              </div>
            </>
          ) : (
            <>
              <CardHeader
                title={`Waiting for agent — ${result.node.name}`}
                action={<Button size="sm" variant="ghost" onClick={closeWizard}>Cancel</Button>}
              />
              <div className="space-y-4 p-4">
                {/* Honest 3-step checklist */}
                <ol className="space-y-3" aria-label="Enrollment progress">
                  <li className="flex items-start gap-3">
                    <CheckIcon done active={false} />
                    <div>
                      <p className="text-xs font-medium text-cvx-text">Enrollment token generated</p>
                      <p className="mt-0.5 text-[11px] text-cvx-faint">
                        Token for <span className="font-mono">{result.node.name}</span> is ready.
                      </p>
                    </div>
                  </li>
                  <li className="flex items-start gap-3">
                    <CheckIcon done={false} active />
                    <div>
                      <p className="text-xs font-medium text-cvx-text">
                        Run the command below on your server
                      </p>
                      <p className="mt-0.5 text-[11px] text-cvx-faint">
                        CVX will detect the agent automatically when it connects.
                      </p>
                    </div>
                  </li>
                  <li className="flex items-start gap-3">
                    <CheckIcon done={false} active={false} />
                    <div>
                      <p className="text-xs font-medium text-cvx-text">
                        Node appears here with detected hardware
                      </p>
                      <p className="mt-0.5 text-[11px] text-cvx-faint">
                        CPU, memory, storage, LXD version, and public IP are collected automatically.
                      </p>
                    </div>
                  </li>
                </ol>
                <CommandBlock
                  label="Run as root on the node (shown once)"
                  command={result.enrollment.install_command}
                />
                <p className="text-[11px] text-cvx-faint">
                  Single use · expires{" "}
                  {new Date(result.enrollment.expires_at).toLocaleString()}. The command installs
                  LXD (if missing), verifies the agent package checksum, and enrolls.
                </p>
              </div>
            </>
          )}
        </Card>
      )}

      {/* Local machine (control plane host) */}
      {localStatus && (
        <Card className={localStatus.state === "ready" ? "border-violet-500/30" : ""}>
          <CardHeader
            title="Local machine"
            action={
              <Button size="sm" variant="ghost" onClick={() => refreshLocal.mutate()} disabled={refreshLocal.isPending}>
                {refreshLocal.isPending ? "Probing…" : "Re-probe"}
              </Button>
            }
          />
          <div className="p-4 text-sm">
            {localStatus.available ? (
              <div className="grid gap-3 sm:grid-cols-4">
                <div>
                  <p className="stat-label">Status</p>
                  <p className="mt-1 flex items-center gap-1.5">
                    <ModeBadge mode="local" />
                    <span className="text-emerald-400 capitalize">{localStatus.state ?? "Ready"}</span>
                  </p>
                </div>
                <div>
                  <p className="stat-label">CPU</p>
                  <p className="mono-data mt-1">{localStatus.resources?.cpu_cores ?? "?"} cores</p>
                </div>
                <div>
                  <p className="stat-label">Memory</p>
                  <p className="mono-data mt-1">
                    {localStatus.resources?.ram_total_mb != null
                      ? `${(localStatus.resources.ram_total_mb / 1024).toFixed(0)} GB`
                      : "?"}
                  </p>
                </div>
                <div>
                  <p className="stat-label">Storage</p>
                  <p className="mono-data mt-1">
                    {localStatus.resources?.storage_used_gb ?? 0} / {localStatus.resources?.storage_total_gb ?? "?"} GB used
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
              <div className="space-y-2">
                <p className="flex items-center gap-2 text-xs text-cvx-faint">
                  <span aria-hidden className="inline-block h-2 w-2 rounded-full border border-cvx-border-strong" />
                  <span className="uppercase tracking-wider">{localStatus.state ?? "Unavailable"}</span>
                </p>
                <p className="text-sm text-cvx-muted">
                  Local compute isn't available on this host.
                </p>
                {localStatus.message && (
                  <p className="text-xs text-cvx-faint">{localStatus.message}</p>
                )}
                {localStatus.diagnostics && localStatus.diagnostics.length > 0 && (
                  <details className="mt-1">
                    <summary className="cursor-pointer text-xs text-cvx-accent hover:underline">
                      View diagnostics
                    </summary>
                    <ul className="mt-2 space-y-2">
                      {localStatus.diagnostics.map((d, i) => (
                        <li key={`${d.check}-${i}`} className="rounded border border-cvx-border p-2.5 text-xs">
                          <p className="font-medium">
                            <span aria-hidden className={d.ok ? "text-emerald-400" : "text-amber-400"}>
                              {d.ok ? "✓" : "! "}
                            </span>{" "}
                            {d.check}
                          </p>
                          <p className="mt-0.5 text-cvx-faint">{d.detail}</p>
                          {"hint" in d && d.hint && (
                            <p className="mt-1 text-cvx-muted">Fix: {d.hint}</p>
                          )}
                        </li>
                      ))}
                    </ul>
                  </details>
                )}
              </div>
            )}
          </div>
        </Card>
      )}

      {isLoading ? (
        <p className="py-8 text-center text-sm text-cvx-faint">Loading…</p>
      ) : !nodes || nodes.length === 0 ? (
        <EmptyState
          title="No remote nodes connected"
          hint="Deploy locally or connect a server with one command."
          action={
            <Button size="sm" variant="primary" onClick={() => setShowAdd(true)}>
              Add Node
            </Button>
          }
        />
      ) : (
        <Card>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-cvx-border text-left text-[11px] uppercase tracking-wider text-cvx-faint">
                <th className="px-4 py-2.5 font-medium">Node</th>
                <th className="px-4 py-2.5 font-medium">Location</th>
                <th className="hidden px-4 py-2.5 font-medium sm:table-cell">Address</th>
                <th className="hidden px-4 py-2.5 font-medium md:table-cell">CPU / RAM</th>
                <th className="hidden px-4 py-2.5 font-medium lg:table-cell">Heartbeat</th>
                <th className="px-4 py-2.5 font-medium">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-cvx-border">
              {nodes.map((n) => (
                <tr key={n.id} className="group transition-colors duration-150 hover:bg-cvx-raised/40">
                  <td className="px-4 py-2.5">
                    <div className="flex items-center gap-2">
                      <Link to={`/app/admin/nodes/${n.id}`} className="font-mono text-cvx-accent hover:underline">
                        {n.name}
                      </Link>
                      {n.kind === "local" && <ModeBadge mode="local" />}
                    </div>
                  </td>
                  <td className="px-4 py-2.5 text-cvx-muted">{n.location}</td>
                  <td className="mono-data hidden px-4 py-2.5 sm:table-cell">
                    {n.status === "pending" && n.public_ip === "pending-detection"
                      ? <span className="text-cvx-faint">detecting…</span>
                      : n.public_ip}
                  </td>
                  <td className="mono-data hidden px-4 py-2.5 text-cvx-muted md:table-cell">
                    {n.cpu_cores != null ? `${n.cpu_cores} cores` : "?"} ·{" "}
                    {n.ram_total_mb != null ? `${(n.ram_total_mb / 1024).toFixed(0)} GB` : "?"}
                  </td>
                  <td className="hidden px-4 py-2.5 text-xs text-cvx-faint lg:table-cell">{fmtRelative(n.last_heartbeat_at)}</td>
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
