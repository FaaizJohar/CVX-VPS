import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { api, ApiError } from "@/lib/api";
import type { Image, LocalStatus, NodeInfo } from "@/types";
import { Button } from "@/components/ui/Button";
import { Field, Input } from "@/components/ui/Input";
import { PageLoader } from "@/components/ui/Loading";
import { ResourceSlider } from "@/components/ui/ResourceSlider";

const STEPS = [
  "Deployment",
  "Operating System",
  "Resources",
  "Network",
  "Access",
  "Review",
] as const;

interface Draft {
  mode: "local" | "node" | "";
  node_id: string;
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
  mode: "",
  node_id: "",
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
  const { data: localStatus } = useQuery({
    queryKey: ["nodes", "local", "status"],
    queryFn: () => api.get<LocalStatus>("/api/v1/nodes/local/status"),
    staleTime: 15_000,
  });

  const agentNodes = useMemo(
    () => (nodes ?? []).filter((n) => n.kind !== "local" && n.status === "online"),
    [nodes],
  );
  const selectedNode = agentNodes.find((n) => n.id === draft.node_id) ?? null;
  const selectedImage = (images ?? []).find((i) => i.id === draft.image_id);
  const localAvailable = localStatus?.available === true;

  useEffect(() => {
    if (draft.mode !== "") return;
    if (agentNodes.length === 0 && localAvailable) {
      setDraft((d) => ({ ...d, mode: "local" }));
    } else if (agentNodes.length > 0 && !localAvailable) {
      setDraft((d) => ({
        ...d,
        mode: "node",
        node_id: d.node_id || (agentNodes[0]?.id ?? ""),
      }));
    }
  }, [draft.mode, agentNodes, localAvailable]);

  const create = useMutation({
    mutationFn: () =>
      api.post<{ job_id: string; vps_id: string; status: string }>("/api/v1/vps", {
        deployment_mode: draft.mode,
        node_id: draft.mode === "node" ? (selectedNode?.id ?? undefined) : undefined,
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
        root_password:
          draft.password_auth_enabled && draft.root_password ? draft.root_password : null,
      }),
    onSuccess: (job) => {
      void qc.invalidateQueries({ queryKey: ["vps"] });
      void qc.invalidateQueries({ queryKey: ["nodes"] });
      navigate(`/app/vps/${job.vps_id}`);
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : "Creation failed."),
  });

