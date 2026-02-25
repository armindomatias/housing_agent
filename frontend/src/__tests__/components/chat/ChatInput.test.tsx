import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { ChatInput } from "@/components/chat/ChatInput";

describe("ChatInput", () => {
  it("renders textarea and send button", () => {
    render(<ChatInput onSend={vi.fn()} disabled={false} />);
    expect(screen.getByRole("textbox")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Enviar mensagem" })).toBeInTheDocument();
  });

  it("disables send button when input is empty", () => {
    render(<ChatInput onSend={vi.fn()} disabled={false} />);
    expect(screen.getByRole("button", { name: "Enviar mensagem" })).toBeDisabled();
  });

  it("disables textarea and button when disabled=true", () => {
    render(<ChatInput onSend={vi.fn()} disabled={true} />);
    expect(screen.getByRole("textbox")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Enviar mensagem" })).toBeDisabled();
  });

  it("calls onSend and clears input when Enter is pressed", async () => {
    const user = userEvent.setup();
    const onSend = vi.fn();
    render(<ChatInput onSend={onSend} disabled={false} />);

    await user.type(screen.getByRole("textbox"), "Olá{Enter}");

    expect(onSend).toHaveBeenCalledWith("Olá");
    expect(screen.getByRole("textbox")).toHaveValue("");
  });

  it("does NOT call onSend when Shift+Enter is pressed", async () => {
    const user = userEvent.setup();
    const onSend = vi.fn();
    render(<ChatInput onSend={onSend} disabled={false} />);

    await user.type(screen.getByRole("textbox"), "Olá{Shift>}{Enter}{/Shift}");

    expect(onSend).not.toHaveBeenCalled();
  });

  it("calls onSend when send button is clicked", async () => {
    const user = userEvent.setup();
    const onSend = vi.fn();
    render(<ChatInput onSend={onSend} disabled={false} />);

    await user.type(screen.getByRole("textbox"), "Mensagem de teste");
    await user.click(screen.getByRole("button", { name: "Enviar mensagem" }));

    expect(onSend).toHaveBeenCalledWith("Mensagem de teste");
  });

  it("does not call onSend for whitespace-only input", async () => {
    const user = userEvent.setup();
    const onSend = vi.fn();
    render(<ChatInput onSend={onSend} disabled={false} />);

    await user.type(screen.getByRole("textbox"), "   {Enter}");

    expect(onSend).not.toHaveBeenCalled();
  });
});
