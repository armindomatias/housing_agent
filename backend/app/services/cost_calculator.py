"""
Deterministic cost calculator for renovation estimates.

Pure function: calculate_costs(features, area_m2, prefs, context) -> RoomCostResult.
No GPT calls — derives costs from structured features + COST_TABLE + LABOR_RATIOS.

Decision logic:
  condition score 1-2  → replace
  condition score 3    → repair/refurbish
  condition score 4-5  → keep (no cost)
"""

import structlog

from app.constants import (
    CONDITION_REPAIR_THRESHOLD,
    CONDITION_REPLACE_THRESHOLD,
    COST_TABLE,
    COUNTERTOP_DEFAULT_LINEAR_M,
    DEFAULT_ROOM_AREA_M2,
    ERA_REPLUMBING_LIKELY,
    ERA_REWIRING_LIKELY,
    FINISH_LEVEL_MULTIPLIERS,
    FLOOR_ACCESSIBILITY_SURCHARGES,
    LABOR_RATIOS,
    LOCATION_COST_MULTIPLIERS,
    ROOM_AREA_WEIGHTS,
    TIME_WEEKS_PER_SCOPE,
    WORK_SCOPE_FROM_AVG_CONDITION,
)
from app.models.features.enums import (
    ConstructionEra,
    FinishLevel,
    FloorMaterial,
    HiddenCostRisk,
    OutletSwitchStyle,
    PlumbingVisibleCondition,
    ScopeComplexity,
    ShowerOrBath,
    WallFinish,
    WorkScope,
)
from app.models.features.modules import (
    BathroomFeatures,
    GenericRoomFeatures,
    KitchenFeatures,
    PropertyContext,
    RoomFeatures,
)
from app.models.features.outputs import (
    CompositeIndices,
    CostBreakdown,
    CostLineItem,
    HiddenCostRiskResult,
    ModuleConfidence,
    RoomCostResult,
    ScopeComplexityResult,
    TimeEstimate,
    UserPreferences,
    WorkScopeResult,
)
from app.models.property import RenovationItem, RoomType

logger = structlog.get_logger(__name__)


def _action_from_condition(score: int | None) -> str:
    """Return action string based on condition score (1-5). None means unassessable → keep."""
    if score is None:
        return "keep"
    if score <= CONDITION_REPLACE_THRESHOLD:
        return "replace"
    if score <= CONDITION_REPAIR_THRESHOLD:
        return "repair"
    return "keep"


def _apply_multipliers(
    cost_min: float,
    cost_max: float,
    finish: FinishLevel,
    regional: float,
    floor_surcharge: float,
    labor_fraction: float,
    diy: bool,
) -> tuple[float, float, float, float]:
    """
    Apply finish, regional, and floor surcharges then split materials/labor.

    Returns: (mat_min, mat_max, labor_min, labor_max)
    """
    finish_mult = FINISH_LEVEL_MULTIPLIERS[finish]
    total_min = cost_min * finish_mult * regional
    total_max = cost_max * finish_mult * regional

    mat_min = total_min * (1 - labor_fraction)
    mat_max = total_max * (1 - labor_fraction)
    labor_min = total_min * labor_fraction * (1 + floor_surcharge)
    labor_max = total_max * labor_fraction * (1 + floor_surcharge)

    if diy:
        labor_min = 0.0
        labor_max = 0.0

    return mat_min, mat_max, labor_min, labor_max


def _scope_from_avg(avg_condition: float) -> WorkScope:
    """Map average condition score to WorkScope."""
    for threshold, scope in WORK_SCOPE_FROM_AVG_CONDITION:
        if avg_condition <= threshold:
            return scope
    return WorkScope.NONE


def _time_from_scope(scope: WorkScope) -> tuple[int, int]:
    return TIME_WEEKS_PER_SCOPE.get(scope, (0, 0))


