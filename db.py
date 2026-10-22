import logging

from pymongo.errors import PyMongoError


async def save_log(collection, doc):
    try:
        await collection.insert_one(doc)
    except PyMongoError as e:
        logging.error(f"寫入問答紀錄失敗：{e}")


async def get_history(collection, limit):
    cursor = collection.find({}, {"_id": 0}).sort("created_at", -1).limit(limit)
    return await cursor.to_list(length=limit)


