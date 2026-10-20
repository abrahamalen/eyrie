"""Response models for every endpoint. They're the API contract: OpenAPI is generated from
them, and the frontend's TypeScript types are generated from that (`make types`)."""
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.tools import ToolId


class SourceInfo(BaseModel):
    id: str
    title: str
    available: bool
    reason: str | None


# --- Claude Code --------------------------------------------------------------------------

class ClaudeTotals(BaseModel):
    cost_usd: float
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_creation_tokens: int


class ClaudeProject(ClaudeTotals):
    path: str
    models: list[str]
    last_start_time: int | None  # epoch milliseconds


class ClaudeModelUsage(BaseModel):
    cost_usd: float
    input_tokens: int
    output_tokens: int


class McpBrief(BaseModel):
    name: str
    type: str
    scope: str


class ClaudeUsage(BaseModel):
    projects: list[ClaudeProject]
    totals: ClaudeTotals
    by_model: dict[str, ClaudeModelUsage]
    enabled_plugins: list[str]
    configured_mcp: list[McpBrief]


# --- Codex --------------------------------------------------------------------------------

class CodexThread(BaseModel):
    id: str
    cwd: str
    model: str
    tokens_used: int
    updated_at: int  # epoch seconds
    reasoning_effort: str | None
    title: str


class CodexTotals(BaseModel):
    tokens_used: int


class CodexUsage(BaseModel):
    threads: list[CodexThread]
    totals: CodexTotals
    by_model: dict[str, int]
    by_cwd: dict[str, int]
    available: bool
    error: str | None = None


# --- MCP and plugins ------------------------------------------------------------------------

class McpServer(BaseModel):
    name: str
    client: ToolId
    scope: Literal["user", "local", "project"]
    type: str
    target: str
    project: str | None


class McpFailure(BaseModel):
    name: str
    status: str
    detail: str


class McpStatus(BaseModel):
    configured: list[McpServer]
    last_known_failures: list[McpFailure]


class Plugin(BaseModel):
    id: str | None
    name: str
    marketplace: str
    version: str | None
    scope: str | None
    enabled: bool
    projectEnabled: bool | None
    installedAt: str | None
    lastUpdated: str | None


class PluginList(BaseModel):
    plugins: list[Plugin]
    error: str | None


# --- Agent memory --------------------------------------------------------------------------

class MemoryFileInfo(BaseModel):
    name: str
    size: int
    modified: str


class MemoryAgent(BaseModel):
    agent: str
    file_count: int
    last_used: str
    files: list[MemoryFileInfo]


class MemoryAgents(BaseModel):
    agents: list[MemoryAgent]


class MemoryFile(BaseModel):
    agent: str
    name: str
    content: str
    etag: str
    modified: str
    linked_from: list[str]


class Trashed(BaseModel):
    trashed_to: str


# --- Tasks --------------------------------------------------------------------------------

class Task(BaseModel):
    id: str
    done: bool
    text: str
    line: int


class TasksSnapshot(BaseModel):
    etag: str
    tasks: list[Task]


# --- Sessions -------------------------------------------------------------------------------

# user: you named it; tool: the tool did; id: a short conversation id; none: no id known either.
NameSource = Literal["user", "tool", "id", "none"]


class Resources(BaseModel):
    """What keeping a session costs (docs/stop-and-idle.md §3.2)."""
    rss_bytes: int | None  # RSS of the process and its descendants: an upper bound
    child_processes: int | None


class Idle(BaseModel):
    """How long a live session has gone without activity, and the suggestion about it (§3)."""
    minutes: int
    since: str  # the activity it's measured from
    exact: bool  # False: the activity is the newest in its directory, not this conversation's
    idle: bool  # at least sessions.idle_hours
    suggested: bool  # idle, not snoozed or dismissed (and detached, if that's required)
    key: str  # for PUT /api/v1/suggestions/{key}
    snoozed_until: str | None
    dismissed: bool
    attached: bool | None  # a client is attached; None: unknown
    context_tokens: int | None  # the last turn's prompt size
    cache_expired: bool | None
    # Set only when the /compact hint applies (large context, cache expired, idle).
    compact_command: str | None


