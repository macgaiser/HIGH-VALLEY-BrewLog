"""BeerXML-Export/-Import eines Suds (Rezept), zum Austausch mit MySpeidel
(Speidel Braumeister) und anderer Brausoftware (Brewfather, BeerSmith,
Brewer's Friend, Brewtarget, ...).

MySpeidel akzeptiert Rezepte per Drag&Drop im BeerXML-Format - der Export
bildet Schüttung, Maischplan, Hopfengaben (inkl. Stopfhopfen) und Hefegabe
eines Suds als Standard-BeerXML-1.0-Datei ab. Der Import liest dieselbe
Struktur umgekehrt: BeerXML kennt nur Rezeptdaten, keine Brautag-Historie
(Messwerte, Datum, Kommentare) - importiert werden also Zutaten/Maischplan/
Zielwerte eines Rezepts, alles andere trägt man wie bei jedem neuen Sud
selbst nach.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from xml.dom import minidom

from sqlmodel import Session

from app.batch_calc import BatchMetrics
from app.formulas import sg_to_plato
from app.models import (
    Batch,
    DryHopAddition,
    GrainAddition,
    HopAddition,
    HopAdditionType,
    InventoryCategory,
    MashStep,
    Settings,
    YeastAddition,
)

_HOP_USE = {
    HopAdditionType.kochen: "Boil",
    HopAdditionType.whirlpool: "Aroma",
    HopAdditionType.nachisomerisierung: "Aroma",
}


def _sub(parent: ET.Element, tag: str, value) -> ET.Element:
    el = ET.SubElement(parent, tag)
    el.text = "" if value is None else str(value)
    return el


def _ebc_to_srm(ebc: float) -> float:
    # BeerXML erwartet Malz-/Bierfarbe in Lovibond/SRM statt EBC - die App
    # rechnet intern mit EBC (siehe formulas.beer_color_ebc: EBC = SRM *
    # 1.97), hier also der Rückweg als Näherung.
    return round(ebc / 1.97, 1)


def build_recipe_xml(batch: Batch, settings: Settings, metrics: BatchMetrics) -> str:
    recipes = ET.Element("RECIPES")
    recipe = ET.SubElement(recipes, "RECIPE")

    _sub(recipe, "NAME", batch.name or f"Sud #{batch.batch_number}")
    _sub(recipe, "VERSION", 1)
    _sub(recipe, "TYPE", "All Grain")

    style = ET.SubElement(recipe, "STYLE")
    _sub(style, "NAME", batch.style or "")
    _sub(style, "VERSION", 1)
    _sub(style, "CATEGORY", "")
    _sub(style, "CATEGORY_NUMBER", "")
    _sub(style, "STYLE_LETTER", "")
    _sub(style, "STYLE_GUIDE", "")
    _sub(style, "TYPE", "Lager" if batch.fermentation_type == "Untergärig" else "Ale")
    _sub(style, "OG_MIN", 0)
    _sub(style, "OG_MAX", 0)
    _sub(style, "FG_MIN", 0)
    _sub(style, "FG_MAX", 0)
    _sub(style, "IBU_MIN", 0)
    _sub(style, "IBU_MAX", 0)
    _sub(style, "COLOR_MIN", 0)
    _sub(style, "COLOR_MAX", 0)

    _sub(recipe, "BREWER", settings.label_brand_name or "")
    _sub(recipe, "BATCH_SIZE", round(batch.target_volume_l or 0, 2))
    _sub(recipe, "BOIL_SIZE", round(batch.post_lauter_volume_l or batch.target_volume_l or 0, 2))
    _sub(recipe, "BOIL_TIME", batch.boil_time_min or 0)
    _sub(
        recipe,
        "EFFICIENCY",
        round(metrics.mash_efficiency_percent, 1) if metrics.mash_efficiency_percent else 70,
    )

    fermentables = ET.SubElement(recipe, "FERMENTABLES")
    for g in batch.grain_additions:
        if not g.malt_name:
            continue
        el = ET.SubElement(fermentables, "FERMENTABLE")
        _sub(el, "NAME", g.malt_name)
        _sub(el, "VERSION", 1)
        _sub(el, "AMOUNT", round(g.amount_kg or 0, 3))
        _sub(el, "TYPE", "Grain")
        _sub(el, "YIELD", 75)
        ebc = g.inventory_item.color_ebc if (g.inventory_item and g.inventory_item.color_ebc) else None
        _sub(el, "COLOR", _ebc_to_srm(ebc) if ebc else 0)

    hops = ET.SubElement(recipe, "HOPS")
    miscs = ET.SubElement(recipe, "MISCS")
    for h in batch.hop_additions:
        if not h.hop_name:
            continue
        # Ueber den Hopfengaben-Dialog koennen auch Lagerartikel der
        # Kategorie "Sonstiges" ausgewaehlt werden (Klaermittel, Wasser-
        # zusaetze usw.) - die landen hier nicht als <HOP>, sondern korrekt
        # als <MISC>.
        if h.inventory_item and h.inventory_item.category == InventoryCategory.sonstiges:
            el = ET.SubElement(miscs, "MISC")
            _sub(el, "NAME", h.hop_name)
            _sub(el, "VERSION", 1)
            _sub(el, "TYPE", "Other")
            _sub(el, "USE", "Boil" if h.addition_type == HopAdditionType.kochen else "Secondary")
            _sub(el, "TIME", round(h.time_min or 0, 1))
            _sub(el, "AMOUNT", round((h.amount_g or 0) / 1000, 4))
            _sub(el, "AMOUNT_IS_WEIGHT", "TRUE")
            continue
        el = ET.SubElement(hops, "HOP")
        _sub(el, "NAME", h.hop_name)
        _sub(el, "VERSION", 1)
        _sub(el, "ALPHA", round(h.alpha_acid_percent or 0, 1))
        _sub(el, "AMOUNT", round((h.amount_g or 0) / 1000, 4))
        _sub(el, "USE", _HOP_USE.get(h.addition_type, "Boil"))
        _sub(el, "TIME", round(h.time_min or 0, 1))
        _sub(el, "FORM", "Pellet")
    for dh in batch.dry_hop_additions:
        if not dh.hop_name:
            continue
        el = ET.SubElement(hops, "HOP")
        _sub(el, "NAME", dh.hop_name)
        _sub(el, "VERSION", 1)
        _sub(el, "ALPHA", 0)
        _sub(el, "AMOUNT", round((dh.amount_g or 0) / 1000, 4))
        _sub(el, "USE", "Dry Hop")
        _sub(el, "TIME", 0)
        _sub(el, "FORM", "Pellet")
        if dh.timing_label:
            _sub(el, "NOTES", dh.timing_label)

    yeasts = ET.SubElement(recipe, "YEASTS")
    for y in batch.yeast_additions:
        if not y.yeast_name:
            continue
        el = ET.SubElement(yeasts, "YEAST")
        _sub(el, "NAME", y.yeast_name)
        _sub(el, "VERSION", 1)
        _sub(el, "TYPE", "Lager" if batch.fermentation_type == "Untergärig" else "Ale")
        _sub(el, "FORM", "Dry")
        _sub(el, "AMOUNT", round(y.amount or 0, 3))
        _sub(el, "AMOUNT_IS_WEIGHT", "TRUE" if (y.unit or "").lower() in ("g", "kg") else "FALSE")
        notes = " ".join(x for x in [y.generation_label, y.comment] if x)
        if notes:
            _sub(el, "NOTES", notes)

    if batch.water_profile:
        wp = batch.water_profile
        waters = ET.SubElement(recipe, "WATERS")
        el = ET.SubElement(waters, "WATER")
        _sub(el, "NAME", wp.name)
        _sub(el, "VERSION", 1)
        _sub(el, "AMOUNT", round((batch.main_water_l or 0) + (batch.sparge_water_l or 0), 2))
        _sub(el, "CALCIUM", wp.calcium_ppm or 0)
        _sub(el, "BICARBONATE", wp.bicarbonate_ppm or 0)
        _sub(el, "SULFATE", wp.sulfate_ppm or 0)
        _sub(el, "CHLORIDE", wp.chloride_ppm or 0)
        _sub(el, "SODIUM", wp.sodium_ppm or 0)
        _sub(el, "MAGNESIUM", wp.magnesium_ppm or 0)
        if wp.ph:
            _sub(el, "PH", wp.ph)

    mash = ET.SubElement(recipe, "MASH")
    _sub(mash, "NAME", "Maischplan")
    _sub(mash, "VERSION", 1)
    _sub(mash, "GRAIN_TEMP", 20)
    mash_steps = ET.SubElement(mash, "MASH_STEPS")
    for step in batch.mash_steps:
        if not step.name:
            continue
        el = ET.SubElement(mash_steps, "MASH_STEP")
        _sub(el, "NAME", step.name)
        _sub(el, "VERSION", 1)
        _sub(el, "TYPE", "Temperature")
        _sub(el, "STEP_TEMP", step.temperature_c or 0)
        _sub(el, "STEP_TIME", step.duration_min or 0)

    _sub(recipe, "NOTES", f"Aus HighValley BrewLog: Sud #{batch.batch_number}")

    rough = ET.tostring(recipes, encoding="unicode")
    pretty = minidom.parseString(rough).toprettyxml(indent="  ")
    lines = [line for line in pretty.split("\n") if line.strip()]
    # minidom erzeugt eine eigene Deklaration ohne Encoding-Angabe - durch
    # eine mit "UTF-8" ersetzen, wie von BeerXML-Lesern erwartet.
    lines[0] = '<?xml version="1.0" encoding="UTF-8"?>'
    return "\n".join(lines)


class BeerXmlParseError(ValueError):
    """Datei ist kein gültiges/lesbares BeerXML."""


_HOP_USE_IMPORT = {
    "BOIL": HopAdditionType.kochen,
    "MASH": HopAdditionType.kochen,
    "FIRST WORT": HopAdditionType.kochen,
    "AROMA": HopAdditionType.whirlpool,
    "WHIRLPOOL": HopAdditionType.whirlpool,
}

_STYLE_TYPE_TO_FERMENTATION = {"LAGER": "Untergärig", "ALE": "Obergärig"}


@dataclass
class ParsedGrain:
    name: str
    amount_kg: float = 0


@dataclass
class ParsedMashStep:
    name: str
    temperature_c: float | None = None
    duration_min: float | None = None


@dataclass
class ParsedHop:
    name: str
    alpha_acid_percent: float | None = None
    amount_g: float = 0
    time_min: float | None = None
    addition_type: HopAdditionType = HopAdditionType.kochen


@dataclass
class ParsedDryHop:
    name: str
    amount_g: float = 0


@dataclass
class ParsedYeast:
    name: str
    amount: float | None = None
    unit: str = "g"


@dataclass
class ParsedRecipe:
    name: str = ""
    style: str = ""
    fermentation_type: str = ""
    target_volume_l: float | None = None
    boil_time_min: float | None = None
    target_og_plato: float | None = None
    color_ebc: float | None = None
    grains: list[ParsedGrain] = field(default_factory=list)
    mash_steps: list[ParsedMashStep] = field(default_factory=list)
    hops: list[ParsedHop] = field(default_factory=list)
    dry_hops: list[ParsedDryHop] = field(default_factory=list)
    yeasts: list[ParsedYeast] = field(default_factory=list)


def _children(el: ET.Element, tag: str) -> list[ET.Element]:
    # BeerXML-Tags sind per Spec Grossbuchstaben, manche Exporteure weichen
    # aber leicht ab (z.B. Gross-/Kleinschreibung) - hier bewusst tolerant
    # per Vergleich in Grossbuchstaben statt exaktem Tag-Match.
    return [c for c in el if c.tag.upper() == tag]


def _child_text(el: ET.Element | None, tag: str, default: str = "") -> str:
    if el is None:
        return default
    matches = _children(el, tag)
    if not matches or matches[0].text is None:
        return default
    return matches[0].text.strip()


def _child_float(el: ET.Element | None, tag: str, default: float | None = None) -> float | None:
    raw = _child_text(el, tag, "")
    if not raw:
        return default
    try:
        return float(raw.replace(",", "."))
    except ValueError:
        return default


def parse_recipes_xml(xml_bytes: bytes) -> list[ParsedRecipe]:
    """Liest eine BeerXML-1.0-Datei (Export aus Brewfather, BeerSmith,
    Brewer's Friend, Brewtarget o.ä.) und extrahiert alle enthaltenen
    Rezepte - das Gegenstück zu build_recipe_xml() oben, dieselbe
    Tag-Struktur, nur rückwärts gelesen. Es werden ausschliesslich
    Rezeptdaten übernommen (Schüttung, Hopfengaben, Hefe, Maischplan,
    Zielwerte) - keine <MISC>-Einträge (dafür gibt es beim Import keine
    verlässliche Zuordnung zu Lagerartikeln)."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise BeerXmlParseError(f"Ungültige BeerXML-Datei: {exc}") from exc

    root_tag = root.tag.upper()
    if root_tag == "RECIPE":
        recipe_els = [root]
    else:
        recipe_els = _children(root, "RECIPE")
    if not recipe_els:
        raise BeerXmlParseError("Keine <RECIPE>-Einträge in der Datei gefunden.")

    parsed: list[ParsedRecipe] = []
    for recipe_el in recipe_els:
        style_el = _children(recipe_el, "STYLE")
        style_el = style_el[0] if style_el else None
        style_type = _child_text(style_el, "TYPE").upper()

        og_sg = _child_float(recipe_el, "OG")
        target_og_plato = round(sg_to_plato(og_sg), 1) if og_sg and og_sg > 1 else None
        est_color_srm = _child_float(recipe_el, "EST_COLOR")

        r = ParsedRecipe(
            name=_child_text(recipe_el, "NAME") or "Import",
            style=_child_text(style_el, "NAME"),
            fermentation_type=_STYLE_TYPE_TO_FERMENTATION.get(style_type, ""),
            target_volume_l=_child_float(recipe_el, "BATCH_SIZE"),
            boil_time_min=_child_float(recipe_el, "BOIL_TIME"),
            target_og_plato=target_og_plato,
            color_ebc=round(est_color_srm * 1.97, 1) if est_color_srm else None,
        )

        fermentables_els = _children(recipe_el, "FERMENTABLES")
        if fermentables_els:
            for f_el in _children(fermentables_els[0], "FERMENTABLE"):
                name = _child_text(f_el, "NAME")
                if not name:
                    continue
                r.grains.append(ParsedGrain(name=name, amount_kg=_child_float(f_el, "AMOUNT", 0) or 0))

        mash_els = _children(recipe_el, "MASH")
        if mash_els:
            steps_els = _children(mash_els[0], "MASH_STEPS")
            if steps_els:
                for s_el in _children(steps_els[0], "MASH_STEP"):
                    name = _child_text(s_el, "NAME")
                    if not name:
                        continue
                    r.mash_steps.append(
                        ParsedMashStep(
                            name=name,
                            temperature_c=_child_float(s_el, "STEP_TEMP"),
                            duration_min=_child_float(s_el, "STEP_TIME"),
                        )
                    )

        hops_els = _children(recipe_el, "HOPS")
        if hops_els:
            for h_el in _children(hops_els[0], "HOP"):
                name = _child_text(h_el, "NAME")
                if not name:
                    continue
                use = _child_text(h_el, "USE").upper()
                amount_g = round((_child_float(h_el, "AMOUNT", 0) or 0) * 1000, 1)
                if use == "DRY HOP":
                    r.dry_hops.append(ParsedDryHop(name=name, amount_g=amount_g))
                else:
                    r.hops.append(
                        ParsedHop(
                            name=name,
                            alpha_acid_percent=_child_float(h_el, "ALPHA"),
                            amount_g=amount_g,
                            time_min=_child_float(h_el, "TIME"),
                            addition_type=_HOP_USE_IMPORT.get(use, HopAdditionType.kochen),
                        )
                    )

        yeasts_els = _children(recipe_el, "YEASTS")
        if yeasts_els:
            for y_el in _children(yeasts_els[0], "YEAST"):
                name = _child_text(y_el, "NAME")
                if not name:
                    continue
                is_weight = _child_text(y_el, "AMOUNT_IS_WEIGHT").upper() == "TRUE"
                amount = _child_float(y_el, "AMOUNT", 0) or 0
                r.yeasts.append(ParsedYeast(name=name, amount=round(amount * 1000, 1), unit="g" if is_weight else "ml"))

        parsed.append(r)

    return parsed


def create_batch_from_recipe(session: Session, recipe: ParsedRecipe, batch_number: int) -> Batch:
    """Legt aus einem per BeerXML importierten Rezept einen neuen Sud an.
    Nur Rezeptdaten sind danach gesetzt (siehe parse_recipes_xml) - Brautag,
    Messwerte und Kommentare bleiben leer und werden wie bei jedem anderen
    Sud auf der Bearbeiten-/Detailseite nachgetragen. Zutaten werden nicht
    mit Lagerartikeln verknüpft (keine verlässliche Namenszuordnung beim
    Import), lösen also auch keine Lagerbuchung aus."""
    batch = Batch(
        batch_number=batch_number,
        name=recipe.name,
        style=recipe.style,
        fermentation_type=recipe.fermentation_type,
        target_volume_l=recipe.target_volume_l,
        color_ebc=recipe.color_ebc,
        boil_time_min=recipe.boil_time_min,
        target_og_plato=recipe.target_og_plato,
    )
    session.add(batch)
    session.commit()
    session.refresh(batch)

    for i, g in enumerate(recipe.grains):
        session.add(GrainAddition(batch_id=batch.id, position=i, malt_name=g.name, amount_kg=g.amount_kg))
    for i, s in enumerate(recipe.mash_steps):
        session.add(
            MashStep(batch_id=batch.id, position=i, name=s.name, temperature_c=s.temperature_c, duration_min=s.duration_min)
        )
    for i, h in enumerate(recipe.hops):
        session.add(
            HopAddition(
                batch_id=batch.id,
                position=i,
                hop_name=h.name,
                alpha_acid_percent=h.alpha_acid_percent,
                amount_g=h.amount_g,
                time_min=h.time_min,
                addition_type=h.addition_type,
            )
        )
    for i, dh in enumerate(recipe.dry_hops):
        session.add(DryHopAddition(batch_id=batch.id, position=i, hop_name=dh.name, amount_g=dh.amount_g))
    for i, y in enumerate(recipe.yeasts):
        session.add(YeastAddition(batch_id=batch.id, position=i, yeast_name=y.name, amount=y.amount, unit=y.unit))

    session.commit()
    session.refresh(batch)
    return batch
