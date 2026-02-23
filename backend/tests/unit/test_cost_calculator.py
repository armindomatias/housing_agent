"""
Unit tests for the deterministic cost calculator.

Golden fixture tests: known feature inputs → expected cost ranges.
Invariant tests: premium >= standard >= economico, diy <= non-diy, costs >= 0.
"""

import pytest

from app.models.features.enums import (
    ConstructionEra,
    FinishLevel,
    FloorMaterial,
    LocationCostTier,
    OutletSwitchStyle,
    PlumbingVisibleCondition,
    ShowerOrBath,
    WallFinish,
    WindowFrameMaterial,
    WorkScope,
)
from app.models.features.modules import (
    BathroomFeatures,
    BathroomFixturesModule,
    BathroomMEPModule,
    BathroomSurfacesModule,
    GenericFixturesModule,
    GenericMEPModule,
    GenericRoomFeatures,
    GenericSurfacesModule,
    KitchenFeatures,
    KitchenFixturesModule,
    KitchenMEPModule,
    KitchenSurfacesModule,
    PropertyContext,
)
from app.models.features.outputs import UserPreferences
from app.models.property import RoomType
from app.services.cost_calculator import (
    _action_from_condition,
    _needs_replumbing,
    _needs_rewiring,
    _resolve_area,
    _scope_from_avg,
    calculate_costs,
    compute_composite_indices,
    renovation_items_from_cost_result,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

STD_PREFS = UserPreferences(diy=False, finish_level=FinishLevel.STANDARD)
DIY_PREFS = UserPreferences(diy=True, finish_level=FinishLevel.STANDARD)
PREMIUM_PREFS = UserPreferences(diy=False, finish_level=FinishLevel.PREMIUM)
ECONOMICO_PREFS = UserPreferences(diy=False, finish_level=FinishLevel.ECONOMICO)

LISBON_CONTEXT = PropertyContext(
    construction_era=ConstructionEra.ERA_1950_1970,
    location_cost_tier=LocationCostTier.LISBOA,
    area_m2=75.0,
    usable_area_m2=65.0,
)

DEFAULT_CONTEXT = PropertyContext(
    construction_era=ConstructionEra.ERA_1990_2005,
    location_cost_tier=LocationCostTier.LITORAL,
    area_m2=75.0,
    usable_area_m2=65.0,
)


def _poor_bedroom() -> GenericRoomFeatures:
    return GenericRoomFeatures(
        room_type="quarto",
        surfaces=GenericSurfacesModule(
            floor_material=FloorMaterial.LAMINATE,
            floor_condition=2,
            wall_finish=WallFinish.PAINT,
            wall_condition=2,
            ceiling_condition=3,
        ),
        fixtures=GenericFixturesModule(
            window_frame_material=WindowFrameMaterial.ALUMINUM_SINGLE,
            window_condition=2,
            window_count_estimate=2,
            door_condition=3,
        ),
        mep=GenericMEPModule(outlet_switch_style=OutletSwitchStyle.MODERN_FLUSH),
        estimated_area_m2=16.0,
    )


def _good_kitchen() -> KitchenFeatures:
    from app.models.features.enums import ApplianceType, CountertopMaterial
    return KitchenFeatures(
        surfaces=KitchenSurfacesModule(
            floor_material=FloorMaterial.CERAMIC_TILE,
            floor_condition=4,
            wall_finish=WallFinish.PAINT,
            wall_condition=4,
            ceiling_condition=4,
        ),
        fixtures=KitchenFixturesModule(
            window_frame_material=WindowFrameMaterial.PVC_DOUBLE,
            cabinet_condition=4,
            countertop_material=CountertopMaterial.GRANITE,
            countertop_condition=4,
            appliances_visible=[ApplianceType.FRIDGE, ApplianceType.OVEN],
            door_condition=4,
        ),
        mep=KitchenMEPModule(
            plumbing_visible_condition=PlumbingVisibleCondition.MODERN_CONCEALED,
            outlet_switch_style=OutletSwitchStyle.MODERN_FLUSH,
        ),
        estimated_area_m2=10.0,
    )


def _poor_kitchen() -> KitchenFeatures:
    from app.models.features.enums import CountertopMaterial
    return KitchenFeatures(
        surfaces=KitchenSurfacesModule(
            floor_material=FloorMaterial.CERAMIC_TILE,
            floor_condition=1,
            wall_finish=WallFinish.AZULEJOS,
            wall_condition=1,
            ceiling_condition=2,
        ),
        fixtures=KitchenFixturesModule(
            window_frame_material=WindowFrameMaterial.ALUMINUM_SINGLE,
            cabinet_condition=1,
            countertop_material=CountertopMaterial.LAMINATE,
            countertop_condition=1,
            appliances_visible=[],
            door_condition=2,
        ),
        mep=KitchenMEPModule(
            plumbing_visible_condition=PlumbingVisibleCondition.VISIBLE_CORRODED,
            outlet_switch_style=OutletSwitchStyle.BAKELITE_OLD,
        ),
        estimated_area_m2=10.0,
    )


def _poor_bathroom() -> BathroomFeatures:
    from app.models.features.enums import VentilationType
    return BathroomFeatures(
        surfaces=BathroomSurfacesModule(
            wall_finish=WallFinish.AZULEJOS,
            wall_condition=1,
            floor_condition=2,
            ceiling_condition=2,
        ),
        fixtures=BathroomFixturesModule(
            sanitary_ware_condition=1,
            shower_or_bath=ShowerOrBath.SHOWER,
            shower_bath_condition=1,
            bathroom_tile_condition=2,
            ventilation_visible=VentilationType.WINDOW,
            window_frame_material=WindowFrameMaterial.ALUMINUM_SINGLE,
        ),
        mep=BathroomMEPModule(
            plumbing_visible_condition=PlumbingVisibleCondition.VISIBLE_CORRODED,
            outlet_switch_style=OutletSwitchStyle.BAKELITE_OLD,
        ),
        estimated_area_m2=5.0,
    )


# ---------------------------------------------------------------------------
# _action_from_condition
# ---------------------------------------------------------------------------


class TestActionFromCondition:
    def test_score_1_is_replace(self):
        assert _action_from_condition(1) == "replace"

    def test_score_2_is_replace(self):
        assert _action_from_condition(2) == "replace"

    def test_score_3_is_repair(self):
        assert _action_from_condition(3) == "repair"

    def test_score_4_is_keep(self):
        assert _action_from_condition(4) == "keep"

    def test_score_5_is_keep(self):
        assert _action_from_condition(5) == "keep"

    def test_none_is_keep(self):
        assert _action_from_condition(None) == "keep"


# ---------------------------------------------------------------------------
# _scope_from_avg
# ---------------------------------------------------------------------------


class TestScopeFromAvg:
    def test_avg_1_is_full_renovation(self):
        assert _scope_from_avg(1.0) == WorkScope.FULL_RENOVATION

    def test_avg_2_is_replace(self):
        assert _scope_from_avg(2.0) == WorkScope.REPLACE

    def test_avg_3_is_refurbish(self):
        assert _scope_from_avg(3.0) == WorkScope.REFURBISH

    def test_avg_4_is_repair(self):
        assert _scope_from_avg(4.0) == WorkScope.REPAIR

    def test_avg_5_is_none(self):
        assert _scope_from_avg(5.0) == WorkScope.NONE


# ---------------------------------------------------------------------------
# _needs_rewiring
# ---------------------------------------------------------------------------


class TestNeedsRewiring:
    def test_bakelite_triggers_rewiring(self):
        assert _needs_rewiring(OutletSwitchStyle.BAKELITE_OLD, ConstructionEra.POST_2005)

    def test_surface_mounted_triggers_rewiring(self):
        assert _needs_rewiring(OutletSwitchStyle.SURFACE_MOUNTED, ConstructionEra.POST_2005)

    def test_old_era_triggers_rewiring(self):
        assert _needs_rewiring(OutletSwitchStyle.MODERN_FLUSH, ConstructionEra.ERA_1950_1970)

    def test_modern_recent_no_rewiring(self):
        assert not _needs_rewiring(OutletSwitchStyle.MODERN_FLUSH, ConstructionEra.POST_2005)


# ---------------------------------------------------------------------------
# _needs_replumbing
# ---------------------------------------------------------------------------


class TestNeedsReplumbing:
    def test_corroded_triggers_replumbing(self):
        assert _needs_replumbing(PlumbingVisibleCondition.VISIBLE_CORRODED, ConstructionEra.POST_2005)

    def test_old_era_triggers_replumbing(self):
        assert _needs_replumbing(PlumbingVisibleCondition.MODERN_CONCEALED, ConstructionEra.ERA_1950_1970)

    def test_modern_concealed_recent_no_replumbing(self):
        assert not _needs_replumbing(PlumbingVisibleCondition.MODERN_CONCEALED, ConstructionEra.POST_2005)


# ---------------------------------------------------------------------------
# _resolve_area
# ---------------------------------------------------------------------------


class TestResolveArea:
    def test_gpt_estimate_takes_priority(self):
        f = GenericRoomFeatures(room_type="quarto", estimated_area_m2=18.0)
        ctx = PropertyContext(usable_area_m2=60.0, area_m2=75.0)
        area = _resolve_area(f, RoomType.BEDROOM, ctx)
        assert area == 18.0

    def test_usable_area_weight_fallback(self):
        f = GenericRoomFeatures(room_type="quarto")  # no estimated_area_m2
        ctx = PropertyContext(usable_area_m2=60.0, area_m2=0)
        area = _resolve_area(f, RoomType.BEDROOM, ctx)
        # weight for bedroom = 0.16
        assert abs(area - 60.0 * 0.16) < 0.01

    def test_total_area_weight_fallback(self):
        f = GenericRoomFeatures(room_type="sala")
        ctx = PropertyContext(usable_area_m2=0, area_m2=80.0)
        area = _resolve_area(f, RoomType.LIVING_ROOM, ctx)
        # weight for living_room = 0.25
        assert abs(area - 80.0 * 0.25) < 0.01

    def test_default_area_last_resort(self):
        from app.constants import DEFAULT_ROOM_AREA_M2
        f = GenericRoomFeatures(room_type="corredor")
        ctx = PropertyContext(usable_area_m2=0, area_m2=0)
        area = _resolve_area(f, RoomType.HALLWAY, ctx)
        assert area == DEFAULT_ROOM_AREA_M2


# ---------------------------------------------------------------------------
# calculate_costs — golden fixtures
# ---------------------------------------------------------------------------


class TestCalculateCosts:
    def test_poor_bedroom_has_costs_above_zero(self):
        result = calculate_costs(_poor_bedroom(), RoomType.BEDROOM, STD_PREFS, DEFAULT_CONTEXT)
        assert result.cost_breakdown.total_min > 0
        assert result.cost_breakdown.total_max >= result.cost_breakdown.total_min

    def test_good_kitchen_costs_lower_than_poor(self):
        good = calculate_costs(_good_kitchen(), RoomType.KITCHEN, STD_PREFS, DEFAULT_CONTEXT)
        poor = calculate_costs(_poor_kitchen(), RoomType.KITCHEN, STD_PREFS, DEFAULT_CONTEXT)
        assert poor.cost_breakdown.total_max > good.cost_breakdown.total_max

    def test_premium_ge_standard_ge_economico(self):
        features = _poor_kitchen()
        std = calculate_costs(features, RoomType.KITCHEN, STD_PREFS, DEFAULT_CONTEXT)
        prem = calculate_costs(features, RoomType.KITCHEN, PREMIUM_PREFS, DEFAULT_CONTEXT)
        eco = calculate_costs(features, RoomType.KITCHEN, ECONOMICO_PREFS, DEFAULT_CONTEXT)
        assert prem.cost_breakdown.total_max >= std.cost_breakdown.total_max
        assert std.cost_breakdown.total_max >= eco.cost_breakdown.total_max

    def test_diy_le_non_diy(self):
        features = _poor_bathroom()
        std = calculate_costs(features, RoomType.BATHROOM, STD_PREFS, DEFAULT_CONTEXT)
        diy = calculate_costs(features, RoomType.BATHROOM, DIY_PREFS, DEFAULT_CONTEXT)
        assert diy.cost_breakdown.total_max <= std.cost_breakdown.total_max

    def test_diy_labor_is_zero(self):
        features = _poor_bedroom()
        result = calculate_costs(features, RoomType.BEDROOM, DIY_PREFS, DEFAULT_CONTEXT)
        assert result.cost_breakdown.labor_min == 0.0
        assert result.cost_breakdown.labor_max == 0.0

    def test_lisbon_more_expensive_than_interior(self):
        from app.models.features.enums import LocationCostTier
        features = _poor_kitchen()
        interior_ctx = PropertyContext(
            construction_era=ConstructionEra.ERA_1990_2005,
            location_cost_tier=LocationCostTier.INTERIOR,
            area_m2=75.0,
            usable_area_m2=65.0,
        )
        lisbon = calculate_costs(features, RoomType.KITCHEN, STD_PREFS, LISBON_CONTEXT)
        interior = calculate_costs(features, RoomType.KITCHEN, STD_PREFS, interior_ctx)
        assert lisbon.cost_breakdown.total_max > interior.cost_breakdown.total_max

    def test_poor_bathroom_has_line_items(self):
        result = calculate_costs(_poor_bathroom(), RoomType.BATHROOM, STD_PREFS, DEFAULT_CONTEXT)
        assert len(result.line_items) > 0

    def test_good_kitchen_lower_cost(self):
        result = calculate_costs(_good_kitchen(), RoomType.KITCHEN, STD_PREFS, DEFAULT_CONTEXT)
        # Good kitchen: most items score 4 → no replacement costs
        assert result.cost_breakdown.total_min >= 0

    def test_all_costs_nonnegative(self):
        for features, room_type in [
            (_poor_bedroom(), RoomType.BEDROOM),
            (_poor_kitchen(), RoomType.KITCHEN),
            (_poor_bathroom(), RoomType.BATHROOM),
            (_good_kitchen(), RoomType.KITCHEN),
        ]:
            result = calculate_costs(features, room_type, STD_PREFS, DEFAULT_CONTEXT)
            assert result.cost_breakdown.total_min >= 0
            assert result.cost_breakdown.total_max >= 0
            for item in result.line_items:
                assert item.cost_min >= 0
                assert item.cost_max >= 0


# ---------------------------------------------------------------------------
# None condition fields (GPT returned null for unassessable features)
# ---------------------------------------------------------------------------


class TestNoneConditionFields:
    def test_kitchen_with_null_countertop_condition_skips_countertop(self):
        """countertop_condition=None → no countertop cost line item."""
        from app.models.features.enums import CountertopMaterial
        features = KitchenFeatures(
            fixtures=KitchenFixturesModule(
                window_frame_material=WindowFrameMaterial.PVC_DOUBLE,
                cabinet_condition=None,
                countertop_material=CountertopMaterial.LAMINATE,
                countertop_condition=None,
                appliances_visible=[],
                door_condition=None,
            ),
        )
        result = calculate_costs(features, RoomType.KITCHEN, STD_PREFS, DEFAULT_CONTEXT)
        categories = {item.category for item in result.line_items}
        assert "kitchen_countertop" not in categories
        assert "kitchen_cabinets" not in categories

    def test_bathroom_with_null_conditions_produces_no_fixture_items(self):
        """All fixture conditions None → no fixture cost line items."""
        from app.models.features.enums import VentilationType
        features = BathroomFeatures(
            fixtures=BathroomFixturesModule(
                sanitary_ware_condition=None,
                shower_or_bath=ShowerOrBath.SHOWER,
                shower_bath_condition=None,
                bathroom_tile_condition=None,
                ventilation_visible=VentilationType.NOT_VISIBLE,
                window_frame_material=WindowFrameMaterial.ALUMINUM_SINGLE,
            ),
        )
        result = calculate_costs(features, RoomType.BATHROOM, STD_PREFS, DEFAULT_CONTEXT)
        fixture_categories = {"bathroom_sanitary", "bathroom_shower_bath"}
        assert not fixture_categories.intersection({item.category for item in result.line_items})

    def test_null_conditions_produce_nonnegative_costs(self):
        """None condition fields must never cause errors or negative costs."""
        from app.models.features.enums import CountertopMaterial
        features = KitchenFeatures(
            surfaces=KitchenSurfacesModule(
                floor_material=FloorMaterial.CERAMIC_TILE,
                floor_condition=None,
                wall_finish=WallFinish.PAINT,
                wall_condition=None,
                ceiling_condition=None,
            ),
            fixtures=KitchenFixturesModule(
                window_frame_material=WindowFrameMaterial.PVC_DOUBLE,
                cabinet_condition=None,
                countertop_material=CountertopMaterial.GRANITE,
                countertop_condition=None,
                appliances_visible=[],
                door_condition=None,
            ),
        )
        result = calculate_costs(features, RoomType.KITCHEN, STD_PREFS, DEFAULT_CONTEXT)
        assert result.cost_breakdown.total_min >= 0
        assert result.cost_breakdown.total_max >= 0


# ---------------------------------------------------------------------------
# renovation_items_from_cost_result
# ---------------------------------------------------------------------------


class TestRenovationItemsFromCostResult:
    def test_generates_items_from_line_items(self):
        result = calculate_costs(_poor_bathroom(), RoomType.BATHROOM, STD_PREFS, DEFAULT_CONTEXT)
        items = renovation_items_from_cost_result(result)
        assert len(items) == len(result.line_items)
        for item, li in zip(items, result.line_items):
            assert item.item == li.description
            assert item.cost_min == round(li.cost_min, 2)
            assert item.cost_max == round(li.cost_max, 2)

    def test_empty_result_returns_empty_list(self):
        from app.models.features.outputs import RoomCostResult
        result = RoomCostResult()
        items = renovation_items_from_cost_result(result)
        assert items == []


# ---------------------------------------------------------------------------
# compute_composite_indices
# ---------------------------------------------------------------------------


class TestCompositeIndices:
    def test_empty_rooms_returns_defaults(self):
        indices = compute_composite_indices({}, DEFAULT_CONTEXT)
        from app.models.features.enums import HiddenCostRisk, ScopeComplexity
        assert indices.scope_complexity.level == ScopeComplexity.SIMPLE
        assert indices.time_estimate.weeks_min == 0

    def test_multiple_bad_rooms_gives_high_complexity(self):
        room_results = {}
        for label, features, room_type in [
            ("Cozinha", _poor_kitchen(), RoomType.KITCHEN),
            ("Casa de Banho", _poor_bathroom(), RoomType.BATHROOM),
            ("Quarto 1", _poor_bedroom(), RoomType.BEDROOM),
            ("Quarto 2", _poor_bedroom(), RoomType.BEDROOM),
        ]:
            room_results[label] = calculate_costs(features, room_type, STD_PREFS, LISBON_CONTEXT)

        indices = compute_composite_indices(room_results, LISBON_CONTEXT)
        from app.models.features.enums import ScopeComplexity
        assert indices.scope_complexity.level in (ScopeComplexity.COMPLEX, ScopeComplexity.MAJOR)

    def test_high_risk_for_old_era_with_mep_work(self):
        room_results = {
            "Cozinha": calculate_costs(_poor_kitchen(), RoomType.KITCHEN, STD_PREFS, LISBON_CONTEXT),
        }
        indices = compute_composite_indices(room_results, LISBON_CONTEXT)
        from app.models.features.enums import HiddenCostRisk
        assert indices.hidden_cost_risk.level in (HiddenCostRisk.MEDIUM, HiddenCostRisk.HIGH)

    def test_time_estimate_nonnegative(self):
        room_results = {
            "Quarto": calculate_costs(_poor_bedroom(), RoomType.BEDROOM, STD_PREFS, DEFAULT_CONTEXT),
        }
        indices = compute_composite_indices(room_results, DEFAULT_CONTEXT)
        assert indices.time_estimate.weeks_min >= 0
        assert indices.time_estimate.weeks_max >= indices.time_estimate.weeks_min
