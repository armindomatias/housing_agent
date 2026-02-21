"use client";

import Link from "next/link";
import { Suspense, useState, FormEvent, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

type AuthTab = "login" | "signup";

function AuthPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const redirectPath = searchParams.get("redirect") || "/";
  const prefillUrl = searchParams.get("url") || "";
  const callbackError = searchParams.get("error");

  const [tab, setTab] = useState<AuthTab>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(
    callbackError ? "Falha na confirmação do email. Tente novamente." : null
  );
  const [signupSuccess, setSignupSuccess] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  const supabase = createClient();

  useEffect(() => {
    // If already logged in, redirect immediately
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (session) {
        const dest = prefillUrl
          ? `${redirectPath}?url=${encodeURIComponent(prefillUrl)}`
          : redirectPath;
        router.replace(dest);
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsLoading(true);

    try {
      if (tab === "login") {
        const { error: signInError } = await supabase.auth.signInWithPassword({
          email,
          password,
        });
        if (signInError) {
          setError("Email ou palavra-passe incorretos.");
          return;
        }
        const dest = prefillUrl
          ? `${redirectPath}?url=${encodeURIComponent(prefillUrl)}`
          : redirectPath;
        router.replace(dest);
      } else {
        const { error: signUpError } = await supabase.auth.signUp({
          email,
          password,
        });
        if (signUpError) {
          setError("Não foi possível criar a conta. Tente novamente.");
          return;
        }
        setSignupSuccess(true);
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <main className="min-h-screen flex items-center justify-center py-12 px-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <Link href="/">
            <h1 className="text-3xl font-bold mb-2 text-primary">Rehabify</h1>
          </Link>
          <p className="text-muted-foreground">
            Aceda à sua conta para analisar imóveis
          </p>
        </div>

        <div className="bg-card rounded-xl border border-border p-6">
          {/* Tab toggle */}
          <div className="flex mb-6 border border-border rounded-lg overflow-hidden">
            <button
              type="button"
              onClick={() => {
                setTab("login");
                setError(null);
                setSignupSuccess(false);
              }}
              className={`flex-1 py-2 text-sm font-medium transition-colors ${
                tab === "login"
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:bg-accent"
              }`}
            >
              Entrar
            </button>
            <button
              type="button"
              onClick={() => {
                setTab("signup");
                setError(null);
                setSignupSuccess(false);
              }}
              className={`flex-1 py-2 text-sm font-medium transition-colors ${
                tab === "signup"
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:bg-accent"
              }`}
            >
              Criar conta
            </button>
          </div>

          {/* Signup success */}
          {signupSuccess && (
            <div className="mb-4 p-4 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg">
              <p className="text-green-800 dark:text-green-200 text-sm">
                Verifique o seu email para confirmar a conta.
              </p>
            </div>
          )}

          {/* Error message */}
          {error && (
            <div className="mb-4 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
              <p className="text-red-800 dark:text-red-200 text-sm">{error}</p>
            </div>
          )}

          {/* Auth form */}
          {!signupSuccess && (
            <form onSubmit={handleSubmit} className="flex flex-col gap-4">
              <div className="flex flex-col gap-1">
                <label htmlFor="email" className="text-sm font-medium">
                  Email
                </label>
                <Input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="o-seu@email.com"
                  required
                  disabled={isLoading}
                />
              </div>

              <div className="flex flex-col gap-1">
                <label htmlFor="password" className="text-sm font-medium">
                  Palavra-passe
                </label>
                <Input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  required
                  disabled={isLoading}
                />
              </div>

              <Button
                type="submit"
                disabled={isLoading || !email || !password}
              >
                {isLoading
                  ? "A processar..."
                  : tab === "login"
                  ? "Entrar"
                  : "Criar conta"}
              </Button>
            </form>
          )}
        </div>
      </div>
    </main>
  );
}

export default function AuthPage() {
  return (
    <Suspense>
      <AuthPageContent />
    </Suspense>
  );
}
