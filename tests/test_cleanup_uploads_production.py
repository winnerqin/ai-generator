from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from scripts.cleanup_uploads_production import (
    OSSVerifier,
    RemoteReference,
    _build_remote_index,
    _identity_from_path,
    _normalize_local_reference,
    _should_scan_column,
    decide_file,
)


class FakeVerifier:
    def __init__(self, responses):
        self.responses = responses

    def head(self, object_key):
        return self.responses[object_key]


class FakeBucket:
    def head_object(self, object_key):
        return SimpleNamespace(content_length=len(object_key))


def _old_file(tmp_path: Path, relative: str, content: bytes = b"payload") -> tuple[Path, Path]:
    uploads = tmp_path / "uploads"
    path = uploads / relative
    path.parent.mkdir(parents=True)
    path.write_bytes(content)
    old_timestamp = (datetime.now() - timedelta(days=10)).timestamp()
    path.touch()
    import os

    os.utime(path, (old_timestamp, old_timestamp))
    return uploads.resolve(), path


def test_normalize_local_reference_handles_public_and_absolute_paths(tmp_path):
    uploads = (tmp_path / "uploads").resolve()
    expected = "user_1/project_2/media_video/example.mp4"

    assert (
        _normalize_local_reference(f"https://example.com/uploads/{expected}", uploads) == expected
    )
    assert _normalize_local_reference(str(uploads / expected), uploads) == expected


def test_identity_matches_local_and_oss_paths():
    local = _identity_from_path("user_4/project_1/media_video/video.mp4")
    remote = _identity_from_path("video_generator/user_4/project_1/video.mp4")
    assert local == remote == ("user_4", "project_1", "video.mp4")


def test_database_column_filter_skips_large_payload_and_audit_fields():
    assert _should_scan_column("video_url", "varchar")
    assert _should_scan_column("reference_urls_json", "json")
    assert _should_scan_column("input_reference_url", "text")
    assert not _should_scan_column("input_payload_json", "json")
    assert not _should_scan_column("raw_response_json", "json")
    assert not _should_scan_column("result_json", "json")


def test_oss_prefetch_populates_cache_concurrently():
    verifier = OSSVerifier.__new__(OSSVerifier)
    verifier.bucket = FakeBucket()
    verifier.cache = {}

    verifier.prefetch(["one", "two", "one"], workers=2, progress_every=1)

    assert verifier.cache == {"one": ("ok", 3), "two": ("ok", 3)}


def test_decide_file_keeps_database_referenced_local_file(tmp_path):
    relative = "user_1/project_1/media_video/example.mp4"
    uploads, path = _old_file(tmp_path, relative)

    decision = decide_file(
        path,
        uploads,
        datetime.now() - timedelta(days=7),
        {relative: {"video_library.url"}},
        {},
        FakeVerifier({}),
    )

    assert decision.action == "KEEP"
    assert decision.reason == "database_references_local_file"


def test_decide_file_marks_only_size_matched_oss_copy_as_eligible(tmp_path):
    relative = "user_1/project_1/media_video/example.mp4"
    uploads, path = _old_file(tmp_path, relative)
    key = "video_generator/user_1/project_1/example.mp4"
    reference = RemoteReference(
        f"https://bucket.oss-cn-test.aliyuncs.com/{key}",
        key,
        "video_library",
        "url",
    )

    decision = decide_file(
        path,
        uploads,
        datetime.now() - timedelta(days=7),
        {},
        _build_remote_index([reference]),
        FakeVerifier({key: ("ok", path.stat().st_size)}),
    )

    assert decision.action == "ELIGIBLE"
    assert decision.reason == "database_uses_verified_oss_copy"
    assert decision.oss_object_key == key


def test_decide_file_requires_matching_oss_size(tmp_path):
    relative = "user_1/project_1/media_video/example.mp4"
    uploads, path = _old_file(tmp_path, relative)
    key = "video_generator/user_1/project_1/example.mp4"
    reference = RemoteReference("https://bucket.example.com/" + key, key, "video_library", "url")

    decision = decide_file(
        path,
        uploads,
        datetime.now() - timedelta(days=7),
        {},
        _build_remote_index([reference]),
        FakeVerifier({key: ("ok", path.stat().st_size + 1)}),
    )

    assert decision.action == "REVIEW"
    assert decision.reason.startswith("oss_missing_unreachable_or_size_mismatch")
