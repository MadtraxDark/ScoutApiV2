"""Deterministic precision-first product matching engine."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from scout_api.modules.matching.identity import (
    ProductIdentity,
    condition_conflict,
    console_soft_model_title_exempt,
    critical_identity_conflict,
    gpu_soft_model_title_exempt,
    looks_like_accessory,
    looks_like_bundle,
    models_compatible,
    token_set_ratio,
    variants_equal,
)
from scout_api.modules.matching.schemas import MatchReason

MatchDecision = Literal["auto_match", "review", "reject"]

AUTO_THRESHOLD = Decimal("0.92")
REVIEW_THRESHOLD = Decimal("0.75")
TITLE_WEIGHT = Decimal("0.35")
BRAND_MODEL_WEIGHT = Decimal("0.45")
TITLE_ONLY_CAP = Decimal("0.74")  # never reaches auto_match alone
# Soft model equality (3≡3i, stripped suffixes) still needs title support.
SOFT_MODEL_TITLE_MIN = 0.75
EXTREME_PRICE_RATIO = Decimal("4.0")


@dataclass(frozen=True)
class MatchScore:
    decision: MatchDecision
    confidence: Decimal
    reasons: tuple[MatchReason, ...]


def _variant_conflict(ref: ProductIdentity, cand: ProductIdentity) -> str | None:
    for key, ref_value in ref.variant_attrs.items():
        cand_value = cand.variant_attrs.get(key)
        if cand_value and not variants_equal(key, ref_value, cand_value):
            return f"variant_{key}_mismatch:{ref_value}!={cand_value}"
    return None


def _brand_compatible(ref: ProductIdentity, cand: ProductIdentity) -> bool:
    if not ref.brand or not cand.brand:
        return True
    return ref.brand == cand.brand or ref.brand in cand.brand or cand.brand in ref.brand


def _price_extreme(ref: ProductIdentity, cand: ProductIdentity) -> bool:
    if ref.price is None or cand.price is None:
        return False
    if ref.price <= 0 or cand.price <= 0:
        return False
    # Only compare same currency.
    if ref.currency and cand.currency and ref.currency != cand.currency:
        return False
    ratio = max(ref.price, cand.price) / min(ref.price, cand.price)
    return ratio >= EXTREME_PRICE_RATIO


class MatchingEngine:
    """Score a candidate listing against a reference product identity."""

    def score(
        self, reference: ProductIdentity, candidate: ProductIdentity
    ) -> MatchScore:
        reasons: list[MatchReason] = []

        conflict = _variant_conflict(reference, candidate)
        if conflict:
            reasons.append(
                MatchReason(code="variant_mismatch", detail=conflict, score=0.0)
            )
            return MatchScore(
                decision="reject",
                confidence=Decimal("0.0000"),
                reasons=tuple(reasons),
            )

        critical = critical_identity_conflict(reference, candidate)
        if critical:
            reasons.append(
                MatchReason(
                    code="critical_conflict",
                    detail=critical,
                    score=0.0,
                )
            )
            return MatchScore(
                decision="reject",
                confidence=Decimal("0.0000"),
                reasons=tuple(reasons),
            )

        if looks_like_accessory(candidate.title, reference_title=reference.title):
            reasons.append(
                MatchReason(
                    code="accessory_reject",
                    detail="candidate_title_looks_like_accessory",
                    score=0.0,
                )
            )
            return MatchScore(
                decision="reject",
                confidence=Decimal("0.0000"),
                reasons=tuple(reasons),
            )

        if looks_like_bundle(candidate.title, reference_title=reference.title):
            reasons.append(
                MatchReason(
                    code="bundle_reject",
                    detail="candidate_title_looks_like_bundle",
                    score=0.0,
                )
            )
            return MatchScore(
                decision="reject",
                confidence=Decimal("0.0000"),
                reasons=tuple(reasons),
            )

        condition = condition_conflict(reference.title, candidate.title)
        if condition:
            reasons.append(
                MatchReason(code="condition_reject", detail=condition, score=0.0)
            )
            return MatchScore(
                decision="reject",
                confidence=Decimal("0.0000"),
                reasons=tuple(reasons),
            )

        # Same store + same product_id → auto
        if (
            reference.store
            and candidate.store
            and reference.store == candidate.store
            and reference.product_id
            and candidate.product_id
            and reference.product_id == candidate.product_id
        ):
            reasons.append(
                MatchReason(
                    code="same_store_product_id",
                    detail="identical_store_local_id",
                    score=1.0,
                )
            )
            return MatchScore(
                decision="auto_match",
                confidence=Decimal("1.0000"),
                reasons=tuple(reasons),
            )

        # GTIN exact (validated) — auto if variants already passed
        if reference.gtin and candidate.gtin and reference.gtin == candidate.gtin:
            reasons.append(
                MatchReason(
                    code="gtin_exact",
                    detail=f"gtin={reference.gtin}",
                    score=1.0,
                )
            )
            if (
                reference.brand
                and candidate.brand
                and not _brand_compatible(reference, candidate)
            ):
                reasons.append(
                    MatchReason(
                        code="gtin_brand_conflict",
                        detail="gtin_match_but_brand_diverges",
                        score=0.5,
                    )
                )
                return MatchScore(
                    decision="review",
                    confidence=Decimal("0.8500"),
                    reasons=tuple(reasons),
                )
            return MatchScore(
                decision="auto_match",
                confidence=Decimal("0.9900"),
                reasons=tuple(reasons),
            )

        # Manufacturer part number exact — strong identifier after GTIN.
        ref_mpns = set(reference.mpn_aliases)
        if reference.mpn:
            ref_mpns.add(reference.mpn)
        cand_mpns = set(candidate.mpn_aliases)
        if candidate.mpn:
            cand_mpns.add(candidate.mpn)
        shared_mpns = ref_mpns & cand_mpns
        if shared_mpns:
            shared = sorted(shared_mpns)[0]
            reasons.append(
                MatchReason(
                    code="mpn_exact",
                    detail=f"mpn={shared}",
                    score=1.0,
                )
            )
            if (
                reference.brand
                and candidate.brand
                and not _brand_compatible(reference, candidate)
            ):
                reasons.append(
                    MatchReason(
                        code="mpn_brand_conflict",
                        detail="mpn_match_but_brand_diverges",
                        score=0.5,
                    )
                )
                return MatchScore(
                    decision="review",
                    confidence=Decimal("0.8500"),
                    reasons=tuple(reasons),
                )
            return MatchScore(
                decision="auto_match",
                confidence=Decimal("0.9800"),
                reasons=tuple(reasons),
            )

        confidence = Decimal("0.0000")
        has_strong_id = False

        if (
            reference.brand
            and candidate.brand
            and _brand_compatible(reference, candidate)
        ):
            reasons.append(
                MatchReason(code="brand_match", detail=reference.brand, score=1.0)
            )
            confidence += Decimal("0.25")
        elif reference.brand and candidate.brand:
            reasons.append(
                MatchReason(
                    code="brand_mismatch",
                    detail=f"{reference.brand}!={candidate.brand}",
                    score=0.0,
                )
            )
            return MatchScore(
                decision="reject",
                confidence=Decimal("0.0000"),
                reasons=tuple(reasons),
            )

        title_sim = token_set_ratio(reference.title, candidate.title)
        model_soft_ok = bool(
            reference.model
            and candidate.model
            and models_compatible(
                reference.model,
                candidate.model,
                left_title=reference.title,
                right_title=candidate.title,
            )
            and reference.brand
            and candidate.brand
            and _brand_compatible(reference, candidate)
        )
        if model_soft_ok and reference.model != candidate.model:
            # Consoles / GPUs: sparse vs marketing titles must not veto family
            # identity when critical edition/VRAM/storage gates already agree.
            if title_sim < SOFT_MODEL_TITLE_MIN and not (
                console_soft_model_title_exempt(reference, candidate)
                or gpu_soft_model_title_exempt(reference, candidate)
            ):
                model_soft_ok = False

        if model_soft_ok:
            reasons.append(
                MatchReason(
                    code="brand_model_exact",
                    detail=f"{reference.brand}:{reference.model}~{candidate.model}",
                    score=1.0,
                )
            )
            confidence += BRAND_MODEL_WEIGHT
            has_strong_id = True
            # Brand+model+compatible variants is high confidence.
            if confidence < AUTO_THRESHOLD:
                confidence = AUTO_THRESHOLD
            if title_sim > 0:
                reasons.append(
                    MatchReason(
                        code="title_similarity",
                        detail=f"token_set_ratio={title_sim:.3f}",
                        score=title_sim,
                    )
                )
            if _price_extreme(reference, candidate):
                reasons.append(
                    MatchReason(
                        code="price_deviation",
                        detail="extreme_price_ratio",
                        score=0.0,
                    )
                )
                return MatchScore(
                    decision="review",
                    confidence=Decimal("0.8800"),
                    reasons=tuple(reasons),
                )
            return MatchScore(
                decision="auto_match",
                confidence=min(confidence, Decimal("0.9700")),
                reasons=tuple(reasons),
            )

        if title_sim > 0:
            reasons.append(
                MatchReason(
                    code="title_similarity",
                    detail=f"token_set_ratio={title_sim:.3f}",
                    score=title_sim,
                )
            )
            confidence += (TITLE_WEIGHT * Decimal(str(round(title_sim, 4)))).quantize(
                Decimal("0.0001")
            )

        # Title alone must never auto-match.
        if not has_strong_id and not (reference.gtin and candidate.gtin):
            confidence = min(confidence, TITLE_ONLY_CAP)

        if _price_extreme(reference, candidate):
            reasons.append(
                MatchReason(
                    code="price_deviation",
                    detail="extreme_price_ratio",
                    score=0.0,
                )
            )
            if confidence >= AUTO_THRESHOLD:
                confidence = REVIEW_THRESHOLD

        confidence = min(confidence, Decimal("1.0000")).quantize(Decimal("0.0001"))

        if has_strong_id and confidence >= AUTO_THRESHOLD:
            decision: MatchDecision = "auto_match"
        elif has_strong_id and confidence >= REVIEW_THRESHOLD:
            decision = "review"
        elif confidence >= AUTO_THRESHOLD and has_strong_id:
            decision = "auto_match"
        elif confidence >= REVIEW_THRESHOLD:
            decision = "review"
        else:
            decision = "reject"

        # Extra safety: without brand+model or GTIN, never auto.
        if decision == "auto_match" and not has_strong_id:
            decision = "review"
            confidence = min(confidence, Decimal("0.8900"))

        return MatchScore(
            decision=decision, confidence=confidence, reasons=tuple(reasons)
        )
