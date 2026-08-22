import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { VPS } from "@/types";
import { Card, CardHeader } from "@/components/ui/Card";

interface ConfigResponse {
  db_config: Record<string, unknown>;
  provider_config: Record<string, unknown>;
}

export default function DevicesTab({ vps }: { vps: VPS }) {
  const { data, isLoading } = useQuery({
    queryKey: ["vps", vps.id, "config"],
    queryFn: () => api.get<ConfigResponse>(`/api/v1/vps/${vps.id}/config`),
  });

  const devices = extractDevices(data?.provider_config ?? {});

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader title="Attached devices" />
        {isLoading ? (
          <p className="px-4 py-8 text-center text-sm text-cvx-faint">Loading…</p>
        ) : devices.length === 0 ? (
          <p className="px-4 py-8 text-center text-sm text-cvx-faint">
            No extra devices attached. The root disk and default NIC are managed implicitly.
          </p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-cvx-border text-left text-[11px] uppercase tracking-wider text-cvx-faint">
                <th className="px-4 py-2 font-medium">Type</th>
                <th className="px-4 py-2 font-medium">Name</th>
                <th className="px-4 py-2 font-medium">Properties</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-cvx-border">
              {devices.map((d) => (
                <tr key={d.name}>
                  <td className="mono-data px-4 py-2">{d.type}</td>
                  <td className="mono-data px-4 py-2">{d.name}</td>
                  <td className="mono-data px-4 py-2 text-xs text-cvx-muted">
                    {Object.entries(d.props)
                      .map(([k, v]) => `${k}=${String(v)}`)
                      .join("  ")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      <Card>
        <CardHeader title="About devices" />
        <p className="px-4 py-3 text-xs leading-relaxed text-cvx-muted">
          Devices (extra disks, NICs, unix sockets, GPU passthrough) are advanced attachments
          managed through raw configuration. Add them from the Configuration tab using
          provider device keys (e.g. <span className="font-mono">disk.*.path</span>). Invalid or
          conflicting device definitions are rejected by the node before apply.
        </p>
      </Card>
    </div>
  );
}

interface DeviceEntry {
  type: string;
  name: string;
  props: Record<string, unknown>;
}

function extractDevices(config: Record<string, unknown>): DeviceEntry[] {
  const out: DeviceEntry[] = [];
  for (const [key, value] of Object.entries(config)) {
    const m = /^(disk|nic|unix-char|unix-block|gpu|usb|tpm|pci)\.([^\s.]+)(?:\.(.+))?$/.exec(key);
    if (!m) continue;
    const type = m[1];
    const name = m[2];
    const prop = m[3];
    if (!type || !name) continue;
    let entry = out.find((d) => d.type === type && d.name === name);
    if (!entry) {
      entry = { type, name, props: {} };
      out.push(entry);
    }
    if (prop && value !== null && value !== "") entry.props[prop] = value;
  }
  return out;
}
