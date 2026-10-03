"""Seed-controlled relational data generation using the shared value pools."""

import random

from bmq.db import TABLES


def generate(rng: random.Random, pools) -> dict[str, list[list]]:
    data: dict[str, list[list]] = {table: [] for table in TABLES}
    counts = {table: rng.randint(*pools["_row_counts"][table]) for table in TABLES}

    def pick(key):
        return rng.choice(pools[key])

    for index in range(1, counts["customers"] + 1):
        data["customers"].append([index, pick("customers.name"), pick("customers.city")])
    for index in range(1, counts["products"] + 1):
        data["products"].append([index, pick("products.name"), pick("products.category"), pick("products.price")])
    if data["customers"]:
        for index in range(1, counts["orders"] + 1):
            data["orders"].append([index, rng.choice(data["customers"])[0], pick("orders.order_date"), pick("orders.status")])
    if data["orders"] and data["products"]:
        for index in range(1, counts["order_items"] + 1):
            data["order_items"].append([index, rng.choice(data["orders"])[0], rng.choice(data["products"])[0], pick("order_items.quantity")])
    return data
