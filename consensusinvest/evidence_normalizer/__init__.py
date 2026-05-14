"""Evidence Normalizer public exports."""

from consensusinvest.evidence_normalizer.models import (
    EvidenceItemDraft,
    EvidenceNormalizationResult,
    NormalizedEvidenceDraft,
    NormalizedSearchResult,
    RawItemDraft,
)
from consensusinvest.evidence_normalizer.service import EvidenceNormalizer

_default_normalizer = EvidenceNormalizer()


def normalize_search_result_package(envelope, package):
    return _default_normalizer.normalize_search_result_package(envelope, package)


__all__ = [
    "EvidenceItemDraft",
    "EvidenceNormalizationResult",
    "EvidenceNormalizer",
    "NormalizedEvidenceDraft",
    "NormalizedSearchResult",
    "RawItemDraft",
    "normalize_search_result_package",
]
