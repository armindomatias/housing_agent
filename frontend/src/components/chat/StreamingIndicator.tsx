import type { ChatStatus } from "@/types/chat";

interface StreamingIndicatorProps {
  status: ChatStatus;
}

export function StreamingIndicator({ status }: StreamingIndicatorProps) {
  if (status !== "thinking") return null;

  return (
    <div className="flex justify-start">
      <div className="bg-muted rounded-lg px-3 py-2 text-sm text-muted-foreground flex items-center gap-1">
        <span>A processar</span>
        <span className="flex gap-0.5">
          <span className="animate-bounce [animation-delay:0ms]">.</span>
          <span className="animate-bounce [animation-delay:150ms]">.</span>
          <span className="animate-bounce [animation-delay:300ms]">.</span>
        </span>
      </div>
    </div>
  );
}
