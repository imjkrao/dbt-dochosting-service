import re

import pytest

from app import keys


def test_version_ids_are_well_formed():
    assert all(keys.VERSION_PATTERN.match(keys.new_version_id()) for _ in range(20))


def test_consecutive_version_ids_sort_chronologically():
    # Regression: at second resolution, ids minted in the same second sorted by
    # their random suffix instead of by time.
    ids = [keys.new_version_id() for _ in range(50)]
    assert ids == sorted(ids)


def test_version_ids_sort_by_time_not_suffix():
    from datetime import datetime, timedelta, timezone

    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    earlier = keys.new_version_id(base)
    later = keys.new_version_id(base + timedelta(microseconds=1))
    assert earlier < later


def test_version_ids_are_unique():
    assert len({keys.new_version_id() for _ in range(200)}) == 200


def test_doc_key_layout():
    version = "20260101T000000000000Z-abcdef12"
    assert (
        keys.doc_key("default", "analytics", version, "index.html")
        == f"orgs/default/projects/analytics/versions/{version}/index.html"
    )


def test_latest_pointer_layout():
    assert keys.latest_pointer_key("default", "analytics") == "orgs/default/projects/analytics/LATEST"


@pytest.mark.parametrize("bad", ["../evil", "a/b", "UPPER", "", "-leading", "with.dot", "x" * 64])
def test_invalid_slugs_are_rejected(bad):
    with pytest.raises(keys.InvalidKeyError):
        keys.validate_slug(bad, field="project")


def test_invalid_version_is_rejected():
    with pytest.raises(keys.InvalidKeyError):
        keys.version_prefix("default", "analytics", "../../etc/passwd")


def test_version_from_key_roundtrips():
    version = keys.new_version_id()
    key = keys.doc_key("default", "proj", version, "manifest.json")
    assert keys.version_from_key(key) == version


def test_version_from_key_returns_none_for_pointer():
    assert keys.version_from_key(keys.latest_pointer_key("default", "proj")) is None


def test_slug_pattern_is_anchored():
    # A regex missing anchors would let traversal through on a partial match.
    assert re.fullmatch(keys.SLUG_PATTERN, "ok-slug_1")
    assert not keys.SLUG_PATTERN.match("bad/slug")
