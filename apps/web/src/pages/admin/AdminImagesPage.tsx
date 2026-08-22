import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api";
import type { Image } from "@/types";
import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Field } from "@/components/ui/Input";

export default function AdminImagesPage() {
  const qc = useQueryClient();
  const [showAdd, setShowAdd] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({
    alias: "",
    display_name: "",
    os_family: "",
    version: "",
    source_identifier: "",
    description: "",
  });

  const { data: images, isLoading } = useQuery({
    queryKey: ["images", "admin"],
    queryFn: () => api.get<Image[]>("/api/v1/images?include_disabled=true"),
  });

  const invalidate = () => void qc.invalidateQueries({ queryKey: ["images"] });

  const create = useMutation({
    mutationFn: () =>
      api.post("/api/v1/images", {
        ...form,
        alias: form.alias.trim(),
        display_name: form.display_name.trim() || form.alias.trim(),
      }),
    onSuccess: () => {
      setShowAdd(false);
      setError(null);
      setForm({ alias: "", display_name: "", os_family: "", version: "", source_identifier: "", description: "" });
      invalidate();
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : "Failed to create image."),
  });

  const toggle = useMutation({
    mutationFn: (img: Image) => api.patch(`/api/v1/images/${img.id}`, { enabled: !img.enabled }),
    onSuccess: invalidate,
    onError: (e) => setError(e instanceof ApiError ? e.message : "Failed."),
  });

  const remove = useMutation({
    mutationFn: (img: Image) => api.delete(`/api/v1/images/${img.id}`),
    onSuccess: invalidate,
    onError: (e) => setError(e instanceof ApiError ? e.message : "Failed to delete image."),
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold">Images</h1>
          <p className="text-xs text-cvx-faint">OS templates available when creating VPS.</p>
        </div>
        <Button variant="primary" onClick={() => setShowAdd(!showAdd)}>
          {showAdd ? "Cancel" : "Add image"}
        </Button>
      </div>

      {error && (
        <p className="rounded-md border border-cvx-danger/30 bg-cvx-danger/5 px-3 py-2 text-xs text-cvx-danger">
          {error}
        </p>
      )}

      {showAdd && (
        <Card>
          <CardHeader title="Register image" />
          <form
            className="grid gap-3 p-4 md:grid-cols-2"
            onSubmit={(e) => {
              e.preventDefault();
              create.mutate();
            }}
          >
            <Field label="Alias" hint="Unique, e.g. ubuntu-24.04">
              <Input required value={form.alias} onChange={(e) => setForm({ ...form, alias: e.target.value })} />
            </Field>
            <Field label="Display name">
              <Input required value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} />
            </Field>
            <Field label="OS family">
              <Input required value={form.os_family} onChange={(e) => setForm({ ...form, os_family: e.target.value })} placeholder="ubuntu" />
            </Field>
            <Field label="Version">
              <Input required value={form.version} onChange={(e) => setForm({ ...form, version: e.target.value })} placeholder="24.04" />
            </Field>
            <Field label="Source identifier" hint="Remote image fingerprint or alias">
              <Input required value={form.source_identifier} onChange={(e) => setForm({ ...form, source_identifier: e.target.value })} placeholder="ubuntu/24.04/cloud" />
            </Field>
            <Field label="Description">
              <Input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
            </Field>
            <div className="md:col-span-2">
              <Button type="submit" variant="primary" disabled={create.isPending}>
                {create.isPending ? "Creating…" : "Create image"}
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
                <th className="px-4 py-2.5 font-medium">Image</th>
                <th className="px-4 py-2.5 font-medium">Alias</th>
                <th className="px-4 py-2.5 font-medium">Arch</th>
                <th className="px-4 py-2.5 font-medium">Min specs</th>
                <th className="px-4 py-2.5 font-medium">Enabled</th>
                <th className="px-4 py-2.5 font-medium"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-cvx-border">
              {(images ?? []).map((img) => (
                <tr key={img.id} className="hover:bg-cvx-raised/40">
                  <td className="px-4 py-2.5">
                    <p>{img.display_name}</p>
                    <p className="text-[11px] text-cvx-faint">{img.description || img.source_identifier}</p>
                  </td>
                  <td className="mono-data px-4 py-2.5 text-cvx-muted">{img.alias}</td>
                  <td className="mono-data px-4 py-2.5">{img.architecture}</td>
                  <td className="mono-data px-4 py-2.5 text-xs text-cvx-faint">
                    {img.min_cpu} vCPU · {img.min_ram_mb / 1024} GB · {img.min_disk_gb} GB
                  </td>
                  <td className="px-4 py-2.5">
                    <span className={img.enabled ? "text-emerald-400" : "text-zinc-500"}>
                      {img.enabled ? "Yes" : "No"}
                    </span>
                  </td>
                  <td className="px-4 py-2.5">
                    <div className="flex justify-end gap-2">
                      <Button size="sm" variant="ghost" onClick={() => toggle.mutate(img)} disabled={toggle.isPending}>
                        {img.enabled ? "Disable" : "Enable"}
                      </Button>
                      <Button size="sm" variant="danger" onClick={() => {
                        if (confirm(`Delete image "${img.display_name}"?`)) remove.mutate(img);
                      }}>
                        Delete
                      </Button>
                    </div>
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
