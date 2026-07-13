import logging
from pymongo import MongoClient


def boost_player(
    player_id,
    level=50,
    gold=500000,
    gems=25000,
    hammer=25000,
    name="NOOB"
):
    logging.info("🧠 Connecting to MongoDB...")

    client = MongoClient("YOUR_CONNECTION_STRING")
    db = client["sorry_users"]
    collection = db["users"]

    update_fields = {
        "pipPrgrsn.lvl": level,
        "info.name": name
    }

    # Optional fields (only applied if passed)
    if gold is not None:
        update_fields["wallet.gold"] = gold

    if gems is not None:
        update_fields["wallet.gems"] = gems

    if hammer is not None:
        update_fields["wallet.pips"] = hammer  

    logging.info(f"🔍 Boosting player {player_id}")

    result = collection.update_one(
        {"info.gameCode": player_id},
        {"$set": update_fields}
    )

    if result.modified_count > 0:
        logging.info("✅ Player boosted successfully")
    else:
        logging.warning("⚠️ No document updated (check gameCode)")