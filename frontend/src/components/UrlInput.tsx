"use client";

import { useState, FormEvent } from "react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
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
    <form onSubmit={handleSubmit} className="w-full max-w-2xl mx-auto">
      <label htmlFor="url" className="sr-only">
        Cole o URL do anúncio do Idealista
      </label>
      <div className="flex flex-col sm:flex-row gap-2">
        <Input
          id="url"
          type="url"
          value={url}
          onChange={(e) => {
            setUrl(e.target.value);
            if (error) setError("");
          }}
          placeholder="https://www.idealista.pt/imovel/12345678/"
          className="h-12 bg-white text-foreground flex-1"
          disabled={isLoading}
        />
        <Button
          type="submit"
          disabled={isLoading || !url}
          className="h-12 px-6 bg-slate-900 text-white hover:bg-slate-800 disabled:bg-slate-400 font-semibold"
        >
          {isLoading ? "A analisar..." : "Analisar"}
        </Button>
      </div>
      {error && <p className="text-white font-medium text-sm mt-2">{error}</p>}
      <p className="text-orange-100 text-sm mt-2">
        Exemplo: https://www.idealista.pt/imovel/12345678/
      </p>
    </form>
  );
}
