import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/Loading";
import { Input } from "@/components/ui/Input";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { fmtDate } from "@/lib/format";

interface ApiKey {
  id: string;
  name: string;
  prefix: string;
  scopes: string[];
  status: string;
  last_used_at: string | null;
  expires_at: string | null;
  created_at: string;
}

export default function AdminApiKeysPage() {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<string | null>(null);

  const { data: keys, isLoading } = useQuery({
    queryKey: ["apikeys"],
    queryFn: () => api.get<ApiKey[]>("/api/v1/apikeys"),
  });

  const create = useMutation({
    mutationFn: () => api.post<{ key: string }>("/api/v1/apikeys", { name: name.trim() }),
    onSuccess: (d) => {
      setCreated(d.key);
      setName("");
      setError(null);
      void qc.invalidateQueries({ queryKey: ["apikeys"] });
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : "Failed to create API key."),
  });

  const revoke = useMutation({
    mutationFn: (id: string) => api.delete(`/api/v1/apikeys/${id}`),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["apikeys"] }),
    onError: (e) => setError(e instanceof ApiError ? e.message : "Revoke failed."),
  });

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-semibold">API keys</h1>
        <p className="text-xs text-cvx-faint">Programmatic access with your account's permissions.</p>
      </div>

      {error && (
        <p className="rounded-md border border-cvx-danger/30 bg-cvx-danger/5 px-3 py-2 text-xs text-cvx-danger">
          {error}
        </p>
      )}

      {created && (
        <Card className="border-emerald-500/30">
          <CardHeader title="API key created — copy it now (shown once)" />
          <div className="space-y-2 p-4">
            <code className="block break-all rounded-md border border-cvx-border bg-cvx-bg p-3 font-mono text-xs text-emerald-300">
              {created}
            </code>
            <Button size="sm" onClick={() => navigator.clipboard.writeText(created)}>Copy</Button>
          </div>
        </Card>
      )}

      <Card>
        <CardHeader title="Create key" />
        <form
          className="flex items-end gap-3 p-4"
          onSubmit={(e) => {
            e.preventDefault();
            create.mutate();
          }}
        >
          <div className="w-72">
            <label className="stat-label mb-1 block">Key name</label>
            <Input required value={name} onChange={(e) => setName(e.target.value)} placeholder="ci-pipeline" maxLength={64} />
          </div>
          <Button type="submit" variant="primary" disabled={create.isPending}>
            {create.isPending ? "Creating…" : "Generate"}
          </Button>
        </form>
      </Card>

      {isLoading ? (
        <p className="py-8 text-center text-sm text-cvx-faint">Loading…</p>
      ) : !keys || keys.length === 0 ? (
        <EmptyState title="No API keys" hint="Generate a key to authenticate scripts against the CVX API." />
      ) : (
        <Card>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-cvx-border text-left text-[11px] uppercase tracking-wider text-cvx-faint">
                <th className="px-4 py-2.5 font-medium">Name</th>
                <th className="px-4 py-2.5 font-medium">Prefix</th>
                <th className="px-4 py-2.5 font-medium">Last used</th>
                <th className="px-4 py-2.5 font-medium">Expires</th>
                <th className="px-4 py-2.5 font-medium">Status</th>
                <th className="px-4 py-2.5 font-medium"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-cvx-border">
              {keys.map((k) => (
                <tr key={k.id} className="hover:bg-cvx-raised/40">
                  <td className="px-4 py-2.5">{k.name}</td>
                  <td className="mono-data px-4 py-2.5 text-cvx-muted">{k.prefix}…</td>
                  <td className="px-4 py-2.5 text-xs text-cvx-faint">{k.last_used_at ? fmtDate(k.last_used_at) : "never"}</td>
                  <td className="px-4 py-2.5 text-xs text-cvx-faint">{k.expires_at ? fmtDate(k.expires_at) : "—"}</td>
                  <td className="px-4 py-2.5"><StatusBadge status={k.status} /></td>
                  <td className="px-4 py-2.5 text-right">
                    {k.status === "active" && (
                      <Button size="sm" variant="danger" onClick={() => {
                        if (confirm(`Revoke API key "${k.name}"? Clients using it will fail immediately.`))
                          revoke.mutate(k.id);
                      }}>
                        Revoke
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
