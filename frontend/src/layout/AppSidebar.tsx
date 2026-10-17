import type { LucideIcon } from 'lucide-react'
import {
  Bot,
  ChartColumnStacked,
  Cloud,
  History,
  LayoutDashboard,
  MonitorPlay,
  Plug,
  Puzzle,
  SquareCheck,
  SquareTerminal,
} from 'lucide-react'
import { matchPath, NavLink, useLocation } from 'react-router-dom'
import { Logo } from '@/components/Logo'
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

type Item = { to: string; label: string; icon: LucideIcon; end?: boolean }

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
      { to: '/claude', label: 'Claude Code', icon: SquareTerminal },
      { to: '/codex', label: 'Codex', icon: Cloud },
      { to: '/nexus', label: 'Nexus memory', icon: Bot },
    ],
  },
  {
    label: 'Tools',
    items: [
      { to: '/mcp', label: 'MCP servers', icon: Plug },
      { to: '/plugins', label: 'Plugins', icon: Puzzle },
    ],
  },
  {
    label: 'You',
    items: [
      { to: '/tasks', label: 'Tasks', icon: SquareCheck },
      { to: '/activity', label: 'Activity', icon: History },
    ],
  },
]

// The active page reads as a small card on the paper, with the icon in the brand colour.
const ACTIVE = 'data-active:bg-card data-active:ring-1 data-active:ring-border data-active:[&_svg]:text-brand'

export function AppSidebar() {
  const { pathname } = useLocation()
  return (
    <Sidebar collapsible="icon">
      <SidebarHeader className="px-3 pt-4 pb-2">
        <Logo tagline={false} />
      </SidebarHeader>
      <SidebarContent className="gap-1 px-1">
        {GROUPS.map((g) => (
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