def _calculate_generic_room(
    features: GenericRoomFeatures,
    area_m2: float,
    prefs: UserPreferences,
    context: PropertyContext,
) -> tuple[list[CostLineItem], WorkScopeResult, ModuleConfidence]:
    """Calculate costs for generic rooms (bedroom, living room, hallway)."""
    items: list[CostLineItem] = []
    regional = LOCATION_COST_MULTIPLIERS.get(context.location_cost_tier, 1.0)
    floor_surcharge = FLOOR_ACCESSIBILITY_SURCHARGES.get(
        context.floor_accessibility.value, 0.0
    )

    surface_conditions: list[int] = []
    fixture_conditions: list[int] = []
    mep_has_data = False

    # --- M1 Surfaces ---
    if features.surfaces:
        s = features.surfaces

        # Floor
        floor_action = _action_from_condition(s.floor_condition)
        if s.floor_condition is not None:
            surface_conditions.append(s.floor_condition)
        if floor_action in ("replace", "repair"):
            key = "replace" if floor_action == "replace" else "repair"
            if key == "replace":
                cost_range = COST_TABLE["flooring"]["replace"].get(
                    s.floor_material,
                    COST_TABLE["flooring"]["replace"][FloorMaterial.NOT_VISIBLE],
                )
                labor_key = "flooring_replace"
                desc = f"Substituição do pavimento ({s.floor_material.value})"
                priority = "alta" if s.floor_condition <= 2 else "media"
            else:
                cost_range = COST_TABLE["flooring"]["repair"]
                labor_key = "flooring_repair"
                desc = "Reparação do pavimento"
                priority = "media"
            mat_min, mat_max, lab_min, lab_max = _apply_multipliers(
                cost_range.min * area_m2,
                cost_range.max * area_m2,
                prefs.finish_level,
                regional,
                floor_surcharge,
                LABOR_RATIOS[labor_key],
                prefs.diy,
            )
            items.append(CostLineItem(
                category="flooring", action=floor_action, description=desc,
                cost_min=mat_min + lab_min, cost_max=mat_max + lab_max,
                materials_min=mat_min, materials_max=mat_max,
                labor_min=lab_min, labor_max=lab_max,
                unit="m2", quantity=area_m2, priority=priority,
            ))

        # Walls
        wall_action = _action_from_condition(s.wall_condition)
        if s.wall_condition is not None:
            surface_conditions.append(s.wall_condition)
        if wall_action in ("replace", "repair"):
            wall_area = area_m2 * 2.5  # approx wall area from floor area
            if s.wall_finish == WallFinish.AZULEJOS and wall_action == "replace":
                remove = COST_TABLE["walls"]["remove_azulejos"]
                install = COST_TABLE["walls"]["install_azulejos"]
                total_per_m2 = remove.min + install.min
                total_per_m2_max = remove.max + install.max
                labor_key = "walls_install_azulejos"
                desc = "Remoção e reinstalação de azulejos"
                priority = "alta"
            elif wall_action == "replace":
                r = COST_TABLE["walls"]["strip_and_replaster"]
                total_per_m2, total_per_m2_max = r.min, r.max
                labor_key = "walls_replaster"
                desc = "Remoção e reboco de paredes"
                priority = "alta"
            else:
                r = COST_TABLE["walls"]["repaint"]
                total_per_m2, total_per_m2_max = r.min, r.max
                labor_key = "walls_repaint"
                desc = "Pintura de paredes"
                priority = "media"
            mat_min, mat_max, lab_min, lab_max = _apply_multipliers(
                total_per_m2 * wall_area,
                total_per_m2_max * wall_area,
                prefs.finish_level, regional, floor_surcharge,
                LABOR_RATIOS[labor_key], prefs.diy,
            )
            items.append(CostLineItem(
                category="walls", action=wall_action, description=desc,
                cost_min=mat_min + lab_min, cost_max=mat_max + lab_max,
                materials_min=mat_min, materials_max=mat_max,
                labor_min=lab_min, labor_max=lab_max,
                unit="m2", quantity=wall_area, priority=priority,
            ))

        # Ceiling
        ceil_action = _action_from_condition(s.ceiling_condition)
        if s.ceiling_condition is not None:
            surface_conditions.append(s.ceiling_condition)
        if ceil_action in ("replace", "repair"):
            if ceil_action == "replace":
                r = COST_TABLE["ceiling"]["full_replaster"]
                labor_key = "ceiling_replaster"
                desc = "Reboco e pintura de teto"
                priority = "alta"
            else:
                r = COST_TABLE["ceiling"]["repair_and_repaint"]
                labor_key = "ceiling_repair"
                desc = "Reparação e pintura de teto"
                priority = "media"
            mat_min, mat_max, lab_min, lab_max = _apply_multipliers(
                r.min * area_m2, r.max * area_m2,
                prefs.finish_level, regional, floor_surcharge,
                LABOR_RATIOS[labor_key], prefs.diy,
            )
            items.append(CostLineItem(
                category="ceiling", action=ceil_action, description=desc,
                cost_min=mat_min + lab_min, cost_max=mat_max + lab_max,
                materials_min=mat_min, materials_max=mat_max,
                labor_min=lab_min, labor_max=lab_max,
                unit="m2", quantity=area_m2, priority=priority,
            ))

    # --- M2 Fixtures ---
    if features.fixtures:
        f = features.fixtures

        # Windows
        if f.window_condition is not None:
            fixture_conditions.append(f.window_condition)
        win_action = _action_from_condition(f.window_condition)
        if win_action in ("replace", "repair") and f.window_count_estimate > 0:
            if win_action == "replace":
                cost_per = COST_TABLE["windows"]["replace"].get(
                    f.window_frame_material,
                    COST_TABLE["windows"]["replace"][FloorMaterial.NOT_VISIBLE],  # type: ignore[index]
                )
                labor_key = "windows_replace"
                desc = f"Substituição de janelas ({f.window_count_estimate} un.)"
                priority = "alta"
            else:
                cost_per = COST_TABLE["windows"]["repair"]
                labor_key = "windows_repair"
                desc = f"Reparação de janelas ({f.window_count_estimate} un.)"
                priority = "media"
            qty = float(f.window_count_estimate)
            mat_min, mat_max, lab_min, lab_max = _apply_multipliers(
                cost_per.min * qty, cost_per.max * qty,
                prefs.finish_level, regional, floor_surcharge,
                LABOR_RATIOS[labor_key], prefs.diy,
            )
            items.append(CostLineItem(
                category="windows", action=win_action, description=desc,
                cost_min=mat_min + lab_min, cost_max=mat_max + lab_max,
                materials_min=mat_min, materials_max=mat_max,
                labor_min=lab_min, labor_max=lab_max,
                unit="unit", quantity=qty, priority=priority,
            ))

        # Door
        if f.door_condition is not None:
            fixture_conditions.append(f.door_condition)
        door_action = _action_from_condition(f.door_condition)
        if door_action in ("replace", "repair"):
            if door_action == "replace":
                r = COST_TABLE["doors"]["replace"]
                labor_key = "doors_replace"
                desc = "Substituição de porta"
                priority = "media"
            else:
                r = COST_TABLE["doors"]["repair_and_paint"]
                labor_key = "doors_repair"
                desc = "Reparação e pintura de porta"
                priority = "baixa"
            mat_min, mat_max, lab_min, lab_max = _apply_multipliers(
                r.min, r.max, prefs.finish_level, regional, floor_surcharge,
                LABOR_RATIOS[labor_key], prefs.diy,
            )
            items.append(CostLineItem(
                category="doors", action=door_action, description=desc,
                cost_min=mat_min + lab_min, cost_max=mat_max + lab_max,
                materials_min=mat_min, materials_max=mat_max,
                labor_min=lab_min, labor_max=lab_max,
                unit="unit", quantity=1.0, priority=priority,
            ))

    # --- M3 MEP ---
    if features.mep:
        m = features.mep
        mep_has_data = True
        rewire_needed = _needs_rewiring(m.outlet_switch_style, context.construction_era)
        if rewire_needed:
            r = COST_TABLE["electrical"]["rewire_room"]
            mat_min, mat_max, lab_min, lab_max = _apply_multipliers(
                r.min, r.max, prefs.finish_level, regional, floor_surcharge,
                LABOR_RATIOS["electrical_rewire"], prefs.diy,
            )
            items.append(CostLineItem(
                category="electrical", action="rewire",
                description="Remodelação da instalação elétrica",
                cost_min=mat_min + lab_min, cost_max=mat_max + lab_max,
                materials_min=mat_min, materials_max=mat_max,
                labor_min=lab_min, labor_max=lab_max,
                unit="room", quantity=1.0, priority="alta",
            ))

    # Build work scope and confidence
    surf_scope = _scope_from_avg(sum(surface_conditions) / len(surface_conditions)) if surface_conditions else WorkScope.NONE
    fix_scope = _scope_from_avg(sum(fixture_conditions) / len(fixture_conditions)) if fixture_conditions else WorkScope.NONE
    mep_scope = WorkScope.REPLACE if any(i.category == "electrical" for i in items) else WorkScope.NONE

    overall_conditions = surface_conditions + fixture_conditions
    overall_scope = _scope_from_avg(sum(overall_conditions) / len(overall_conditions)) if overall_conditions else WorkScope.NONE

    work_scope = WorkScopeResult(
        surfaces=surf_scope, fixtures=fix_scope, mep=mep_scope, overall=overall_scope
    )

    confidence = ModuleConfidence(
        surfaces=0.8 if features.surfaces else None,
        fixtures=0.7 if features.fixtures else None,
        mep=0.6 if mep_has_data else None,
        overall=0.7 if (features.surfaces or features.fixtures) else 0.3,
    )

    return items, work_scope, confidence