class Session(BaseModel):
    name: str
    tool: ToolId | None
    cwd: str | None
    mode: str | None
    conversation_id: str | None
    created: str | None
    last_output: str | None
    attached: int
    alive: bool
    exit_status: int | None
    command: str | None
    attach: str
    # The name you (or the tool) gave the conversation, else its short id, else `name`.
    display_name: str
    name_source: NameSource
    # Exact command to pick the conversation up again in a terminal (shown, never run).
    resume_command: str | None
    resources: Resources
    idle: Idle | None  # None when not running, or its activity is unknown


class ExternalSession(BaseModel):
    """A Claude Code / Codex session running in one of your own terminals (not started by Eyrie)."""
    pid: int
    tool: ToolId
    tty: str
    cwd: str | None
    resume: str | None
    started: str
    last_activity: str | None
    idle_minutes: int | None
    activity_exact: bool
    conversation_id: str | None
    display_name: str
    name_source: NameSource
    # False when the conversation is a best guess (newest in its directory).
    name_exact: bool
    terminal: str | None  # what it runs in: "iTerm2", "Warp", "tmux", …
    # What sessions.focus can do: select the tab, select the tmux pane, raise the app, nothing.
    focus: Literal["tab", "pane", "app", "none"]
    href: str
    # The process's exact start time: sessions.stop_external must name it (pid reuse check).
    process_started: str | None
    uid_ok: bool  # runs as you
    resume_command: str | None
    resources: Resources
    idle: Idle | None


class SessionsSnapshot(BaseModel):
    sessions: list[Session]
    external: list[ExternalSession]
    dirs: list[str]
    error: str | None


class Conversation(BaseModel):
    id: str
    started: str
    last: str
    messages: int
    project: str | None


class Screen(BaseModel):
    name: str
    text: str


# --- Usage --------------------------------------------------------------------------------

class UsageRange(BaseModel):
    days: int
    start: str
    end: str


class DayModel(BaseModel):
    cost: float
    tokens: int


class UsageDay(BaseModel):
    day: str
    models: dict[str, DayModel]


class UsageModel(BaseModel):
    model: str
    tool: ToolId
    priced: bool
    cost: float
    input: int
    output: int
    cache_read: int
    cache_write: int
    tokens: int
    messages: int


class UsageProject(BaseModel):
    project: str
    cost: float
    tokens: int
    sessions: int


class UsageTool(BaseModel):
    tool: ToolId
    cost: float
    tokens: int
    sessions: int


class UsageTotals(BaseModel):
    cost: float
    tokens: int
    messages: int
    sessions: int


class IndexStats(BaseModel):
    files: int
    messages: int
    oldest: str | None
    last_scan_ms: float


class Pricing(BaseModel):
    updated: str
    unpriced_models: list[str]


class UsageReport(BaseModel):
    range: UsageRange
    days: list[UsageDay]
    by_model: list[UsageModel]
    by_project: list[UsageProject]
    by_tool: list[UsageTool]
    totals: UsageTotals
    index: IndexStats
    pricing: Pricing
    note: str


# --- Actions, audit, misc -----------------------------------------------------------------

class ActionPreview(BaseModel):
    action: str
    argv: list[str]
    destructive: bool
    dry_run: Literal[True]


class ActionResult(BaseModel):
    action: str
    argv: list[str]
    ok: bool
    exit_code: int
    message: str
    duration_ms: float
    # sessions.stop_external: exited | still_running | stuck | already_exited | reused | denied
    state: str | None = None


class AuditEntry(BaseModel):
    ts: str
    action: str
    argv: list[str]
    params: dict[str, Any]
    ok: bool
    exit_code: int
    duration_ms: float
    message: str


class AttentionItem(BaseModel):
    kind: Literal["cli_missing", "session_exited_error", "session_idle", "mcp_failed", "unpriced_model"]
    severity: Literal["problem", "attention"]
    title: str
    detail: str
    href: str
    since: str | None


class SummarySession(BaseModel):
    name: str
    tool: ToolId | None
    project: str | None
    alive: bool
    exit_status: int | None
    idle_minutes: int | None
    last_output: str | None
    # False for sessions in your own terminals: Eyrie can see them but not attach to them.
    managed: bool
    tty: str | None
    pid: int | None
    display_name: str
    name_source: NameSource
    conversation_id: str | None
    href: str  # the app's page for this session (/sessions?open=… or /sessions?ext=…)


