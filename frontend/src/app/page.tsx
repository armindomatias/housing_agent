"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { MessageCircle } from "lucide-react";
import { Navbar } from "@/components/Navbar";
import { UrlInput } from "@/components/UrlInput";
import { HowItWorks } from "@/components/HowItWorks";
import { AnalysisLoadingSkeleton } from "@/components/AnalysisLoadingSkeleton";
import { ResultsDisplay } from "@/components/ResultsDisplay";
import { ChatPanel } from "@/components/ChatPanel";
import { usePropertyAnalysis } from "@/hooks/usePropertyAnalysis";
import { useAuth } from "@/hooks/useAuth";
import { AUTH_PAGE_PATH } from "@/lib/config";
import { Button } from "@/components/ui/button";

function HomeContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const prefillUrl = searchParams.get("url") || "";

  const { user } = useAuth();
  const {
    isAnalyzing,
    events,
    result,
    error,
    currentStep,
    totalSteps,
    analyze,
    reset,
  } = usePropertyAnalysis();

  const [chatOpen, setChatOpen] = useState(false);

  const handleAnalyze = (url: string) => {
    if (!user) {
      router.push(
        `${AUTH_PAGE_PATH}?redirect=/&url=${encodeURIComponent(url)}`
      );
      return;
    }
    analyze(url);
    setChatOpen(true);
  };

  const handleReset = () => {
    reset();
    setChatOpen(false);
  };

  const showLanding = !isAnalyzing && !result;

  return (
    <div className="min-h-screen flex flex-col">
      <Navbar />

      <main className="flex-1 flex flex-col">
        {/* Hero section */}
        {showLanding && (
          <section className="bg-orange-500 py-20 px-4">
            <div className="max-w-3xl mx-auto text-center space-y-6">
              <h1 className="text-4xl sm:text-5xl font-bold text-white leading-tight">
                Quanto custa remodelar o seu imóvel?
              </h1>
              <p className="text-lg text-orange-100 max-w-xl mx-auto">
                Cole o link de um anúncio do Idealista e receba uma estimativa
                detalhada de custos de remodelação, divisão a divisão.
              </p>
              <div className="pt-2">
                <UrlInput
                  onSubmit={handleAnalyze}
                  isLoading={isAnalyzing}
                  defaultValue={prefillUrl}
                />
              </div>
            </div>
          </section>
        )}

        {/* Error display */}
        {showLanding && error && (
          <div className="max-w-3xl mx-auto w-full px-4 py-4">
            <div className="bg-destructive/10 border border-destructive/30 rounded-lg p-4">
              <p className="text-destructive text-sm">
                <strong>Erro:</strong> {error}
              </p>
              <button
                onClick={handleReset}
                className="mt-2 text-sm text-destructive underline underline-offset-2"
              >
                Tentar novamente
              </button>
            </div>
          </div>
        )}

        {/* How it works */}
        {showLanding && !error && <HowItWorks />}

        {/* Progress while analyzing */}
        {isAnalyzing && (
          <div className="flex-1 px-4 py-12">
            <div className="max-w-4xl mx-auto">
              <AnalysisLoadingSkeleton
                events={events}
                currentStep={currentStep}
                totalSteps={totalSteps}
              />
            </div>
          </div>
        )}

        {/* Results — split layout on desktop, full-width + floating button on mobile */}
        {result && (
          <div className="flex-1 flex overflow-hidden">
            {/* Results panel */}
            <div
              className={
                chatOpen
                  ? "flex-1 min-w-0 overflow-y-auto px-4 py-10 lg:pr-0"
                  : "flex-1 min-w-0 overflow-y-auto px-4 py-10"
              }
            >
              <div
                className={
                  chatOpen
                    ? "max-w-4xl mx-auto lg:mx-0 lg:max-w-none"
                    : "max-w-4xl mx-auto"
                }
              >
                <ResultsDisplay estimate={result} onReset={handleReset} />
              </div>
            </div>

            {/* Chat panel — side panel on desktop (lg+) */}
            {chatOpen && (
              <div className="hidden lg:flex w-[30%] shrink-0 border-l border-border overflow-hidden">
                <ChatPanel onCollapse={() => setChatOpen(false)} />
              </div>
            )}
          </div>
        )}
      </main>

      {/* Floating chat button — visible when results exist and chat is closed */}
      {result && !chatOpen && (
        <Button
          onClick={() => setChatOpen(true)}
          className="fixed bottom-6 right-6 rounded-full shadow-lg h-12 w-12 p-0"
          aria-label="Abrir assistente"
        >
          <MessageCircle className="h-5 w-5" />
        </Button>
      )}

      <footer className={`border-t border-border py-6 px-4 ${result ? "hidden lg:block" : ""}`}>
        <p className="text-center text-sm text-muted-foreground">
          Rehabify fornece estimativas indicativas. Para decisões de
          investimento, consulte profissionais qualificados.
        </p>
      </footer>
    </div>
  );
}

export default function Home() {
  return (
    <Suspense>
      <HomeContent />
    </Suspense>
  );
}
