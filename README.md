# ssh-key-rotation

An Ansible role that rotates SSH host keys and `authorized_keys` across a
fleet, records what it did in a central key inventory file, and optionally
notifies owners over a webhook.

**Scope.** This is a role plus a thin orchestration playbook, not a fleet
management platform. It targets hosts you already manage over SSH with an
existing Ansible inventory. There's no real cloud or ticketing integration:
the "central inventory" is a JSON file on the control node, and "notify
owners" is a single `uri` POST to a configurable webhook URL (disabled by
default). CI validates syntax, lints, unit-tests the pure-python merge/diff
logic, and exercises notification tasks against a loopback HTTP server.
It never connects to the managed fleet. Actually rotating keys against live infrastructure is a manual,
reviewed operation, not something this repo runs unattended.

## Architecture

- `roles/ssh_key_rotation/tasks/host_keys.yml` — fingerprints the existing
  host keys, optionally backs up and removes them, regenerates the
  configured key types with `community.crypto.openssh_keypair`, and reads
  back the new fingerprints.
- `roles/ssh_key_rotation/tasks/authorized_keys.yml` — reads each managed
  user's current `authorized_keys`, reports whether the desired set from
  the central inventory would change anything, then applies it with
  `ansible.posix.authorized_key` using `exclusive: true` — any key not in
  the desired set is removed, which is what makes rotation actually revoke
  access instead of only adding new keys.
- `roles/ssh_key_rotation/tasks/inventory_update.yml` — merges a per-host
  record (host key fingerprints, rotation timestamp, authorized key count)
  into a central JSON inventory file on the control node.
- `roles/ssh_key_rotation/tasks/notify.yml` — POSTs a rotation summary to
  `ssh_key_rotation_notify_url` when `ssh_key_rotation_notify_enabled` is
  true. A failed notification is logged as a warning; it never fails the
  rotation itself.
- `roles/ssh_key_rotation/filter_plugins/ssh_key_rotation.py` — the actual
  merge/diff/record-building logic, kept free of Ansible imports so it can
  be unit tested directly with pytest (see `tests/test_filters.py`).

## Prerequisites

- Ansible core >= 2.15 (`pip install -r requirements.txt`)
- Collections: `ansible-galaxy collection install -r requirements.yml`
  (`ansible.posix`, `community.crypto`, `community.general`)
- SSH access with `become` privileges to the target fleet
- An inventory file listing the fleet (see `inventory/hosts.ini`)

## Usage

```bash
pip install -r requirements.txt
ansible-galaxy collection install -r requirements.yml

# dry run against your real inventory first
ansible-playbook -i inventory/hosts.ini site.yml --check --diff

# apply
ansible-playbook -i inventory/hosts.ini site.yml
```

Configure the managed users and their desired keys in `group_vars/all.yml`
(see the committed example), and point `ssh_key_rotation_inventory_path`
at wherever you want the central rotation record kept.

To enable webhook notifications:

```yaml
ssh_key_rotation_notify_enabled: true
ssh_key_rotation_notify_url: "https://hooks.example.com/ssh-key-rotation"
ssh_key_rotation_owner_email: "ops@example.com"
```

## Example central inventory output

```json
{
  "web01.example.com": {
    "host": "web01.example.com",
    "host_key_fingerprint": "256 SHA256:exampleexampleexampleexampleexampleexample web01 (ED25519)",
    "rotated_at": "2026-01-15T03:00:00Z",
    "authorized_key_count": 2
  }
}
```

## Security considerations

- SSH host-key checking stays enabled. Trust the existing host fingerprints
  before connecting. After rotation, verify replacement fingerprints through
  a trusted channel before updating the control node's `known_hosts`.
- Host keys are rotated by removing the old key and generating a new one
  with `community.crypto.openssh_keypair` — private key material never
  leaves the target host.
- `authorized_key` with `exclusive: true` means a key removed from the
  central inventory is actually revoked on the next run, not just left in
  place alongside new keys.
- Backups of rotated-out host keys are written to
  `/etc/ssh/rotated-keys` with `0600` permissions, root-owned.
- The notification payload contains fingerprints and hostnames, not key
  material or credentials; the webhook URL defaults to a local, inert
  address so nothing is sent anywhere unless explicitly enabled.
- Treat the central inventory JSON file itself as sensitive-ish: it maps
  hostnames to host key fingerprints and authorized key counts, which is
  fleet topology information.

## Idempotency

- Running the role again without `ssh_key_rotation_force_host_key_rotation`
  only fills in missing host key types; it does not generate new ones over
  existing valid keys.
- `authorized_keys` reconciliation is fully idempotent: re-running with an
  unchanged desired key list produces no changes (verified by
  `tests/test_filters.py::test_keys_changed_false_when_already_reconciled`).
- The central inventory merge replaces only the entry for the current host
  each run, so re-running does not duplicate or accumulate records.

## Tests

```bash
pip install -r requirements-test.txt
ansible-galaxy collection install -r requirements.yml
yamllint .
ansible-lint
ansible-playbook site.yml --syntax-check
pytest tests
```

The filter-plugin tests cover the merge logic directly, including the
negative cases: a stale key being dropped, an unchanged set reporting no
change, and blank lines being ignored. There's no mocked-cluster or
mocked-cloud test here — the role only ever talks to hosts in your
Ansible inventory over SSH, which CI does not have, so the playbook
itself is validated by syntax-check and lint rather than a live fleet run.
Notification tests execute the actual task file against a local HTTP server:
success produces no warning, while HTTP 500 and a disconnected response
both produce a warning without failing the playbook.

Two failure paths are untested: `authorized_keys.yml`'s "no authorized_keys
file yet" case and `host_keys.yml`'s "no host key of this type yet" case.
Both now fail loudly on anything *other* than that one expected message
(see the `failed_when` conditions in each file), but exercising the
expected-message path itself would mean standing up a real filesystem/SSH
target with specific files missing - more than this repo's scope covers.
