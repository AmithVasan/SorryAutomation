import logging
from pymongo import MongoClient

def boost_player_level(player_id):
    logging.info("🧠 Connecting to MongoDB...")

    client = MongoClient("YOUR_CONNECTION_STRING")
    db = client["sorry_users"]
    collection = db["users"]

    logging.info(f"🔍 Updating player {player_id} → level 50")

    result = collection.update_one(
        {"info.gameCode": player_id},
        {"$set": {"pipPrgrsn.lvl": 50}}
    )

    if result.modified_count > 0:
        logging.info("✅ Player level boosted successfully")
    else:
        logging.warning("⚠️ No document updated (check gameCode)")