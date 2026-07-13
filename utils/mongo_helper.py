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
# BOOST PLAYER LEVEL (ENHANCED LOGGING ONLY)
# -------------------------------
def boost_player_level(
    player_id,
    level=50,
    gold=5000,
    gems=1050,
    hammer=30000,
    name="NOOB"
):
    if not player_id:
        logging.warning("⚠️ boost_player_level called with empty player_id")
        return False

    try:
        db = get_client()[DB_NAME]
        collection = db[COLLECTION_NAME]

        # -------------------------------
        # FETCH CURRENT STATE (for logging)
        # -------------------------------
        user = collection.find_one({"info.gameCode": player_id})

        if user:
            old_level = user.get("pipPrgrsn", {}).get("lvl", 0)
            old_name = user.get("info", {}).get("name", "UNKNOWN")
            old_gold = user.get("wallet", {}).get("gold", 0)
            old_gems = user.get("wallet", {}).get("gems", 0)
            old_hammer = user.get("wallet", {}).get("pips", 0)
        else:
            old_level = 0
            old_name = "UNKNOWN"
            old_gold = 0
            old_gems = 0
            old_hammer = 0

        update_fields = {
            "pipPrgrsn.lvl": level,
            "info.name": name,
            "wallet.gold": gold,
            "wallet.gems": gems,
            "wallet.pips": hammer
        }

        result = collection.update_one(
            {"info.gameCode": player_id},
            {"$set": update_fields}
        )

        # -------------------------------
        # ENHANCED LOGGING
        # -------------------------------
        if result.modified_count > 0:
            logging.info("🚀 PLAYER BOOST SUMMARY")
            logging.info(f"   🆔 Player      : {player_id}")

            logging.info(f"   👤 Name        : {old_name} → {name}")
            logging.info(f"   📈 Level       : {old_level} → {level}")

            logging.info(f"   🟡 Gold        : {old_gold} → {gold} (+{gold - old_gold})")
            logging.info(f"   💎 Gems        : {old_gems} → {gems} (+{gems - old_gems})")
            logging.info(f"   🔨 Hammer      : {old_hammer} → {hammer} (+{hammer - old_hammer})")

        elif result.matched_count > 0:
            logging.info(f"✅ Player {player_id} already boosted — no update needed")
        else:
            logging.warning(f"⚠️ Player {player_id} not found in DB — check gameCode")
            return False

        return True

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
# BEACH BUDDIES — TOP UP EVENT AMMO
# -------------------------------
def set_beach_buddies_ammo(player_id, ammo=3000):
    """
    Set the Beach Buddies (CoOp event) available ammo for a player.

    Writes bbData.ammAvail so the event has enough spins to build every
    castle.  Call this BEFORE opening Beach Buddies from the lobby.

    Returns True on success, False otherwise.
    """
    if not player_id:
        logging.warning("⚠️ set_beach_buddies_ammo called with empty player_id")
        return False

    try:
        db = get_client()[DB_NAME]
        collection = db[COLLECTION_NAME]

        user = collection.find_one({"info.gameCode": player_id})
        old_ammo = (
            user.get("bbData", {}).get("ammAvail", 0) if user else 0
        )

        result = collection.update_one(
            {"info.gameCode": player_id},
            {"$set": {"bbData.ammAvail": ammo}},
        )

        if result.matched_count == 0:
            logging.warning(f"⚠️ Player {player_id} not found — cannot set BB ammo")
            return False

        logging.info(
            f"🏖️ Beach Buddies ammo set → bbData.ammAvail: {old_ammo} → {ammo} "
            f"(player {player_id})"
        )
        return True

    except Exception as e:
        logging.error(f"❌ Mongo error in set_beach_buddies_ammo: {e}")
        return False


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
    
# -------------------------------
# UNLOCK SEASON PASS
# -------------------------------
def unlock_season_pass(player_id, points=30000):

    if not player_id:
        logging.warning(
            "⚠️ unlock_season_pass called with empty player_id"
        )
        return False

    try:

        db = get_client()[DB_NAME]
        collection = db[COLLECTION_NAME]

        result = collection.update_one(
            {"info.gameCode": player_id},
            {
                "$set": {
                    "seasonPass.points": points
                }
            }
        )

        if result.modified_count > 0:

            logging.info(
                f"✅ Season Pass points updated → {points}"
            )

        elif result.matched_count > 0:

            logging.info(
                "ℹ️ Season Pass already updated"
            )

        else:

            logging.warning(
                f"⚠️ Player {player_id} not found"
            )

            return False

        return True

    except Exception as e:

        logging.error(
            f"❌ Mongo error in unlock_season_pass: {e}"
        )

        return False