"""Actor resolution — the first stage of the authorization pipeline.

Ref: RFC-001 §3 (R3.1-R3.3), §4.5a (R4.11a), INV-2.

The Subject is resolved once per request, from the database rather than from
the token, and is immutable thereafter.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.orm import Session

from .roles import Role, invalid_role_combination

#: R4.11a. Claim-derived authority ends when the account stops being usable,
#: and account status is the only lever that ends it in v0.1 (§4.5a). So this
#: is a rule, not a convenience: INVITED, SUSPENDED and DISABLED resolve to no
#: authority at all.
USABLE_ACCOUNT_STATUS = "ACTIVATED"


@dataclass(frozen=True, slots=True)
class Subject:
    """The authenticated actor. Immutable for the lifetime of the request."""

    account_id: uuid.UUID
    party_id: uuid.UUID | None
    roles: frozenset[Role]
    account_status: str
    #: INV-2: set when the account holds an invalid role combination. Carried on
    #: the subject rather than raised, so that non-separation-sensitive work can
    #: still proceed while separation-sensitive actions fail closed.
    role_anomaly: frozenset[Role] | None = field(default=None)

    @property
    def is_usable(self) -> bool:
        return self.account_status == USABLE_ACCOUNT_STATUS

    @property
    def has_party(self) -> bool:
        """R3.1. A null party never matches an owner check.

        Written as an explicit guard because `NULL = NULL` is `NULL` in SQL and
        a careless predicate can invert into an allow.
        """
        return self.party_id is not None

    def has_any_role(self, allowed: frozenset[Role]) -> bool:
        """R2.3. Literal set intersection. No ordering is computed."""
        return bool(self.roles & allowed)


class AccountNotResolvable(Exception):
    """The bearer identifies no account that may act. Surfaces as 401."""


def resolve_subject(session: Session, account_id: uuid.UUID) -> Subject:
    """Load the acting subject from the database.

    R3.2: `party_id`, roles and status are read per request, never taken from
    the token, so a token minted before a party was detached or an account was
    disabled stops conferring access immediately.
    """
    row = session.execute(
        text(
            """
            SELECT a.account_id, a.party_id, a.status::text AS status,
                   COALESCE(
                     ARRAY_AGG(r.role::text) FILTER (WHERE r.role IS NOT NULL),
                     ARRAY[]::text[]
                   ) AS roles
              FROM turab.user_accounts a
              LEFT JOIN turab.user_account_roles r ON r.account_id = a.account_id
             WHERE a.account_id = :account_id
             GROUP BY a.account_id, a.party_id, a.status
            """
        ),
        {"account_id": account_id},
    ).mappings().first()

    if row is None:
        raise AccountNotResolvable(f"no account {account_id}")

    if row["status"] != USABLE_ACCOUNT_STATUS:
        # R4.11a. Not merely "no roles": the account may not act at all.
        raise AccountNotResolvable(f"account {account_id} is {row['status']}")

    roles = frozenset(Role(r) for r in row["roles"])
    return Subject(
        account_id=row["account_id"],
        party_id=row["party_id"],
        roles=roles,
        account_status=row["status"],
        role_anomaly=invalid_role_combination(roles),
    )