  function canAdvance(): boolean {
    if (step === 0) {
      if (!draft.mode) return false;
      if (draft.mode === "local") return localAvailable;
      return Boolean(selectedNode);
    }
    if (step === 1) return Boolean(selectedImage);
    if (step === 3 && !draft.name.trim()) return false;
    if (step === 4 && draft.password_auth_enabled) return draft.root_password.length >= 8;
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

  const noTargets = agentNodes.length === 0 && !localAvailable;

  return (
    <form onSubmit={onSubmit} className="mx-auto max-w-2xl space-y-6">
      <header>
        <h1 className="font-display text-xl font-semibold tracking-tight">Create VPS</h1>
        <ol aria-label="Progress" className="mt-4 flex gap-1">
          {STEPS.map((label, i) => (
            <li key={label} className="flex-1">
              <button
                type="button"
                aria-current={i === step ? "step" : undefined}
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
              <div
                role="presentation"
                className={`mt-1 h-px ${i <= step ? "bg-cvx-accent/60" : "bg-cvx-border"}`}
              />
            </li>
          ))}
        </ol>
      </header>

      <div className="panel min-h-[320px] p-5">
        {step === 0 && (
          <div className="space-y-5">
            <div>
              <h2 className="text-base font-semibold text-cvx-text">Where should this VPS run?</h2>
              <p className="mt-1 text-xs text-cvx-faint">
                You can move workloads between targets later — pick where it starts.
              </p>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <button
                type="button"
                disabled={agentNodes.length === 0}
                onClick={() =>
                  setDraft({
                    ...draft,
                    mode: "node",
                    node_id: draft.node_id || agentNodes[0]?.id || "",
                  })
                }
                aria-pressed={draft.mode === "node"}
                className={`group flex flex-col rounded-lg border p-4 text-left transition-all duration-200 ${
                  draft.mode === "node"
                    ? "border-cvx-accent bg-cvx-accent/10 ring-1 ring-cvx-accent/40"
                    : agentNodes.length > 0
                      ? "border-cvx-border hover:border-cvx-accent/40 hover:bg-cvx-accent/5"
                      : "cursor-not-allowed border-cvx-border opacity-50"
                }`}
              >
                <div className="flex items-center justify-between">
                  <span aria-hidden className="text-lg">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                      <rect x="4" y="4" width="16" height="6" rx="1" /><rect x="4" y="14" width="16" height="6" rx="1" />
                      <circle cx="8" cy="7" r="1" fill="currentColor" /><circle cx="8" cy="17" r="1" fill="currentColor" />
                    </svg>
                  </span>
                  <span className="rounded border border-cvx-border bg-cvx-raised px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wider text-cvx-muted">
                    {agentNodes.length} online
                  </span>
                </div>
                <p className="mt-3 text-sm font-medium">Deploy on Node</p>
                <p className="mt-1 text-xs leading-relaxed text-cvx-faint">
                  Run this VPS on a connected infrastructure node.
                </p>
                <p className="mt-3 space-x-1.5 text-[10px] uppercase tracking-wider text-cvx-faint">
                  <span>Remote</span><span>·</span><span>Node agent</span><span>·</span><span>Multi-location</span>
                </p>
                <p className={`mt-auto pt-3 text-xs font-medium ${draft.mode === "node" ? "text-cvx-accent" : "text-cvx-muted group-hover:text-cvx-text"}`}>
                  Choose Node →
                </p>
              </button>

              <button
                type="button"
                disabled={!localAvailable}
                onClick={() => setDraft({ ...draft, mode: "local" })}
                aria-pressed={draft.mode === "local"}
                className={`group flex flex-col rounded-lg border p-4 text-left transition-all duration-200 ${
                  draft.mode === "local"
                    ? "border-violet-500/60 bg-violet-500/10 ring-1 ring-violet-500/40"
                    : localAvailable
                      ? "border-cvx-border hover:border-violet-500/40 hover:bg-violet-500/5"
                      : "cursor-not-allowed border-cvx-border opacity-50"
                }`}
              >
                <div className="flex items-center justify-between">
                  <span aria-hidden className="text-lg">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                      <rect x="2" y="3" width="20" height="14" rx="2" /><path d="M8 21h8M12 18v3" />
                    </svg>
                  </span>
                  {localAvailable && (
                    <span className="rounded border border-emerald-500/30 bg-emerald-500/10 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wider text-emerald-400">
                      Ready
                    </span>
                  )}
                </div>
                <p className="mt-3 text-sm font-medium">Deploy Locally</p>
                <p className="mt-1 text-xs leading-relaxed text-cvx-faint">
                  Run this VPS directly on the machine running CVX.
                </p>
                <p className="mt-3 space-x-1.5 text-[10px] uppercase tracking-wider text-cvx-faint">
                  <span>Local compute</span><span>·</span><span>No agent</span>
                  {localStatus?.resources && (
                    <>
                      <span>·</span>
                      <span>{localStatus.resources.cpu_cores} cores</span>
                    </>
                  )}
                </p>
                <p className={`mt-auto pt-3 text-xs font-medium ${draft.mode === "local" ? "text-violet-400" : "text-cvx-muted group-hover:text-cvx-text"}`}>
                  Use This Machine →
                </p>
              </button>
            </div>

            {draft.mode === "node" && (
              <Field label="Target node" hint="Only online nodes can accept deployments">
                <select
                  value={selectedNode?.id ?? ""}
                  onChange={(e) => setDraft({ ...draft, node_id: e.target.value })}
                  className="input-base"
                  aria-label="Target node"
                >
                  {agentNodes.map((n) => (
                    <option key={n.id} value={n.id}>
                      {n.name} — {n.location}
                    </option>
                  ))}
                </select>
              </Field>
            )}
          </div>
        )}

        {step === 1 && (
          <div className="space-y-4">
            <p className="stat-label">Operating system</p>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              {(images ?? []).map((img) => (
                <button
                  key={img.id}
                  type="button"
                  onClick={() => setDraft({ ...draft, image_id: img.id })}
                  aria-pressed={draft.image_id === img.id}
                  className={`rounded-lg border p-3.5 text-left transition-all duration-150 ${
                    draft.image_id === img.id
                      ? "border-cvx-accent bg-cvx-accent/10 ring-1 ring-cvx-accent/40"
                      : "border-cvx-border hover:border-cvx-border-strong hover:bg-cvx-raised/40"
                  }`}
                >
                  <div className="flex items-start justify-between">
                    <div>
                      <p className="text-sm font-medium text-cvx-text">{img.display_name}</p>
                      <p className="mt-0.5 text-[11px] text-cvx-faint">
                        {img.os_family} · {img.architecture}
                      </p>
                    </div>
                    {draft.image_id === img.id && (
                      <span className="shrink-0 text-cvx-accent">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <path d="M20 6L9 17l-5-5" />
                        </svg>
                      </span>
                    )}
                  </div>
                  {img.size_mb ? (
                    <p className="mt-1.5 text-[10px] text-cvx-faint">{img.size_mb} MB</p>
                  ) : null}
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

        {step === 2 && (
          <div className="space-y-6">
            <ResourceSlider
              label="CPU cores"
              unit="vCPU"
              value={draft.cpu_limit}
              min={1}
              max={32}
              onChange={(v) => setDraft({ ...draft, cpu_limit: v })}
              presets={[1, 2, 4, 8, 16]}
            />
            <ResourceSlider
              label="Memory"
              unit="MB"
              value={draft.ram_mb}
              min={256}
              max={65536}
              step={256}
              onChange={(v) => setDraft({ ...draft, ram_mb: v })}
              presets={[512, 1024, 2048, 4096, 8192, 16384]}
            />
            <ResourceSlider
              label="Swap"
              unit="MB"
              value={draft.swap_mb}
              min={0}
              max={16384}
              step={256}
              onChange={(v) => setDraft({ ...draft, swap_mb: v })}
              presets={[0, 512, 1024, 2048, 4096]}
            />
            <ResourceSlider
              label="Disk"
              unit="GB"
              value={draft.disk_gb}
              min={5}
              max={500}
              onChange={(v) => setDraft({ ...draft, disk_gb: v })}
              presets={[10, 25, 50, 100, 200]}
            />
            <ResourceSlider
              label="Process limit"
              unit=""
              value={draft.process_limit}
              min={32}
              max={4096}
              step={32}
              onChange={(v) => setDraft({ ...draft, process_limit: v })}
              presets={[64, 128, 256, 512, 1024]}
            />
          </div>
        )}

        {step === 3 && (
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

        {step === 4 && (
          <div className="space-y-5">
            <div className="rounded-lg border border-cvx-accent/20 bg-cvx-accent/5 p-3.5">
              <p className="text-xs font-medium text-cvx-accent">Recommended: Use SSH keys</p>
              <p className="mt-1 text-[11px] leading-relaxed text-cvx-muted">
                SSH keys are more secure than passwords and are set up once.
                You can paste your public key below.
              </p>
            </div>
            <Field label="SSH public keys" hint="One OpenSSH key per line (ssh-ed25519, ssh-rsa…)">
              <textarea
                className="input-base min-h-[120px] font-mono text-xs"
                value={draft.ssh_keys}
                onChange={(e) => setDraft({ ...draft, ssh_keys: e.target.value })}
                placeholder="ssh-ed25519 AAAA… user@host"
                aria-label="SSH public keys"
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
                  The password is delivered once and never stored by CVX.
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

        {step === 5 && (
          <div className="space-y-4">
            <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm">
              {[
                [
                  "Deployment",
                  draft.mode === "local"
                    ? "This machine (local LXD)"
                    : selectedNode
                      ? `${selectedNode.name} (${selectedNode.location})`
                      : "—",
                ],
                ["OS", selectedImage?.display_name ?? "—"],
                ["Name", draft.name],
                ["Hostname", draft.hostname || `${draft.name}.local`],
                ["CPU", `${draft.cpu_limit} vCPU`],
                ["RAM", `${(draft.ram_mb / 1024).toFixed(1)} GB`],
                ["Swap", `${(draft.swap_mb / 1024).toFixed(1)} GB`],
                ["Disk", `${draft.disk_gb} GB`],
                ["Process limit", String(draft.process_limit)],
                ["IPv4", draft.ipv4 || "DHCP"],
                ["IPv6", draft.ipv6 || "—"],
                [
                  "Access",
                  `${
                    draft.ssh_keys.trim() ? "SSH keys" : ""
                  }${draft.password_auth_enabled ? `${draft.ssh_keys.trim() ? " + " : ""}password` : ""}` ||
                    "—",
                ],
              ].map(([k, v]) => (
                <div key={k}>
                  <dt className="stat-label">{k}</dt>
                  <dd className="mt-0.5 break-all">{v}</dd>
                </div>
              ))}
            </dl>
          </div>
        )}
      </div>

      {(error || noTargets) && (
        <p
          role="alert"
          className="rounded-md border border-cvx-danger/30 bg-cvx-danger/5 px-3 py-2 text-xs text-cvx-danger"
        >
          {error ??
            "No deployment targets are available yet — enroll an online node or enable local deployment."}
        </p>
      )}

      <div className="flex items-center justify-between">
        <Button type="button" variant="ghost" disabled={step === 0} onClick={() => setStep(step - 1)}>
          Back
        </Button>
        <Button type="submit" variant="primary" disabled={!canAdvance() || create.isPending}>
          {step < STEPS.length - 1 ? "Continue" : create.isPending ? "Deploying…" : "Deploy VPS"}
        </Button>
      </div>
    </form>
  );
}