class SuggestionItem(BaseModel):
    """A session Eyrie suggests stopping (docs/stop-and-idle.md §6.1)."""
    key: str
    managed: bool
    name: str | None  # Eyrie session name
    pid: int | None  # external session
    tool: ToolId
    display_name: str
    project: str | None
    idle_minutes: int
    idle_exact: bool
    rss_bytes: int | None
    child_processes: int | None
    context_tokens: int | None
    compact_command: str | None
    href: str


class Suggestions(BaseModel):
    idle_hours: int
    count: int
    rss_bytes: int  # held by the suggested sessions
    items: list[SuggestionItem]


class Snooze(BaseModel):
    key: str
    until: str | None  # None: dismissed until the session is used again
    activity: str | None
    at: str


class DayCost(BaseModel):
    day: str
    cost: float


class Spend(BaseModel):
    today: float
    yesterday: float
    last_7_days: list[DayCost]
    change_vs_prev_7_pct: float | None
    top_project_today: str | None


class SummaryTasks(BaseModel):
    open_count: int
    next: list[Task]


class RecentProject(BaseModel):
    path: str
    last_used: str
    tool: ToolId


class ToolHealth(BaseModel):
    found: bool
    version: str | None
    path: str | None
    used: bool  # the tool's state folder exists


class Health(BaseModel):
    tmux: ToolHealth
    # None when the tool isn't enabled here (tools.enabled)
    claude: ToolHealth | None
    codex: ToolHealth | None
    gemini: ToolHealth | None
    usage_index: IndexStats | None


class Summary(BaseModel):
    state: Literal["ok", "attention", "problem"]
    attention: list[AttentionItem]
    sessions: list[SummarySession]
    spend: Spend
    tasks: SummaryTasks | None  # None when no tasks file is set
    recent_projects: list[RecentProject]
    health: Health
    suggestions: Suggestions
    generated_at: str


class McpInfo(BaseModel):
    scopes: list[Literal["user", "local", "project"]]
    transports: list[Literal["stdio", "http", "sse"]]
    headers: bool
    bearer_token_env_var: bool


class ToolInfo(BaseModel):
    """What one tool can do here, so the UI offers only that."""
    id: ToolId
    title: str
    installed: bool
    used: bool
    enabled: bool
    session_modes: list[Literal["new", "continue", "resume"]]
    resume_requires_cwd: bool
    # Eyrie picks a new conversation's id up front (so the preview matches what runs).
    picks_conversation_id: bool
    mcp: McpInfo | None
    plugins: bool


class Features(BaseModel):
    """What this machine has, so pages for missing things aren't shown."""
    tasks: bool         # a tasks file is set
    agent_memory: bool  # Claude Code is enabled and its agent-memory folder exists
    mcp: bool           # an enabled tool has MCP support
    plugins: bool       # an enabled tool has plugins
    terminal_windows: bool  # macOS: Eyrie can open a session in Terminal/iTerm2


class Meta(BaseModel):
    home: str
    version: str
    features: Features
    # False until first-run setup has written a config file
    configured: bool
    tools: list[ToolInfo]


# --- Setup --------------------------------------------------------------------------------

class ConfigFile(BaseModel):
    path: str
    exists: bool
    etag: str


class DetectedTool(BaseModel):
    id: ToolId
    title: str
    installed: bool
    version: str | None
    path: str | None
    home: str | None
    used: bool
    enabled: bool


class SuggestedRoot(BaseModel):
    path: str
    projects: int


class AgentMemoryInfo(BaseModel):
    path: str
    exists: bool


class SetupState(BaseModel):
    config: ConfigFile
    tools_enabled: Literal["auto"] | list[ToolId]
    tools: list[DetectedTool]
    roots: list[str]
    suggested_roots: list[SuggestedRoot]
    tasks: str | None
    obsidian_vaults: list[str]
    agent_memory: AgentMemoryInfo
    idle_hours: int


class SetupBody(BaseModel):
    tools_enabled: Literal["auto"] | list[ToolId]
    roots: list[str] = []
    tasks: str | None = None
    # Suggest stopping sessions idle this long; None leaves the current value.
    idle_hours: int | None = Field(None, ge=1, le=720)


class Token(BaseModel):
    token: str


class Status(BaseModel):
    status: str


SOURCE_MODELS: dict[str, type[BaseModel]] = {
    "claude": ClaudeUsage,
    "codex": CodexUsage,
    "mcp": McpStatus,
    "plugins": PluginList,
    "memory": MemoryAgents,
    "tasks": TasksSnapshot,
    "sessions": SessionsSnapshot,
    "usage": UsageReport,
}
