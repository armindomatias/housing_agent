import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock Next.js navigation
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

// Mock Supabase client
const mockSignInWithPassword = vi.fn();
const mockSignUp = vi.fn();
const mockGetSession = vi.fn().mockResolvedValue({ data: { session: null } });

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => ({
    auth: {
      getSession: mockGetSession,
      signInWithPassword: mockSignInWithPassword,
      signUp: mockSignUp,
      onAuthStateChange: vi.fn(() => ({
        data: { subscription: { unsubscribe: vi.fn() } },
      })),
    },
  }),
}));

import AuthPage from "@/app/auth/page";

/** Get the submit button (type="submit") from all buttons with the given name. */
function getSubmitButton(name: string) {
  const buttons = screen.getAllByRole("button", { name });
  const submit = buttons.find((btn) => btn.getAttribute("type") === "submit");
  expect(submit).toBeDefined();
  return submit!;
}

/** Get the tab button (type="button") from all buttons with the given name. */
function getTabButton(name: string) {
  const buttons = screen.getAllByRole("button", { name });
  const tab = buttons.find((btn) => btn.getAttribute("type") === "button");
  expect(tab).toBeDefined();
  return tab!;
}

describe("AuthPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetSession.mockResolvedValue({ data: { session: null } });
  });

  it("renders login form with correct Portuguese labels by default", () => {
    render(<AuthPage />);

    expect(screen.getByLabelText("Email")).toBeInTheDocument();
    expect(screen.getByLabelText("Palavra-passe")).toBeInTheDocument();
    // Submit button exists in login tab
    expect(getSubmitButton("Entrar")).toBeInTheDocument();
  });

  it("switches to signup tab on click and shows signup form", async () => {
    const user = userEvent.setup();
    render(<AuthPage />);

    await user.click(getTabButton("Criar conta"));

    // After switching, the submit button should say "Criar conta"
    expect(getSubmitButton("Criar conta")).toBeInTheDocument();
  });

  it("shows error message on failed login", async () => {
    mockSignInWithPassword.mockResolvedValue({
      error: { message: "Invalid credentials" },
    });

    const user = userEvent.setup();
    render(<AuthPage />);

    await user.type(screen.getByLabelText("Email"), "test@example.com");
    await user.type(screen.getByLabelText("Palavra-passe"), "wrongpassword");
    await user.click(getSubmitButton("Entrar"));

    expect(
      await screen.findByText("Email ou palavra-passe incorretos.")
    ).toBeInTheDocument();
  });
});