def _calculate_kitchen(
    features: KitchenFeatures,
    area_m2: float,
    prefs: UserPreferences,
    context: PropertyContext,
) -> tuple[list[CostLineItem], WorkScopeResult, ModuleConfidence]:
    """Calculate costs for kitchen rooms."""
    items: list[CostLineItem] = []
    regional = LOCATION_COST_MULTIPLIERS.get(context.location_cost_tier, 1.0)
    floor_surcharge = FLOOR_ACCESSIBILITY_SURCHARGES.get(context.floor_accessibility.value, 0.0)

    surface_conditions: list[int] = []
    fixture_conditions: list[int] = []

    # --- M1 Surfaces (same logic as generic) ---
    if features.surfaces:
        s = features.surfaces
        surface_conditions.extend(c for c in [s.floor_condition, s.wall_condition, s.ceiling_condition] if c is not None)

        # Floor
        floor_action = _action_from_condition(s.floor_condition)
        if floor_action != "keep":
            key = "replace" if floor_action == "replace" else "repair"
            cost_range = (
                COST_TABLE["flooring"]["replace"].get(s.floor_material, COST_TABLE["flooring"]["replace"][FloorMaterial.NOT_VISIBLE])
                if key == "replace"
                else COST_TABLE["flooring"]["repair"]
            )
            labor_key = f"flooring_{key}"
            mat_min, mat_max, lab_min, lab_max = _apply_multipliers(
                cost_range.min * area_m2, cost_range.max * area_m2,
                prefs.finish_level, regional, floor_surcharge,
                LABOR_RATIOS[labor_key], prefs.diy,
            )
            items.append(CostLineItem(
                category="flooring", action=floor_action,
                description=f"Substituição do pavimento ({s.floor_material.value})" if floor_action == "replace" else "Reparação do pavimento",
                cost_min=mat_min + lab_min, cost_max=mat_max + lab_max,
                materials_min=mat_min, materials_max=mat_max,
                labor_min=lab_min, labor_max=lab_max,
                unit="m2", quantity=area_m2,
                priority="alta" if s.floor_condition <= 2 else "media",
            ))

        # Walls (kitchen often has azulejos)
        wall_action = _action_from_condition(s.wall_condition)
        if wall_action != "keep":
            wall_area = area_m2 * 2.5
            if s.wall_finish == WallFinish.AZULEJOS:
                total_min_pm2 = COST_TABLE["walls"]["remove_azulejos"].min + COST_TABLE["walls"]["install_azulejos"].min
                total_max_pm2 = COST_TABLE["walls"]["remove_azulejos"].max + COST_TABLE["walls"]["install_azulejos"].max
                labor_key = "walls_install_azulejos"
                desc = "Remoção e reinstalação de azulejos"
            elif wall_action == "replace":
                r = COST_TABLE["walls"]["strip_and_replaster"]
                total_min_pm2, total_max_pm2 = r.min, r.max
                labor_key = "walls_replaster"
                desc = "Remoção e reboco de paredes"
            else:
                r = COST_TABLE["walls"]["repaint"]
                total_min_pm2, total_max_pm2 = r.min, r.max
                labor_key = "walls_repaint"
                desc = "Pintura de paredes"
            mat_min, mat_max, lab_min, lab_max = _apply_multipliers(
                total_min_pm2 * wall_area, total_max_pm2 * wall_area,
                prefs.finish_level, regional, floor_surcharge,
                LABOR_RATIOS[labor_key], prefs.diy,
            )
            items.append(CostLineItem(
                category="walls", action=wall_action, description=desc,
                cost_min=mat_min + lab_min, cost_max=mat_max + lab_max,
                materials_min=mat_min, materials_max=mat_max,
                labor_min=lab_min, labor_max=lab_max,
                unit="m2", quantity=wall_area,
                priority="alta" if wall_action == "replace" else "media",
            ))

        # Ceiling
        ceil_action = _action_from_condition(s.ceiling_condition)
        if ceil_action != "keep":
            r = COST_TABLE["ceiling"]["full_replaster"] if ceil_action == "replace" else COST_TABLE["ceiling"]["repair_and_repaint"]
            labor_key = "ceiling_replaster" if ceil_action == "replace" else "ceiling_repair"
            mat_min, mat_max, lab_min, lab_max = _apply_multipliers(
                r.min * area_m2, r.max * area_m2,
                prefs.finish_level, regional, floor_surcharge,
                LABOR_RATIOS[labor_key], prefs.diy,
            )
            items.append(CostLineItem(
                category="ceiling", action=ceil_action,
                description="Reboco e pintura de teto" if ceil_action == "replace" else "Reparação e pintura de teto",
                cost_min=mat_min + lab_min, cost_max=mat_max + lab_max,
                materials_min=mat_min, materials_max=mat_max,
                labor_min=lab_min, labor_max=lab_max,
                unit="m2", quantity=area_m2,
                priority="alta" if ceil_action == "replace" else "media",
            ))

    # --- M2 Fixtures ---
    if features.fixtures:
        f = features.fixtures
        fixture_conditions.extend(c for c in [f.cabinet_condition, f.countertop_condition, f.door_condition] if c is not None)

        # Cabinets
        cab_action = _action_from_condition(f.cabinet_condition)
        if cab_action != "keep":
            key = "replace_full" if cab_action == "replace" else "reface" if f.cabinet_condition == 3 else "repair"
            r = COST_TABLE["kitchen_cabinets"][key]
            labor_key = f"kitchen_cabinets_{key.replace('_full', '_replace') if key == 'replace_full' else key}"
            if "replace" in key:
                labor_key = "kitchen_cabinets_replace"
            elif key == "reface":
                labor_key = "kitchen_cabinets_reface"
            else:
                labor_key = "kitchen_cabinets_repair"
            mat_min, mat_max, lab_min, lab_max = _apply_multipliers(
                r.min, r.max, prefs.finish_level, regional, floor_surcharge,
                LABOR_RATIOS[labor_key], prefs.diy,
            )
            items.append(CostLineItem(
                category="kitchen_cabinets", action=cab_action,
                description="Substituição de móveis de cozinha" if cab_action == "replace" else "Renovação de móveis de cozinha",
                cost_min=mat_min + lab_min, cost_max=mat_max + lab_max,
                materials_min=mat_min, materials_max=mat_max,
                labor_min=lab_min, labor_max=lab_max,
                unit="room", quantity=1.0,
                priority="alta" if cab_action == "replace" else "media",
            ))

        # Countertop
        ctr_action = _action_from_condition(f.countertop_condition)
        if ctr_action != "keep":
            if ctr_action == "replace":
                cost_per_m = COST_TABLE["kitchen_countertop"]["replace"].get(
                    f.countertop_material,
                    COST_TABLE["kitchen_countertop"]["replace"][FloorMaterial.NOT_VISIBLE],  # type: ignore[index]
                )
                qty = COUNTERTOP_DEFAULT_LINEAR_M
                mat_min, mat_max, lab_min, lab_max = _apply_multipliers(
                    cost_per_m.min * qty, cost_per_m.max * qty,
                    prefs.finish_level, regional, floor_surcharge,
                    LABOR_RATIOS["kitchen_countertop_replace"], prefs.diy,
                )
                items.append(CostLineItem(
                    category="kitchen_countertop", action="replace",
                    description=f"Substituição de bancada ({f.countertop_material.value})",
                    cost_min=mat_min + lab_min, cost_max=mat_max + lab_max,
                    materials_min=mat_min, materials_max=mat_max,
                    labor_min=lab_min, labor_max=lab_max,
                    unit="linear_m", quantity=qty, priority="media",
                ))
            else:
                r = COST_TABLE["kitchen_countertop"]["repair"]
                mat_min, mat_max, lab_min, lab_max = _apply_multipliers(
                    r.min, r.max, prefs.finish_level, regional, floor_surcharge,
                    LABOR_RATIOS["kitchen_countertop_repair"], prefs.diy,
                )
                items.append(CostLineItem(
                    category="kitchen_countertop", action="repair",
                    description="Reparação de bancada",
                    cost_min=mat_min + lab_min, cost_max=mat_max + lab_max,
                    materials_min=mat_min, materials_max=mat_max,
                    labor_min=lab_min, labor_max=lab_max,
                    unit="room", quantity=1.0, priority="baixa",
                ))

        # Door
        door_action = _action_from_condition(f.door_condition)
        if door_action != "keep":
            r = COST_TABLE["doors"]["replace"] if door_action == "replace" else COST_TABLE["doors"]["repair_and_paint"]
            labor_key = "doors_replace" if door_action == "replace" else "doors_repair"
            mat_min, mat_max, lab_min, lab_max = _apply_multipliers(
                r.min, r.max, prefs.finish_level, regional, floor_surcharge,
                LABOR_RATIOS[labor_key], prefs.diy,
            )
            items.append(CostLineItem(
                category="doors", action=door_action,
                description="Substituição de porta" if door_action == "replace" else "Reparação de porta",
                cost_min=mat_min + lab_min, cost_max=mat_max + lab_max,
                materials_min=mat_min, materials_max=mat_max,
                labor_min=lab_min, labor_max=lab_max,
                unit="unit", quantity=1.0, priority="media",
            ))

        # Appliances budget if none visible
        if not f.appliances_visible:
            r = COST_TABLE["kitchen_appliances"]["full_set"]
            mat_min, mat_max, lab_min, lab_max = _apply_multipliers(
                r.min, r.max, prefs.finish_level, regional, floor_surcharge,
                LABOR_RATIOS["kitchen_appliances_install"], prefs.diy,
            )
            items.append(CostLineItem(
                category="kitchen_appliances", action="install",
                description="Eletrodomésticos (nenhum visível nas fotos)",
                cost_min=mat_min + lab_min, cost_max=mat_max + lab_max,
                materials_min=mat_min, materials_max=mat_max,
                labor_min=lab_min, labor_max=lab_max,
                unit="room", quantity=1.0, priority="alta",
            ))

    # --- M3 MEP ---
    if features.mep:
        m = features.mep
        rewire_needed = _needs_rewiring(m.outlet_switch_style, context.construction_era)
        replumb_needed = _needs_replumbing(m.plumbing_visible_condition, context.construction_era)
        if rewire_needed:
            r = COST_TABLE["electrical"]["rewire_room"]
            mat_min, mat_max, lab_min, lab_max = _apply_multipliers(
                r.min, r.max, prefs.finish_level, regional, floor_surcharge,
                LABOR_RATIOS["electrical_rewire"], prefs.diy,
            )
            items.append(CostLineItem(
                category="electrical", action="rewire",
                description="Remodelação da instalação elétrica",
                cost_min=mat_min + lab_min, cost_max=mat_max + lab_max,
                materials_min=mat_min, materials_max=mat_max,
                labor_min=lab_min, labor_max=lab_max,
                unit="room", quantity=1.0, priority="alta",
            ))
        if replumb_needed:
            r = COST_TABLE["plumbing"]["replace_room"]
            mat_min, mat_max, lab_min, lab_max = _apply_multipliers(
                r.min, r.max, prefs.finish_level, regional, floor_surcharge,
                LABOR_RATIOS["plumbing_replace"], prefs.diy,
            )
            items.append(CostLineItem(
                category="plumbing", action="replace",
                description="Substituição de canalização",
                cost_min=mat_min + lab_min, cost_max=mat_max + lab_max,
                materials_min=mat_min, materials_max=mat_max,
                labor_min=lab_min, labor_max=lab_max,
                unit="room", quantity=1.0, priority="alta",
            ))

    surf_scope = _scope_from_avg(sum(surface_conditions) / len(surface_conditions)) if surface_conditions else WorkScope.NONE
    fix_scope = _scope_from_avg(sum(fixture_conditions) / len(fixture_conditions)) if fixture_conditions else WorkScope.NONE
    mep_scope = WorkScope.REPLACE if any(i.category in ("electrical", "plumbing") for i in items) else WorkScope.NONE
    overall_conditions = surface_conditions + fixture_conditions
    overall_scope = _scope_from_avg(sum(overall_conditions) / len(overall_conditions)) if overall_conditions else WorkScope.NONE

    work_scope = WorkScopeResult(surfaces=surf_scope, fixtures=fix_scope, mep=mep_scope, overall=overall_scope)
    confidence = ModuleConfidence(
        surfaces=0.8 if features.surfaces else None,
        fixtures=0.8 if features.fixtures else None,
        mep=0.6 if features.mep else None,
        overall=0.75 if (features.surfaces and features.fixtures) else 0.4,
    )
    return items, work_scope, confidence


