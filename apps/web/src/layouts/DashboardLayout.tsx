import { useCallback, useEffect, useMemo, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth, useIsAdmin } from "@/lib/auth";
import { Spinner } from "@/components/ui/Loading";
import { CommandPalette } from "@/components/ui/CommandPalette";
import { DropdownMenu } from "@/components/ui/DropdownMenu";
import type { DropdownAction } from "@/components/ui/DropdownMenu";
import { Tooltip } from "@/components/ui/Tooltip";

const SIDEBAR_KEY = "cvx-sidebar-collapsed";
const SIDEBAR_W_EXPANDED = 14;  /* w-56 = 14rem */
const SIDEBAR_W_COLLAPSED = 3.5; /* w-14 = 3.5rem */

/* ────── Icons (18×18, stroke-based) ────── */
const icons: Record<string, React.ReactNode> = {
  overview: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" />
      <rect x="3" y="14" width="7" height="7" rx="1" /><rect x="14" y="14" width="7" height="7" rx="1" />
    </svg>
  ),
  vps: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <rect x="2" y="3" width="20" height="14" rx="2" /><path d="M8 21h8M12 18v3" />
    </svg>
  ),
  nodes: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <rect x="4" y="4" width="16" height="6" rx="1" /><rect x="4" y="14" width="16" height="6" rx="1" />
      <circle cx="8" cy="7" r="1" fill="currentColor" /><circle cx="8" cy="17" r="1" fill="currentColor" />
    </svg>
  ),
  images: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <circle cx="8.5" cy="8.5" r="1.5" /><path d="M21 15l-5-5L5 21" />
    </svg>
  ),
  ips: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" /><path d="M2 12h20M12 2a15.3 15.3 0 014 10 15.3 15.3 0 01-4 10 15.3 15.3 0 01-4-10A15.3 15.3 0 0112 2z" />
    </svg>
  ),
  users: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2" /><circle cx="9" cy="7" r="4" />
      <path d="M23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75" />
    </svg>
  ),
  logs: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
      <path d="M14 2v6h6M16 13H8M16 17H8M10 9H8" />
    </svg>
  ),
  apikeys: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 11-7.778 7.778 5.5 5.5 0 017.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4" />
    </svg>
  ),
  collapse: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M11 19l-7-7 7-7M18 19l-7-7 7-7" />
    </svg>
  ),
  expand: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M13 5l7 7-7 7M6 5l7 7-7 7" />
    </svg>
  ),
};

interface NavItemDef {
  to: string;
  label: string;
  icon: string;
  end?: boolean;
}

const overviewNav: NavItemDef[] = [
  { to: "/app", label: "Overview", icon: "overview", end: true },
];

const infraNav: NavItemDef[] = [
  { to: "/app/vps", label: "Virtual Servers", icon: "vps" },
];

const adminNav: NavItemDef[] = [
  { to: "/app/admin/nodes", label: "Nodes", icon: "nodes" },
  { to: "/app/admin/images", label: "Images", icon: "images" },
  { to: "/app/admin/ips", label: "IP Addresses", icon: "ips" },
  { to: "/app/admin/users", label: "Users", icon: "users" },
  { to: "/app/admin/logs", label: "Logs", icon: "logs" },
  { to: "/app/admin/apikeys", label: "API Keys", icon: "apikeys" },
];

/* ────── Breadcrumb generation ────── */
const breadcrumbMap: Record<string, string> = {
  app: "Overview",
  vps: "Virtual Servers",
  new: "Create VPS",
  admin: "Administration",
  nodes: "Nodes",
  images: "Images",
  ips: "IP Addresses",
  users: "Users",
  logs: "Logs",
  apikeys: "API Keys",
  command: "Command",
  terminal: "Terminal",
  performance: "Performance",
  network: "Network",
  storage: "Storage",
  devices: "Devices",
  security: "Security",
  snapshots: "Snapshots",
  backups: "Backups",
  configuration: "Configuration",
  unlock: "Unlock",
};

function useBreadcrumbs() {
  const location = useLocation();
  return useMemo(() => {
    const parts = location.pathname.split("/").filter(Boolean);
    const crumbs: { label: string; to: string }[] = [];
    let accumulated = "";
    for (let i = 0; i < parts.length; i++) {
      const part = parts[i];
      if (!part) continue;
      accumulated += `/${part}`;
      /* Skip /app as root — don't show as breadcrumb */
      if (accumulated === "/app") continue;
      /* Skip UUIDs — they are dynamic VPS/node IDs */
      if (/^[0-9a-f]{8}-/i.test(part)) {
        /* Use the name from the page title or just show "…" */
        crumbs.push({ label: "…", to: accumulated });
        continue;
      }
      crumbs.push({
        label: breadcrumbMap[part] ?? part,
        to: accumulated,
      });
    }
    return crumbs;
  }, [location.pathname]);
}

