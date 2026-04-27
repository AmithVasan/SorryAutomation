import os
import logging
from pymongo import MongoClient

# -------------------------------
# CONFIG
# -------------------------------
MONGO_URI = os.environ.get("MONGO_URI")
DB_NAME = "sorry_users"
COLLECTION_NAME = "users"

# -------------------------------
# SHARED CLIENT
# -------------------------------
_client = None

def get_client():
    global _client
    if _client is None:
        if not MONGO_URI:
            raise ValueError("❌ MONGO_URI environment variable not set")
        _client = MongoClient(MONGO_URI)
        logging.info("✅ MongoDB client created")
    return _client


def close_client():
    global _client
    if _client is not None:
        _client.close()
        _client = None
        logging.info("🔌 MongoDB client closed")


# -------------------------------
# BOOST PLAYER LEVEL
# -------------------------------
def boost_player_level(player_id):
    if not player_id:
        logging.warning("⚠️ boost_player_level called with empty player_id")
        return False

    try:
        db = get_client()[DB_NAME]
        result = db[COLLECTION_NAME].update_one(
            {"info.gameCode": player_id},
            {"$set": {"pipPrgrsn.lvl": 50}}
        )

        if result.modified_count > 0:
            logging.info(f"🚀 Player {player_id} boosted to level 50")
        elif result.matched_count > 0:
            logging.info(f"✅ Player {player_id} already at level 50 — no update needed")
        else:
            logging.warning(f"⚠️ Player {player_id} not found in DB — check gameCode")
            return False

    except Exception as e:
        logging.error(f"❌ Mongo error in boost_player_level: {e}")
        return False


# -------------------------------
# GET USER WALLET
# -------------------------------
def get_user_wallet(player_id):
    if not player_id:
        logging.warning("⚠️ get_user_wallet called with empty player_id")
        return {}

    try:
        db = get_client()[DB_NAME]
        user = db[COLLECTION_NAME].find_one({"info.gameCode": player_id})

        if not user:
            logging.warning(f"⚠️ No user found for player_id: {player_id}")
            return {}

        wallet = user.get("wallet", {})
        logging.info(f"💰 Wallet fetched for {player_id}: {wallet}")
        return wallet

    except Exception as e:
        logging.error(f"❌ Mongo error in get_user_wallet: {e}")
        return {}


# -------------------------------
# GET USER SNAPSHOT (OPTIONAL)
# -------------------------------
def get_user_from_db(player_id):
    """
    Returns the full user document.
    Useful for cross-checking UI state against DB.
    """
    if not player_id:
        return None

    try:
        db = get_client()[DB_NAME]
        return db[COLLECTION_NAME].find_one({"info.gameCode": player_id})

    except Exception as e:
        logging.error(f"❌ Mongo error in get_user_from_db: {e}")
        return None