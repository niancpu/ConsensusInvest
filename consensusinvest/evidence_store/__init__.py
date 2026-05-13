"""Evidence Store internal client boundary."""

from consensusinvest.evidence_store.client import (
    EvidenceStore,
    EvidenceStoreClient,
    FakeEvidenceStoreClient,
    InMemoryEvidenceStoreClient,
)
from consensusinvest.evidence_store.models import (
    EvidenceDetail,
    EvidenceItem,
    EvidencePage,
    EvidenceQuery,
    EvidenceReference,
    EvidenceReferenceBatch,
    EvidenceReferenceQuery,
    EvidenceReferenceResult,
    EvidenceStructure,
    EvidenceStructureDraft,
    IngestRejectedItem,
    IngestResult,
    MarketSnapshot,
    MarketSnapshotDraft,
    MarketSnapshotPage,
    MarketSnapshotQuery,
    RawItem,
)
from consensusinvest.evidence_store.sqlite import SQLiteEvidenceStoreClient

__all__ = [
    "EvidenceDetail",
    "EvidenceItem",
    "EvidencePage",
    "EvidenceQuery",
    "EvidenceReference",
    "EvidenceReferenceBatch",
    "EvidenceReferenceQuery",
    "EvidenceReferenceResult",
    "EvidenceStore",
    "EvidenceStoreClient",
    "EvidenceStructure",
    "EvidenceStructureDraft",
    "FakeEvidenceStoreClient",
    "InMemoryEvidenceStoreClient",
    "IngestRejectedItem",
    "IngestResult",
    "MarketSnapshot",
    "MarketSnapshotDraft",
    "MarketSnapshotPage",
    "MarketSnapshotQuery",
    "RawItem",
    "SQLiteEvidenceStoreClient",
]
