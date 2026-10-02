import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from database.models import AffiliateProduct, db, init_db
from services.catalog_seed import export_seed, sync_catalog_from_seed


def add_product(external_id: str, title: str, price: int) -> None:
    AffiliateProduct.create(
        source="manual",
        external_id=external_id,
        title=title,
        title_norm=title.lower(),
        price=price,
        marketplace="mvideo",
        tracking_link=f"https://example.com/{external_id}",
        updated_at=datetime(2026, 10, 1, 12, 0),
    )


class CatalogSeedTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.seed = Path(self.tmp.name) / "catalog_seed.json.gz"
        init_db(":memory:")

    def tearDown(self) -> None:
        if not db.is_closed():
            db.close()
        self.tmp.cleanup()

    def reopen_empty_db(self) -> None:
        db.close()
        init_db(":memory:")

    def test_empty_server_db_gets_catalog(self) -> None:
        add_product("1", "Колонка JBL Flip 7", 9990)
        add_product("2", "Игровая мышь Razer", 4990)
        self.assertEqual(export_seed(self.seed), 2)

        self.reopen_empty_db()
        self.assertEqual(sync_catalog_from_seed(self.seed), 2)
        product = AffiliateProduct.get(AffiliateProduct.external_id == "1")
        self.assertEqual((product.title, product.price), ("Колонка JBL Flip 7", 9990))
        # Тот же снимок повторно не загружается.
        self.assertIsNone(sync_catalog_from_seed(self.seed))

    def use_db(self, name: str) -> None:
        db.close()
        init_db(str(Path(self.tmp.name) / name))

    def test_new_seed_replaces_catalog(self) -> None:
        self.use_db("local.db")
        add_product("1", "Колонка JBL Flip 7", 9990)
        export_seed(self.seed)
        self.use_db("server.db")
        sync_catalog_from_seed(self.seed)

        self.use_db("local.db")
        AffiliateProduct.delete().execute()
        add_product("3", "Наушники Sony WH-CH720N", 8866)
        export_seed(self.seed)

        self.use_db("server.db")
        self.assertEqual(sync_catalog_from_seed(self.seed), 1)
        self.assertEqual([p.external_id for p in AffiliateProduct.select()], ["3"])

    def test_same_seed_is_identical_file(self) -> None:
        add_product("1", "Колонка JBL Flip 7", 9990)
        export_seed(self.seed)
        first = self.seed.read_bytes()
        export_seed(self.seed)
        self.assertEqual(first, self.seed.read_bytes())


if __name__ == "__main__":
    unittest.main()
