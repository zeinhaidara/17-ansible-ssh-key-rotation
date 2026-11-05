"""Pure-python helpers for the ssh_key_rotation role.

Kept free of ansible imports so the merge/diff logic can be unit tested
without a live inventory or connection to a host.
"""


def merge_authorized_keys(current_keys, desired_keys):
    """Return the exact key set that should end up in authorized_keys.

    The central inventory of desired keys is the single source of truth,
    so the result is just the desired set, deduplicated and sorted for a
    stable diff. Any key present on the host but missing from the desired
    set is dropped (this is what makes rotation actually revoke access).
    """
    deduped = sorted(set(k.strip() for k in desired_keys if k.strip()))
    return deduped


def keys_changed(current_keys, desired_keys):
    """True if applying the desired set would change what's on the host."""
    return sorted(set(k.strip() for k in current_keys if k.strip())) != merge_authorized_keys(
        current_keys, desired_keys
    )


def build_inventory_record(host, host_key_fingerprint, rotated_at, authorized_key_count):
    """Build the record written back to the central key inventory."""
    return {
        "host": host,
        "host_key_fingerprint": host_key_fingerprint,
        "rotated_at": rotated_at,
        "authorized_key_count": authorized_key_count,
    }


def fingerprint_changed(old_fingerprint, new_fingerprint):
    """True when a host key rotation actually produced a new fingerprint."""
    return old_fingerprint != new_fingerprint


class FilterModule:
    def filters(self):
        return {
            "merge_authorized_keys": merge_authorized_keys,
            "keys_changed": keys_changed,
            "build_inventory_record": build_inventory_record,
            "fingerprint_changed": fingerprint_changed,
        }
