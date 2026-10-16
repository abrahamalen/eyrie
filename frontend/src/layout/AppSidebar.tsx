import { Bot, ChevronRight, Cloud, LayoutDashboard, Plug, SquareTerminal, SquareCheck } from 'lucide-react'
import { NavLink, useLocation } from 'react-router-dom'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
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
  SidebarMenuSub,
  SidebarMenuSubButton,
  SidebarMenuSubItem,
} from '@/components/ui/sidebar'

const navLinkClass = ({ isActive }: { isActive: boolean }) =>
  `flex w-full items-center gap-2 ${isActive ? 'bg-sidebar-accent text-sidebar-accent-foreground' : ''}`

export function AppSidebar() {
  const location = useLocation()
  const claudeFamilyActive = location.pathname === '/claude' || location.pathname === '/nexus'

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader>
        <div className="flex items-center gap-2 px-2 py-1.5">
          <span className="flex size-7 shrink-0 items-center justify-center rounded-md bg-primary text-primary-foreground text-sm font-bold">
            E
          </span>
          <span className="font-semibold tracking-tight group-data-[collapsible=icon]:hidden">Eyrie</span>
        </div>
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <SidebarMenu>
            <SidebarMenuItem>
              <SidebarMenuButton asChild tooltip="Overview">
                <NavLink to="/" end className={navLinkClass}>
                  <LayoutDashboard className="size-4 shrink-0" />
                  <span className="truncate">Overview</span>
                </NavLink>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarGroup>

        <SidebarGroup>
          <SidebarGroupLabel>Coding Agents</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              <Collapsible defaultOpen={claudeFamilyActive} className="group/collapsible">
                <SidebarMenuItem>
                  <SidebarMenuButton asChild tooltip="Claude Code">
                    <NavLink to="/claude" className={navLinkClass}>
                      <SquareTerminal className="size-4 shrink-0" />
                      <span className="truncate">Claude Code</span>
                    </NavLink>
                  </SidebarMenuButton>
                  <CollapsibleTrigger asChild>
                    <SidebarMenuButton
                      className="absolute right-1 top-1 h-6 w-6 p-0 data-[state=open]:rotate-90"
                      aria-label="Toggle Nexus Agents"
                    >
                      <ChevronRight className="size-3.5 transition-transform" />
                    </SidebarMenuButton>
                  </CollapsibleTrigger>
                  <CollapsibleContent>
                    <SidebarMenuSub>
                      <SidebarMenuSubItem>
                        <SidebarMenuSubButton asChild>
                          <NavLink to="/nexus" className={navLinkClass}>
                            <Bot className="size-4 shrink-0" />
                            <span className="truncate">Nexus Agents</span>
                          </NavLink>
                        </SidebarMenuSubButton>
                      </SidebarMenuSubItem>
                    </SidebarMenuSub>
                  </CollapsibleContent>
                </SidebarMenuItem>
              </Collapsible>

              <SidebarMenuItem>
                <SidebarMenuButton asChild tooltip="Codex">
                  <NavLink to="/codex" className={navLinkClass}>
                    <Cloud className="size-4 shrink-0" />
                    <span className="truncate">Codex</span>
                  </NavLink>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        <SidebarGroup>
          <SidebarGroupLabel>Tools</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton asChild tooltip="MCP Servers">
                  <NavLink to="/mcp" className={navLinkClass}>
                    <Plug className="size-4 shrink-0" />
                    <span className="truncate">MCP Servers</span>
                  </NavLink>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        <SidebarGroup>
          <SidebarGroupContent>
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton asChild tooltip="Tasks">
                  <NavLink to="/tasks" className={navLinkClass}>
                    <SquareCheck className="size-4 shrink-0" />
                    <span className="truncate">Tasks</span>
                  </NavLink>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
    </Sidebar>
  )
}
