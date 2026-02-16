import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { UrlInput } from "@/components/UrlInput";

describe("UrlInput", () => {
  it("renders the input and submit button", () => {
    render(<UrlInput onSubmit={vi.fn()} isLoading={false} />);

    expect(screen.getByRole("textbox")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Analisar" })).toBeInTheDocument();
  });

  it("disables input and button when loading", () => {
    render(<UrlInput onSubmit={vi.fn()} isLoading={true} />);

    expect(screen.getByRole("textbox")).toBeDisabled();
    expect(screen.getByRole("button", { name: "A analisar..." })).toBeDisabled();
  });

  it("disables submit button when URL is empty", () => {
    render(<UrlInput onSubmit={vi.fn()} isLoading={false} />);

    expect(screen.getByRole("button", { name: "Analisar" })).toBeDisabled();
  });

  it("calls onSubmit with valid Idealista URL", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<UrlInput onSubmit={onSubmit} isLoading={false} />);

    await user.type(
      screen.getByRole("textbox"),
      "https://www.idealista.pt/imovel/12345678/"
    );
    await user.click(screen.getByRole("button", { name: "Analisar" }));

    expect(onSubmit).toHaveBeenCalledWith(
      "https://www.idealista.pt/imovel/12345678/"
    );
  });

  it("shows error for non-Idealista URL", async () => {
    const user = userEvent.setup();
    render(<UrlInput onSubmit={vi.fn()} isLoading={false} />);

    await user.type(
      screen.getByRole("textbox"),
      "https://www.example.com/property/123"
    );
    await user.click(screen.getByRole("button", { name: "Analisar" }));

    expect(
      screen.getByText("O URL deve ser do Idealista Portugal (idealista.pt)")
    ).toBeInTheDocument();
  });

  it("shows error for Idealista URL without /imovel/", async () => {
    const user = userEvent.setup();
    render(<UrlInput onSubmit={vi.fn()} isLoading={false} />);

    await user.type(
      screen.getByRole("textbox"),
      "https://www.idealista.pt/comprar-casas/lisboa/"
    );
    await user.click(screen.getByRole("button", { name: "Analisar" }));

    expect(
      screen.getByText("O URL deve ser de um anúncio específico (/imovel/...)")
    ).toBeInTheDocument();
  });
});
