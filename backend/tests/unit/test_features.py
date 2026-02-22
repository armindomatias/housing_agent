"""
Unit tests for feature models.

Tests: model validation, discriminated union routing, condition score range,
notes field defaults, and area estimation fallback logic.
"""

import pytest
from pydantic import ValidationError

from app.models.features.enums import (
    FloorMaterial,
    OutletSwitchStyle,
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
)
from app.models.features.outputs import (
    CostBreakdown,
    ModuleConfidence,
    UserPreferences,
    WorkScopeResult,
)


# ---------------------------------------------------------------------------
# GenericRoomFeatures
# ---------------------------------------------------------------------------


class TestGenericRoomFeatures:
    def test_valid_bedroom(self):
        f = GenericRoomFeatures(
            room_type="quarto",
            surfaces=GenericSurfacesModule(
                floor_material=FloorMaterial.HARDWOOD,
                floor_condition=3,
                wall_finish=WallFinish.PAINT,
                wall_condition=4,
                ceiling_condition=5,
            ),
            fixtures=GenericFixturesModule(
                window_frame_material=WindowFrameMaterial.PVC_DOUBLE,
                window_condition=4,
                window_count_estimate=2,
                door_condition=3,
            ),
            mep=GenericMEPModule(outlet_switch_style=OutletSwitchStyle.MODERN_FLUSH),
            estimated_area_m2=14.0,
            room_notes="Quarto em bom estado geral.",
        )
        assert f.room_type == "quarto"
        assert f.surfaces.floor_condition == 3
        assert f.estimated_area_m2 == 14.0

    def test_valid_living_room(self):
        f = GenericRoomFeatures(room_type="sala")
        assert f.room_type == "sala"
        assert f.surfaces is None
        assert f.fixtures is None

    def test_invalid_room_type_rejected(self):
        with pytest.raises(ValidationError):
            GenericRoomFeatures(room_type="cozinha")  # kitchen should use KitchenFeatures

    def test_condition_score_bounds(self):
        with pytest.raises(ValidationError):
            GenericSurfacesModule(
                floor_material=FloorMaterial.HARDWOOD,
                floor_condition=6,  # max is 5
                wall_finish=WallFinish.PAINT,
                wall_condition=4,
                ceiling_condition=5,
            )

    def test_condition_score_lower_bound(self):
        with pytest.raises(ValidationError):
            GenericSurfacesModule(
                floor_material=FloorMaterial.HARDWOOD,
                floor_condition=0,  # min is 1
                wall_finish=WallFinish.PAINT,
                wall_condition=4,
                ceiling_condition=5,
            )

    def test_notes_default_empty(self):
        f = GenericRoomFeatures(room_type="corredor")
        assert f.room_notes == ""

    def test_area_defaults_none(self):
        f = GenericRoomFeatures(room_type="varanda")
        assert f.estimated_area_m2 is None


# ---------------------------------------------------------------------------
# KitchenFeatures
# ---------------------------------------------------------------------------


class TestKitchenFeatures:
    def test_valid_kitchen(self):
        f = KitchenFeatures(
            surfaces=KitchenSurfacesModule(
                floor_material=FloorMaterial.CERAMIC_TILE,
                floor_condition=2,
                wall_finish=WallFinish.AZULEJOS,
                wall_condition=2,
                ceiling_condition=3,
            ),
            fixtures=KitchenFixturesModule(
                window_frame_material=WindowFrameMaterial.ALUMINUM_SINGLE,
                cabinet_condition=1,
                countertop_material=__import__("app.models.features.enums", fromlist=["CountertopMaterial"]).CountertopMaterial.LAMINATE,
                countertop_condition=2,
                appliances_visible=[],
                door_condition=3,
            ),
            mep=KitchenMEPModule(
                plumbing_visible_condition=__import__("app.models.features.enums", fromlist=["PlumbingVisibleCondition"]).PlumbingVisibleCondition.VISIBLE_CORRODED,
                outlet_switch_style=OutletSwitchStyle.BAKELITE_OLD,
            ),
            estimated_area_m2=10.5,
            kitchen_notes="Cozinha muito degradada, necessita remodelação completa.",
        )
        assert f.room_type == "cozinha"
        assert f.fixtures.cabinet_condition == 1

    def test_discriminator_is_cozinha(self):
        f = KitchenFeatures()
        assert f.room_type == "cozinha"

    def test_appliances_default_empty(self):
        f = KitchenFeatures()
        assert f.fixtures is None  # optional

    def test_kitchen_notes_default_empty(self):
        f = KitchenFeatures()
        assert f.kitchen_notes == ""


