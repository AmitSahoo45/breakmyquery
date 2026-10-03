from contextlib import closing
from copy import deepcopy
import random

from bmq.db import build_db, dump_dataset
from bmq.fuzz import generate


POOLS = {
    "customers.name": ["Asha", "Ravi", "Ravi"],
    "customers.city": ["Pune", None],
    "products.name": ["Pen", "Bag"],
    "products.category": ["Books", None],
    "products.price": [0, 100, 100],
    "orders.order_date": ["2026-09-01 00:00", "2026-09-30 18:45"],
    "orders.status": ["paid", "cancelled"],
    "order_items.quantity": [1, 1, 2],
    "_row_counts": {"customers": [1, 5], "products": [1, 4], "orders": [0, 6], "order_items": [0, 6]},
}


def test_generator_is_reproducible_and_produces_valid_foreign_keys():
    left, right = random.Random(42), random.Random(42)
    seen = set()
    for _ in range(30):
        data = generate(left, POOLS)
        assert data == generate(right, POOLS)
        with closing(build_db(data)) as conn:
            assert dump_dataset(conn) == data
        for table, rows in data.items():
            assert [row[0] for row in rows] == list(range(1, len(rows) + 1))
            low, high = POOLS["_row_counts"][table]
            assert low <= len(rows) <= high
        seen.update(row[2] for row in data["customers"])
    assert seen == {"Pune", None}


def test_missing_customer_parents_skip_orders_and_items():
    pools = deepcopy(POOLS)
    pools["_row_counts"].update(customers=[0, 0], orders=[6, 6], order_items=[6, 6])
    data = generate(random.Random(42), pools)
    assert data["customers"] == []
    assert data["orders"] == []
    assert data["order_items"] == []


def test_missing_product_parents_skip_items_but_keep_orders():
    pools = deepcopy(POOLS)
    pools["_row_counts"].update(products=[0, 0], orders=[3, 3], order_items=[6, 6])
    data = generate(random.Random(42), pools)
    assert data["products"] == []
    assert len(data["orders"]) == 3
    assert data["order_items"] == []
