"""
Structured output prompt for room feature extraction.

The JSON schema is auto-generated from Pydantic models so enum values are
never duplicated in prompt text — Pydantic is the single source of truth.

Usage:
    from app.prompts.feature_extraction import build_extraction_prompt, get_response_format
    prompt = build_extraction_prompt(room_label, room_type, num_images)
    response_format = get_response_format(room_type)
"""

import json

from app.models.features.modules import (
    BathroomFeatures,
    GenericRoomFeatures,
    KitchenFeatures,
)
from app.models.property import RoomType


def _schema_for_room_type(room_type: RoomType) -> dict:
    """Return the JSON schema dict for the given room type's feature model."""
    if room_type == RoomType.KITCHEN:
        return KitchenFeatures.model_json_schema()
    if room_type == RoomType.BATHROOM:
        return BathroomFeatures.model_json_schema()
    return GenericRoomFeatures.model_json_schema()


def get_response_format(room_type: RoomType) -> dict:
    """
    Build the response_format dict for OpenAI structured output.

    Uses json_schema format with the Pydantic-generated schema.
    """
    # OpenAI requires additionalProperties: false at every level for strict mode.
    # We use json_object mode (not strict) to avoid this complexity in v1.
    # The schema is embedded in the prompt text via build_extraction_prompt().
    return {"type": "json_object"}


def build_extraction_prompt(
    room_label: str,
    room_type: RoomType,
    num_images: int,
) -> str:
    """
    Build the feature extraction prompt for a given room.

    The prompt is in Portuguese (as required for AI-facing text).
    The JSON schema is injected so GPT knows exactly what fields to return.

    Args:
        room_label: Human-readable label, e.g. "Cozinha", "Quarto 2"
        room_type:  Room type enum to select correct feature model
        num_images: Number of images provided (for context)
    """
    schema = _schema_for_room_type(room_type)
    schema_str = json.dumps(schema, ensure_ascii=False, indent=2)

    base = f"""És um especialista em inspeção e avaliação de imóveis em Portugal. Analisa {'esta fotografia' if num_images == 1 else f'estas {num_images} fotografias'} desta divisão e extrai as características estruturais visíveis.

DIVISÃO: {room_label}
FOTOGRAFIAS: {num_images}

INSTRUÇÃO PRINCIPAL:
Extrai APENAS o que consegues VER nas fotografias. Não deduzes nem inventas.
Para cada campo, usa o valor que melhor descreve o que é visível.
Quando não consegues avaliar, usa o valor "not_visible" ou "not_assessable" conforme disponível.

ESCALA DE CONDIÇÃO (1-5):
1 = Necessita substituição completa (deteriorado, danificado, obsoleto)
2 = Mau estado (reparações significativas necessárias)
3 = Estado razoável (reparações menores necessárias)
4 = Bom estado (pequenos retoques apenas)
5 = Excelente (como novo, sem intervenção necessária)

ÁREA ESTIMADA:
Estima a área da divisão em m² com base nas proporções visíveis nas fotografias.
Se não conseguires estimar, deixa null.

NOTAS:
No campo de notas ({room_label.lower()}_notes ou room_notes), descreve em português (1-3 frases) as observações mais relevantes da divisão, incluindo:
- Estado geral e elementos mais degradados
- Características específicas que afetam o custo de remodelação
- Elementos positivos que podem ser preservados

SCHEMA JSON A SEGUIR:
{schema_str}

IMPORTANTE:
- Devolve APENAS JSON válido e completo segundo o schema
- Todos os campos obrigatórios devem estar presentes
- Usa os valores de enum exatamente como definidos no schema
- condition scores devem ser inteiros entre 1 e 5; usa null quando não consegues avaliar
- estimated_area_m2 deve ser um número decimal (ex: 12.5) ou null"""

    return base


# ---------------------------------------------------------------------------
# Prompt for property-level context (no GPT needed — derived from metadata)
# ---------------------------------------------------------------------------

PROPERTY_CONTEXT_NOTES = """
Property-level context (construction_era, location_cost_tier, etc.) is derived
from PropertyData metadata without additional GPT calls. See:
  app.services.feature_extractor.derive_property_context()
"""
