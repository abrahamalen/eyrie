import { Route, Routes } from 'react-router-dom'
import { AppLayout } from '@/layout/AppLayout'
import { OverviewPage } from '@/pages/OverviewPage'
import { ClaudePage } from '@/pages/ClaudePage'
import { CodexPage } from '@/pages/CodexPage'
import { McpPage } from '@/pages/McpPage'
import { NexusPage } from '@/pages/NexusPage'
import { TasksPage } from '@/pages/TasksPage'
import { UsagePage } from '@/pages/UsagePage'

export default function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<OverviewPage />} />
        <Route path="claude" element={<ClaudePage />} />
        <Route path="codex" element={<CodexPage />} />
        <Route path="mcp" element={<McpPage />} />
        <Route path="nexus" element={<NexusPage />} />
        <Route path="tasks" element={<TasksPage />} />
        <Route path="usage" element={<UsagePage />} />
      </Route>
    </Routes>
  )
}
