"use client";

import type { RenovationEstimate, RoomAnalysis } from "@/types/analysis";

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

const priorityLabels: Record<string, { label: string; color: string }> = {
  alta: { label: "Alta", color: "bg-red-100 text-red-800" },
  media: { label: "Média", color: "bg-yellow-100 text-yellow-800" },
  baixa: { label: "Baixa", color: "bg-green-100 text-green-800" },
};

function formatCurrency(value: number): string {
  return new Intl.NumberFormat("pt-PT", {
    style: "currency",
    currency: "EUR",
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
}

function RoomCard({ room }: { room: RoomAnalysis }) {
  const condition = conditionLabels[room.condition] || conditionLabels.razoavel;
  const confidencePercent = Math.round(room.confidence * 100);

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
      <div className="flex justify-between items-start mb-3">
        <h3 className="text-lg font-semibold">{room.room_label}</h3>
        <span className={`text-sm font-medium ${condition.color}`}>
          {condition.label}
        </span>
      </div>

      <p className="text-gray-600 dark:text-gray-400 text-sm mb-3">
        {room.condition_notes}
      </p>

      {/* Cost range */}
      <div className="bg-gray-50 dark:bg-gray-900 rounded p-3 mb-3">
        <div className="flex justify-between items-center">
          <span className="text-gray-600 dark:text-gray-400">Custo estimado:</span>
          <span className="font-semibold">
            {formatCurrency(room.cost_min)} - {formatCurrency(room.cost_max)}
          </span>
        </div>
        <div className="text-xs text-gray-500 mt-1">
          Confiança: {confidencePercent}%
        </div>
      </div>

      {/* Renovation items */}
      {room.renovation_items.length > 0 && (
        <div className="space-y-2">
          <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300">
            Trabalhos recomendados:
          </h4>
          <ul className="space-y-1">
            {room.renovation_items.map((item, idx) => {
              const priority = priorityLabels[item.priority] || priorityLabels.media;
              return (
                <li key={idx} className="flex items-start gap-2 text-sm">
                  <span
                    className={`px-1.5 py-0.5 rounded text-xs ${priority.color}`}
                  >
                    {priority.label}
                  </span>
                  <span className="flex-1">{item.item}</span>
                  <span className="text-gray-500 shrink-0">
                    {formatCurrency(item.cost_min)} - {formatCurrency(item.cost_max)}
                  </span>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}

/**
 * Display component for renovation estimate results.
 * Shows property info, room-by-room breakdown, and total costs.
 */
export function ResultsDisplay({ estimate, onReset }: ResultsDisplayProps) {
  const confidencePercent = Math.round(estimate.overall_confidence * 100);

  return (
    <div className="w-full max-w-4xl space-y-6">
      {/* Header with totals */}
      <div className="bg-gradient-to-r from-blue-600 to-blue-700 rounded-xl p-6 text-white">
        <h2 className="text-2xl font-bold mb-2">Estimativa de Remodelação</h2>

        {estimate.property_data && (
          <p className="text-blue-100 mb-4">
            {estimate.property_data.title || estimate.property_data.location}
          </p>
        )}

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="bg-white/10 rounded-lg p-4">
            <div className="text-blue-200 text-sm">Custo Mínimo</div>
            <div className="text-2xl font-bold">
              {formatCurrency(estimate.total_cost_min)}
            </div>
          </div>
          <div className="bg-white/10 rounded-lg p-4">
            <div className="text-blue-200 text-sm">Custo Máximo</div>
            <div className="text-2xl font-bold">
              {formatCurrency(estimate.total_cost_max)}
            </div>
          </div>
          <div className="bg-white/10 rounded-lg p-4">
            <div className="text-blue-200 text-sm">Confiança</div>
            <div className="text-2xl font-bold">{confidencePercent}%</div>
          </div>
        </div>

        {estimate.property_data && estimate.property_data.price > 0 && (
          <div className="mt-4 text-blue-100 text-sm">
            Preço do imóvel: {formatCurrency(estimate.property_data.price)} |
            Custo total: {formatCurrency(estimate.property_data.price + estimate.total_cost_min)} -{" "}
            {formatCurrency(estimate.property_data.price + estimate.total_cost_max)}
          </div>
        )}
      </div>

      {/* Summary */}
      {estimate.summary && (
        <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-4">
          <h3 className="font-semibold mb-2">Resumo</h3>
          <p className="text-gray-700 dark:text-gray-300 whitespace-pre-line">
            {estimate.summary}
          </p>
        </div>
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
      <div className="bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg p-4">
        <p className="text-yellow-800 dark:text-yellow-200 text-sm">
          <strong>Aviso:</strong> {estimate.disclaimer}
        </p>
      </div>

      {/* Actions */}
      <div className="flex gap-4">
        <button
          onClick={onReset}
          className="px-6 py-3 bg-gray-200 dark:bg-gray-700 text-gray-800 dark:text-gray-200 font-medium rounded-lg hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors"
        >
          Analisar outro imóvel
        </button>
      </div>
    </div>
  );
}
