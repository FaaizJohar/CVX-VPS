import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api";
import type { User } from "@/types";
import { useAuth } from "@/lib/auth";
import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { Input, Select } from "@/components/ui/Input";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { fmtDate, fmtRelative } from "@/lib/format";

export default function AdminUsersPage() {
  const qc = useQueryClient();
  const { user: me } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({ email: "", password: "", name: "" });

  const { data: users, isLoading } = useQuery({
    queryKey: ["users"],
    queryFn: () => api.get<User[]>("/api/v1/users"),
  });

  const invalidate = () => void qc.invalidateQueries({ queryKey: ["users"] });

  const create = useMutation({
    mutationFn: () => api.post("/api/v1/users", form),
    onSuccess: () => {
      setShowAdd(false);
      setError(null);
      setForm({ email: "", password: "", name: "" });
      invalidate();
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : "Failed to create user."),
  });

  const patch = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Record<string, unknown> }) =>
      api.patch(`/api/v1/users/${id}`, body),
    onSuccess: invalidate,
    onError: (e) => setError(e instanceof ApiError ? e.message : "Update failed."),
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold">Users</h1>
          <p className="text-xs text-cvx-faint">Panel accounts and role assignment.</p>
        </div>
        <Button variant="primary" onClick={() => setShowAdd(!showAdd)}>
          {showAdd ? "Cancel" : "Create user"}
        </Button>
      </div>

      {error && (
        <p className="rounded-md border border-cvx-danger/30 bg-cvx-danger/5 px-3 py-2 text-xs text-cvx-danger">
          {error}
        </p>
      )}

      {showAdd && (
        <Card>
          <CardHeader title="Create user" />
          <form
            className="grid gap-3 p-4 md:grid-cols-3"
            onSubmit={(e) => {
              e.preventDefault();
              create.mutate();
            }}
          >
            <Input required type="email" placeholder="email@example.com" value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })} />
            <Input required type="password" minLength={10} placeholder="Password (min 10 chars)" value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })} />
            <Input placeholder="Full name (optional)" value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })} />
            <div className="md:col-span-3">
              <Button type="submit" variant="primary" disabled={create.isPending}>
                {create.isPending ? "Creating…" : "Create"}
              </Button>
            </div>
          </form>
        </Card>
      )}

      {isLoading ? (
        <p className="py-8 text-center text-sm text-cvx-faint">Loading…</p>
      ) : (
        <Card>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-cvx-border text-left text-[11px] uppercase tracking-wider text-cvx-faint">
                <th className="px-4 py-2.5 font-medium">User</th>
                <th className="px-4 py-2.5 font-medium">Role</th>
                <th className="px-4 py-2.5 font-medium">Status</th>
                <th className="px-4 py-2.5 font-medium">Last login</th>
                <th className="px-4 py-2.5 font-medium">Created</th>
                <th className="px-4 py-2.5 font-medium"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-cvx-border">
              {(users ?? []).map((u) => {
                const isSelf = me?.id === u.id;
                return (
                  <tr key={u.id} className="hover:bg-cvx-raised/40">
                    <td className="px-4 py-2.5">
                      <p>{u.name || "—"}{isSelf && <span className="ml-1 text-[10px] text-cvx-accent">(you)</span>}</p>
                      <p className="font-mono text-[11px] text-cvx-faint">{u.email}</p>
                    </td>
                    <td className="px-4 py-2.5">
                      <Select
                        value={u.role}
                        disabled={isSelf || patch.isPending}
                        onChange={(e) => patch.mutate({ id: u.id, body: { role: e.target.value } })}
                        className="w-28"
                      >
                        <option value="user">user</option>
                        <option value="admin">admin</option>
                        <option value="owner">owner</option>
                      </Select>
                    </td>
                    <td className="px-4 py-2.5"><StatusBadge status={u.status} /></td>
                    <td className="px-4 py-2.5 text-xs text-cvx-faint">{fmtRelative(u.last_login_at)}</td>
                    <td className="px-4 py-2.5 text-xs text-cvx-faint">{fmtDate(u.created_at)}</td>
                    <td className="px-4 py-2.5 text-right">
                      {!isSelf && (
                        <Button
                          size="sm"
                          variant={u.status === "active" ? "danger" : "outline"}
                          disabled={patch.isPending}
                          onClick={() =>
                            patch.mutate({
                              id: u.id,
                              body: { status: u.status === "active" ? "disabled" : "active" },
                            })
                          }
                        >
                          {u.status === "active" ? "Disable" : "Enable"}
                        </Button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
