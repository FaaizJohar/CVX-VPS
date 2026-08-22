export interface User {
  id: string;
  email: string;
  name: string;
  role: "owner" | "admin" | "user";
  status: string;
  totp_enabled: boolean;
  last_login_at: string | null;
  created_at: string;
}

export interface NodeInfo {
  id: string;
  name: string;
  location: string;
  hostname: string;
  public_ip: string;
  description: string;
  status: string;
  kind?: "agent" | "local";
  agent_version: string | null;
  lxd_version: string | null;
  os_name: string | null;
  os_version: string | null;
  architecture: string | null;
  cpu_model: string | null;
  cpu_cores: number | null;
  ram_total_mb: number | null;
  storage_total_gb: number | null;
  storage_driver: string | null;
  cpu_percent: number | null;
  ram_used_mb: number | null;
  storage_used_gb: number | null;
  load1: number | null;
  uptime_seconds: number | null;
  enrolled_at: string | null;
  last_heartbeat_at: string | null;
  created_at: string;
}

export interface VPS {
  id: string;
  node_id: string;
  owner_id: string;
  image_id: string | null;
  name: string;
  hostname: string;
  status: string;
  deployment_mode?: "node" | "local";
  cpu_limit: number;
  ram_mb: number;
  swap_mb: number;
  disk_gb: number;
  process_limit: number;
  ipv4: string | null;
  ipv6: string | null;
  mac_address: string | null;
  network_name: string | null;
  dns_servers: string[];
  ssh_keys: string[];
  password_auth_enabled: boolean;
  privileged: boolean;
  provision_error: string | null;
  created_at: string;
  updated_at: string;
}

export interface Image {
  id: string;
  alias: string;
  display_name: string;
  os_family: string;
  version: string;
  architecture: string;
  source_type: string;
  source_remote: string;
  source_identifier: string;
  description: string;
  size_mb: number | null;
  enabled: boolean;
  min_cpu: number;
  min_ram_mb: number;
  min_disk_gb: number;
}

export interface Snapshot {
  id: string;
  vps_id: string;
  name: string;
  description: string | null;
  stateful: boolean;
  size_bytes: number | null;
  created_at: string;
}

export interface Backup {
  id: string;
  vps_id: string;
  node_id: string;
  name: string;
  status: string;
  size_bytes: number | null;
  checksum_sha256: string | null;
  storage_path: string | null;
  optimized_storage: boolean;
  error: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface LogItem {
  id: string;
  source: string;
  severity: string;
  message: string;
  meta: Record<string, unknown>;
  vps_id: string | null;
  node_id: string | null;
  created_at: string;
}

export interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface MetricPoint {
  ts: string;
  cpu_percent: number | null;
  mem_used_mb: number | null;
  mem_total_mb: number | null;
  swap_used_mb: number | null;
  disk_used_gb: number | null;
  disk_total_gb: number | null;
  disk_read_bps: number | null;
  disk_write_bps: number | null;
  net_rx_bps: number | null;
  net_tx_bps: number | null;
}

export interface LocalStatus {
  available: boolean;
  reason?: "disabled" | "no_lxd_socket" | "lxd_unreachable";
  node_id?: string | null;
  cpu_cores?: number;
  ram_total_mb?: number;
  storage_total_gb?: number;
  storage_used_gb?: number;
  socket_path?: string;
  lxd_version?: string;
  os_name?: string;
  hostname?: string;
}
