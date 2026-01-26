"use client";

import type { StreamEvent } from "@/types/analysis";

interface ProgressIndicatorProps {
  events: StreamEvent[];
  currentStep: number;
  totalSteps: number;
}

const STEP_LABELS = [
  "Iniciar",
  "Obter dados",
  "Classificar fotos",
  "Agrupar divisões",
  "Estimar custos",
  "Finalizar",
];

/**
 * Progress indicator showing real-time analysis progress.
 * Displays step progress and streaming messages.
 */
export function ProgressIndicator({
  events,
  currentStep,
  totalSteps,
}: ProgressIndicatorProps) {
  const progressPercent = (currentStep / totalSteps) * 100;

  // Get only the last 5 events for display
  const recentEvents = events.slice(-5);

  return (
    <div className="w-full max-w-2xl space-y-4">
      {/* Progress bar */}
      <div className="space-y-2">
        <div className="flex justify-between text-sm text-gray-600 dark:text-gray-400">
          <span>
            Passo {currentStep} de {totalSteps}
          </span>
          <span>{STEP_LABELS[currentStep] || ""}</span>
        </div>
        <div className="w-full bg-gray-200 rounded-full h-2 dark:bg-gray-700">
          <div
            className="bg-blue-600 h-2 rounded-full transition-all duration-300"
            style={{ width: `${progressPercent}%` }}
          />
        </div>
      </div>

      {/* Event log */}
      <div className="bg-gray-100 dark:bg-gray-800 rounded-lg p-4 min-h-[120px]">
        <div className="space-y-2 font-mono text-sm">
          {recentEvents.map((event, index) => (
            <div
              key={index}
              className={`flex items-start gap-2 ${
                event.type === "error"
                  ? "text-red-600"
                  : event.type === "result"
                    ? "text-green-600"
                    : event.type === "progress"
                      ? "text-gray-500"
                      : "text-gray-700 dark:text-gray-300"
              }`}
            >
              <span className="shrink-0">
                {event.type === "status" && ">>"}
                {event.type === "progress" && "  "}
                {event.type === "result" && "OK"}
                {event.type === "error" && "!!"}
              </span>
              <span>{event.message}</span>
            </div>
          ))}
          {recentEvents.length === 0 && (
            <div className="text-gray-500 animate-pulse">A iniciar análise...</div>
          )}
        </div>
      </div>
    </div>
  );
}
