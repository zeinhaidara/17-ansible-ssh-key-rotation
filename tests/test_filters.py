import pathlib
import sys

sys.path.insert(
    0,
    str(pathlib.Path(__file__).resolve().parent.parent / "roles" / "ssh_key_rotation" / "filter_plugins"),
)

from ssh_key_rotation import (  # noqa: E402
    build_inventory_record,
    fingerprint_changed,
    keys_changed,
    merge_authorized_keys,
)


def test_merge_authorized_keys_dedupes_and_sorts():
    current = ["key-b", "key-a", "key-a"]
    desired = ["key-c", "key-a"]
    assert merge_authorized_keys(current, desired) == ["key-a", "key-c"]


def test_merge_authorized_keys_drops_keys_not_in_desired_set():
    current = ["stale-key"]
    desired = ["fresh-key"]
    assert merge_authorized_keys(current, desired) == ["fresh-key"]


def test_merge_authorized_keys_ignores_blank_lines():
    assert merge_authorized_keys([], ["key-a", "", "  "]) == ["key-a"]


def test_keys_changed_true_when_sets_differ():
    assert keys_changed(["old-key"], ["new-key"]) is True


def test_keys_changed_false_when_already_reconciled():
    assert keys_changed(["key-a", "key-b"], ["key-b", "key-a"]) is False


def test_build_inventory_record_shape():
    record = build_inventory_record("web01", "SHA256:abc", "2026-01-01T00:00:00Z", 3)
    assert record == {
        "host": "web01",
        "host_key_fingerprint": "SHA256:abc",
        "rotated_at": "2026-01-01T00:00:00Z",
        "authorized_key_count": 3,
    }


def test_fingerprint_changed_true_on_rotation():
    assert fingerprint_changed("SHA256:old", "SHA256:new") is True


def test_fingerprint_changed_false_when_unchanged():
    assert fingerprint_changed("SHA256:same", "SHA256:same") is False
