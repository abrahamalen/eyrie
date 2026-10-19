import type { LucideIcon } from 'lucide-react'
import {
  Bot,
  ChartColumnStacked,
  Cloud,
  History,
  Settings,
  LayoutDashboard,
  MonitorPlay,
  Plug,
  Puzzle,
  SquareCheck,
  SquareTerminal,
} from 'lucide-react'
import { matchPath, NavLink, useLocation } from 'react-router-dom'
import { Logo } from '@/components/Logo'
import { useMeta } from '@/tools'
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from '@/components/ui/sidebar'

type Meta = ReturnType<typeof useMeta>
// `show`: only when this machine has the thing (tools.enabled, a tasks file, ...).
type Item = { to: string; label: string; icon: LucideIcon; end?: boolean; show?: (m: Meta) => boolean }

const enabled = (id: string) => (m: Meta) => m.tools.some((t) => t.id === id && t.enabled)

const GROUPS: { label: string; items: Item[] }[] = [
  {
    label: 'Work',
    items: [
      { to: '/', label: 'Overview', icon: LayoutDashboard, end: true },
      { to: '/sessions', label: 'Sessions', icon: MonitorPlay },
      { to: '/usage', label: 'Usage', icon: ChartColumnStacked },
    ],
  },
  {
    label: 'Agents',
    items: [
      { to: '/claude', label: 'Claude Code', icon: SquareTerminal, show: enabled('claude') },
      { to: '/codex', label: 'Codex', icon: Cloud, show: enabled('codex') },
      { to: '/memory', label: 'Agent memory', icon: Bot, show: (m) => m.features.agent_memory },
    ],
  },
  {
    label: 'Tools',
    items: [
      { to: '/mcp', label: 'MCP servers', icon: Plug, show: (m) => m.features.mcp },
      { to: '/plugins', label: 'Plugins', icon: Puzzle, show: (m) => m.features.plugins },
    ],
  },
  {
    label: 'You',
    items: [
      { to: '/tasks', label: 'Tasks', icon: SquareCheck, show: (m) => m.features.tasks },
      { to: '/activity', label: 'Activity', icon: History },
      { to: '/settings', label: 'Settings', icon: Settings },
    ],
  },
]

// The active page reads as a small card on the paper, with the icon in the brand colour.
const ACTIVE = 'data-active:bg-card data-active:ring-1 data-active:ring-border data-active:[&_svg]:text-brand'

export function AppSidebar() {
  const { pathname } = useLocation()
  const meta = useMeta()
  const groups = GROUPS.map((g) => ({ ...g, items: g.items.filter((it) => !it.show || it.show(meta)) }))
    .filter((g) => g.items.length)
  return (
    <Sidebar collapsible="icon">
      <SidebarHeader className="px-3 pt-4 pb-2">
        <Logo tagline={false} />
      </SidebarHeader>
      <SidebarContent className="gap-1 px-1">
        {groups.map((g) => (
          <SidebarGroup key={g.label}>
            <SidebarGroupLabel className="eyebrow text-[10.5px]">{g.label}</SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                {g.items.map((it) => (
                  <SidebarMenuItem key={it.to}>
                    <SidebarMenuButton
                      render={<NavLink to={it.to} end={it.end} />}
                      isActive={!!matchPath({ path: it.to, end: !!it.end }, pathname)}
                      className={ACTIVE}
                      tooltip={it.label}
                    >
                      <it.icon className="size-4 shrink-0" />
                      <span className="truncate">{it.label}</span>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        ))}
      </SidebarContent>
    </Sidebar>
  )
}
