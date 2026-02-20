"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { UrlInput } from "@/components/UrlInput";
import { ProgressIndicator } from "@/components/ProgressIndicator";
import { ResultsDisplay } from "@/components/ResultsDisplay";
import { usePropertyAnalysis } from "@/hooks/usePropertyAnalysis";
import { useAuth } from "@/hooks/useAuth";
import { AUTH_PAGE_PATH } from "@/lib/config";

export default function Home() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const prefillUrl = searchParams.get("url") || "";

  const { user, loading: authLoading, signOut } = useAuth();
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

  return (
    <main className="min-h-screen py-12 px-4">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <header className="text-center mb-12 relative">
          {/* User info (top-right) */}
          {!authLoading && user && (
            <div className="absolute right-0 top-0 flex items-center gap-3">
              <span className="text-sm text-gray-600 dark:text-gray-400">
                {user.email}
              </span>
              <button
                onClick={signOut}
                className="text-sm px-3 py-1.5 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
              >
                Sair
              </button>
            </div>
          )}
          {!authLoading && !user && (
            <div className="absolute right-0 top-0">
              <button
                onClick={() => router.push(AUTH_PAGE_PATH)}
                className="text-sm px-3 py-1.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
              >
                Entrar
              </button>
            </div>
          )}

          <h1 className="text-4xl font-bold mb-4">Rehabify</h1>
          <p className="text-xl text-gray-600 dark:text-gray-400">
            Estimativa de custos de remodelação para imóveis em Portugal
          </p>
        </header>

        {/* Content */}
        <div className="flex flex-col items-center gap-8">
          {/* Show URL input if not analyzing and no result */}
          {!isAnalyzing && !result && (
            <>
              <UrlInput
                onSubmit={handleAnalyze}
                isLoading={isAnalyzing}
                defaultValue={prefillUrl}
              />

              {/* Show error if exists */}
              {error && (
                <div className="w-full max-w-2xl bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
                  <p className="text-red-800 dark:text-red-200">
                    <strong>Erro:</strong> {error}
                  </p>
                  <button
                    onClick={reset}
                    className="mt-2 text-sm text-red-600 dark:text-red-400 underline"
                  >
                    Tentar novamente
                  </button>
                </div>
              )}

              {/* How it works */}
              <div className="w-full max-w-2xl mt-8">
                <h2 className="text-xl font-semibold mb-4">Como funciona?</h2>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-4 text-center">
                    <div className="text-3xl mb-2">1</div>
                    <h3 className="font-medium mb-1">Cole o URL</h3>
                    <p className="text-sm text-gray-600 dark:text-gray-400">
                      Copie o link do anúncio do Idealista
                    </p>
                  </div>
                  <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-4 text-center">
                    <div className="text-3xl mb-2">2</div>
                    <h3 className="font-medium mb-1">Análise IA</h3>
                    <p className="text-sm text-gray-600 dark:text-gray-400">
                      A IA analisa as fotos do imóvel
                    </p>
                  </div>
                  <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-4 text-center">
                    <div className="text-3xl mb-2">3</div>
                    <h3 className="font-medium mb-1">Estimativa</h3>
                    <p className="text-sm text-gray-600 dark:text-gray-400">
                      Receba custos detalhados por divisão
                    </p>
                  </div>
                </div>
              </div>
            </>
          )}

          {/* Show progress while analyzing */}
          {isAnalyzing && (
            <ProgressIndicator
              events={events}
              currentStep={currentStep}
              totalSteps={totalSteps}
            />
          )}

          {/* Show results when complete */}
          {result && <ResultsDisplay estimate={result} onReset={reset} />}
        </div>

        {/* Footer */}
        <footer className="mt-16 text-center text-sm text-gray-500">
          <p>
            Rehabify fornece estimativas indicativas. Para decisões de investimento,
            consulte profissionais qualificados.
          </p>
        </footer>
      </div>
    </main>
  );
}
