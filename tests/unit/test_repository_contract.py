"""Architecture gates for the user-frozen persistence access contract."""
import ast
import importlib
from pathlib import Path

from sqlalchemy.orm import Session


def test_repository_methods_never_own_transaction_or_session_lifecycle() -> None:
    root = Path(__file__).resolve().parents[2] / "app" / "repositories"
    forbidden = {"commit", "rollback", "close", "begin", "begin_nested", "merge", "delete"}
    for path in root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                assert node.func.attr not in forbidden, f"{path.name}: {node.func.attr}"


def test_repository_construction_and_staging_do_not_connect(monkeypatch) -> None:
    import psycopg
    from app.models import Store, User
    from app.repositories.identity import IdentityRepository, StoreRepository

    def reject(*args, **kwargs):
        raise AssertionError("Unexpected eager DB connection")

    monkeypatch.setattr(psycopg, "connect", reject)
    with Session() as session:
        for name, classes in {
            "catalog": ["CatalogRepository"], "constraints": ["ConstraintsRepository"],
            "decision": ["DecisionRepository"], "forecast": ["ForecastRepository"],
            "identity": ["IdentityRepository", "StoreRepository"], "inventory": ["InventoryRepository"],
            "recipe": ["RecipeRepository"], "sales": ["SalesRepository"], "supplier": ["SupplierRepository"],
        }.items():
            module = importlib.import_module("app.repositories." + name)
            for cls in classes:
                getattr(module, cls)(session)
        IdentityRepository(session).add_user(User(email="fixture@example.test", password_hash="opaque", display_name="Fixture"))
        StoreRepository(session).add_store(Store(name="Fixture"))
        assert len(session.new) == 2
