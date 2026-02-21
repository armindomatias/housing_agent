"use client";

import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/hooks/useAuth";
import { AUTH_PAGE_PATH } from "@/lib/config";

export function Navbar() {
  const router = useRouter();
  const { user, loading, signOut } = useAuth();

  return (
    <nav className="sticky top-0 z-50 w-full border-b border-border bg-background/95 backdrop-blur-sm">
      <div className="max-w-6xl mx-auto px-4 h-16 flex items-center justify-between">
        <span className="text-xl font-bold text-primary tracking-tight">Rehabify</span>

        <div className="flex items-center gap-3">
          {!loading && user && (
            <>
              <span className="text-sm text-muted-foreground hidden sm:inline">
                {user.email}
              </span>
              <Button variant="outline" size="sm" onClick={signOut}>
                Sair
              </Button>
            </>
          )}
          {!loading && !user && (
            <Button size="sm" onClick={() => router.push(AUTH_PAGE_PATH)}>
              Entrar
            </Button>
          )}
        </div>
      </div>
    </nav>
  );
}
