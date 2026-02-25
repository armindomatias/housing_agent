"use client";

import { PanelRightClose } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { MessageList } from "./chat/MessageList";
import { ChatInput } from "./chat/ChatInput";
import { useChat } from "@/hooks/useChat";
import { CHAT_TITLE } from "@/lib/config";

interface ChatPanelProps {
  onCollapse: () => void;
}

export function ChatPanel({ onCollapse }: ChatPanelProps) {
  const { messages, status, streamingContent, sendMessage } = useChat();
  const isDisabled = status === "thinking" || status === "streaming";

  return (
    <div className="flex flex-col h-full w-full">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 shrink-0">
        <span className="text-sm font-semibold text-foreground">{CHAT_TITLE}</span>
        <Button
          variant="ghost"
          size="icon"
          onClick={onCollapse}
          aria-label="Fechar painel de chat"
          className="h-7 w-7"
        >
          <PanelRightClose className="h-4 w-4" />
        </Button>
      </div>

      <Separator />

      {/* Messages */}
      <MessageList
        messages={messages}
        status={status}
        streamingContent={streamingContent}
      />

      {/* Input */}
      <ChatInput onSend={sendMessage} disabled={isDisabled} />
    </div>
  );
}
