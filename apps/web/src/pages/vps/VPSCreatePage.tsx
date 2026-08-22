import { useMemo, useState } from "react";
import type { FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { api, ApiError } from "@/lib/api";
import type { Image, NodeInfo } from "@/types";
import { Button } from "@/components/ui/Button";
import { Field, Input, Select } from "@/components/ui/Input";
import { PageLoader } from "@/components/ui/Loading";

const STEPS = ["Operating System", "Resources", "Network", "Access", "Review"] as const;

interface Draft {
  image_id: string;
  name: string;
  hostname: string;
  cpu_limit: number;
  ram_mb: number;
  swap_mb: number;
  disk_gb: number;
  process_limit: number;
  network_name: string;
  ipv4: string;
  ipv6: string;
  dns_servers: string;
  ssh_keys: string;
  password_auth_enabled: boolean;
  root_password: string;
}

const initialDraft: Draft = {
  image_id: "",
  name: "",
  hostname: "",
  cpu_limit: 1,
  ram_mb: 1024,
  swap_mb: 0,
  disk_gb: 10,
  process_limit: 256,
  network_name: "",
  ipv4: "",
  ipv6: "",
  dns_servers: "",
  ssh_keys: "",
  password_auth_enabled: false,
  root_password: "",
};

export default function VPSCreatePage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [step, setStep] = useState(0);
  const [draft, setDraft] = useState<Draft>(initialDraft);
  const [error, setError] = useState<string | null>(null);

  const { data: nodes } = useQuery({
    queryKey: ["nodes"],
    queryFn: () => api.get<NodeInfo[]>("/api/v1/nodes"),
  });
  const { data: images } = useQuery({
    queryKey: ["images"],
    queryFn: () => api.get<Image[]>("/api/v1/images"),
  });

  const onlineNodes = useMemo(
    () => (nodes ?? []).filter((n) => n.status === "online"),
    [nodes],
  );
  const [nodeId, setNodeId] = useState("");
  const selectedNode = onlineNodes.find((n) => n.id === nodeId) ?? onlineNodes[0];
  const selectedImage = (images ?? []).find((i) => i.id === draft.image_id);

  const create = useMutation({
    mutationFn: () =>
      api.post<{ id: string }>("/api/v1/vps", {
        node_id: selectedNode?.id,
        image_id: draft.image_id || undefined,
        name: draft.name,
        hostname: draft.hostname || `${draft.name}.local`,
        cpu_limit: draft.cpu_limit,
        ram_mb: draft.ram_mb,
        swap_mb: draft.swap_mb,
        disk_gb: draft.disk_gb,
        process_limit: draft.process_limit,
        network_name: draft.network_name || null,
        ipv4: draft.ipv4 || null,
        ipv6: draft.ipv6 || null,
        dns_servers: draft.dns_servers ? draft.dns_servers.split(/[\s,]+/).filter(Boolean) : [],
        ssh_keys: draft.ssh_keys ? draft.ssh_keys.split("\n").map((s) => s.trim()).filter(Boolean) : [],
        password_auth_enabled: draft.password_auth_enabled,
        root_password: draft.password_auth_enabled && draft.root_password ? draft.root_password : null,
      }),
    onSuccess: (vps) => {
      void qc.invalidateQueries({ queryKey: ["vps"] });
      navigate(`/app/vps/${vps.id}`);
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : "Creation failed."),
  });

  function canAdvance(): boolean {
    if (step === 0) return Boolean(selectedImage);
    if (step === 3 && draft.password_auth_enabled) return draft.root_password.length >= 8;
    return true;
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (step < STEPS.length - 1) {
      if (canAdvance()) setStep(step + 1);
      return;
    }
    setError(null);
    create.mutate();
  }

  if (!nodes || !images) return <PageLoader />;

  if (onlineNodes.length === 0) {
    return (
      <div className="mx-auto max-w-lg py-16 text-center">
        <h2 className="text-lg font-medium">No online nodes</h2>
        <p className="mt-2 text-sm text-cvx-muted">
          A node must be enrolled and online before you can provision VPS.
        </p>
        <Button className="mt-4" onClick={() => navigate("/app/admin/nodes")}>
          Go to Nodes
        </Button>
      </div>
    );
  }

  return (
    <form onSubmit={onSubmit} className="mx-auto max-w-2xl space-y-6">
      <header>
        <h1 className="text-xl font-semibold">Create VPS</h1>
        {/* Step indicator */}
        <ol className="mt-4 flex gap-1">
          {STEPS.map((label, i) => (
            <li key={label} className="flex-1">
              <button
                type="button"
                onClick={() => i < step && setStep(i)}
                className={`w-full rounded-sm px-2 py-1.5 text-left text-[11px] uppercase tracking-wider transition-colors ${
                  i === step
                    ? "bg-cvx-accent/15 text-cvx-accent"
                    : i < step
                      ? "text-cvx-muted hover:bg-cvx-raised"
                      : "text-cvx-faint"
                }`}
              >
                <span className="font-mono">{String(i + 1).padStart(2, "0")}</span> {label}
              </button>
              <div className={`mt-1 h-px ${i <= step ? "bg-cvx-accent/60" : "bg-cvx-border"}`} />
            </li>
          ))}
        </ol>
      </header>

      <div className="panel min-h-[320px] p-5">
        {step === 0 && (
          <div className="space-y-4">
            <p className="stat-label">Node</p>
            <Select value={selectedNode?.id ?? ""} onChange={(e) => setNodeId(e.target.value)}>
              {onlineNodes.map((n) => (
                <option key={n.id} value={n.id}>
                  {n.name} — {n.location}
                </option>
              ))}
            </Select>

            <p className="stat-label pt-2">Operating system</p>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              {(images ?? []).map((img) => (
                <button
                  key={img.id}
                  type="button"
                  onClick={() => setDraft({ ...draft, image_id: img.id })}
                  className={`rounded-md border p-3 text-left transition-colors ${
                    draft.image_id === img.id
                      ? "border-cvx-accent bg-cvx-accent/10"
                      : "border-cvx-border hover:border-cvx-border-strong"
                  }`}
                >
                  <p className="text-sm font-medium">{img.display_name}</p>
                  <p className="mt-0.5 text-xs text-cvx-faint">
                    {img.os_family} · {img.architecture}
                    {img.size_mb ? ` · ${img.size_mb} MB` : ""}
                  </p>
                </button>
              ))}
              {images?.length === 0 && (
                <p className="col-span-full py-4 text-center text-sm text-cvx-faint">
                  No images in the catalog. Ask an admin to add images.
                </p>
              )}
            </div>
          </div>
        )}

        {step === 1 && (
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
            <Field label="CPU cores">
              <Input type="number" min={1} max={64} value={draft.cpu_limit}
                onChange={(e) => setDraft({ ...draft, cpu_limit: Number(e.target.value) })} />
            </Field>
            <Field label="RAM (MB)">
              <Input type="number" min={128} step={128} value={draft.ram_mb}
                onChange={(e) => setDraft({ ...draft, ram_mb: Number(e.target.value) })} />
            </Field>
            <Field label="Swap (MB)">
              <Input type="number" min={0} step={128} value={draft.swap_mb}
                onChange={(e) => setDraft({ ...draft, swap_mb: Number(e.target.value) })} />
            </Field>
            <Field label="Disk (GB)">
              <Input type="number" min={5} value={draft.disk_gb}
                onChange={(e) => setDraft({ ...draft, disk_gb: Number(e.target.value) })} />
            </Field>
            <Field label="Process limit">
              <Input type="number" min={32} step={32} value={draft.process_limit}
                onChange={(e) => setDraft({ ...draft, process_limit: Number(e.target.value) })} />
            </Field>
          </div>
        )}

        {step === 2 && (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field label="VPS name" hint="Identifier used across CVX">
              <Input required value={draft.name} pattern="[a-zA-Z0-9][a-zA-Z0-9._-]*"
                onChange={(e) => setDraft({ ...draft, name: e.target.value })} placeholder="web-01" />
            </Field>
            <Field label="Hostname">
              <Input value={draft.hostname}
                onChange={(e) => setDraft({ ...draft, hostname: e.target.value })}
                placeholder="web01.example.com" />
            </Field>
            <Field label="IPv4" hint="Leave empty for DHCP on the bridge">
              <Input value={draft.ipv4} onChange={(e) => setDraft({ ...draft, ipv4: e.target.value })}
                placeholder="203.0.113.10" />
            </Field>
            <Field label="IPv6">
              <Input value={draft.ipv6} onChange={(e) => setDraft({ ...draft, ipv6: e.target.value })}
                placeholder="2001:db8::10" />
            </Field>
            <Field label="DNS servers" hint="Space or comma separated">
              <Input value={draft.dns_servers}
                onChange={(e) => setDraft({ ...draft, dns_servers: e.target.value })}
                placeholder="1.1.1.1 8.8.8.8" />
            </Field>
          </div>
        )}

        {step === 3 && (
          <div className="space-y-4">
            <Field label="SSH public keys" hint="One OpenSSH key per line (ssh-ed25519, ssh-rsa…)">
              <textarea
                className="input-base min-h-[120px] font-mono text-xs"
                value={draft.ssh_keys}
                onChange={(e) => setDraft({ ...draft, ssh_keys: e.target.value })}
                placeholder="ssh-ed25519 AAAA… user@host"
              />
            </Field>

            <label className="flex items-center gap-3 rounded-md border border-cvx-border p-3">
              <input
                type="checkbox"
                checked={draft.password_auth_enabled}
                onChange={(e) => setDraft({ ...draft, password_auth_enabled: e.target.checked })}
                className="h-4 w-4 accent-[#3d7bfd]"
              />
              <div>
                <p className="text-sm">Enable root password authentication</p>
                <p className="text-xs text-cvx-faint">
                  The password is delivered to the node once and never stored by CVX.
                </p>
              </div>
            </label>

            {draft.password_auth_enabled && (
              <Field label="Root password" hint="Minimum 8 characters. Shown once, never stored.">
                <Input
                  type="password"
                  minLength={8}
                  value={draft.root_password}
                  onChange={(e) => setDraft({ ...draft, root_password: e.target.value })}
                />
              </Field>
            )}
          </div>
        )}

        {step === 4 && (
          <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm">
            {[
              ["Node", selectedNode ? `${selectedNode.name} (${selectedNode.location})` : "—"],
              ["Operating system", selectedImage?.display_name ?? "—"],
              ["Name", draft.name],
              ["Hostname", draft.hostname || `${draft.name}.local`],
              ["CPU", `${draft.cpu_limit} vCPU`],
              ["RAM", `${(draft.ram_mb / 1024).toFixed(1)} GB`],
              ["Swap", `${(draft.swap_mb / 1024).toFixed(1)} GB`],
              ["Disk", `${draft.disk_gb} GB`],
              ["Process limit", String(draft.process_limit)],
              ["IPv4", draft.ipv4 || "DHCP"],
              ["IPv6", draft.ipv6 || "—"],
              ["Access", draft.ssh_keys.trim() ? "SSH keys" : "" + (draft.password_auth_enabled ? " + password" : "")],
            ].map(([k, v]) => (
              <div key={k}>
                <dt className="stat-label">{k}</dt>
                <dd className="mt-0.5 break-all">{v}</dd>
              </div>
            ))}
          </dl>
        )}
      </div>

      {error && (
        <p className="rounded-md border border-cvx-danger/30 bg-cvx-danger/5 px-3 py-2 text-xs text-cvx-danger">
          {error}
        </p>
      )}

      <div className="flex items-center justify-between">
        <Button type="button" variant="ghost" disabled={step === 0} onClick={() => setStep(step - 1)}>
          Back
        </Button>
        <Button type="submit" variant="primary" disabled={!canAdvance() || create.isPending}>
          {step < STEPS.length - 1 ? "Continue" : create.isPending ? "Provisioning…" : "Create VPS"}
        </Button>
      </div>
    </form>
  );
}