def _calculate_bathroom(
    features: BathroomFeatures,
    area_m2: float,
    prefs: UserPreferences,
    context: PropertyContext,
) -> tuple[list[CostLineItem], WorkScopeResult, ModuleConfidence]:
    """Calculate costs for bathroom rooms."""
    items: list[CostLineItem] = []
    regional = LOCATION_COST_MULTIPLIERS.get(context.location_cost_tier, 1.0)
    floor_surcharge = FLOOR_ACCESSIBILITY_SURCHARGES.get(context.floor_accessibility.value, 0.0)

    surface_conditions: list[int] = []
    fixture_conditions: list[int] = []

    # --- M1 Surfaces ---
    if features.surfaces:
        s = features.surfaces
        surface_conditions.extend(c for c in [s.wall_condition, s.floor_condition, s.ceiling_condition] if c is not None)

        # Wall tiles (bathroom)
        wall_action = _action_from_condition(s.wall_condition)
        if wall_action != "keep":
            wall_area = area_m2 * 2.5
            if wall_action == "replace":
                r = COST_TABLE["bathroom_tiles"]["replace_wall_tiles"]
                desc = "Substituição de azulejos"
                priority = "alta"
                labor_key = "bathroom_tiles_replace"
            else:
                r = COST_TABLE["bathroom_tiles"]["repair_grout"]
                desc = "Reparação de juntas/azulejos"
                priority = "media"
                labor_key = "bathroom_tiles_repair"
            mat_min, mat_max, lab_min, lab_max = _apply_multipliers(
                r.min * wall_area, r.max * wall_area,
                prefs.finish_level, regional, floor_surcharge,
                LABOR_RATIOS[labor_key], prefs.diy,
            )
            items.append(CostLineItem(
                category="bathroom_tiles", action=wall_action, description=desc,
                cost_min=mat_min + lab_min, cost_max=mat_max + lab_max,
                materials_min=mat_min, materials_max=mat_max,
                labor_min=lab_min, labor_max=lab_max,
                unit="m2", quantity=wall_area, priority=priority,
            ))

        # Floor (almost always tile in PT bathrooms)
        floor_action = _action_from_condition(s.floor_condition)
        if floor_action != "keep":
            r = COST_TABLE["flooring"]["replace"][FloorMaterial.CERAMIC_TILE] if floor_action == "replace" else COST_TABLE["flooring"]["repair"]
            labor_key = "flooring_replace" if floor_action == "replace" else "flooring_repair"
            mat_min, mat_max, lab_min, lab_max = _apply_multipliers(
                r.min * area_m2, r.max * area_m2,
                prefs.finish_level, regional, floor_surcharge,
                LABOR_RATIOS[labor_key], prefs.diy,
            )
            items.append(CostLineItem(
                category="flooring", action=floor_action,
                description="Substituição de pavimento (cerâmico)" if floor_action == "replace" else "Reparação de pavimento",
                cost_min=mat_min + lab_min, cost_max=mat_max + lab_max,
                materials_min=mat_min, materials_max=mat_max,
                labor_min=lab_min, labor_max=lab_max,
                unit="m2", quantity=area_m2,
                priority="alta" if floor_action == "replace" else "media",
            ))

        # Ceiling
        ceil_action = _action_from_condition(s.ceiling_condition)
        if ceil_action != "keep":
            r = COST_TABLE["ceiling"]["repair_and_repaint"]
            mat_min, mat_max, lab_min, lab_max = _apply_multipliers(
                r.min * area_m2, r.max * area_m2,
                prefs.finish_level, regional, floor_surcharge,
                LABOR_RATIOS["ceiling_repair"], prefs.diy,
            )
            items.append(CostLineItem(
                category="ceiling", action=ceil_action,
                description="Reparação e pintura de teto",
                cost_min=mat_min + lab_min, cost_max=mat_max + lab_max,
                materials_min=mat_min, materials_max=mat_max,
                labor_min=lab_min, labor_max=lab_max,
                unit="m2", quantity=area_m2, priority="media",
            ))

    # --- M2 Fixtures ---
    if features.fixtures:
        f = features.fixtures
        fixture_conditions.extend(c for c in [f.sanitary_ware_condition, f.shower_bath_condition, f.bathroom_tile_condition] if c is not None)

        # Sanitary ware
        san_action = _action_from_condition(f.sanitary_ware_condition)
        if san_action != "keep":
            if san_action == "replace":
                r = COST_TABLE["bathroom_sanitary"]["replace_full_set"]
                labor_key = "bathroom_sanitary_replace"
                desc = "Substituição de louças sanitárias"
                priority = "alta"
            else:
                r = COST_TABLE["bathroom_sanitary"]["repair"]
                labor_key = "bathroom_sanitary_repair"
                desc = "Reparação de louças sanitárias"
                priority = "media"
            mat_min, mat_max, lab_min, lab_max = _apply_multipliers(
                r.min, r.max, prefs.finish_level, regional, floor_surcharge,
                LABOR_RATIOS[labor_key], prefs.diy,
            )
            items.append(CostLineItem(
                category="bathroom_sanitary", action=san_action, description=desc,
                cost_min=mat_min + lab_min, cost_max=mat_max + lab_max,
                materials_min=mat_min, materials_max=mat_max,
                labor_min=lab_min, labor_max=lab_max,
                unit="room", quantity=1.0, priority=priority,
            ))

        # Shower/bath
        shower_action = _action_from_condition(f.shower_bath_condition)
        if shower_action != "keep":
            if shower_action == "replace":
                if f.shower_or_bath == ShowerOrBath.WALK_IN_SHOWER:
                    r = COST_TABLE["bathroom_shower_bath"]["replace_walk_in"]
                elif f.shower_or_bath == ShowerOrBath.BATHTUB:
                    r = COST_TABLE["bathroom_shower_bath"]["replace_bathtub"]
                else:
                    r = COST_TABLE["bathroom_shower_bath"]["replace_shower"]
                labor_key = "bathroom_shower_replace"
                desc = "Substituição de duche/banheira"
                priority = "alta"
            else:
                r = COST_TABLE["bathroom_shower_bath"]["reseal"]
                labor_key = "bathroom_shower_reseal"
                desc = "Reselagem de duche/banheira"
                priority = "media"
            mat_min, mat_max, lab_min, lab_max = _apply_multipliers(
                r.min, r.max, prefs.finish_level, regional, floor_surcharge,
                LABOR_RATIOS[labor_key], prefs.diy,
            )
            items.append(CostLineItem(
                category="bathroom_shower_bath", action=shower_action, description=desc,
                cost_min=mat_min + lab_min, cost_max=mat_max + lab_max,
                materials_min=mat_min, materials_max=mat_max,
                labor_min=lab_min, labor_max=lab_max,
                unit="unit", quantity=1.0, priority=priority,
            ))

    # --- M3 MEP ---
    if features.mep:
        m = features.mep
        rewire_needed = _needs_rewiring(m.outlet_switch_style, context.construction_era)
        replumb_needed = _needs_replumbing(m.plumbing_visible_condition, context.construction_era)
        if rewire_needed:
            r = COST_TABLE["electrical"]["rewire_room"]
            mat_min, mat_max, lab_min, lab_max = _apply_multipliers(
                r.min, r.max, prefs.finish_level, regional, floor_surcharge,
                LABOR_RATIOS["electrical_rewire"], prefs.diy,
            )
            items.append(CostLineItem(
                category="electrical", action="rewire",
                description="Remodelação da instalação elétrica",
                cost_min=mat_min + lab_min, cost_max=mat_max + lab_max,
                materials_min=mat_min, materials_max=mat_max,
                labor_min=lab_min, labor_max=lab_max,
                unit="room", quantity=1.0, priority="alta",
            ))
        if replumb_needed:
            r = COST_TABLE["plumbing"]["replace_room"]
            mat_min, mat_max, lab_min, lab_max = _apply_multipliers(
                r.min, r.max, prefs.finish_level, regional, floor_surcharge,
                LABOR_RATIOS["plumbing_replace"], prefs.diy,
            )
            items.append(CostLineItem(
                category="plumbing", action="replace",
                description="Substituição de canalização",
                cost_min=mat_min + lab_min, cost_max=mat_max + lab_max,
                materials_min=mat_min, materials_max=mat_max,
                labor_min=lab_min, labor_max=lab_max,
                unit="room", quantity=1.0, priority="alta",
            ))

    surf_scope = _scope_from_avg(sum(surface_conditions) / len(surface_conditions)) if surface_conditions else WorkScope.NONE
    fix_scope = _scope_from_avg(sum(fixture_conditions) / len(fixture_conditions)) if fixture_conditions else WorkScope.NONE
    mep_scope = WorkScope.REPLACE if any(i.category in ("electrical", "plumbing") for i in items) else WorkScope.NONE
    overall_conditions = surface_conditions + fixture_conditions
    overall_scope = _scope_from_avg(sum(overall_conditions) / len(overall_conditions)) if overall_conditions else WorkScope.NONE

    work_scope = WorkScopeResult(surfaces=surf_scope, fixtures=fix_scope, mep=mep_scope, overall=overall_scope)
    confidence = ModuleConfidence(
        surfaces=0.8 if features.surfaces else None,
        fixtures=0.8 if features.fixtures else None,
        mep=0.6 if features.mep else None,
        overall=0.75 if (features.surfaces and features.fixtures) else 0.4,
    )
    return items, work_scope, confidence


