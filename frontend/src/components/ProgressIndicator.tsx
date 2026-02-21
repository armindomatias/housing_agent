"use client";

import type { StreamEvent } from "@/types/analysis";
import { Card, CardContent } from "@/components/ui/card";
import { MAX_RECENT_EVENTS, STEP_LABELS } from "@/lib/config";

interface ProgressIndicatorProps {
  events: StreamEvent[];
  currentStep: number;
  totalSteps: number;
}

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

  // Get only the last MAX_RECENT_EVENTS events for display
  const recentEvents = events.slice(-MAX_RECENT_EVENTS);

  return (
    <div className="w-full max-w-2xl space-y-4">
      {/* Progress bar */}
      <div className="space-y-2">
        <div className="flex justify-between text-sm text-muted-foreground">
          <span>
            Passo {currentStep} de {totalSteps}
          </span>
          <span>{STEP_LABELS[currentStep] || ""}</span>
        </div>
        <div className="w-full bg-secondary rounded-full h-2">
          <div
            className="bg-primary h-2 rounded-full transition-all duration-300"
            style={{ width: `${progressPercent}%` }}
          />
        </div>
      </div>

      {/* Event log */}
      <Card>
        <CardContent className="pt-4 min-h-[120px]">
          <div className="space-y-2 font-mono text-sm">
            {recentEvents.map((event, index) => (
              <div
                key={index}
                className={`flex items-start gap-2 ${
                  event.type === "error"
                    ? "text-destructive"
                    : event.type === "result"
                      ? "text-green-600"
                      : event.type === "progress"
                        ? "text-muted-foreground"
                        : "text-foreground"
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
              <div className="text-muted-foreground animate-pulse">A iniciar análise...</div>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
