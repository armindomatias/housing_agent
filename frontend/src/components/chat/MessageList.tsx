"use client";

import { useEffect, useRef } from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { ChatMessageBubble } from "./ChatMessageBubble";
import { StreamingIndicator } from "./StreamingIndicator";
import { CHAT_WELCOME_MESSAGE } from "@/lib/config";
import type { ChatMessage, ChatStatus } from "@/types/chat";

interface MessageListProps {
  messages: ChatMessage[];
  status: ChatStatus;
  streamingContent: string;
}

export function MessageList({
  messages,
  status,
  streamingContent,
}: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingContent, status]);

  const streamingMessage: ChatMessage | null =
    status === "streaming" && streamingContent
      ? {
          id: "__streaming__",
          role: "assistant",
          content: streamingContent,
          timestamp: new Date(),
        }
      : null;

  return (
    <ScrollArea className="flex-1 min-h-0 px-3 py-3">
      <div className="space-y-3">
        {messages.length === 0 && status === "idle" && (
          <div className="flex justify-start">
            <div className="bg-muted rounded-lg px-3 py-2 text-sm text-muted-foreground max-w-[90%]">
              {CHAT_WELCOME_MESSAGE}
            </div>
          </div>
        )}

        {messages.map((message) => (
          <ChatMessageBubble key={message.id} message={message} />
        ))}

        {streamingMessage && (
          <ChatMessageBubble message={streamingMessage} />
        )}

        <StreamingIndicator status={status} />

        <div ref={bottomRef} />
      </div>
    </ScrollArea>
  );
}
