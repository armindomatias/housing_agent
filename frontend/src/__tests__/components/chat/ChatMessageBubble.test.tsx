import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { ChatMessageBubble } from "@/components/chat/ChatMessageBubble";
import type { ChatMessage } from "@/types/chat";

function makeMessage(overrides: Partial<ChatMessage>): ChatMessage {
  return {
    id: "test-id",
    role: "user",
    content: "Mensagem de teste",
    timestamp: new Date(),
    ...overrides,
  };
}

describe("ChatMessageBubble", () => {
  it("renders user message content", () => {
    render(<ChatMessageBubble message={makeMessage({ content: "Olá!" })} />);
    expect(screen.getByText("Olá!")).toBeInTheDocument();
  });

  it("renders assistant message content", () => {
    render(
      <ChatMessageBubble
        message={makeMessage({ role: "assistant", content: "Resposta do assistente" })}
      />
    );
    expect(screen.getByText("Resposta do assistente")).toBeInTheDocument();
  });

  it("applies user bubble styling (justify-end)", () => {
    const { container } = render(
      <ChatMessageBubble message={makeMessage({ role: "user" })} />
    );
    expect(container.firstChild).toHaveClass("justify-end");
  });

  it("applies assistant bubble styling (justify-start)", () => {
    const { container } = render(
      <ChatMessageBubble message={makeMessage({ role: "assistant" })} />
    );
    expect(container.firstChild).toHaveClass("justify-start");
  });

  it("applies error styling when isError=true", () => {
    const { container } = render(
      <ChatMessageBubble
        message={makeMessage({ role: "assistant", isError: true, content: "Erro" })}
      />
    );
    const bubble = container.querySelector("[class*='destructive']");
    expect(bubble).toBeInTheDocument();
  });

  it("renders markdown in assistant messages", () => {
    render(
      <ChatMessageBubble
        message={makeMessage({ role: "assistant", content: "**negrito**" })}
      />
    );
    expect(screen.getByText("negrito").tagName).toBe("STRONG");
  });
});
