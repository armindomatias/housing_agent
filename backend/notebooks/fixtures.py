"""
Fixtures for testing LangGraph nodes in notebooks.

Provides realistic state snapshots at each pipeline stage for offline testing.
Each function returns a GraphState dict with all data up to that point.
"""

from typing import Any

from app.models.property import (
    ImageClassification,
    PropertyData,
    RenovationEstimate,
    RenovationItem,
    RoomAnalysis,
    RoomCondition,
    RoomType,
    StreamEvent,
)


# Sample Idealista URL for testing
SAMPLE_URL = "https://www.idealista.pt/imovel/33687154/"


def get_state_after(stage: str) -> dict[str, Any]:
    """
    Get state snapshot after a specific pipeline stage.

    Args:
        stage: One of "initial", "scrape", "classify", "group", "estimate", "summarize"

    Returns:
        GraphState dict at that stage
    """
    if stage == "initial":
        return _state_initial()
    elif stage == "scrape":
        return _state_after_scrape()
    elif stage == "classify":
        return _state_after_classify()
    elif stage == "group":
        return _state_after_group()
    elif stage == "estimate":
        return _state_after_estimate()
    elif stage == "summarize":
        return _state_after_summarize()
    else:
        raise ValueError(
            f"Unknown stage: {stage}. "
            f"Valid stages: initial, scrape, classify, group, estimate, summarize"
        )


def _state_initial() -> dict[str, Any]:
    """Initial state before any node runs."""
    return {
        "url": SAMPLE_URL,
        "user_id": "test_user",
        "property_data": None,
        "image_urls": [],
        "classifications": [],
        "grouped_images": {},
        "room_analyses": [],
        "estimate": None,
        "summary": "",
        "stream_events": [],
        "error": None,
        "current_step": "starting",
    }


def _state_after_scrape() -> dict[str, Any]:
    """State after scrape_node completes."""
    property_data = PropertyData(
        url=SAMPLE_URL,
        title="T2 remodelado no centro do Porto",
        price=185000.0,
        area_m2=75.0,
        num_rooms=2,
        num_bathrooms=1,
        floor="3",
        location="Porto, Porto",
        description="Apartamento T2 no centro do Porto, com varanda e muita luz natural.",
        image_urls=[
            "https://img4.idealista.pt/blur/WEB_DETAIL/0/id.pro.pt.image.master/01/5c/b3/1234567891.jpg",
            "https://img4.idealista.pt/blur/WEB_DETAIL/0/id.pro.pt.image.master/01/5c/b3/1234567892.jpg",
            "https://img4.idealista.pt/blur/WEB_DETAIL/0/id.pro.pt.image.master/01/5c/b3/1234567893.jpg",
            "https://img4.idealista.pt/blur/WEB_DETAIL/0/id.pro.pt.image.master/01/5c/b3/1234567894.jpg",
            "https://img4.idealista.pt/blur/WEB_DETAIL/0/id.pro.pt.image.master/01/5c/b3/1234567895.jpg",
            "https://img4.idealista.pt/blur/WEB_DETAIL/0/id.pro.pt.image.master/01/5c/b3/1234567896.jpg",
        ],
        operation="sale",
        property_type="flat",
        latitude=41.1496,
        longitude=-8.6109,
        image_tags={
            "https://img4.idealista.pt/blur/WEB_DETAIL/0/id.pro.pt.image.master/01/5c/b3/1234567891.jpg": "Sala",
            "https://img4.idealista.pt/blur/WEB_DETAIL/0/id.pro.pt.image.master/01/5c/b3/1234567892.jpg": "Cozinha",
            "https://img4.idealista.pt/blur/WEB_DETAIL/0/id.pro.pt.image.master/01/5c/b3/1234567893.jpg": "Quarto",
            "https://img4.idealista.pt/blur/WEB_DETAIL/0/id.pro.pt.image.master/01/5c/b3/1234567894.jpg": "Casa de banho",
            "https://img4.idealista.pt/blur/WEB_DETAIL/0/id.pro.pt.image.master/01/5c/b3/1234567895.jpg": "Quarto",
            "https://img4.idealista.pt/blur/WEB_DETAIL/0/id.pro.pt.image.master/01/5c/b3/1234567896.jpg": "Exterior",
        },
        has_elevator=True,
        condition_status="good",
        raw_data={},
    )

    state = _state_initial()
    state.update(
        {
            "property_data": property_data,
            "image_urls": property_data.image_urls,
            "stream_events": [
                StreamEvent(
                    type="status",
                    message="A obter dados do Idealista...",
                    step=1,
                    total_steps=5,
                ),
                StreamEvent(
                    type="status",
                    message=f"Encontradas {len(property_data.image_urls)} fotografias",
                    step=1,
                    total_steps=5,
                    data={"num_images": len(property_data.image_urls), "title": property_data.title},
                ),
            ],
            "current_step": "scraped",
        }
    )
    return state


