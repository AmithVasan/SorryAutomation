import os
import logging
from pymongo import MongoClient

# -------------------------------
# CONFIG
# -------------------------------
MONGO_URI = os.environ.get("MONGO_URI")
DB_NAME = "sorry_users"
COLLECTION_NAME = "users"
# Device↔account map (1:1 by deviceID); links to users via gameCode.
ACCOUNTS_DB = "sorry_accounts"
ACCOUNTS_COLLECTION = "accounts"

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
    hammer=3000,
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
# ACCOUNT BY DEVICE (READ-ONLY)
# -------------------------------
def get_account_by_device(device_id):
    """Given a device id (from DeviceManager.GetDeviceId()), find the account
    tied to it. The device→account link lives in sorry_accounts.accounts (1:1 by
    `deviceID`); name/level come from sorry_users.users via `info.gameCode`.

    Returns a dict:
        {"exists": bool, "device_id": ..., "gameCode": ..., "userID": ...,
         "name": ..., "level": ...}
    Read-only. Never raises.
    """
    if not device_id:
        return {"exists": False, "device_id": device_id}
    try:
        client = get_client()
        acc = client[ACCOUNTS_DB][ACCOUNTS_COLLECTION].find_one({"deviceID": device_id})
        if not acc:
            logging.info(f"👤 No account for device {device_id} — new-user only")
            return {"exists": False, "device_id": device_id}
        gc = acc.get("gameCode")
        user = client[DB_NAME][COLLECTION_NAME].find_one({"info.gameCode": gc}) or {}
        name = (user.get("info") or {}).get("name")
        level = (user.get("pipPrgrsn") or {}).get("lvl")
        logging.info(f"👤 Account for device {device_id}: gameCode={gc} name={name} level={level}")
        return {"exists": True, "device_id": device_id, "gameCode": gc,
                "userID": acc.get("userID"), "name": name, "level": level}
    except Exception as e:
        logging.error(f"❌ Mongo error in get_account_by_device: {e}")
        return {"exists": False, "device_id": device_id, "error": str(e)}


# -------------------------------
# DELETE ACCOUNT BY DEVICE  (for the "New user" flow)
# -------------------------------
def delete_account_by_device(device_id, delete_user_doc=False):
    """Delete the account tied to a device — mirrors the manual 'Delete Document'
    on sorry_accounts.accounts (matched by `deviceID`). BACKS UP the doc to the
    log first so a mistake is recoverable. `delete_user_doc=False` by default to
    match the manual accounts-only delete (the old users doc simply orphans, as
    it does today); pass True to also remove the linked sorry_users.users doc.

    IMPORTANT: after calling this, RELAUNCH the game (force-stop + restart), or
    the still-running client keeps the old account — same discipline as boosting.

    Returns {"deleted": bool, "gameCode": ..., "backup": <doc>}. Never raises.
    """
    if not device_id:
        return {"deleted": False, "reason": "no device_id"}
    try:
        client = get_client()
        acc_col = client[ACCOUNTS_DB][ACCOUNTS_COLLECTION]
        acc = acc_col.find_one({"deviceID": device_id})
        if not acc:
            logging.info(f"🗑️ No account to delete for device {device_id}")
            return {"deleted": False, "reason": "no account"}
        gc = acc.get("gameCode")
        logging.info(f"🗄️ [delete] backup (accounts) before delete: {acc}")
        user_backup = None
        if delete_user_doc and gc:
            user_backup = client[DB_NAME][COLLECTION_NAME].find_one({"info.gameCode": gc})
        acc_col.delete_one({"_id": acc["_id"]})
        logging.info(f"🗑️ [delete] removed sorry_accounts.accounts for device {device_id} (gameCode={gc})")
        if delete_user_doc and gc:
            res = client[DB_NAME][COLLECTION_NAME].delete_one({"info.gameCode": gc})
            logging.info(f"🗑️ [delete] removed users doc gameCode={gc} (n={res.deleted_count})")
        return {"deleted": True, "gameCode": gc, "backup": acc, "user_backup": user_backup}
    except Exception as e:
        logging.error(f"❌ Mongo error in delete_account_by_device: {e}")
        return {"deleted": False, "error": str(e)}


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
# TREASURE ISLAND (Fortune Island) — TOP UP EVENT AMMO
# -------------------------------
def set_treasure_island_ammo(player_id, ammo=900):
    """
    Set the Treasure Island (Fortune Island) available ammo for a player.

    Writes frtnIslndDt.ammCnt so there are enough chest opens to finish the
    event.  (ammCnt sits directly under frtnIslndDt — a sibling of `data`, NOT
    inside it.)  Call this while the game is KILLED, then launch, so the boosted
    value is loaded fresh and not overwritten by the running game.

    Returns True on success, False otherwise.
    """
    if not player_id:
        logging.warning("⚠️ set_treasure_island_ammo called with empty player_id")
        return False

    try:
        db = get_client()[DB_NAME]
        collection = db[COLLECTION_NAME]

        user = collection.find_one({"info.gameCode": player_id})
        old_ammo = (
            user.get("frtnIslndDt", {}).get("ammCnt", 0) if user else 0
        )

        result = collection.update_one(
            {"info.gameCode": player_id},
            {"$set": {"frtnIslndDt.ammCnt": ammo}},
        )

        if result.matched_count == 0:
            logging.warning(f"⚠️ Player {player_id} not found — cannot set TI ammo")
            return False

        logging.info(
            f"🏝️ Treasure Island ammo set → frtnIslndDt.ammCnt: "
            f"{old_ammo} → {ammo} (player {player_id})"
        )
        return True

    except Exception as e:
        logging.error(f"❌ Mongo error in set_treasure_island_ammo: {e}")
        return False