/* ────── Nav Item Component ────── */
function NavItem({ item, collapsed, onNavigate }: { item: NavItemDef; collapsed: boolean; onNavigate?: () => void }) {
  const link = (
    <NavLink
      to={item.to}
      end={item.end}
      onClick={onNavigate}
      className={({ isActive }) =>
        `flex items-center gap-2.5 rounded-md transition-colors ${
          collapsed ? "justify-center px-2 py-2" : "px-3 py-2"
        } ${
          isActive
            ? "bg-cvx-raised text-cvx-text"
            : "text-cvx-muted hover:bg-cvx-raised/60 hover:text-cvx-text"
        }`
      }
    >
      <span className="shrink-0">{icons[item.icon]}</span>
      {!collapsed && <span className="truncate text-sm">{item.label}</span>}
    </NavLink>
  );

  if (collapsed) {
    return (
      <Tooltip content={item.label} side="right">
        {link}
      </Tooltip>
    );
  }
  return link;
}

/* ────── Page Transition ────── */
function PageTransition({ children }: { children: React.ReactNode }) {
  const location = useLocation();
  return (
    <div key={location.pathname} className="h-full animate-fade-up">
      {children}
    </div>
  );
}

/* ────── Main Layout ────── */
export function DashboardLayout() {
  const { user, loading, logout } = useAuth();
  const isAdmin = useIsAdmin();
  const navigate = useNavigate();
  const breadcrumbs = useBreadcrumbs();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return localStorage.getItem(SIDEBAR_KEY) === "1";
    } catch {
      return false;
    }
  });

  const toggleCollapse = useCallback(() => {
    setCollapsed((v) => {
      const next = !v;
      try { localStorage.setItem(SIDEBAR_KEY, next ? "1" : "0"); } catch { /* noop */ }
      return next;
    });
  }, []);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen((v) => !v);
      }
      if (e.key === "Escape") {
        setMobileOpen(false);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Spinner className="h-6 w-6" />
      </div>
    );
  }
  if (!user) {
    void navigate("/login");
    return null;
  }

  const closeMobile = () => setMobileOpen(false);

  const sidebarWidth = collapsed ? SIDEBAR_W_COLLAPSED : SIDEBAR_W_EXPANDED;

  const sidebar = (
    <nav className="flex h-full flex-col overflow-y-auto scrollbar-thin">
      {/* Logo */}
      <div className={`flex items-center ${collapsed ? "justify-center px-2 pt-4" : "gap-2 px-4 pt-4 pb-2"}`}>
        <NavLink to="/app" onClick={closeMobile} className="flex items-center gap-2">
          <span className="font-display text-lg font-semibold tracking-tight text-cvx-text">CVX</span>
          {!collapsed && (
            <span className="rounded border border-cvx-border px-1 py-0.5 text-[9px] uppercase tracking-widest text-cvx-faint">
              v1.1
            </span>
          )}
        </NavLink>
      </div>

      {/* Command palette trigger */}
      {!collapsed ? (
        <button
          type="button"
          onClick={() => setPaletteOpen(true)}
          aria-label="Open command palette"
          className="mx-3 mb-3 flex items-center justify-between rounded-md border border-cvx-border bg-cvx-raised/60 px-3 py-2 text-xs text-cvx-faint transition-colors hover:border-cvx-border-strong hover:text-cvx-muted"
        >
          <span>Search…</span>
          <kbd className="rounded border border-cvx-border px-1 font-mono text-[10px]">⌘K</kbd>
        </button>
      ) : (
        <Tooltip content="Search (⌘K)" side="right">
          <button
            type="button"
            onClick={() => setPaletteOpen(true)}
            aria-label="Open command palette"
            className="mx-auto mb-3 flex items-center justify-center rounded-md border border-cvx-border bg-cvx-raised/60 p-2 text-cvx-faint transition-colors hover:border-cvx-border-strong hover:text-cvx-muted"
          >
            {icons.vps}
          </button>
        </Tooltip>
      )}

      {/* Nav groups */}
      <div className="space-y-1 px-2">
        {!collapsed && (
          <p className="px-2 pb-1 text-[10px] font-medium uppercase tracking-[0.16em] text-cvx-faint">
            Overview
          </p>
        )}
        {overviewNav.map((n) => (
          <NavItem key={n.to} item={n} collapsed={collapsed} onNavigate={closeMobile} />
        ))}
      </div>

      <div className="space-y-1 px-2 pt-3">
        {!collapsed && (
          <p className="px-2 pb-1 text-[10px] font-medium uppercase tracking-[0.16em] text-cvx-faint">
            Infrastructure
          </p>
        )}
        {infraNav.map((n) => (
          <NavItem key={n.to} item={n} collapsed={collapsed} onNavigate={closeMobile} />
        ))}
      </div>

      {isAdmin && (
        <div className="space-y-1 px-2 pt-3">
          {!collapsed && (
            <p className="px-2 pb-1 text-[10px] font-medium uppercase tracking-[0.16em] text-cvx-faint">
              Administration
            </p>
          )}
          {adminNav.map((n) => (
            <NavItem key={n.to} item={n} collapsed={collapsed} onNavigate={closeMobile} />
          ))}
        </div>
      )}

      {/* Collapse toggle + account */}
      <div className="mt-auto border-t border-cvx-border pt-3 pb-3 px-2 space-y-1">
        <button
          type="button"
          onClick={toggleCollapse}
          className={`flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-sm text-cvx-muted transition-colors hover:bg-cvx-raised hover:text-cvx-text ${
            collapsed ? "justify-center" : ""
          }`}
        >
          <span className="shrink-0">{collapsed ? icons.expand : icons.collapse}</span>
          {!collapsed && <span>Collapse</span>}
        </button>
      </div>
    </nav>
  );

  const accountActions: DropdownAction[] = [
    {       label: (user.name || user.email || "User").charAt(0).toUpperCase(), disabled: true },
    { separator: true, label: "" },
    {
      label: "Sign out",
      danger: true,
      onClick: () => void logout().then(() => navigate("/login")),
    },
  ];

  return (
    <div className="flex h-full">
      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />

      {/* Desktop sidebar */}
      <aside
        className="hidden border-r border-cvx-border bg-cvx-panel lg:block transition-all duration-200 ease-out shrink-0"
        style={{ width: `${sidebarWidth}rem` }}
      >
        {sidebar}
      </aside>

      {/* Mobile drawer */}
      {mobileOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="animate-fade-in absolute inset-0 bg-black/60" onClick={closeMobile} />
          <aside className="animate-slide-left absolute left-0 top-0 h-full w-64 border-r border-cvx-border bg-cvx-panel">
            {sidebar}
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Desktop topbar */}
        <header className="hidden items-center justify-between border-b border-cvx-border bg-cvx-panel px-4 py-2 lg:flex">
          <div className="flex items-center gap-2 text-sm">
            <span className="text-cvx-faint">CVX</span>
            {breadcrumbs.map((crumb, i) => (
              <span key={crumb.to} className="flex items-center gap-2">
                <span className="text-cvx-faint/50">/</span>
                {i === breadcrumbs.length - 1 ? (
                  <span className="font-medium text-cvx-text">{crumb.label}</span>
                ) : (
                  <button
                    type="button"
                    onClick={() => navigate(crumb.to)}
                    className="text-cvx-muted hover:text-cvx-text transition-colors"
                  >
                    {crumb.label}
                  </button>
                )}
              </span>
            ))}
          </div>
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => setPaletteOpen(true)}
              className="flex items-center gap-2 rounded-md border border-cvx-border bg-cvx-raised/60 px-3 py-1.5 text-xs text-cvx-faint transition-colors hover:border-cvx-border-strong hover:text-cvx-muted"
            >
              <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
                <circle cx="7" cy="7" r="4.5" /><path d="M10.5 10.5L14 14" />
              </svg>
              <span>Search</span>
              <kbd className="rounded border border-cvx-border px-1 font-mono text-[10px]">⌘K</kbd>
            </button>
            <DropdownMenu
              align="right"
              trigger={
                <button type="button" className="flex items-center gap-2 rounded-md p-1.5 text-sm text-cvx-muted hover:bg-cvx-raised hover:text-cvx-text transition-colors">
                  <span className="flex h-6 w-6 items-center justify-center rounded-full bg-cvx-accent/15 text-[11px] font-semibold text-cvx-accent uppercase">
                    {(user.name || user.email)[0]}
                  </span>
                  <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5">
                    <path d="M3 5l3 3 3-3" />
                  </svg>
                </button>
              }
              actions={accountActions}
            />
          </div>
        </header>

        {/* Mobile topbar */}
        <header className="flex items-center justify-between border-b border-cvx-border bg-cvx-panel px-4 py-3 lg:hidden">
          <button onClick={() => setMobileOpen(true)} aria-label="Open menu" className="rounded-md p-1.5 hover:bg-cvx-raised">
            <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M2 4.5h14M2 9h14M2 13.5h14" />
            </svg>
          </button>
          <span className="font-display font-semibold">CVX</span>
          <button
            type="button"
            onClick={() => setPaletteOpen(true)}
            aria-label="Search"
            className="rounded-md p-1.5 hover:bg-cvx-raised"
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
              <circle cx="7" cy="7" r="4.5" />
              <path d="M10.5 10.5L14 14" />
            </svg>
          </button>
        </header>

        <main className="min-h-0 flex-1 overflow-y-auto p-4 md:p-6 scrollbar-thin">
          <PageTransition>
            <Outlet />
          </PageTransition>
        </main>
      </div>
    </div>
  );
}