def _state_after_classify() -> dict[str, Any]:
    """State after classify_node completes."""
    state = _state_after_scrape()

    classifications = [
        ImageClassification(
            image_url="https://img4.idealista.pt/blur/WEB_DETAIL/0/id.pro.pt.image.master/01/5c/b3/1234567891.jpg",
            room_type=RoomType.LIVING_ROOM,
            room_number=1,
            confidence=0.95,
        ),
        ImageClassification(
            image_url="https://img4.idealista.pt/blur/WEB_DETAIL/0/id.pro.pt.image.master/01/5c/b3/1234567892.jpg",
            room_type=RoomType.KITCHEN,
            room_number=1,
            confidence=0.92,
        ),
        ImageClassification(
            image_url="https://img4.idealista.pt/blur/WEB_DETAIL/0/id.pro.pt.image.master/01/5c/b3/1234567893.jpg",
            room_type=RoomType.BEDROOM,
            room_number=1,
            confidence=0.88,
        ),
        ImageClassification(
            image_url="https://img4.idealista.pt/blur/WEB_DETAIL/0/id.pro.pt.image.master/01/5c/b3/1234567894.jpg",
            room_type=RoomType.BATHROOM,
            room_number=1,
            confidence=0.91,
        ),
        ImageClassification(
            image_url="https://img4.idealista.pt/blur/WEB_DETAIL/0/id.pro.pt.image.master/01/5c/b3/1234567895.jpg",
            room_type=RoomType.BEDROOM,
            room_number=2,
            confidence=0.87,
        ),
        ImageClassification(
            image_url="https://img4.idealista.pt/blur/WEB_DETAIL/0/id.pro.pt.image.master/01/5c/b3/1234567896.jpg",
            room_type=RoomType.EXTERIOR,
            room_number=1,
            confidence=0.94,
        ),
    ]

    events = list(state["stream_events"])
    events.extend(
        [
            StreamEvent(
                type="status",
                message=f"A classificar {len(classifications)} fotografias...",
                step=2,
                total_steps=5,
            ),
            StreamEvent(
                type="status",
                message="Divisões identificadas: 1x sala, 1x cozinha, 2x quarto, 1x casa_de_banho",
                step=2,
                total_steps=5,
            ),
        ]
    )

    state.update(
        {
            "classifications": classifications,
            "stream_events": events,
            "current_step": "classified",
        }
    )
    return state


