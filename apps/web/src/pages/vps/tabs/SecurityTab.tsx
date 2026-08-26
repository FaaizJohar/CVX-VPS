import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { VPS } from "@/types";
import { Card, CardHeader } from "@/components/ui/Card";
import { StatusBadge } from "@/components/ui/StatusBadge";

interface SecurityEventItem {
  id: string;
  severity: string;
  category: string;
  message: string;
  created_at: string;
}

export default function SecurityTab({ vps }: { vps: VPS }) {
  const [page, setPage] = useState(1);
  const { data: events } = useQuery({
    queryKey: ["vps", vps.id, "security-events", page],
    queryFn: () =>
      api.get<{ items: SecurityEventItem[]; total: number }>(
        `/api/v1/logs/security-events?vps_id=${vps.id}&page=${page}&page_size=20`,
      ),
    refetchInterval: 30_000,
  });

  // Real posture indicators only — derived from actual configuration.
  const posture: Array<{ label: string; state: "good" | "warn" | "bad"; detail: string }> = [
    {
      label: "Container isolation",
      state: vps.privileged ? "bad" : "good",
      detail: vps.privileged ? "Privileged mode — full host access" : "Unprivileged",
    },
    {
      label: "Password authentication",
      state: vps.password_auth_enabled ? "warn" : "good",
      detail: vps.password_auth_enabled
        ? "Enabled — SSH password logins permitted"
        : "Disabled — key-based access only",
    },
    {
      label: "SSH keys installed",
      state: vps.ssh_keys.length > 0 ? "good" : "warn",
      detail:
        vps.ssh_keys.length > 0
          ? `${vps.ssh_keys.length} key(s) provisioned`
          : "No SSH keys provisioned",
    },
  ];

  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <Card>
        <CardHeader title="Security posture" />
        <ul className="divide-y divide-cvx-border">
          {posture.map((p) => (
            <li key={p.label} className="flex items-center justify-between gap-3 px-4 py-3">
              <div>
                <p className="text-sm">{p.label}</p>
                <p className="text-xs text-cvx-faint">{p.detail}</p>
              </div>
              <StatusBadge status={p.state === "good" ? "active" : p.state === "warn" ? "warning" : "critical"} />
            </li>
          ))}
        </ul>
      </Card>

      <Card>
        <CardHeader title="Security events" />
        {!events || events.items.length === 0 ? (
          <p className="px-4 py-8 text-center text-sm text-cvx-faint">No recorded events.</p>
        ) : (
          <>
            <ul className="divide-y divide-cvx-border">
              {events.items.map((e) => (
                <li key={e.id} className="px-4 py-3">
                  <div className="flex items-start justify-between gap-3">
                    <p className="text-sm">{e.message}</p>
                    <StatusBadge status={e.severity} />
                  </div>
                  <p className="mt-1 font-mono text-[11px] text-cvx-faint">
                    {e.category} · {new Date(e.created_at).toLocaleString()}
                  </p>
                </li>
              ))}
            </ul>
            <div className="flex items-center justify-between border-t border-cvx-border px-4 py-2 text-xs text-cvx-faint">
              <span>{events.total} events</span>
              <div className="flex gap-2">
                <button disabled={page <= 1} onClick={() => setPage(page - 1)} className="flex items-center gap-1 disabled:opacity-30 hover:text-cvx-text">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
                  Prev
                </button>
                <button disabled={page * 20 >= events.total} onClick={() => setPage(page + 1)} className="flex items-center gap-1 disabled:opacity-30 hover:text-cvx-text">
                  Next
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
                </button>
              </div>
            </div>
          </>
        )}
      </Card>
    </div>
  );
}