def _needs_rewiring(style: OutletSwitchStyle, era: ConstructionEra) -> bool:
    """Determine if rewiring is likely needed."""
    if style in (OutletSwitchStyle.BAKELITE_OLD, OutletSwitchStyle.SURFACE_MOUNTED):
        return True
    return ERA_REWIRING_LIKELY.get(era, False)


def _needs_replumbing(condition: PlumbingVisibleCondition, era: ConstructionEra) -> bool:
    """Determine if replumbing is likely needed."""
    if condition == PlumbingVisibleCondition.VISIBLE_CORRODED:
        return True
    return ERA_REPLUMBING_LIKELY.get(era, False)


def _resolve_area(
    features: RoomFeatures,
    room_type: RoomType,
    context: PropertyContext,
) -> float:
    """
    Resolve the room area in m2.

    Priority:
    1. GPT-estimated area from features
    2. usable_area_m2 * ROOM_AREA_WEIGHTS[room_type]
    3. area_m2 * ROOM_AREA_WEIGHTS[room_type]
    4. DEFAULT_ROOM_AREA_M2
    """
    # 1. GPT estimate
    if hasattr(features, "estimated_area_m2") and features.estimated_area_m2 and features.estimated_area_m2 > 0:
        return features.estimated_area_m2

    weight = ROOM_AREA_WEIGHTS.get(room_type, 0.12)

    # 2. usable area
    if context.usable_area_m2 > 0:
        return context.usable_area_m2 * weight

    # 3. constructed area
    if context.area_m2 > 0:
        return context.area_m2 * weight

    # 4. default
    return DEFAULT_ROOM_AREA_M2


