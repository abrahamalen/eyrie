"""Response models for every endpoint. They're the API contract: OpenAPI is generated from
them, and the frontend's TypeScript types are generated from that (`make types`)."""
from typing import Any, Literal

from pydantic import BaseModel


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
    client: Literal["claude", "codex"]
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


# --- Nexus --------------------------------------------------------------------------------

class NexusFileInfo(BaseModel):
    name: str
    size: int
    modified: str


class NexusAgent(BaseModel):
    agent: str
    file_count: int
    last_used: str
    files: list[NexusFileInfo]


class NexusAgents(BaseModel):
    agents: list[NexusAgent]


class NexusFile(BaseModel):
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

class Session(BaseModel):
    name: str
    tool: Literal["claude", "codex"] | None
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


class SessionsSnapshot(BaseModel):
    sessions: list[Session]
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


class UsageTotals(BaseModel):
    cost: float
    tokens: int
    messages: int
    sessions: int


class CodexModelUsage(BaseModel):
    model: str
    threads: int
    tokens: int


class CodexSummary(BaseModel):
    available: bool
    threads: int
    tokens: int
    by_model: list[CodexModelUsage]
    error: str | None = None


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
    totals: UsageTotals
    codex: CodexSummary
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


class AuditEntry(BaseModel):
    ts: str
    action: str
    argv: list[str]
    params: dict[str, Any]
    ok: bool
    exit_code: int
    duration_ms: float
    message: str


class Meta(BaseModel):
    home: str
    version: str


class Token(BaseModel):
    token: str


class Health(BaseModel):
    status: str


SOURCE_MODELS: dict[str, type[BaseModel]] = {
    "claude": ClaudeUsage,
    "codex": CodexUsage,
    "mcp": McpStatus,
    "plugins": PluginList,
    "nexus": NexusAgents,
    "tasks": TasksSnapshot,
    "sessions": SessionsSnapshot,
    "usage": UsageReport,
}
