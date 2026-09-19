"""Role assignment.

Ref: RFC-001 R2.1; implementation invariant INV-2.

INV-2 has two halves: reject the invalid combination at assignment time (here),
and fail closed for separation-sensitive actions when it is nonetheless found in
existing data (the policy layer). Both are needed — the database permits the
combination, since `user_account_roles` is keyed `(account_id, role)`, so the
service is the only thing preventing it, and data predating the service exists.
"""
from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..auth.roles import Role, invalid_role_combination


class InvalidRoleCombination(Exception):
    """INV-2. The grant would create a prohibited combination."""

    def __init__(self, account_id: uuid.UUID, offending: frozenset[Role]) -> None:
        self.account_id = account_id
        self.offending = offending
        names = "+".join(sorted(r.value for r in offending))
        super().__init__(
            f"account {account_id} would hold {names}, which collapses the "
            "maker-checker separation; the grant is rejected"
        )


def current_roles(session: Session, account_id: uuid.UUID) -> frozenset[Role]:
    rows = session.execute(
        text(
            "SELECT role::text FROM turab.user_account_roles WHERE account_id = :a"
        ),
        {"a": account_id},
    ).scalars().all()
    return frozenset(Role(r) for r in rows)


def grant_role(session: Session, account_id: uuid.UUID, role: Role) -> frozenset[Role]:
    """Grant a role, refusing combinations that break separation of duties."""
    resulting = current_roles(session, account_id) | {role}
    offending = invalid_role_combination(resulting)
    if offending:
        raise InvalidRoleCombination(account_id, offending)

    session.execute(
        text(
            """
            INSERT INTO turab.user_account_roles (account_id, role)
            VALUES (:a, :r)
            ON CONFLICT (account_id, role) DO NOTHING
            """
        ),
        {"a": account_id, "r": role.value},
    )
    return resulting


def find_role_anomalies(session: Session) -> list[tuple[uuid.UUID, frozenset[Role]]]:
    """Every existing account holding an invalid combination.

    Run as a test and available operationally: INV-2 requires the anomaly to be
    detectable in data that predates the guard, not only blocked going forward.
    """
    rows = session.execute(
        text(
            """
            SELECT account_id,
                   ARRAY_AGG(role::text ORDER BY role::text) AS roles
              FROM turab.user_account_roles
             GROUP BY account_id
            """
        )
    ).mappings().all()
    found: list[tuple[uuid.UUID, frozenset[Role]]] = []
    for row in rows:
        roles = frozenset(Role(r) for r in row["roles"])
        offending = invalid_role_combination(roles)
        if offending:
            found.append((row["account_id"], offending))
    return found
