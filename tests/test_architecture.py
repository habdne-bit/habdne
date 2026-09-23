"""Architecture tests — the structural half of Q6.

Ref: RFC-001 R10.3, R10.3b, R4.5, R14.1, R14.9.

These assert properties of the source tree, not of a running request. They
catch the refactor that quietly reintroduces a bypass, which a behavioural test
only catches if someone remembers to write one for the new path.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "turab"
ROUTES = SRC / "api" / "routes"

FORBIDDEN_IN_ROUTES = ("sqlalchemy", "psycopg", "turab.db", "..db", "...db")
REPOSITORY_HINTS = ("repository", "repositories", "session_factory", "create_engine")


def _imports(path: pathlib.Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            prefix = "." * node.level
            names.append(f"{prefix}{module}")
            names.extend(f"{prefix}{module}.{a.name}" for a in node.names)
    return names


def _route_modules() -> list[pathlib.Path]:
    return [p for p in ROUTES.rglob("*.py") if p.name != "__init__.py"]


def test_there_are_route_modules_to_check():
    """Guard against this whole file silently passing on an empty set."""
    assert _route_modules(), "no route modules found; the checks below would be vacuous"


@pytest.mark.parametrize("module", _route_modules(), ids=lambda p: p.name)
def test_routes_do_not_import_sessions_or_repositories(module):
    """R10.3 (1). A route that cannot reach a session cannot issue an
    unscoped query, whatever the query is called."""
    imported = _imports(module)
    for name in imported:
        low = name.lower()
        assert not any(low.startswith(f) or f in low for f in FORBIDDEN_IN_ROUTES), (
            f"{module.name} imports {name!r}: routes must reach data only through "
            "application services (RFC-001 R10.3)"
        )
        assert not any(h in low for h in REPOSITORY_HINTS), (
            f"{module.name} imports {name!r}, which looks like a repository or a "
            "session factory (RFC-001 R10.3)"
        )


def _sql_literals(path: pathlib.Path) -> list[str]:
    """Every string literal that is actually SQL, excluding docstrings.

    Docstrings are excluded deliberately: a comment explaining WHY a table is
    not consulted is exactly what we want to keep, and a naive text search
    would forbid documenting the rule it enforces.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = node.body[0] if node.body else None
            if (
                isinstance(doc, ast.Expr)
                and isinstance(doc.value, ast.Constant)
                and isinstance(doc.value.value, str)
            ):
                docstrings.add(id(doc.value))
    out = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstrings
        ):
            upper = node.value.upper()
            if "SELECT" in upper or "FROM " in upper or "JOIN " in upper:
                out.append(node.value)
    return out


def test_authorization_sql_never_reads_party_property_relations():
    """R4.5 / decision 1. A domain relationship is not an authorization source.

    Checked across the whole authorization package and against executed SQL, so
    the predicate cannot be reintroduced in any module of it.
    """
    offenders = []
    for path in (SRC / "auth").rglob("*.py"):
        for sql in _sql_literals(path):
            if "party_property_relations" in sql:
                offenders.append(f"{path.name}: {sql.strip()[:60]}")
    assert not offenders, (
        f"{offenders} query party_property_relations: relations are eligibility "
        "to claim, never authority (RFC-001 R4.5)"
    )


def test_the_relations_check_would_catch_a_violation():
    """The check above passes trivially if _sql_literals never finds SQL.

    This asserts the detector actually sees the loaders' SQL, so a future change
    that breaks extraction cannot make the rule silently vacuous.
    """
    sql = _sql_literals(SRC / "auth" / "loaders.py")
    assert sql, "no SQL extracted from loaders.py; the relations check is vacuous"
    assert any("record_claim_events" in s for s in sql), (
        "expected the claim-authority SQL to be visible to the detector"
    )


def test_no_loader_accepts_an_id_without_a_subject():
    """R10.3 (2). There must be no `get_by_id(id)` shaped loader.

    A loader whose signature omits the subject is the bypass these loaders
    exist to prevent.
    """
    loaders = SRC / "auth" / "loaders.py"
    tree = ast.parse(loaders.read_text(encoding="utf-8"))
    checked = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name.startswith("load_"):
            args = [a.arg for a in node.args.args]
            assert "subject" in args, (
                f"{node.name} takes {args}: every loader must require a subject"
            )
            checked += 1
    assert checked >= 6, f"expected the loader set to be checked, saw {checked}"