# -------------------------------
# BUMP TO SPIN (BTS) — TOP UP EVENT AMMO
# -------------------------------
def set_bump_to_spin_ammo(player_id, ammo=500):
    """
    Set the Bump To Spin (BTS) available ammo for a player.

    Writes bmpToSpn.ammo so there are enough spins to fill every tier.
    (Field verified against a live doc: `ammo` sits directly under the
    top-level `bmpToSpn` object, alongside `pnts`, `isRylPsActv`,
    `frePsClms`, `rylPsClms`.)  Call this while the game is KILLED, then
    launch, so the boosted value is loaded fresh and not overwritten by the
    running game on shutdown.

    Returns True on success, False otherwise.
    """
    if not player_id:
        logging.warning("⚠️ set_bump_to_spin_ammo called with empty player_id")
        return False

    try:
        db = get_client()[DB_NAME]
        collection = db[COLLECTION_NAME]

        user = collection.find_one({"info.gameCode": player_id})
        old_ammo = (
            user.get("bmpToSpn", {}).get("ammo", 0) if user else 0
        )

        result = collection.update_one(
            {"info.gameCode": player_id},
            {"$set": {"bmpToSpn.ammo": ammo}},
        )

        if result.matched_count == 0:
            logging.warning(f"⚠️ Player {player_id} not found — cannot set BTS ammo")
            return False

        logging.info(
            f"🎡 Bump To Spin ammo set → bmpToSpn.ammo: "
            f"{old_ammo} → {ammo} (player {player_id})"
        )
        return True

    except Exception as e:
        logging.error(f"❌ Mongo error in set_bump_to_spin_ammo: {e}")
        return False


# -------------------------------
# PUZZLE THEATRE (PT) — TOP UP EVENT AMMO
# -------------------------------
def set_puzzle_theatre_ammo(player_id, ammo=5000):
    """
    Set the Puzzle Theatre (Puzzle Event) available ammo for a player.

    Writes puzzleEventData.ammoBalance so there is enough ammo to reveal every
    puzzle piece across all boards.  Call this after closing the event to the
    lobby, then re-open the event so the boosted balance is picked up.

    Returns True on success, False otherwise.
    """
    if not player_id:
        logging.warning("⚠️ set_puzzle_theatre_ammo called with empty player_id")
        return False

    try:
        db = get_client()[DB_NAME]
        collection = db[COLLECTION_NAME]

        user = collection.find_one({"info.gameCode": player_id})
        old_ammo = (
            user.get("puzzleEventData", {}).get("ammoBalance", 0) if user else 0
        )

        result = collection.update_one(
            {"info.gameCode": player_id},
            {"$set": {"puzzleEventData.ammoBalance": ammo}},
        )

        if result.matched_count == 0:
            logging.warning(f"⚠️ Player {player_id} not found — cannot set PT ammo")
            return False

        logging.info(
            f"🎭 Puzzle Theatre ammo set → puzzleEventData.ammoBalance: "
            f"{old_ammo} → {ammo} (player {player_id})"
        )
        return True

    except Exception as e:
        logging.error(f"❌ Mongo error in set_puzzle_theatre_ammo: {e}")
        return False


def get_puzzle_theatre_ammo(player_id):
    """Return puzzleEventData.ammoBalance from the DB (authoritative), or None."""
    doc = get_user_from_db(player_id) or {}
    return (doc.get("puzzleEventData") or {}).get("ammoBalance")


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