def _state_after_group() -> dict[str, Any]:
    """State after group_node completes."""
    state = _state_after_classify()

    grouped_images = {
        "sala_1": [
            {
                "image_url": "https://img4.idealista.pt/blur/WEB_DETAIL/0/id.pro.pt.image.master/01/5c/b3/1234567891.jpg",
                "room_type": "sala",
                "room_number": 1,
                "confidence": 0.95,
            }
        ],
        "cozinha_1": [
            {
                "image_url": "https://img4.idealista.pt/blur/WEB_DETAIL/0/id.pro.pt.image.master/01/5c/b3/1234567892.jpg",
                "room_type": "cozinha",
                "room_number": 1,
                "confidence": 0.92,
            }
        ],
        "quarto_1": [
            {
                "image_url": "https://img4.idealista.pt/blur/WEB_DETAIL/0/id.pro.pt.image.master/01/5c/b3/1234567893.jpg",
                "room_type": "quarto",
                "room_number": 1,
                "confidence": 0.88,
            }
        ],
        "casa_de_banho_1": [
            {
                "image_url": "https://img4.idealista.pt/blur/WEB_DETAIL/0/id.pro.pt.image.master/01/5c/b3/1234567894.jpg",
                "room_type": "casa_de_banho",
                "room_number": 1,
                "confidence": 0.91,
            }
        ],
        "quarto_2": [
            {
                "image_url": "https://img4.idealista.pt/blur/WEB_DETAIL/0/id.pro.pt.image.master/01/5c/b3/1234567895.jpg",
                "room_type": "quarto",
                "room_number": 2,
                "confidence": 0.87,
            }
        ],
    }

    events = list(state["stream_events"])
    events.extend(
        [
            StreamEvent(
                type="status",
                message="A agrupar fotografias por divisão...",
                step=3,
                total_steps=5,
            ),
            StreamEvent(
                type="status",
                message=f"Agrupadas 5 fotos em 5 divisões",
                step=3,
                total_steps=5,
                data={"num_rooms": 5, "rooms": list(grouped_images.keys())},
            ),
        ]
    )

    state.update(
        {
            "grouped_images": grouped_images,
            "stream_events": events,
            "current_step": "grouped",
        }
    )
    return state


def _state_after_estimate() -> dict[str, Any]:
    """State after estimate_node completes."""
    state = _state_after_group()

    room_analyses = [
        RoomAnalysis(
            room_type=RoomType.LIVING_ROOM,
            room_number=1,
            room_label="Sala",
            images=["https://img4.idealista.pt/blur/WEB_DETAIL/0/id.pro.pt.image.master/01/5c/b3/1234567891.jpg"],
            condition=RoomCondition.GOOD,
            condition_notes="Sala em bom estado, com piso em madeira e janelas recentes.",
            renovation_items=[
                RenovationItem(
                    item="Pintura de paredes",
                    cost_min=300,
                    cost_max=600,
                    priority="media",
                    notes="Paredes com sinais de desgaste",
                ),
                RenovationItem(
                    item="Recuperação do piso em madeira",
                    cost_min=800,
                    cost_max=1500,
                    priority="baixa",
                    notes="Piso precisa de lixamento e verniz",
                ),
            ],
            cost_min=1100,
            cost_max=2100,
            confidence=0.85,
        ),
        RoomAnalysis(
            room_type=RoomType.KITCHEN,
            room_number=1,
            room_label="Cozinha",
            images=["https://img4.idealista.pt/blur/WEB_DETAIL/0/id.pro.pt.image.master/01/5c/b3/1234567892.jpg"],
            condition=RoomCondition.POOR,
            condition_notes="Cozinha com mobiliário antigo e eletrodomésticos em fim de vida.",
            renovation_items=[
                RenovationItem(
                    item="Mobiliário de cozinha",
                    cost_min=3000,
                    cost_max=6000,
                    priority="alta",
                    notes="Armários e bancada novos",
                ),
                RenovationItem(
                    item="Eletrodomésticos",
                    cost_min=1500,
                    cost_max=3000,
                    priority="alta",
                    notes="Fogão, frigorífico, exaustor",
                ),
                RenovationItem(
                    item="Pintura e azulejos",
                    cost_min=800,
                    cost_max=1500,
                    priority="media",
                    notes="Renovar revestimentos",
                ),
            ],
            cost_min=5300,
            cost_max=10500,
            confidence=0.88,
        ),
        RoomAnalysis(
            room_type=RoomType.BEDROOM,
            room_number=1,
            room_label="Quarto 1",
            images=["https://img4.idealista.pt/blur/WEB_DETAIL/0/id.pro.pt.image.master/01/5c/b3/1234567893.jpg"],
            condition=RoomCondition.FAIR,
            condition_notes="Quarto principal em estado razoável, precisa de atualização.",
            renovation_items=[
                RenovationItem(
                    item="Pintura de paredes",
                    cost_min=250,
                    cost_max=500,
                    priority="media",
                    notes="Paredes com manchas",
                ),
                RenovationItem(
                    item="Substituição de janela",
                    cost_min=400,
                    cost_max=800,
                    priority="media",
                    notes="Janela com isolamento fraco",
                ),
            ],
            cost_min=650,
            cost_max=1300,
            confidence=0.82,
        ),
        RoomAnalysis(
            room_type=RoomType.BATHROOM,
            room_number=1,
            room_label="Casa de Banho",
            images=["https://img4.idealista.pt/blur/WEB_DETAIL/0/id.pro.pt.image.master/01/5c/b3/1234567894.jpg"],
            condition=RoomCondition.NEEDS_FULL_RENOVATION,
            condition_notes="Casa de banho antiga com louças sanitárias e azulejos datados.",
            renovation_items=[
                RenovationItem(
                    item="Louças sanitárias",
                    cost_min=800,
                    cost_max=1500,
                    priority="alta",
                    notes="Sanita, lavatório, banheira",
                ),
                RenovationItem(
                    item="Azulejos e impermeabilização",
                    cost_min=1500,
                    cost_max=3000,
                    priority="alta",
                    notes="Azulejos novos em parede e chão",
                ),
                RenovationItem(
                    item="Canalização e torneiras",
                    cost_min=500,
                    cost_max=1000,
                    priority="alta",
                    notes="Atualizar tubagens e torneiras",
                ),
            ],
            cost_min=2800,
            cost_max=5500,
            confidence=0.90,
        ),
        RoomAnalysis(
            room_type=RoomType.BEDROOM,
            room_number=2,
            room_label="Quarto 2",
            images=["https://img4.idealista.pt/blur/WEB_DETAIL/0/id.pro.pt.image.master/01/5c/b3/1234567895.jpg"],
            condition=RoomCondition.GOOD,
            condition_notes="Quarto secundário em bom estado, apenas cosmética.",
            renovation_items=[
                RenovationItem(
                    item="Pintura de paredes",
                    cost_min=250,
                    cost_max=500,
                    priority="baixa",
                    notes="Atualizar cor",
                ),
            ],
            cost_min=250,
            cost_max=500,
            confidence=0.80,
        ),
    ]

    events = list(state["stream_events"])
    events.extend(
        [
            StreamEvent(
                type="status",
                message=f"A analisar estado de 5 divisões...",
                step=4,
                total_steps=5,
            ),
            StreamEvent(
                type="status",
                message=f"Análise completa de 5 divisões",
                step=4,
                total_steps=5,
            ),
        ]
    )

    state.update(
        {
            "room_analyses": room_analyses,
            "stream_events": events,
            "current_step": "estimated",
        }
    )
    return state


