import datetime
from pymongo.mongo_client import MongoClient
from tqdm import tqdm


def get_connection():
    return MongoClient("")


def migrate():
    collection_old = get_connection()["kleineprints_new"]["printess_templates"]
    collection_new = get_connection()["kleineprints"][
        "jep_tools__customer_project"
    ]

    current_date = datetime.datetime.now(datetime.timezone.utc)

    query = {
        "$and": [
            {"$or": [{"deleted": False}, {"deleted": {"$exists": False}}]},
            {"$or": [{"copied": False}, {"copied": {"$exists": False}}]},
            {"available_until": {"$gte": current_date}},
        ]
    }
    total = collection_old.count_documents(query)
    print(f"Insgesamt {total} Templates zu migrieren")

    # find all not deleted templates in old collection
    templates = collection_old.find(query)

    migrated_count = 0
    for template in tqdm(templates, total=total, desc="Migriere Templates"):
        # migrate to new collection
        created_at = template.get("created_at", current_date)
        available_until = template.get(
            "available_until", current_date + datetime.timedelta(days=30)
        )

        new_change = {
            "token": template["save_token"],
            "thumbnail_url": template["thumbnail_url"],
            "variant": {
                "id": template.get("variant_id", ""),
                "name": "",
            },
            "created_at": created_at,
        }

        new_data = {
            "name": "",
            "tool": "old_printess_save",
            "source": "shopify",
            "customer_id": template["customer_id"],
            "product": {
                "id": template.get("product_id", ""),
                "name": template.get("product_name", ""),
                "handle": template.get("product_handle", ""),
            },
            "changes": [new_change],
            "current": new_change,
            "is_deleted": False,
            # "is_copied": template.get("copied", False),
            "created_at": created_at,
            "updated_at": created_at,
            "available_until": available_until,
        }

        # check if already exists
        existing_project = collection_new.find_one(
            {"changes.token": template["save_token"]}
        )
        if existing_project:
            # print("Project already exists")
            continue

        collection_new.insert_one(new_data)
        migrated_count += 1
    print(
        f"Migration abgeschlossen: {migrated_count} von {total} Templates migriert"
    )


migrate()
