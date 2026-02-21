"use client";

import type { StreamEvent } from "@/types/analysis";
import { Skeleton } from "@/components/ui/skeleton";
import { STEP_LABELS } from "@/lib/config";

interface AnalysisLoadingSkeletonProps {
  events: StreamEvent[];
  currentStep: number;
  totalSteps: number;
}

function RoomCardSkeleton() {
  return (
    <div className="rounded-lg border border-border bg-card p-4 space-y-3">
      {/* Title row */}
      <div className="flex justify-between items-center">
        <Skeleton className="h-5 w-32" />
        <Skeleton className="h-4 w-16" />
      </div>

      {/* Image strip */}
      <div className="flex gap-2">
        <Skeleton className="h-28 w-40 flex-shrink-0 rounded" />
        <Skeleton className="h-28 w-40 flex-shrink-0 rounded" />
      </div>

      {/* Cost box */}
      <Skeleton className="h-14 w-full rounded" />

      {/* Renovation items */}
      <div className="space-y-2">
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-5/6" />
        <Skeleton className="h-4 w-4/6" />
      </div>
    </div>
  );
}

export function AnalysisLoadingSkeleton({
  events,
  currentStep,
  totalSteps,
}: AnalysisLoadingSkeletonProps) {
  const progressPercent = (currentStep / totalSteps) * 100;
  const lastEvent = events[events.length - 1];

  const eventPrefix =
    lastEvent?.type === "error"
      ? "!!"
      : lastEvent?.type === "result"
        ? "OK"
        : lastEvent?.type === "progress"
          ? "  "
          : ">>";

  return (
    <div className="w-full max-w-4xl space-y-6">
      {/* Progress bar + step label */}
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

      {/* Live status strip */}
      <div className="font-mono text-sm text-muted-foreground truncate">
        {lastEvent ? (
          <span>
            {eventPrefix} {lastEvent.message}
          </span>
        ) : (
          <span className="animate-pulse">A iniciar análise...</span>
        )}
      </div>

      {/* Header skeleton — dark bg with 3 stat cards */}
      <div className="bg-slate-900 rounded-xl p-6 space-y-4">
        <Skeleton className="h-7 w-56 bg-white/10" />
        <Skeleton className="h-4 w-72 bg-white/10" />
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-2">
          <div className="bg-white/10 rounded-lg p-4 space-y-2">
            <Skeleton className="h-3 w-20 bg-white/20" />
            <Skeleton className="h-7 w-28 bg-white/20" />
          </div>
          <div className="bg-white/10 rounded-lg p-4 space-y-2">
            <Skeleton className="h-3 w-20 bg-white/20" />
            <Skeleton className="h-7 w-28 bg-white/20" />
          </div>
          <div className="bg-white/10 rounded-lg p-4 space-y-2">
            <Skeleton className="h-3 w-20 bg-white/20" />
            <Skeleton className="h-7 w-28 bg-white/20" />
          </div>
        </div>
      </div>

      {/* Hero images skeleton */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <Skeleton className="h-48 w-full rounded-lg" />
        <Skeleton className="h-48 w-full rounded-lg" />
      </div>

      {/* Summary skeleton */}
      <div className="rounded-lg border border-border bg-card p-4 space-y-2">
        <Skeleton className="h-5 w-24" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-5/6" />
        <Skeleton className="h-4 w-3/4" />
      </div>

      {/* Room grid skeleton — 4 cards in md:grid-cols-2 */}
      <div>
        <Skeleton className="h-6 w-48 mb-4" />
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <RoomCardSkeleton />
          <RoomCardSkeleton />
          <RoomCardSkeleton />
          <RoomCardSkeleton />
        </div>
      </div>
    </div>
  );
}
