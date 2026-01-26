"use client";

import { useState, useCallback } from "react";
import type { StreamEvent, RenovationEstimate } from "@/types/analysis";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface UsePropertyAnalysisResult {
  isAnalyzing: boolean;
  events: StreamEvent[];
  result: RenovationEstimate | null;
  error: string | null;
  currentStep: number;
  totalSteps: number;
  analyze: (url: string) => Promise<void>;
  reset: () => void;
}

/**
 * Custom hook for analyzing properties with streaming progress.
 *
 * Uses Server-Sent Events (SSE) to receive real-time progress updates
 * as the backend analyzes the property.
 *
 * @example
 * const { analyze, events, result, isAnalyzing } = usePropertyAnalysis();
 * await analyze("https://www.idealista.pt/imovel/12345678/");
 */
export function usePropertyAnalysis(): UsePropertyAnalysisResult {
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [events, setEvents] = useState<StreamEvent[]>([]);
  const [result, setResult] = useState<RenovationEstimate | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [currentStep, setCurrentStep] = useState(0);
  const [totalSteps, setTotalSteps] = useState(5);

  const reset = useCallback(() => {
    setIsAnalyzing(false);
    setEvents([]);
    setResult(null);
    setError(null);
    setCurrentStep(0);
  }, []);

  const analyze = useCallback(async (url: string) => {
    // Reset state
    setIsAnalyzing(true);
    setEvents([]);
    setResult(null);
    setError(null);
    setCurrentStep(0);

    try {
      // Create SSE connection via fetch with POST
      const response = await fetch(`${API_URL}/api/v1/analyze`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "text/event-stream",
        },
        body: JSON.stringify({ url }),
      });

      if (!response.ok) {
        throw new Error(`Erro HTTP: ${response.status}`);
      }

      if (!response.body) {
        throw new Error("Resposta sem corpo");
      }

      // Read the stream
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();

        if (done) break;

        // Decode the chunk and add to buffer
        buffer += decoder.decode(value, { stream: true });

        // Process complete SSE messages
        const lines = buffer.split("\n");
        buffer = lines.pop() || ""; // Keep incomplete line in buffer

        for (const line of lines) {
          // SSE format: "data: {...json...}"
          if (line.startsWith("data: ")) {
            const jsonStr = line.slice(6).trim();
            if (jsonStr) {
              try {
                const event: StreamEvent = JSON.parse(jsonStr);

                // Update state based on event
                setEvents((prev) => [...prev, event]);
                setCurrentStep(event.step);
                setTotalSteps(event.total_steps);

                if (event.type === "error") {
                  setError(event.message);
                }

                if (event.type === "result" && event.data?.estimate) {
                  setResult(event.data.estimate);
                }
              } catch (e) {
                console.error("Failed to parse SSE event:", e, jsonStr);
              }
            }
          }
        }
      }
    } catch (e) {
      const errorMessage = e instanceof Error ? e.message : "Erro desconhecido";
      setError(errorMessage);
      console.error("Analysis error:", e);
    } finally {
      setIsAnalyzing(false);
    }
  }, []);

  return {
    isAnalyzing,
    events,
    result,
    error,
    currentStep,
    totalSteps,
    analyze,
    reset,
  };
}
