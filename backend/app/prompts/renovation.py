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
- planta: Planta/Desenho técnico do imóvel
- outro: Imagem genuinamente não identificável (logótipo, gráfico, detalhe decorativo extremo)

REGRAS IMPORTANTES:
- Espaços mistos: Para espaços mistos (ex: sala com zona de jantar, quarto com escritório), classifica como o tipo DOMINANTE da divisão. Uma sala de estar com zona de refeições é "sala". Um quarto usado como escritório é "quarto".
- Mau estado: Se a divisão estiver em mau estado mas for reconhecível como um tipo específico (ex: cozinha degradada), classifica como esse tipo. O estado mau não é razão para classificar como "outro".
- Espaço habitável ambíguo: Se o espaço é claramente uma divisão habitável mas não consegues determinar o tipo exato, classifica como "sala" (a opção mais comum/versátil) com confiança reduzida.
- Usa "outro" APENAS para imagens que NÃO mostram uma divisão (ex: logótipos, gráficos de marketing, fotografias de detalhes decorativos isolados).

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
{{
    "condition": "razoavel",
    "condition_notes": "Descrição detalhada do estado atual da divisão",
    "renovation_items": [
        {{
            "item": "Descrição do trabalho",
            "cost_min": 1000,
            "cost_max": 2000,
            "priority": "alta",
            "notes": "Notas adicionais"
        }}
    ],
    "cost_min": 5000,
    "cost_max": 10000,
    "confidence": 0.8,
    "reasoning": "Explicação da análise e estimativa"
}}

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


# Prompt for clustering photos of the same room type into distinct physical rooms
ROOM_CLUSTERING_PROMPT = """Analisa estas {num_images} fotografias de {room_type_label} de um imóvel em Portugal.

OBJETIVO: Agrupa as fotografias por divisão FÍSICA. Fotografias que mostram a mesma divisão (mesmo espaço físico, possivelmente de ângulos diferentes) devem pertencer ao mesmo grupo.

INSTRUÇÕES:
1. Compara elementos visuais entre as fotografias: mobília, cores das paredes, pavimento, janelas, iluminação, decoração
2. Fotografias do MESMO espaço físico terão elementos consistentes (mesmo chão, mesmas janelas, mesma mobília)
3. Fotografias de espaços DIFERENTES terão elementos distintos

REGRA CRÍTICA - PREFERIR SEPARAR:
- Em caso de dúvida, coloca fotografias em grupos SEPARADOS
- É MELHOR criar grupos a mais do que juntar fotografias de divisões diferentes
- Só agrupa fotografias quando tens CERTEZA que mostram o mesmo espaço

{metadata_hint}
RESPONDE APENAS em JSON com este formato exato:
{{
    "clusters": [
        {{
            "room_number": 1,
            "image_indices": [0, 3],
            "confidence": 0.85,
            "visual_cues": "Mesmo pavimento em madeira clara, mesma cama com colcha azul, mesma janela com cortinas brancas"
        }},
        {{
            "room_number": 2,
            "image_indices": [1, 2, 4],
            "confidence": 0.75,
            "visual_cues": "Pavimento em cerâmico cinzento, beliche, parede com papel de parede infantil"
        }}
    ],
    "total_rooms": 2,
    "reasoning": "Explicação geral da análise"
}}

IMPORTANTE:
- image_indices referem-se à posição de cada fotografia (0-indexed) na lista fornecida
- TODAS as fotografias devem aparecer em exatamente UM cluster
- room_number começa em 1 e incrementa sequencialmente
- confidence entre 0.0 e 1.0 (quanto mais certeza na separação, mais alto)
- Se todas as fotografias parecem mostrar a MESMA divisão, devolve um único cluster"""


# Prompt for analysing floor plan images and generating layout optimisation ideas
FLOOR_PLAN_ANALYSIS_PROMPT = """És um especialista em design de interiores e arquitetura em Portugal. Analisa esta planta de um imóvel e sugere ideias criativas para otimizar o layout.

{property_context}INSTRUÇÕES:
1. Analisa a distribuição atual dos espaços na planta
2. Identifica oportunidades para melhorar o layout
3. Sugere 2-4 ideias criativas (não mais) para otimizar o espaço
4. Considera tendências modernas de design de interiores em Portugal
5. As sugestões são ideias, não recomendações — o utilizador deve consultar um profissional

CONSIDERA:
- Abrir espaços para conceito open-plan (cozinha-sala)
- Otimização de corredores e zonas de circulação
- Conversão de divisões para usos mais funcionais
- Aproveitamento de zonas mal utilizadas
- Melhoria da luminosidade natural

Responde APENAS em JSON com este formato:
{{
    "ideas": [
        {{
            "title": "Título curto e descritivo",
            "description": "Descrição detalhada da ideia (2-3 frases)",
            "potential_impact": "Impacto esperado na qualidade de vida ou valor do imóvel",
            "estimated_complexity": "baixa"
        }}
    ],
    "property_context": "Breve descrição do layout atual (ex: T2 com 75m², layout tradicional)",
    "confidence": 0.8
}}

NOTAS:
- estimated_complexity deve ser "baixa", "media" ou "alta"
- confidence entre 0.0 e 1.0 (baseado na qualidade/clareza da planta)
- Máximo 4 ideias — qualidade sobre quantidade
- Sê criativo mas realista para o mercado português
- Lembra: são SUGESTÕES, o utilizador deve consultar um profissional"""


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
