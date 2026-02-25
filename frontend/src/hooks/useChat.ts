"use client";

import { useState, useCallback, useRef } from "react";
import type { ChatMessage, ChatStatus, ChatSSEEvent } from "@/types/chat";
import {
  API_BASE_URL,
  API_CHAT_PATH,
  SSE_DATA_PREFIX,
  SSE_DATA_PREFIX_LENGTH,
} from "@/lib/config";
import { createClient } from "@/lib/supabase/client";

interface UseChatResult {
  messages: ChatMessage[];
  status: ChatStatus;
  streamingContent: string;
  sendMessage: (text: string) => Promise<void>;
}

export function useChat(): UseChatResult {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [status, setStatus] = useState<ChatStatus>("idle");
  const [streamingContent, setStreamingContent] = useState("");
  const conversationIdRef = useRef<string | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  const sendMessage = useCallback(async (text: string) => {
    if (!text.trim()) return;

    // Abort any in-progress request
    abortControllerRef.current?.abort();
    const controller = new AbortController();
    abortControllerRef.current = controller;

    const userMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: text.trim(),
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setStatus("thinking");
    setStreamingContent("");

    try {
      const supabase = createClient();
      const {
        data: { session },
      } = await supabase.auth.getSession();
      const token = session?.access_token;

      const response = await fetch(`${API_BASE_URL}${API_CHAT_PATH}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "text/event-stream",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          message: text.trim(),
          conversation_id: conversationIdRef.current,
        }),
        signal: controller.signal,
      });

      if (!response.ok) {
        throw new Error(`Erro HTTP: ${response.status}`);
      }

      if (!response.body) {
        throw new Error("Resposta sem corpo");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let accumulatedContent = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (line.startsWith(SSE_DATA_PREFIX)) {
            const jsonStr = line.slice(SSE_DATA_PREFIX_LENGTH).trim();
            if (!jsonStr) continue;

            try {
              const event: ChatSSEEvent = JSON.parse(jsonStr);

              if (event.type === "thinking") {
                setStatus("thinking");
              } else if (event.type === "message") {
                setStatus("streaming");
                if (event.content) {
                  accumulatedContent += event.content;
                  setStreamingContent(accumulatedContent);
                }
                if (event.done) {
                  const assistantMessage: ChatMessage = {
                    id: crypto.randomUUID(),
                    role: "assistant",
                    content: accumulatedContent,
                    timestamp: new Date(),
                  };
                  setMessages((prev) => [...prev, assistantMessage]);
                  setStreamingContent("");
                  setStatus("idle");
                  accumulatedContent = "";
                }
              } else if (event.type === "error") {
                const errorMessage: ChatMessage = {
                  id: crypto.randomUUID(),
                  role: "assistant",
                  content: event.message || "Ocorreu um erro inesperado.",
                  timestamp: new Date(),
                  isError: true,
                };
                setMessages((prev) => [...prev, errorMessage]);
                setStatus("idle");
              } else if (event.type === "tool_call" || event.type === "action") {
                // v1: log only, no UI display
                console.debug("Chat event:", event.type, event);
              }
            } catch (e) {
              console.error("Failed to parse chat SSE event:", e, jsonStr);
            }
          }
        }
      }
    } catch (e) {
      if ((e as Error).name === "AbortError") return;

      const errorMessage: ChatMessage = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: "Não foi possível enviar a mensagem. Tente novamente.",
        timestamp: new Date(),
        isError: true,
      };
      setMessages((prev) => [...prev, errorMessage]);
      setStatus("idle");
      console.error("Chat error:", e);
    }
  }, []);

  return { messages, status, streamingContent, sendMessage };
}
