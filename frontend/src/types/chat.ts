export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  timestamp: Date;
  isError?: boolean;
}

export type ChatStatus = "idle" | "thinking" | "streaming";

// SSE event from backend
export interface ChatSSEEvent {
  type:
    | "thinking"
    | "tool_call"
    | "action"
    | "message"
    | "todo_update"
    | "error";
  message?: string;
  content?: string;
  done?: boolean;
  tool?: string;
  args?: Record<string, unknown>;
  action_type?: string;
  summary?: string;
  todos?: Array<{ id: string; task: string; status: string }>;
}