def calculate_costs(
    features: RoomFeatures,
    room_type: RoomType,
    prefs: UserPreferences,
    context: PropertyContext,
) -> RoomCostResult:
    """
    Pure function: calculate renovation costs from structured features.

    Args:
        features:  Structured features extracted from room photos by GPT.
        room_type: Room type enum (determines area weight + routing).
        prefs:     User preferences (diy, finish_level, etc.).
        context:   Property-level context (era, region, floor, area).

    Returns:
        RoomCostResult with cost_breakdown, line_items, work_scope, module_confidence.
    """
    area_m2 = _resolve_area(features, room_type, context)

    try:
        if isinstance(features, KitchenFeatures):
            items, work_scope, confidence = _calculate_kitchen(features, area_m2, prefs, context)
        elif isinstance(features, BathroomFeatures):
            items, work_scope, confidence = _calculate_bathroom(features, area_m2, prefs, context)
        else:
            items, work_scope, confidence = _calculate_generic_room(features, area_m2, prefs, context)
    except Exception as e:
        logger.error("cost_calculator_error", room_type=room_type.value, error=str(e))
        return RoomCostResult()

    # Aggregate breakdown
    breakdown = CostBreakdown(
        materials_min=sum(i.materials_min for i in items),
        materials_max=sum(i.materials_max for i in items),
        labor_min=sum(i.labor_min for i in items),
        labor_max=sum(i.labor_max for i in items),
    )

    return RoomCostResult(
        cost_breakdown=breakdown,
        line_items=items,
        module_confidence=confidence,
        work_scope=work_scope,
    )


