import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "@/lib/auth";
import { PageLoader } from "@/components/ui/Loading";
import { ToastProvider } from "@/components/ui/Toast";

const LoginPage = lazy(() => import("./pages/auth/LoginPage"));
const DashboardLayout = lazy(() => import("./layouts/DashboardLayout").then((m) => ({ default: m.DashboardLayout })));
const OverviewPage = lazy(() => import("./pages/dash/OverviewPage"));
const VPSListPage = lazy(() => import("./pages/vps/VPSListPage"));
const VPSCreatePage = lazy(() => import("./pages/vps/VPSCreatePage"));
const VPSUnlockPage = lazy(() => import("./pages/vps/VPSUnlockPage"));
const VPSWorkspace = lazy(() => import("./pages/vps/VPSWorkspace"));
const AdminNodesPage = lazy(() => import("./pages/admin/AdminNodesPage"));
const NodeDetailPage = lazy(() => import("./pages/admin/NodeDetailPage"));
const AdminImagesPage = lazy(() => import("./pages/admin/AdminImagesPage"));
const AdminIPsPage = lazy(() => import("./pages/admin/AdminIPsPage"));
const AdminUsersPage = lazy(() => import("./pages/admin/AdminUsersPage"));
const AdminLogsPage = lazy(() => import("./pages/admin/AdminLogsPage"));
const AdminApiKeysPage = lazy(() => import("./pages/admin/AdminApiKeysPage"));

function Protected({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <PageLoader />;
  if (!user) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export function App() {
  return (
    <ToastProvider>
      <Suspense fallback={<PageLoader />}>
        <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/app"
          element={
            <Protected>
              <DashboardLayout />
            </Protected>
          }
        >
          <Route index element={<OverviewPage />} />
          <Route path="vps" element={<VPSListPage />} />
          <Route path="vps/new" element={<VPSCreatePage />} />
          <Route path="vps/:id/unlock" element={<VPSUnlockPage />} />
          <Route path="vps/:id/*" element={<VPSWorkspace />} />
          <Route path="admin/nodes" element={<AdminNodesPage />} />
          <Route path="admin/nodes/:id" element={<NodeDetailPage />} />
          <Route path="admin/images" element={<AdminImagesPage />} />
          <Route path="admin/ips" element={<AdminIPsPage />} />
          <Route path="admin/users" element={<AdminUsersPage />} />
          <Route path="admin/logs" element={<AdminLogsPage />} />
          <Route path="admin/apikeys" element={<AdminApiKeysPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/app" replace />} />
        </Routes>
      </Suspense>
    </ToastProvider>
  );
}