def _state_after_summarize() -> dict[str, Any]:
    """State after summarize_node completes (final state)."""
    state = _state_after_estimate()

    property_data = state["property_data"]
    room_analyses = state["room_analyses"]

    total_min = sum(r.cost_min for r in room_analyses)
    total_max = sum(r.cost_max for r in room_analyses)

    summary = (
        "O imóvel necessita de remodelação moderada a profunda, principalmente na cozinha "
        "e casa de banho. A sala e quartos estão em melhor estado, necessitando apenas de "
        "melhorias cosméticas. O custo estimado representa 5-11% do valor do imóvel, o que "
        "é expectável para um apartamento do centro do Porto nestas condições."
    )

    estimate = RenovationEstimate(
        property_url=property_data.url,
        property_data=property_data,
        room_analyses=room_analyses,
        total_cost_min=total_min,
        total_cost_max=total_max,
        overall_confidence=0.85,
        summary=summary,
    )

    events = list(state["stream_events"])
    events.extend(
        [
            StreamEvent(
                type="status",
                message="A calcular custos finais...",
                step=5,
                total_steps=5,
            ),
            StreamEvent(
                type="result",
                message=f"Estimativa completa: {total_min:,.0f}€ - {total_max:,.0f}€",
                step=5,
                total_steps=5,
                data={"estimate": estimate.model_dump()},
            ),
        ]
    )

    state.update(
        {
            "estimate": estimate,
            "summary": summary,
            "stream_events": events,
            "current_step": "completed",
        }
    )
    return state