def test_routes_reach_data_only_through_the_access_service():
    """R10.3 (2). Routes import the service, never a loader directly."""
    for module in _route_modules():
        imported = " ".join(_imports(module))
        assert "loaders.load_" not in imported, (
            f"{module.name} imports a loader directly; go through AccessService "
            "so the audit in RFC-001 R6.3 cannot be skipped at a call site"
        )


def test_nothing_writes_to_the_frozen_contract():
    """R14.1. The generated OpenAPI is checked against the contract, never
    written over it."""
    offenders = []
    for path in SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "openapi_v0.2.3.yaml" in text and (
            "write_text" in text or "open(" in text and '"w"' in text
        ):
            offenders.append(path.name)
    assert not offenders, f"{offenders} may write to the frozen contract"


# --- command routes must carry an object check ----------------------------
#
# The read paths get theirs from the scoped loaders, which cannot return a row
# the caller may not see. A command has no loader, so the check is an explicit
# call — and an explicit call is exactly what gets forgotten. It was: Slice 1
# first shipped PATCH /parties, phone attachment and consent granting with the
# role gate and no object gate, which let a customer act on any party id.

_SCOPE_GUARDS = (
    "authorize_party_scope",
    "authorize_request_scope",
    # Slice 3. R4.1 evaluated by REUSING `load_property`, the loader the read
    # path uses, so one authority rule has one implementation.
    "authorize_property_scope",
    # Slice 3, step 2. RFC-001 §4.6 evaluated by REUSING `load_offer`.
    "authorize_offer_scope",
    "authorize_staff_only",
)

#: Commands whose object rule lives elsewhere, each with its reason. A route
#: may only be here deliberately; the test below fails for anything else.
_GUARD_EXEMPT = {
    # Claiming is how a customer ACQUIRES authority, so an ownership check
    # would make it unusable. Its object rule is INV-1 in services/claims.py.
    "claim_record",
    # Revocation checks ownership through the scoped CONSENT_GRANT loader.
    "revoke_consent",
    # Slice 3. Creating a PROPERTY has no object to own and no party to scope
    # to: `properties` has no `party_id` column and `PropertyCreate` carries no
    # party field, so authority over the new record comes from
    # `created_by_account_id` alone (R4.1) — it is CREATED by this call, not
    # checked by it.
    #
    # Note what is deliberately NOT done here instead. Scoping it to
    # `party_property_relations` would make a relation an authorization input
    # (forbidden, R4.5) and would require inferring a relation from an act of
    # creation (forbidden until the relations contract exists, G3-6). Refusing
    # a customer whose account has no party would be inventing a rule: property
    # authority is account-scoped (R4.2), so a party-less account creating and
    # owning a property is coherent.
    #
    # The route still carries the role gate, and `postProperties` is exercised
    # against the RFC-001 scenarios in the Slice 3 authorization tests.
    "create_property",
}


def _command_route_functions(module: pathlib.Path):
    """Route handlers that take a CommandService, i.e. that mutate."""
    tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        takes_command = any(
            isinstance(a.annotation, ast.Name) and a.annotation.id == "Command"
            for a in node.args.args
            if a.annotation is not None
        )
        if takes_command:
            yield node


def test_there_are_command_routes_to_check():
    found = [n.name for m in _route_modules() for n in _command_route_functions(m)]
    assert found, "no command routes found; the check below would be vacuous"


@pytest.mark.parametrize("module", _route_modules(), ids=lambda p: p.name)
def test_every_command_route_performs_an_object_check(module):
    """A mutating route must call a scope guard, or be a named exemption."""
    for node in _command_route_functions(module):
        if node.name in _GUARD_EXEMPT:
            continue
        called = {
            n.func.attr
            for n in ast.walk(node)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        }
        assert called & set(_SCOPE_GUARDS), (
            f"{module.name}:{node.name} mutates but performs no object check. "
            f"Call one of {_SCOPE_GUARDS}, or add it to _GUARD_EXEMPT with a "
            "reason (RFC-001 §4)."
        )


def test_the_guard_check_is_not_vacuous():
    """Every exemption must name a real route, or the list is rotting."""
    names = {n.name for m in _route_modules() for n in _command_route_functions(m)}
    stale = _GUARD_EXEMPT - names
    assert not stale, f"_GUARD_EXEMPT names routes that no longer exist: {stale}"
