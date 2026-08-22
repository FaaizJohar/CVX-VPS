import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { useState } from "react";
import { api } from "@/lib/api";
import type { VPS } from "@/types";
import { Button } from "@/components/ui/Button";
import { Card, CardHeader, Stat } from "@/components/ui/Card";
import { StatusBadge } from "@/components/ui/StatusBadge";

interface LiveState {
  reachable: boolean;
  status?: string;
  ips?: Record<string, string>;
  process_count?: number | null;
  created_at?: string | null;
}

export default function CommandTab({ vps }: { vps: VPS }) {
  const qc = useQueryClient();
  const [actionError, setActionError] = useState<string | null>(null);

  const { data: live } = useQuery({
    queryKey: ["vps", vps.id, "state"],
    queryFn: () => api.get<LiveState>(`/api/v1/vps/${vps.id}/state`),
    refetchInterval: 20_000,
  });

  const action = useMutation({
    mutationFn: (a: string) => api.post(`/api/v1/vps/${vps.id}/${a}`),
    onSuccess: () => {
      setActionError(null);
      void qc.invalidateQueries({ queryKey: ["vps", vps.id] });
    },
    onError: () => setActionError("Action failed on the node. Check node connectivity."),
  });

  const running = vps.status === "running";

  return (
    <div className="space-y-4">
      {/* Quick actions */}
      <div className="flex flex-wrap gap-2">
        <Button disabled={running || action.isPending} onClick={() => action.mutate("start")}>
          Start
        </Button>
        <Button disabled={!running || action.isPending} onClick={() => action.mutate("stop")}>
          Stop
        </Button>
        <Button disabled={!running || action.isPending} onClick={() => action.mutate("restart")}>
          Restart
        </Button>
        <Button disabled={!running || action.isPending} onClick={() => action.mutate("shutdown")}>
          Shutdown
        </Button>
        <Link to={`/app/vps/${vps.id}/terminal`}>
          <Button variant="primary">Console</Button>
        </Link>
      </div>

      {actionError && (
        <p className="rounded-md border border-cvx-danger/30 bg-cvx-danger/5 px-3 py-2 text-xs text-cvx-danger">
          {actionError}
        </p>
      )}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Status" value={<StatusBadge status={vps.status} />} />
        <Stat label="Uptime" value={live?.reachable ? "Live" : "—"} sub={live?.created_at ? `since ${new Date(live.created_at).toLocaleDateString()}` : undefined} />
        <Stat label="Processes" value={live?.process_count ?? "—"} />
        <Stat
          label="Health"
          value={
            !live?.reachable
              ? "Unknown"
              : vps.status === "running"
                ? "Operational"
                : "Offline"
          }
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader title="System" />
          <dl className="divide-y divide-cvx-border text-sm">
            {[
              ["Hostname", vps.hostname],
              ["Operating system image", `#${vps.image_id?.slice(0, 8) ?? "—"}`],
              ["Node", vps.node_id.slice(0, 8)],
              ["Created", new Date(vps.created_at).toLocaleString()],
            ].map(([k, v]) => (
              <div key={k} className="flex justify-between gap-4 px-4 py-2.5">
                <dt className="text-cvx-faint">{k}</dt>
                <dd className="mono-data truncate">{v}</dd>
              </div>
            ))}
          </dl>
        </Card>

        <Card>
          <CardHeader title="Resources" />
          <dl className="divide-y divide-cvx-border text-sm">
            {[
              ["CPU", `${vps.cpu_limit} vCPU`],
              ["Memory", `${(vps.ram_mb / 1024).toFixed(1)} GB`],
              ["Swap", `${(vps.swap_mb / 1024).toFixed(1)} GB`],
              ["Disk", `${vps.disk_gb} GB`],
              ["Process limit", String(vps.process_limit)],
            ].map(([k, v]) => (
              <div key={k} className="flex justify-between gap-4 px-4 py-2.5">
                <dt className="text-cvx-faint">{k}</dt>
                <dd className="mono-data">{v}</dd>
              </div>
            ))}
          </dl>
        </Card>

        <Card>
          <CardHeader title="Network" />
          <dl className="divide-y divide-cvx-border text-sm">
            <div className="flex justify-between gap-4 px-4 py-2.5">
              <dt className="text-cvx-faint">IPv4</dt>
              <dd className="mono-data">{vps.ipv4 ?? "—"}</dd>
            </div>
            <div className="flex justify-between gap-4 px-4 py-2.5">
              <dt className="text-cvx-faint">IPv6</dt>
              <dd className="mono-data break-all">{vps.ipv6 ?? "—"}</dd>
            </div>
            <div className="flex justify-between gap-4 px-4 py-2.5">
              <dt className="text-cvx-faint">MAC</dt>
              <dd className="mono-data">{vps.mac_address ?? "—"}</dd>
            </div>
            {(Object.entries(live?.ips ?? {}).length > 0) && (
              <div className="px-4 py-2.5">
                <dt className="pb-1 text-cvx-faint">Interfaces (live)</dt>
                {Object.entries(live?.ips ?? {}).map(([iface, ip]) => (
                  <div key={iface} className="flex justify-between font-mono text-xs text-cvx-muted">
                    <span>{iface}</span><span>{ip}</span>
                  </div>
                ))}
              </div>
            )}
          </dl>
        </Card>

        <Card>
          <CardHeader title="Access" />
          <dl className="divide-y divide-cvx-border text-sm">
            <div className="flex justify-between gap-4 px-4 py-2.5">
              <dt className="text-cvx-faint">SSH keys</dt>
              <dd className="mono-data">{vps.ssh_keys.length}</dd>
            </div>
            <div className="flex justify-between gap-4 px-4 py-2.5">
              <dt className="text-cvx-faint">Password auth</dt>
              <dd className="mono-data">{vps.password_auth_enabled ? "Enabled" : "Disabled"}</dd>
            </div>
            <div className="flex justify-between gap-4 px-4 py-2.5">
              <dt className="text-cvx-faint">Isolation</dt>
              <dd className="mono-data">{vps.privileged ? "Privileged" : "Unprivileged"}</dd>
            </div>
          </dl>
        </Card>
      </div>

      {vps.provision_error && (
        <Card className="border-cvx-danger/40">
          <CardHeader title="Provision error" />
          <pre className="overflow-x-auto p-4 font-mono text-xs text-cvx-danger whitespace-pre-wrap">
            {vps.provision_error}
          </pre>
        </Card>
      )}
    </div>
  );
}
