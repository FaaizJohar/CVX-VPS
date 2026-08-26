import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api";
import type { Snapshot, VPS } from "@/types";
import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/Loading";
import { Input } from "@/components/ui/Input";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { fmtBytes, fmtDate } from "@/lib/format";

export default function SnapshotsTab({ vps }: { vps: VPS }) {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [stateful, setStateful] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [confirmAction, setConfirmAction] = useState<{ type: "restore" | "delete"; snap: string } | null>(null);
  const [renameTarget, setRenameTarget] = useState<{ snap: string; currentName: string } | null>(null);
  const [renameValue, setRenameValue] = useState("");

  const { data: snapshots, isLoading } = useQuery({
    queryKey: ["vps", vps.id, "snapshots"],
    queryFn: () => api.get<Snapshot[]>(`/api/v1/vps/${vps.id}/snapshots`),
    refetchInterval: 30_000,
  });

  const invalidate = () => void qc.invalidateQueries({ queryKey: ["vps", vps.id, "snapshots"] });

  const create = useMutation({
    mutationFn: () =>
      api.post(`/api/v1/vps/${vps.id}/snapshots`, {
        name: name.trim() || undefined,
        stateful,
      }),
    onSuccess: () => {
      setName("");
      setError(null);
      invalidate();
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : "Snapshot creation failed."),
  });

  const op = useMutation({
    mutationFn: ({ snap, action, newName }: { snap: string; action: string; newName?: string }) =>
      action === "delete"
        ? api.delete(`/api/v1/vps/${vps.id}/snapshots/${snap}`)
        : action === "rename"
          ? api.post(`/api/v1/vps/${vps.id}/snapshots/${snap}/rename?new_name=${encodeURIComponent(newName ?? "")}`)
          : api.post(`/api/v1/vps/${vps.id}/snapshots/${snap}/restore`),
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
        <CardHeader title="Create snapshot" />
        <form
          className="flex flex-wrap items-end gap-3 p-4"
          onSubmit={(e) => {
            e.preventDefault();
            create.mutate();
          }}
        >
          <div className="w-56">
            <label className="stat-label mb-1 block">Name (optional)</label>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="auto-generated"
              maxLength={128}
            />
          </div>
          <label className="flex cursor-pointer items-center gap-2 pb-2 text-sm text-cvx-muted">
            <input
              type="checkbox"
              checked={stateful}
              onChange={(e) => setStateful(e.target.checked)}
              className="accent-cvx-accent"
            />
            Stateful (include runtime state)
          </label>
          <Button type="submit" variant="primary" disabled={create.isPending}>
            {create.isPending ? "Creating…" : "Take snapshot"}
          </Button>
        </form>
        {error && (
          <p className="border-t border-cvx-border px-4 py-2 text-xs text-cvx-danger">{error}</p>
        )}
      </Card>

      <Card>
        <CardHeader
          title={`Snapshots${snapshots ? ` (${snapshots.length})` : ""}`}
        />
        {isLoading ? (
          <p className="px-4 py-8 text-center text-sm text-cvx-faint">Loading…</p>
        ) : !snapshots || snapshots.length === 0 ? (
          <EmptyState
            title="No snapshots"
            hint="Snapshots capture the full disk (and optionally memory) at a point in time. They are stored on the node."
          />
        ) : (
          <ul className="divide-y divide-cvx-border">
            {snapshots.map((s) => (
              <li key={`${s.name}-${s.created_at}`} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
                <div className="min-w-0">
                  <p className="truncate font-mono text-sm">{s.name}</p>
                  <p className="text-xs text-cvx-faint">
                    {fmtDate(s.created_at)} · {fmtBytes(s.size_bytes)} ·{" "}
                    {s.stateful ? "stateful" : "stateless"}
                  </p>
                </div>
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    disabled={op.isPending}
                    onClick={() => setConfirmAction({ type: "restore", snap: s.name })}
                  >
                    Restore
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={op.isPending}
                    onClick={() => { setRenameTarget({ snap: s.name, currentName: s.name }); setRenameValue(s.name); }}
                  >
                    Rename
                  </Button>
                  <Button
                    size="sm"
                    variant="danger"
                    disabled={op.isPending}
                    onClick={() => setConfirmAction({ type: "delete", snap: s.name })}
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
        title={`Restore "${confirmAction?.snap}"?`}
        message="Current disk state will be lost. The snapshot will be restored to replace the running instance."
        confirmLabel="Restore"
        busy={op.isPending}
        onConfirm={() => { if (confirmAction) op.mutate({ snap: confirmAction.snap, action: "restore" }); setConfirmAction(null); }}
        onClose={() => setConfirmAction(null)}
      />
      <ConfirmDialog
        open={confirmAction?.type === "delete"}
        title={`Delete "${confirmAction?.snap}"?`}
        message="This snapshot will be permanently removed. This cannot be undone."
        confirmLabel="Delete"
        danger
        busy={op.isPending}
        onConfirm={() => { if (confirmAction) op.mutate({ snap: confirmAction.snap, action: "delete" }); setConfirmAction(null); }}
        onClose={() => setConfirmAction(null)}
      />

      {/* Rename modal */}
      {renameTarget && (
        <div className="animate-fade-in fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true">
          <div className="absolute inset-0 bg-black/60 backdrop-blur-[2px]" onClick={() => setRenameTarget(null)} />
          <div className="panel animate-fade-up relative w-full max-w-sm p-5 shadow-2xl shadow-black/40">
            <h2 className="text-sm font-semibold text-cvx-text">Rename snapshot</h2>
            <div className="mt-3">
              <Input
                value={renameValue}
                onChange={(e) => setRenameValue(e.target.value)}
                autoFocus
                onKeyDown={(e) => {
                  if (e.key === "Enter" && renameValue.trim() && renameValue !== renameTarget.currentName) {
                    op.mutate({ snap: renameTarget.snap, action: "rename", newName: renameValue.trim() });
                    setRenameTarget(null);
                  }
                }}
              />
            </div>
            <div className="mt-4 flex justify-end gap-2">
              <Button size="sm" onClick={() => setRenameTarget(null)}>Cancel</Button>
              <Button
                size="sm"
                variant="primary"
                disabled={!renameValue.trim() || renameValue === renameTarget.currentName || op.isPending}
                onClick={() => {
                  op.mutate({ snap: renameTarget.snap, action: "rename", newName: renameValue.trim() });
                  setRenameTarget(null);
                }}
              >
                Rename
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
