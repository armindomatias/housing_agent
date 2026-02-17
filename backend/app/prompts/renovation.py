"""
Portuguese prompts for renovation analysis.
All AI-facing prompts are in Portuguese (Portugal) as per project requirements.
"""

# Prompt for classifying a single image to identify which room it shows
IMAGE_CLASSIFICATION_PROMPT = """Analisa esta fotografia de um imóvel em Portugal e identifica a divisão mostrada.

INSTRUÇÕES:
1. Identifica que divisão é mostrada na fotografia
2. Se for quarto ou casa de banho, indica o número (1, 2, 3...) baseado em características únicas
3. Avalia a tua confiança na classificação

TIPOS DE DIVISÃO VÁLIDOS:
- cozinha: Cozinha
- sala: Sala de estar/jantar
- quarto: Quarto (indica número se possível distinguir)
- casa_de_banho: Casa de banho/WC
- corredor: Corredor/Hall de entrada
- varanda: Varanda/Terraço
- exterior: Vista exterior do edifício/fachada
- garagem: Garagem
- arrecadacao: Arrecadação/Despensa
- outro: Não identificável ou espaço misto

Responde APENAS em JSON com este formato exato:
{
    "room_type": "cozinha",
    "room_number": 1,
    "confidence": 0.9,
    "reasoning": "Breve explicação da classificação"
}

IMPORTANTE:
- room_number deve ser sempre um número inteiro >= 1 (nunca null ou 0)
- Se houver apenas uma divisão deste tipo, usa 1
- Se não conseguires distinguir quartos/WCs múltiplos, usa 1"""


# Prompt for analyzing a room's condition and estimating renovation costs
ROOM_ANALYSIS_PROMPT = """És um especialista em remodelações de imóveis em Portugal. Analisa as fotografias desta divisão e estima os custos de remodelação.

DIVISÃO: {room_label}
NÚMERO DE FOTOGRAFIAS: {num_images}

INSTRUÇÕES:
1. Avalia o estado atual da divisão (excelente, bom, razoável, mau, necessita remodelação total)
2. Identifica todos os trabalhos de remodelação necessários ou recomendados
3. Estima custos em EUR usando preços do mercado português (2024/2025)

REFERÊNCIAS DE PREÇOS (EUR, Portugal):
- Pintura: 8-15€/m² (paredes e tetos)
- Pavimento flutuante: 25-50€/m²
- Pavimento cerâmico: 40-80€/m²
- Móveis de cozinha: 3.000-15.000€ (completo)
- Bancada de cozinha: 500-2.500€
- Eletrodomésticos: 2.000-8.000€ (conjunto completo)
- Louças sanitárias (WC completo): 500-3.000€
- Base de duche + resguardo: 400-1.500€
- Torneiras e acessórios WC: 200-800€
- Azulejos WC: 30-60€/m²
- Janelas (por unidade): 300-800€
- Porta interior: 150-400€
- Instalação elétrica (divisão): 300-800€
- Canalização (WC completo): 500-2.000€

DEVOLVE APENAS JSON VÁLIDO E COMPLETO no seguinte formato:
{
    "condition": "razoavel",
    "condition_notes": "Descrição detalhada do estado atual da divisão",
    "renovation_items": [
        {
            "item": "Descrição do trabalho",
            "cost_min": 1000,
            "cost_max": 2000,
            "priority": "alta",
            "notes": "Notas adicionais"
        }
    ],
    "cost_min": 5000,
    "cost_max": 10000,
    "confidence": 0.8,
    "reasoning": "Explicação da análise e estimativa"
}

CRÍTICO:
- O JSON deve estar completo e bem formatado
- NUNCA omitas campos obrigatórios (condition, cost_min, cost_max, confidence, reasoning)
- Se não tiveres certeza, indica confidence baixo (0.3-0.5)
- Se as fotos forem insuficientes, devolve análise conservadora mas completa

PRIORIDADES:
- alta: Necessário para habitabilidade ou segurança
- media: Recomendado para conforto e modernização
- baixa: Opcional/estético

IMPORTANTE:
- Sê conservador nas estimativas (melhor sobrestimar que subestimar)
- Considera mão de obra + materiais
- Se as fotos não permitirem ver bem, reduz a confiança
- Indica sempre um intervalo (min-max) realista"""


# Prompt for generating a final summary of all renovation needs
SUMMARY_PROMPT = """Com base nas análises individuais de cada divisão, gera um resumo executivo da remodelação necessária para este imóvel.

DADOS DO IMÓVEL:
- Preço: {price}€
- Área: {area_m2}m²
- Localização: {location}

ANÁLISES POR DIVISÃO:
{room_summaries}

CUSTOS TOTAIS:
- Mínimo: {total_min}€
- Máximo: {total_max}€

Gera um resumo em português (Portugal) que:
1. Descreve o estado geral do imóvel
2. Identifica as prioridades principais de remodelação
3. Contextualiza o custo face ao valor do imóvel
4. Recomenda próximos passos

Responde em formato de texto corrido (1-2 parágrafos), não em JSON."""
