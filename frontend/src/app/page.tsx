"use client";

import { Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Navbar } from "@/components/Navbar";
import { UrlInput } from "@/components/UrlInput";
import { HowItWorks } from "@/components/HowItWorks";
import { AnalysisLoadingSkeleton } from "@/components/AnalysisLoadingSkeleton";
import { ResultsDisplay } from "@/components/ResultsDisplay";
import { usePropertyAnalysis } from "@/hooks/usePropertyAnalysis";
import { useAuth } from "@/hooks/useAuth";
import { AUTH_PAGE_PATH } from "@/lib/config";

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

  const handleAnalyze = (url: string) => {
    if (!user) {
      router.push(
        `${AUTH_PAGE_PATH}?redirect=/&url=${encodeURIComponent(url)}`
      );
      return;
    }
    analyze(url);
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
                onClick={reset}
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

        {/* Results */}
        {result && (
          <div className="px-4 py-10">
            <div className="max-w-4xl mx-auto">
              <ResultsDisplay estimate={result} onReset={reset} />
            </div>
          </div>
        )}
      </main>

      <footer className="border-t border-border py-6 px-4">
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
