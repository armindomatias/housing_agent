"use client";

import { useState, FormEvent } from "react";
import { IDEALISTA_DOMAIN, IDEALISTA_PATH_SEGMENT } from "@/lib/config";

interface UrlInputProps {
  onSubmit: (url: string) => void;
  isLoading: boolean;
  defaultValue?: string;
}

/**
 * URL input component for Idealista property URLs.
 * Validates that the URL is a valid Idealista listing.
 */
export function UrlInput({ onSubmit, isLoading, defaultValue = "" }: UrlInputProps) {
  const [url, setUrl] = useState(defaultValue);
  const [error, setError] = useState("");

  const validateUrl = (value: string): boolean => {
    try {
      const urlObj = new URL(value);
      if (!urlObj.hostname.includes(IDEALISTA_DOMAIN)) {
        setError("O URL deve ser do Idealista Portugal (idealista.pt)");
        return false;
      }
      if (!urlObj.pathname.includes(IDEALISTA_PATH_SEGMENT)) {
        setError("O URL deve ser de um anúncio específico (/imovel/...)");
        return false;
      }
      setError("");
      return true;
    } catch {
      setError("Por favor insira um URL válido");
      return false;
    }
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (validateUrl(url)) {
      onSubmit(url);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="w-full max-w-2xl">
      <div className="flex flex-col gap-4">
        <label htmlFor="url" className="text-lg font-medium">
          Cole o URL do anúncio do Idealista
        </label>
        <div className="flex gap-2">
          <input
            id="url"
            type="url"
            value={url}
            onChange={(e) => {
              setUrl(e.target.value);
              if (error) setError("");
            }}
            placeholder="https://www.idealista.pt/imovel/12345678/"
            className="flex-1 px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent dark:bg-gray-800 dark:border-gray-600"
            disabled={isLoading}
          />
          <button
            type="submit"
            disabled={isLoading || !url}
            className="px-6 py-3 bg-blue-600 text-white font-medium rounded-lg hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
          >
            {isLoading ? "A analisar..." : "Analisar"}
          </button>
        </div>
        {error && <p className="text-red-500 text-sm">{error}</p>}
        <p className="text-gray-500 text-sm">
          Exemplo: https://www.idealista.pt/imovel/12345678/
        </p>
      </div>
    </form>
  );
}
