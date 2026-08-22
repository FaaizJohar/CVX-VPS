import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { api, ApiError } from "@/lib/api";
import type { VPS } from "@/types";
import { Button } from "@/components/ui/Button";
import { Input, Select } from "@/components/ui/Input";
import { ModeBadge } from "@/components/ui/ModeBadge";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { EmptyState, PageLoader } from "@/components/ui/Loading";
import { fmtDate } from "@/lib/format";

export default function VPSListPage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["vps", "list", search, statusFilter],
    queryFn: () =>
      api.get<{ items: VPS[]; total: number }>(
        `/api/v1/vps?page=1&page_size=100${search ? `&search=${encodeURIComponent(search)}` : ""}${statusFilter ? `&status=${statusFilter}` : ""}`,
      ),
  });

  const deleteVps = useMutation({
    mutationFn: (id: string) => api.delete(`/api/v1/vps/${id}`),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["vps"] }),
  });

  if (isLoading) return <PageLoader />;

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Virtual Servers</h1>
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
        />
        <Select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="w-40">
          <option value="">All statuses</option>
          <option value="running">Running</option>
          <option value="stopped">Stopped</option>
          <option value="error">Error</option>
        </Select>
      </div>

      {!data ? (
        <PageLoader />
      ) : data.items.length === 0 ? (
        <EmptyState
          title="No virtual servers"
          hint="Provision your first VPS from the node pool."
          action={
            <Button variant="primary" onClick={() => navigate("/app/vps/new")}>
              Create VPS
            </Button>
          }
        />
      ) : (
        <div className="panel overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-cvx-border text-left text-[11px] uppercase tracking-wider text-cvx-faint">
                <th className="px-4 py-3 font-medium">Name</th>
                <th className="hidden px-4 py-3 font-medium md:table-cell">IPv4</th>
                <th className="hidden px-4 py-3 font-medium lg:table-cell">Resources</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="hidden px-4 py-3 font-medium lg:table-cell">Created</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-cvx-border">
              {data.items.map((v) => (
                <tr key={v.id} className="hover:bg-cvx-raised/40">
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <Link to={`/app/vps/${v.id}`} className="font-mono hover:text-cvx-accent-hover">
                        {v.name}
                      </Link>
                      <ModeBadge mode={v.deployment_mode} />
                    </div>
                    <p className="text-xs text-cvx-faint">{v.hostname}</p>
                  </td>
                  <td className="mono-data hidden px-4 py-3 text-cvx-muted md:table-cell">
                    {v.ipv4 ?? "—"}
                  </td>
                  <td className="mono-data hidden px-4 py-3 text-cvx-muted lg:table-cell">
                    {v.cpu_limit} vCPU · {(v.ram_mb / 1024).toFixed(1)} GB · {v.disk_gb} GB
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={v.status} />
                  </td>
                  <td className="hidden px-4 py-3 text-xs text-cvx-faint lg:table-cell">
                    {fmtDate(v.created_at)}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex justify-end gap-2">
                      <Link to={`/app/vps/${v.id}`}>
                        <Button size="sm">Open</Button>
                      </Link>
                      <Button
                        size="sm"
                        variant="danger"
                        onClick={() => {
                          if (window.confirm(`Delete ${v.name}? This cannot be undone.`)) {
                            deleteVps.mutate(v.id);
                          }
                        }}
                      >
                        Delete
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {deleteVps.isError && (
        <p className="text-xs text-cvx-danger">
          {deleteVps.error instanceof ApiError ? deleteVps.error.message : "Delete failed."}
        </p>
      )}
    </div>
  );
}