# ---------------------------------------------------------------------------
# BathroomFeatures
# ---------------------------------------------------------------------------


class TestBathroomFeatures:
    def test_valid_bathroom(self):
        from app.models.features.enums import ShowerOrBath, VentilationType
        f = BathroomFeatures(
            surfaces=BathroomSurfacesModule(
                wall_finish=WallFinish.AZULEJOS,
                wall_condition=2,
                floor_condition=3,
                ceiling_condition=4,
            ),
            fixtures=BathroomFixturesModule(
                sanitary_ware_condition=2,
                shower_or_bath=ShowerOrBath.SHOWER,
                shower_bath_condition=2,
                bathroom_tile_condition=2,
                ventilation_visible=VentilationType.WINDOW,
                window_frame_material=WindowFrameMaterial.ALUMINUM_SINGLE,
            ),
            mep=BathroomMEPModule(
                plumbing_visible_condition=__import__("app.models.features.enums", fromlist=["PlumbingVisibleCondition"]).PlumbingVisibleCondition.VISIBLE_CORRODED,
                outlet_switch_style=OutletSwitchStyle.ROUND_RECESSED,
            ),
            estimated_area_m2=5.5,
            bathroom_notes="Casa de banho com azulejos deteriorados.",
        )
        assert f.room_type == "casa_de_banho"
        assert f.fixtures.sanitary_ware_condition == 2

    def test_discriminator_is_casa_de_banho(self):
        f = BathroomFeatures()
        assert f.room_type == "casa_de_banho"


# ---------------------------------------------------------------------------
# CostBreakdown properties
# ---------------------------------------------------------------------------


class TestCostBreakdown:
    def test_total_min_max(self):
        bd = CostBreakdown(materials_min=500, materials_max=800, labor_min=300, labor_max=500)
        assert bd.total_min == 800.0
        assert bd.total_max == 1300.0

    def test_defaults_zero(self):
        bd = CostBreakdown()
        assert bd.total_min == 0.0
        assert bd.total_max == 0.0


# ---------------------------------------------------------------------------
# UserPreferences
# ---------------------------------------------------------------------------


class TestUserPreferences:
    def test_defaults(self):
        from app.models.features.enums import FinishLevel, PropertyPurpose
        p = UserPreferences()
        assert p.diy is False
        assert p.finish_level == FinishLevel.STANDARD
        assert p.budget_ceiling is None
        assert p.property_purpose == PropertyPurpose.HABITACAO_PROPRIA

    def test_diy_true(self):
        p = UserPreferences(diy=True)
        assert p.diy is True

    def test_budget_ceiling(self):
        p = UserPreferences(budget_ceiling=50000.0)
        assert p.budget_ceiling == 50000.0


# ---------------------------------------------------------------------------
# WorkScopeResult
# ---------------------------------------------------------------------------


class TestWorkScopeResult:
    def test_defaults_all_none(self):
        ws = WorkScopeResult()
        assert ws.overall == WorkScope.NONE
        assert ws.surfaces == WorkScope.NONE
        assert ws.mep == WorkScope.NONE

    def test_custom_scope(self):
        ws = WorkScopeResult(overall=WorkScope.REPLACE, surfaces=WorkScope.REPLACE)
        assert ws.overall == WorkScope.REPLACE
