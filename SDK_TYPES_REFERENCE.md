# Cursor TypeScript SDK Type Definitions Reference

This file contains the core type definitions from the Cursor TypeScript SDK to guide the Python SDK implementation.
Use these fields and types to construct the corresponding Python dataclasses.

```typescript
// --- Models & Catalog ---

interface ModelSelection {
	id: string;
	params?: ModelParameterValue[];
}

interface ModelParameterValue {
	id: string;
	value: string;
}

interface ModelListItem {
	id: string;
	displayName: string;
	description?: string;
	parameters?: ModelParameterDefinition[];
	variants?: ModelVariant[];
}

interface ModelParameterDefinition {
	id: string;
	displayName?: string;
	values: Array<{ value: string; displayName?: string }>;
}

interface ModelVariant {
	params: ModelParameterValue[];
	displayName: string;
	description?: string;
	isDefault?: boolean;
}

// --- Messages ---

type SDKMessage =
	| SDKSystemMessage
	| SDKUserMessageEvent
	| SDKAssistantMessage
	| SDKThinkingMessage
	| SDKToolUseMessage
	| SDKStatusMessage
	| SDKTaskMessage
	| SDKRequestMessage;

interface SDKSystemMessage {
	type: "system";
	subtype?: "init";
	agent_id: string;
	run_id: string;
	model?: ModelSelection;
	tools?: string[];
}

interface SDKUserMessageEvent {
	type: "user";
	agent_id: string;
	run_id: string;
	message: { role: "user"; content: TextBlock[] };
}

interface SDKAssistantMessage {
	type: "assistant";
	agent_id: string;
	run_id: string;
	message: {
	  role: "assistant";
	  content: Array<TextBlock | ToolUseBlock>;
	};
}

interface SDKThinkingMessage {
	type: "thinking";
	agent_id: string;
	run_id: string;
	text: string;
	thinking_duration_ms?: number;
}

interface SDKToolUseMessage {
	type: "tool_call";
	agent_id: string;
	run_id: string;
	call_id: string;
	name: string;
	status: "running" | "completed" | "error";
	args?: unknown;
	result?: unknown;
	truncated?: { args?: boolean; result?: boolean };
}

interface SDKStatusMessage {
	type: "status";
	agent_id: string;
	run_id: string;
	status: "CREATING" | "RUNNING" | "FINISHED" | "ERROR" | "CANCELLED" | "EXPIRED";
	message?: string;
}

interface SDKTaskMessage {
	type: "task";
	agent_id: string;
	run_id: string;
	status?: string;
	text?: string;
}

interface SDKRequestMessage {
	type: "request";
	agent_id: string;
	run_id: string;
	request_id: string;
}

interface TextBlock {
	type: "text";
	text: string;
}

interface ToolUseBlock {
	type: "tool_use";
	id: string;
	name: string;
	input: unknown;
}

// --- Interaction Updates (Deltas) ---

type InteractionUpdate =
	| TextDeltaUpdate
	| ThinkingDeltaUpdate
	| ThinkingCompletedUpdate
	| ToolCallStartedUpdate
	| ToolCallCompletedUpdate
	| PartialToolCallUpdate
	| TokenDeltaUpdate
	| StepStartedUpdate
	| StepCompletedUpdate
	| TurnEndedUpdate
	| UserMessageAppendedUpdate
	| SummaryUpdate
	| SummaryStartedUpdate
	| SummaryCompletedUpdate
	| ShellOutputDeltaUpdate;

interface TextDeltaUpdate { type: "text-delta"; text: string; }
interface ThinkingDeltaUpdate { type: "thinking-delta"; text: string; }
interface ThinkingCompletedUpdate { type: "thinking-completed"; thinkingDurationMs: number; }
interface ToolCallStartedUpdate { type: "tool-call-started"; callId: string; toolCall: unknown; modelCallId: string; }
interface PartialToolCallUpdate { type: "partial-tool-call"; callId: string; toolCall: unknown; modelCallId: string; }
interface ToolCallCompletedUpdate { type: "tool-call-completed"; callId: string; toolCall: unknown; modelCallId: string; }
interface TokenDeltaUpdate { type: "token-delta"; tokens: number; }
interface StepStartedUpdate { type: "step-started"; stepId: number; }
interface StepCompletedUpdate { type: "step-completed"; stepId: number; stepDurationMs: number; }
interface TurnEndedUpdate { 
    type: "turn-ended"; 
    usage?: { inputTokens: number; outputTokens: number; cacheReadTokens: number; cacheWriteTokens: number; }; 
}
interface UserMessageAppendedUpdate { type: "user-message-appended"; userMessage: unknown; }
interface SummaryUpdate { type: "summary"; summary: string; }
interface SummaryStartedUpdate { type: "summary-started"; }
interface SummaryCompletedUpdate { type: "summary-completed"; }
interface ShellOutputDeltaUpdate { type: "shell-output-delta"; event: Record<string, unknown>; }

// --- Conversation Turns ---

type ConversationTurn =
	| { type: "agentConversationTurn"; turn: AgentConversationTurn }
	| { type: "shellConversationTurn"; turn: ShellConversationTurn };

interface AgentConversationTurn {
	userMessage?: UserMessage;
	steps: ConversationStep[];
}

interface ShellConversationTurn {
	shellCommand?: ShellCommand;
	shellOutput?: ShellOutput;
}

type ConversationStep =
	| { type: "assistantMessage"; message: AssistantMessage }
	| { type: "toolCall"; message: unknown }
	| { type: "thinkingMessage"; message: ThinkingMessage };

interface AssistantMessage { text: string; }
interface ThinkingMessage { text: string; thinkingDurationMs?: number; }
interface UserMessage { text: string; }
interface ShellCommand { command: string; workingDirectory?: string; }
interface ShellOutput { stdout: string; stderr: string; exitCode: number; }

// --- MCP Servers & Config ---

type McpServerConfig =
	| { type?: "stdio"; command: string; args?: string[]; env?: Record<string, string>; cwd?: string; }
	| { type?: "http" | "sse"; url: string; headers?: Record<string, string>; auth?: { CLIENT_ID: string; CLIENT_SECRET?: string; scopes?: string[]; }; };

interface AgentDefinition {
    description: string;
    prompt: string;
    model: ModelSelection | "inherit";
    mcpServers: Array<string | Record<string, McpServerConfig>>;
}

// --- Options & Results ---

interface AgentOptions {
    model?: ModelSelection;
    apiKey?: string;
    name?: string;
    local?: LocalOptions;
    cloud?: CloudOptions;
    mcpServers?: Record<string, McpServerConfig>;
    agents?: Record<string, AgentDefinition>;
    agentId?: string;
}

interface CloudOptions {
    env?: { type: "cloud" | "pool" | "machine"; name?: string; };
    repos?: Array<{ url: string; startingRef?: string; prUrl?: string; }>;
    workOnCurrentBranch?: boolean;
    autoCreatePR?: boolean;
    skipReviewerRequest?: boolean;
}

type SettingSource = "project" | "user" | "team" | "mdm" | "plugins" | "all";

interface LocalOptions {
    cwd?: string | string[];
    settingSources?: SettingSource[];
    sandboxOptions?: { enabled: boolean; };
}

interface SendOptions {
    model?: ModelSelection;
    mcpServers?: Record<string, McpServerConfig>;
    onStep?: (args: { step: unknown }) => void;
    onDelta?: (args: { update: InteractionUpdate }) => void;
    local?: { force?: boolean; };
}

interface ListResult<T> {
    items: T[];
    nextCursor?: string;
}
```
