from __future__ import annotations

import pytest

from common.text_normalization import (
    canonical_business_text,
    normalize_french_business_text,
)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (
            "Direction Financiére",
            "Direction Financière",
        ),
        (
            "Génération automatique de la couverture de stock relatif "
            "à chaque simulation",
            "Génération automatique de la couverture de stock relative "
            "à chaque simulation",
        ),
        (
            "Détermination des quantités par article par code besoin "
            "(par poste) / spécialité, etc.",
            "Les quantités sont déterminées par article, selon le code "
            "besoin (par poste) ou la spécialité.",
        ),
        (
            "Le SI doit tenir compte des critères suivants : Les "
            "prévisions de vente, niveau de stock actuel.",
            "Le SI doit tenir compte des critères suivants : les "
            "prévisions de vente et le niveau de stock actuel.",
        ),
        (
            "hospitalier, Officinal, vaccin",
            "hospitalier, officinal, vaccin",
        ),
    ],
)
def test_normalizes_display_text_globally(
    source: str,
    expected: str,
) -> None:
    assert normalize_french_business_text(source) == expected


def test_normalization_is_idempotent() -> None:
    source = (
        "Les quantités sont déterminées par article, selon le code "
        "besoin (par poste) ou la spécialité."
    )

    once = normalize_french_business_text(source)
    twice = normalize_french_business_text(once)

    assert twice == once


def test_raw_and_corrected_names_are_equivalent() -> None:
    raw = (
        "Génération automatique de la couverture "
        "de stock relatif à chaque simulation "
        "(Autonomie)"
    )
    corrected = (
        "Génération automatique de la couverture "
        "de stock relative à chaque simulation "
        "(Autonomie)"
    )

    assert canonical_business_text(raw) == canonical_business_text(
        corrected
    )


def test_real_operation_name_difference_is_preserved() -> None:
    first = "Générer la couverture de stock"
    second = "Supprimer la simulation"

    assert canonical_business_text(first) != canonical_business_text(
        second
    )


def test_shared_normalization_is_idempotent() -> None:
    source = (
        "Direction Financiére réalise une analyse "
        "de la couverture de stock relatif."
    )

    once = normalize_french_business_text(source)
    twice = normalize_french_business_text(once)

    assert once == twice
    assert "Direction Financière" in once
    assert "couverture de stock relative" in once
