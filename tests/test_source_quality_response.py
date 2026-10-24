import uuid

from app.database.models import Source
from app.routers.sources import _to_response, SourceDetail


def source(**values):
    return Source(id=uuid.uuid4(), title="Tài liệu", source_type="file", status="ready",
                  chunk_status="ready", wiki_status="ready", **values)


def test_legacy_source_response_does_not_claim_measured_coverage():
    response = _to_response(source(metadata_={}))
    quality = response.processing_quality
    assert quality["extraction"]["status"] == "unknown"
    assert quality["source_index"]["indexed"] is None
    assert quality["wiki"]["published"] is None
    assert SourceDetail(**response.model_dump()).processing_quality == quality


def test_source_response_uses_whitelisted_quality_not_opaque_metadata():
    response = _to_response(source(metadata_={"private_internal_key": "hidden"}))
    assert "private_internal_key" not in str(response.model_dump())
    assert set(response.processing_quality) >= {"extraction", "source_index", "wiki", "warnings"}
