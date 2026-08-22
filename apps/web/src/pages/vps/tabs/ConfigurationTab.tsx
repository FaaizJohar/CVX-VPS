import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api";
import type { VPS } from "@/types";
import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Field } from "@/components/ui/Input";

interface ConfigResponse {
  db_config: Record<string, unknown>;
  provider_config: Record<string, unknown>;
}

export default function ConfigurationTab({ vps }: { vps: VPS }) {
  const qc = useQueryClient();

  // --- Resource limits (PATCH /vps/{id}) ---
  const [res, setRes] = useState({
    cpu_limit: String(vps.cpu_limit),
    ram_mb: String(vps.ram_mb),
    swap_mb: String(vps.swap_mb),
    disk_gb: String(vps.disk_gb),
    process_limit: String(vps.process_limit),
  });
  const [resMsg, setResMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const saveRes = useMutation({
    mutationFn: () =>
      api.patch(`/api/v1/vps/${vps.id}`, {
        cpu_limit: Number(res.cpu_limit),
        ram_mb: Number(res.ram_mb),
        swap_mb: Number(res.swap_mb),
        disk_gb: Number(res.disk_gb),
        process_limit: Number(res.process_limit),
      }),
    onSuccess: () => {
      setResMsg({ ok: true, text: "Resource limits updated." });
      void qc.invalidateQueries({ queryKey: ["vps", vps.id] });
    },
    onError: (e) =>
      setResMsg({ ok: false, text: e instanceof ApiError ? e.message : "Update failed." }),
  });

  // --- Raw provider config (GET/PUT /vps/{id}/config) ---
  const { data: cfg } = useQuery({
    queryKey: ["vps", vps.id, "config"],
    queryFn: () => api.get<ConfigResponse>(`/api/v1/vps/${vps.id}/config`),
  });

  const [rawText, setRawText] = useState("");
  const [rawDirty, setRawDirty] = useState(false);
  const [rawMsg, setRawMsg] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    if (!rawDirty && cfg) {
      setRawText(JSON.stringify(cfg.provider_config ?? {}, null, 2));
    }
  }, [cfg, rawDirty]);

  const saveRaw = useMutation({
    mutationFn: () => {
      const parsed: Record<string, string> = JSON.parse(rawText);
      return api.put(`/api/v1/vps/${vps.id}/config`, { config: parsed });
    },
    onSuccess: () => {
      setRawMsg({ ok: true, text: "Configuration applied on the node." });
      setRawDirty(false);
      void qc.invalidateQueries({ queryKey: ["vps", vps.id, "config"] });
    },
    onError: (e) => {
      const text =
        e instanceof ApiError ? e.message : e instanceof SyntaxError ? "Invalid JSON." : "Apply failed.";
      setRawMsg({ ok: false, text });
    },
  });

  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <Card>
        <CardHeader title="Resource limits" />
        <form
          className="grid grid-cols-2 gap-3 p-4"
          onSubmit={(e) => {
            e.preventDefault();
            saveRes.mutate();
          }}
        >
          <Field label="CPU limit (vCPU)">
            <Input type="number" min={1} max={64} value={res.cpu_limit}
              onChange={(e) => setRes({ ...res, cpu_limit: e.target.value })} />
          </Field>
          <Field label="Memory (MB)">
            <Input type="number" min={128} step={128} value={res.ram_mb}
              onChange={(e) => setRes({ ...res, ram_mb: e.target.value })} />
          </Field>
          <Field label="Swap (MB)">
            <Input type="number" min={0} step={128} value={res.swap_mb}
              onChange={(e) => setRes({ ...res, swap_mb: e.target.value })} />
          </Field>
          <Field label="Disk (GB)" hint="Grow-only on most storage drivers">
            <Input type="number" min={5} value={res.disk_gb}
              onChange={(e) => setRes({ ...res, disk_gb: e.target.value })} />
          </Field>
          <Field label="Process limit">
            <Input type="number" min={32} value={res.process_limit}
              onChange={(e) => setRes({ ...res, process_limit: e.target.value })} />
          </Field>
          <div className="col-span-2 flex items-center gap-3">
            <Button type="submit" variant="primary" disabled={saveRes.isPending}>
              {saveRes.isPending ? "Applying…" : "Apply limits"}
            </Button>
            {resMsg && (
              <span className={`text-xs ${resMsg.ok ? "text-emerald-400" : "text-cvx-danger"}`}>
                {resMsg.text}
              </span>
            )}
          </div>
        </form>
      </Card>

      <Card>
        <CardHeader title="Raw configuration" />
        <form
          className="space-y-3 p-4"
          onSubmit={(e) => {
            e.preventDefault();
            saveRaw.mutate();
          }}
        >
          <p className="text-xs leading-relaxed text-cvx-faint">
            Provider-level key/value configuration applied directly on the node. Managed keys
            (limits, network, security) are controlled by the panel and may be overwritten.
          </p>
          <textarea
            value={rawText}
            onChange={(e) => {
              setRawText(e.target.value);
              setRawDirty(true);
            }}
            spellCheck={false}
            rows={16}
            className="input-base font-mono text-xs leading-relaxed"
          />
          <div className="flex items-center gap-3">
            <Button type="submit" variant="primary" disabled={saveRaw.isPending || !rawDirty}>
              {saveRaw.isPending ? "Applying…" : "Apply configuration"}
            </Button>
            {rawDirty && !saveRaw.isPending && (
              <Button type="button" variant="ghost" onClick={() => setRawDirty(false)}>
                Discard changes
              </Button>
            )}
            {rawMsg && (
              <span className={`text-xs ${rawMsg.ok ? "text-emerald-400" : "text-cvx-danger"}`}>
                {rawMsg.text}
              </span>
            )}
          </div>
        </form>
      </Card>

      <Card className="xl:col-span-2">
        <CardHeader title="Panel-managed settings" />
        <pre className="max-h-64 overflow-auto p-4 font-mono text-xs text-cvx-muted scrollbar-thin">
          {JSON.stringify(cfg?.db_config ?? {}, null, 2)}
        </pre>
      </Card>
    </div>
  );
}
