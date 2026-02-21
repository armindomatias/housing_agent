"use client";

import type { RenovationEstimate, RoomAnalysis } from "@/types/analysis";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { LOCALE, CURRENCY, MAX_HERO_IMAGES, MIN_UNIQUE_HERO_IMAGES } from "@/lib/config";

interface ResultsDisplayProps {
  estimate: RenovationEstimate;
  onReset: () => void;
}

const conditionLabels: Record<string, { label: string; color: string }> = {
  excelente: { label: "Excelente", color: "text-green-600" },
  bom: { label: "Bom", color: "text-green-500" },
  razoavel: { label: "Razoável", color: "text-yellow-600" },
  mau: { label: "Mau", color: "text-orange-600" },
  necessita_remodelacao_total: { label: "Remodelação Total", color: "text-red-600" },
};

const priorityBadgeVariant: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
  alta: "destructive",
  media: "secondary",
  baixa: "outline",
};

const priorityLabels: Record<string, string> = {
  alta: "Alta",
  media: "Média",
  baixa: "Baixa",
};

function formatCurrency(value: number): string {
  return new Intl.NumberFormat(LOCALE, {
    style: "currency",
    currency: CURRENCY,
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
}

function RoomCard({ room }: { room: RoomAnalysis }) {
  const condition = conditionLabels[room.condition] || conditionLabels.razoavel;
  const confidencePercent = Math.round(room.confidence * 100);

  return (
    <Card>
      <CardContent className="pt-4">
        <div className="flex justify-between items-start mb-3">
          <h3 className="text-lg font-semibold">{room.room_label}</h3>
          <span className={`text-sm font-medium ${condition.color}`}>
            {condition.label}
          </span>
        </div>

        {/* Room images */}
        {room.images && room.images.length > 0 && (
          <div className="flex overflow-x-auto gap-2 mb-3 pb-1">
            {room.images.map((url, idx) => (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                key={idx}
                src={url}
                alt={`${room.room_label} ${idx + 1}`}
                className="h-28 w-auto flex-shrink-0 rounded object-cover"
              />
            ))}
          </div>
        )}

        <p className="text-muted-foreground text-sm mb-3">{room.condition_notes}</p>

        {/* Cost range */}
        <div className="bg-muted rounded p-3 mb-3">
          <div className="flex justify-between items-center">
            <span className="text-muted-foreground text-sm">Custo estimado:</span>
            <span className="font-semibold">
              {formatCurrency(room.cost_min)} - {formatCurrency(room.cost_max)}
            </span>
          </div>
          <div className="text-xs text-muted-foreground mt-1">
            Confiança: {confidencePercent}%
          </div>
        </div>

        {/* Renovation items */}
        {room.renovation_items.length > 0 && (
          <div className="space-y-2">
            <h4 className="text-sm font-medium">Trabalhos recomendados:</h4>
            <ul className="space-y-1">
              {room.renovation_items.map((item, idx) => {
                const variant = priorityBadgeVariant[item.priority] ?? "secondary";
                const label = priorityLabels[item.priority] ?? "Média";
                return (
                  <li key={idx} className="flex items-start gap-2 text-sm">
                    <Badge variant={variant} className="shrink-0 text-xs">
                      {label}
                    </Badge>
                    <span className="flex-1">{item.item}</span>
                    <span className="text-muted-foreground shrink-0">
                      {formatCurrency(item.cost_min)} - {formatCurrency(item.cost_max)}
                    </span>
                  </li>
                );
              })}
            </ul>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

/**
 * Display component for renovation estimate results.
 * Shows property info, room-by-room breakdown, and total costs.
 */
export function ResultsDisplay({ estimate, onReset }: ResultsDisplayProps) {
  const confidencePercent = Math.round(estimate.overall_confidence * 100);

  // Compute hero images: prefer images not used in any room analysis
  const heroImages = (() => {
    if (!estimate.property_data?.image_urls?.length) return [];
    const usedUrls = new Set(
      estimate.room_analyses.flatMap((r) => r.images ?? [])
    );
    const general = estimate.property_data.image_urls.filter(
      (url) => !usedUrls.has(url)
    );
    const candidates = general.length >= MIN_UNIQUE_HERO_IMAGES ? general : estimate.property_data.image_urls;
    return candidates.slice(0, MAX_HERO_IMAGES);
  })();

  return (
    <div className="w-full space-y-6">
      {/* Header with totals */}
      <div className="bg-gradient-to-r from-slate-900 to-slate-800 rounded-xl p-6 text-white">
        <h2 className="text-2xl font-bold mb-2">Estimativa de Remodelação</h2>

        {estimate.property_data && (
          <p className="text-slate-400 mb-4">
            {estimate.property_data.title || estimate.property_data.location}
          </p>
        )}

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="bg-white/10 rounded-lg p-4">
            <div className="text-slate-400 text-sm">Custo Mínimo</div>
            <div className="text-2xl font-bold">
              {formatCurrency(estimate.total_cost_min)}
            </div>
          </div>
          <div className="bg-white/10 rounded-lg p-4">
            <div className="text-slate-400 text-sm">Custo Máximo</div>
            <div className="text-2xl font-bold">
              {formatCurrency(estimate.total_cost_max)}
            </div>
          </div>
          <div className="bg-white/10 rounded-lg p-4">
            <div className="text-slate-400 text-sm">Confiança</div>
            <div className="text-2xl font-bold text-orange-400">{confidencePercent}%</div>
          </div>
        </div>

        {estimate.property_data && estimate.property_data.price > 0 && (
          <div className="mt-4 text-slate-400 text-sm">
            Preço do imóvel: {formatCurrency(estimate.property_data.price)} |
            Custo total: {formatCurrency(estimate.property_data.price + estimate.total_cost_min)} -{" "}
            {formatCurrency(estimate.property_data.price + estimate.total_cost_max)}
          </div>
        )}
      </div>

      {/* Hero images */}
      {heroImages.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {heroImages.map((url, idx) => (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              key={idx}
              src={url}
              alt={`Imóvel foto ${idx + 1}`}
              className="w-full h-48 object-cover rounded-lg"
            />
          ))}
        </div>
      )}

      {/* Summary */}
      {estimate.summary && (
        <Card>
          <CardContent className="pt-4">
            <h3 className="font-semibold mb-2">Resumo</h3>
            <p className="text-muted-foreground whitespace-pre-line">{estimate.summary}</p>
          </CardContent>
        </Card>
      )}

      {/* Room breakdown */}
      <div>
        <h3 className="text-xl font-semibold mb-4">
          Análise por Divisão ({estimate.room_analyses.length})
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {estimate.room_analyses.map((room, idx) => (
            <RoomCard key={idx} room={room} />
          ))}
        </div>
      </div>

      {/* Disclaimer */}
      <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
        <p className="text-yellow-800 text-sm">
          <strong>Aviso:</strong> {estimate.disclaimer}
        </p>
      </div>

      {/* Actions */}
      <div className="flex gap-4">
        <Button variant="outline" onClick={onReset}>
          Analisar outro imóvel
        </Button>
      </div>
    </div>
  );
}
