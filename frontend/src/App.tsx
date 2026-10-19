import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { AppLayout } from '@/layout/AppLayout'
import { OverviewPage } from '@/pages/OverviewPage'
import { ClaudePage } from '@/pages/ClaudePage'
import { CodexPage } from '@/pages/CodexPage'
import { McpPage } from '@/pages/McpPage'
import { MemoryPage } from '@/pages/MemoryPage'
import { TasksPage } from '@/pages/TasksPage'
import { UsagePage } from '@/pages/UsagePage'
import { PluginsPage } from '@/pages/PluginsPage'
import { ActivityPage } from '@/pages/ActivityPage'
import { SessionsPage } from '@/pages/SessionsPage'
import { SetupPage } from '@/pages/SetupPage'
import { isConfigured } from '@/tools'

export default function App() {
  // First run: nothing is configured yet, so everything leads to setup.
  const { pathname } = useLocation()
  if (!isConfigured() && pathname !== '/setup') return <Navigate to="/setup" replace />
  return (
    <Routes>
      <Route path="setup" element={<SetupPage firstRun />} />
      <Route element={<AppLayout />}>
        <Route index element={<OverviewPage />} />
        <Route path="claude" element={<ClaudePage />} />
        <Route path="codex" element={<CodexPage />} />
        <Route path="mcp" element={<McpPage />} />
        <Route path="memory" element={<MemoryPage />} />
        <Route path="tasks" element={<TasksPage />} />
        <Route path="sessions" element={<SessionsPage />} />
        <Route path="usage" element={<UsagePage />} />
        <Route path="plugins" element={<PluginsPage />} />
        <Route path="activity" element={<ActivityPage />} />
        <Route path="settings" element={<SetupPage firstRun={false} />} />
      </Route>
    </Routes>
  )
}