def renovation_items_from_cost_result(result: RoomCostResult) -> list[RenovationItem]:
    """
    Convert CostLineItems to RenovationItems for backward compatibility.

    The old RoomAnalysis.renovation_items field expects RenovationItem objects.
    This generates them from the deterministic cost calculator output.
    """
    return [
        RenovationItem(
            item=item.description,
            cost_min=round(item.cost_min, 2),
            cost_max=round(item.cost_max, 2),
            priority=item.priority,
            notes="",
        )
        for item in result.line_items
    ]


def compute_composite_indices(
    room_results: dict[str, RoomCostResult],
    context: PropertyContext,
) -> CompositeIndices:
    """
    Compute property-level composite indices from per-room cost results.

    Args:
        room_results: Dict of room_label -> RoomCostResult.
        context:      Property-level context.

    Returns:
        CompositeIndices with work_scope, time_estimate, hidden_cost_risk, scope_complexity.
    """
    from app.models.features.outputs import (
        WorkScopeResult,
    )

    if not room_results:
        return CompositeIndices()

    # Overall work scope = worst scope across all rooms
    all_scopes = [r.work_scope.overall for r in room_results.values()]
    scope_order = [WorkScope.NONE, WorkScope.REPAIR, WorkScope.REFURBISH, WorkScope.REPLACE, WorkScope.FULL_RENOVATION]
    worst_scope = max(all_scopes, key=lambda s: scope_order.index(s) if s in scope_order else 0)

    # Time estimate = sum of time per room, capped by parallel work
    time_min_sum = 0
    time_max_sum = 0
    for r in room_results.values():
        t_min, t_max = _time_from_scope(r.work_scope.overall)
        time_min_sum += t_min
        time_max_sum += t_max
    # Rooms can be done partially in parallel: divide by ~1.5
    time_min = max(1, int(time_min_sum / 1.5)) if time_min_sum > 0 else 0
    time_max = max(1, int(time_max_sum / 1.5)) if time_max_sum > 0 else 0

    # Hidden cost risk
    risk_factors: list[str] = []
    has_mep_work = any(r.work_scope.mep != WorkScope.NONE for r in room_results.values())
    if has_mep_work:
        risk_factors.append("Trabalhos de instalações (elétrica/canalização) identificados")
    if ERA_REWIRING_LIKELY.get(context.construction_era, False):
        risk_factors.append(f"Edifício de época {context.construction_era.value} — risco de instalações desatualizadas")
    if ERA_REPLUMBING_LIKELY.get(context.construction_era, False):
        risk_factors.append("Risco de canalização obsoleta")

    if len(risk_factors) >= 2:
        risk_level = HiddenCostRisk.HIGH
    elif len(risk_factors) == 1:
        risk_level = HiddenCostRisk.MEDIUM
    elif context.construction_era == ConstructionEra.UNKNOWN:
        risk_level = HiddenCostRisk.UNKNOWN
    else:
        risk_level = HiddenCostRisk.LOW

    # Scope complexity
    rooms_needing_work = sum(1 for r in room_results.values() if r.work_scope.overall != WorkScope.NONE)
    modules_needing_work = sum(
        (1 if r.work_scope.surfaces != WorkScope.NONE else 0) +
        (1 if r.work_scope.fixtures != WorkScope.NONE else 0) +
        (1 if r.work_scope.mep != WorkScope.NONE else 0)
        for r in room_results.values()
    )

    if worst_scope == WorkScope.FULL_RENOVATION or rooms_needing_work >= 5:
        complexity = ScopeComplexity.MAJOR
    elif worst_scope == WorkScope.REPLACE or rooms_needing_work >= 3:
        complexity = ScopeComplexity.COMPLEX
    elif rooms_needing_work >= 2:
        complexity = ScopeComplexity.MODERATE
    else:
        complexity = ScopeComplexity.SIMPLE

    return CompositeIndices(
        work_scope=WorkScopeResult(overall=worst_scope),
        time_estimate=TimeEstimate(weeks_min=time_min, weeks_max=time_max),
        hidden_cost_risk=HiddenCostRiskResult(level=risk_level, factors=risk_factors),
        scope_complexity=ScopeComplexityResult(
            level=complexity,
            room_count=len(room_results),
            modules_needing_work=modules_needing_work,
        ),
    )
