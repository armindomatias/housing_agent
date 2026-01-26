"use client";

import { UrlInput } from "@/components/UrlInput";
import { ProgressIndicator } from "@/components/ProgressIndicator";
import { ResultsDisplay } from "@/components/ResultsDisplay";
import { usePropertyAnalysis } from "@/hooks/usePropertyAnalysis";

export default function Home() {
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

  return (
    <main className="min-h-screen py-12 px-4">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <header className="text-center mb-12">
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
              <UrlInput onSubmit={analyze} isLoading={isAnalyzing} />

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
