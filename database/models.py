from __future__ import annotations

from datetime import datetime
from peewee import (
    BooleanField,
    CharField,
    DateTimeField,
    ForeignKeyField,
    IntegerField,
    Model,
    SqliteDatabase,
    TextField,
)
from playhouse.migrate import SqliteMigrator, migrate

db = SqliteDatabase(None)


class BaseModel(Model):
    class Meta:
        database = db


class User(BaseModel):
    telegram_id = IntegerField(unique=True)
    username = CharField(null=True)
    intro_seen = BooleanField(default=False)
    created_at = DateTimeField(default=datetime.utcnow)


class RecommendationRequest(BaseModel):
    user = ForeignKeyField(User, backref="requests", on_delete="CASCADE")
    mode = CharField()
    age = IntegerField()
    gender = CharField()
    event = CharField()
    relation = CharField()
    budget = IntegerField()
    hobbies = TextField(default="")
    photos_count = IntegerField(default=0)
    created_at = DateTimeField(default=datetime.utcnow)


class RecommendationItem(BaseModel):
    request = ForeignKeyField(RecommendationRequest, backref="items", on_delete="CASCADE")
    name = CharField()
    reason = TextField()
    keywords_json = TextField()
    price_level = CharField()
    fits_budget = BooleanField(default=True)
    offers_json = TextField(default="[]")
    created_at = DateTimeField(default=datetime.utcnow)


class ItemFeedback(BaseModel):
    """Оценка идеи пользователем: +1 «подходит», -1 «мимо»."""

    item = ForeignKeyField(RecommendationItem, backref="feedback", on_delete="CASCADE")
    telegram_id = IntegerField()
    vote = IntegerField()
    created_at = DateTimeField(default=datetime.utcnow)

    class Meta:
        indexes = ((("item", "telegram_id"), True),)


class Payment(BaseModel):
    user = ForeignKeyField(User, backref="payments", on_delete="CASCADE")
    provider = CharField()
    kind = CharField()
    amount_rub = IntegerField()
    status = CharField(default="created")
    provider_payment_id = CharField(unique=True)
    idempotency_key = CharField(null=True, unique=True)
    created_at = DateTimeField(default=datetime.utcnow)


class Subscription(BaseModel):
    user = ForeignKeyField(User, backref="subscriptions", on_delete="CASCADE")
    is_active = BooleanField(default=False)
    expires_at = DateTimeField(null=True)
    created_at = DateTimeField(default=datetime.utcnow)


class CacheEntry(BaseModel):
    cache_key = CharField(unique=True)
    value_json = TextField()
    expires_at = DateTimeField()
    created_at = DateTimeField(default=datetime.utcnow)


class AppSetting(BaseModel):
    key = CharField(unique=True)
    value = CharField()
    updated_at = DateTimeField(default=datetime.utcnow)


class AffiliateProduct(BaseModel):
    source = CharField(index=True)
    external_id = CharField()
    product_id = CharField(null=True)
    sku = CharField(null=True)
    title = CharField()
    title_norm = CharField(index=True)
    image_url = TextField(null=True)
    price = IntegerField(default=0, index=True)
    category = CharField(null=True, index=True)
    marketplace = CharField(default="unknown", index=True)
    store_title = CharField(null=True)
    external_link = TextField(null=True)
    tracking_link = TextField()
    updated_at = DateTimeField(default=datetime.utcnow, index=True)

    class Meta:
        indexes = ((("source", "external_id"), True),)


class FsmRecord(BaseModel):
    """Шаг анкеты и ответы пользователя: переживают перезапуск бота."""

    key = CharField(unique=True)
    state = CharField(null=True)
    data_json = TextField(default="{}")
    updated_at = DateTimeField(default=datetime.utcnow)


def init_db(path: str) -> None:
    db.init(path)
    db.connect(reuse_if_open=True)
    db.create_tables(
        [
            User,
            RecommendationRequest,
            RecommendationItem,
            Payment,
            Subscription,
            CacheEntry,
            AppSetting,
            AffiliateProduct,
            FsmRecord,
            ItemFeedback,
        ]
    )
    _add_missing_columns()


def _add_missing_columns() -> None:
    """create_tables не трогает существующие таблицы — новые колонки добавляем сами."""
    existing = {column.name for column in db.get_columns(RecommendationItem._meta.table_name)}
    if "offers_json" not in existing:
        migrate(SqliteMigrator(db).add_column(RecommendationItem._meta.table_name, "offers_json", RecommendationItem.offers_json))
