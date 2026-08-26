import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api";
import type { Backup, VPS } from "@/types";
import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { EmptyState, Spinner } from "@/components/ui/Loading";
import { Input } from "@/components/ui/Input";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { fmtBytes, fmtDate } from "@/lib/format";

export default function BackupsTab({ vps }: { vps: VPS }) {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [confirmAction, setConfirmAction] = useState<{ type: "restore" | "delete"; id: string; name: string } | null>(null);

  const { data: backups, isLoading } = useQuery({
    queryKey: ["vps", vps.id, "backups"],
    queryFn: () => api.get<Backup[]>(`/api/v1/vps/${vps.id}/backups`),
    refetchInterval: (q) =>
      q.state.data?.some((b) => b.status === "pending" || b.status === "running") ? 5_000 : 30_000,
  });

  const invalidate = () => void qc.invalidateQueries({ queryKey: ["vps", vps.id, "backups"] });

  const create = useMutation({
    mutationFn: () =>
      api.post(`/api/v1/vps/${vps.id}/backups`, {
        name: name.trim() || undefined,
      }),
    onSuccess: () => {
      setName("");
      setError(null);
      invalidate();
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : "Backup creation failed."),
  });

  const op = useMutation({
    mutationFn: ({ id, action }: { id: string; action: "restore" | "delete" }) =>
      action === "restore"
        ? api.post(`/api/v1/vps/${vps.id}/backups/${id}/restore`)
        : api.delete(`/api/v1/vps/${vps.id}/backups/${id}`),
    onSuccess: () => {
      setError(null);
      invalidate();
      void qc.invalidateQueries({ queryKey: ["vps", vps.id] });
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : "Operation failed."),
  });

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader title="Create backup" />
        <form
          className="flex flex-wrap items-end gap-3 p-4"
          onSubmit={(e) => {
            e.preventDefault();
            create.mutate();
          }}
        >
          <div className="w-56">
            <label className="stat-label mb-1 block">Name (optional)</label>
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="auto-generated" />
          </div>
          <Button type="submit" variant="primary" disabled={create.isPending}>
            {create.isPending ? "Starting…" : "Create backup"}
          </Button>
          <p className="pb-2 text-xs text-cvx-faint">
            Backups are exported archives stored on the node — they survive snapshot deletion and
            can be restored to rebuild the VPS disk.
          </p>
        </form>
        {error && (
          <p className="border-t border-cvx-border px-4 py-2 text-xs text-cvx-danger">{error}</p>
        )}
      </Card>

      <Card>
        <CardHeader title={`Backups${backups ? ` (${backups.length})` : ""}`} />
        {isLoading ? (
          <p className="px-4 py-8 text-center text-sm text-cvx-faint">Loading…</p>
        ) : !backups || backups.length === 0 ? (
          <EmptyState title="No backups" hint="Create a backup to keep a restorable archive of this VPS." />
        ) : (
          <ul className="divide-y divide-cvx-border">
            {backups.map((b) => (
              <li key={b.id} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <p className="truncate font-mono text-sm">{b.name}</p>
                    <StatusBadge status={b.status} />
                    {(b.status === "pending" || b.status === "running") && <Spinner className="h-3 w-3" />}
                  </div>
                  <p className="text-xs text-cvx-faint">
                    {fmtDate(b.created_at)}
                    {b.completed_at && ` · finished ${fmtDate(b.completed_at)}`}
                    {b.size_bytes != null && ` · ${fmtBytes(b.size_bytes)}`}
                    {b.optimized_storage && " · optimized"}
                  </p>
                  {b.error && <p className="mt-1 text-xs text-cvx-danger">{b.error}</p>}
                </div>
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    disabled={op.isPending || b.status !== "completed"}
                    onClick={() => setConfirmAction({ type: "restore", id: b.id, name: b.name })}
                  >
                    Restore
                  </Button>
                  <Button
                    size="sm"
                    variant="danger"
                    disabled={op.isPending}
                    onClick={() => setConfirmAction({ type: "delete", id: b.id, name: b.name })}
                  >
                    Delete
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <ConfirmDialog
        open={confirmAction?.type === "restore"}
        title={`Restore backup "${confirmAction?.name}"?`}
        message="Current disk state will be replaced with the backup contents. This operation may take several minutes."
        confirmLabel="Restore"
        busy={op.isPending}
        onConfirm={() => { if (confirmAction) op.mutate({ id: confirmAction.id, action: "restore" }); setConfirmAction(null); }}
        onClose={() => setConfirmAction(null)}
      />
      <ConfirmDialog
        open={confirmAction?.type === "delete"}
        title={`Delete backup "${confirmAction?.name}"?`}
        message="This backup will be permanently removed. This cannot be undone."
        confirmLabel="Delete"
        danger
        busy={op.isPending}
        onConfirm={() => { if (confirmAction) op.mutate({ id: confirmAction.id, action: "delete" }); setConfirmAction(null); }}
        onClose={() => setConfirmAction(null)}
      />
    </div>
  );
}
