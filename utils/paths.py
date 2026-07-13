# -----------------------------------------------------------------------
# All AltTester UI paths and device coordinates in one place.
# Update here when the game UI changes — no hunting across test files.
# -----------------------------------------------------------------------

# -----------------------------------------------------------------------
# DEVICE COORDINATES  (x, y as strings for ADB input tap)
# -----------------------------------------------------------------------
DEVICE_COORDS = {
    "real": {
        "ip_field": ("500", "1350"),
        "restart":  ("534", "1519"),
    },
    "emulator": {
        "ip_field": ("1250", "966"),
        "restart":  ("1285", "1116"),
    },
}


# -----------------------------------------------------------------------
# NAVIGATION
# -----------------------------------------------------------------------
HOME_BUTTON  = "/Canvas/uiLayer/btmContent/lobbyBtmContent/lobbyBtmGrp/footerSection/Icons_Layout/Home/HomeIcon"
SHOP_BUTTON  = "/Canvas/uiLayer/btmContent/lobbyBtmContent/lobbyBtmGrp/footerSection/Icons_Layout/Shop/ShopIcon"


# -----------------------------------------------------------------------
# LOGIN
# -----------------------------------------------------------------------
LOGIN_SCREEN      = "/Canvas/midUiLayer/loginScreen"
GUEST_BUTTON      = "/Canvas/midUiLayer/loginScreen/buttonsParent/guestCTA/TouchArea"


# -----------------------------------------------------------------------
# HOME HUD WALLET
# -----------------------------------------------------------------------
HOME_GOLD_TEXT   = "/Canvas/uiLayer/TableManager/layout/viewPort/content/HomeScreen/topSections/commonHUD/root/Container/coinBar/text"
HOME_GEMS_TEXT   = "/Canvas/uiLayer/TableManager/layout/viewPort/content/HomeScreen/topSections/commonHUD/root/Container/gemBar/text"
HOME_HAMMER_TEXT = "/Canvas/uiLayer/TableManager/layout/viewPort/content/HomeScreen/topSections/commonHUD/root/Container/hammerBar/text"


# -----------------------------------------------------------------------
# SHOP HUD WALLET
# -----------------------------------------------------------------------
SHOP_GOLD_TEXT   = "/Canvas/uiLayer/TableManager/layout/viewPort/content/ShopScreenRevamped/root/layout/header/commonHUD/root/Container/coinBar/text"
SHOP_GEMS_TEXT   = "/Canvas/uiLayer/TableManager/layout/viewPort/content/ShopScreenRevamped/root/layout/header/commonHUD/root/Container/gemBar/text"


# -----------------------------------------------------------------------
# PROFILE MODAL
# -----------------------------------------------------------------------
PROFILE_BUTTON   = "/Canvas/uiLayer/TableManager/layout/viewPort/content/HomeScreen/topSections/commonHUD/root/profileSection/profileIcon/ProfileButton"
PROFILE_CLOSE    = "/Canvas/ModalLayer/SelfProfileModal(Clone)/rootMain/closeCTA/touchArea"
PROFILE_NAME     = "/Canvas/ModalLayer/SelfProfileModal(Clone)/rootMain/contentMask/Content/topSection/section-Name/playerName"
PROFILE_COUNTRY  = "/Canvas/ModalLayer/SelfProfileModal(Clone)/rootMain/contentMask/Content/topSection/section-Country/TextStyle_subText_medium_bold/countryNameText"
PROFILE_ID       = "/Canvas/ModalLayer/SelfProfileModal(Clone)/rootMain/contentMask/Content/topSection/selection-ID/proifleIDText/playerIDText"
PROFILE_LEVEL    = "/Canvas/ModalLayer/SelfProfileModal(Clone)/rootMain/contentMask/Content/bottomSection/midSection/cohort_parent/Level-Button/container/progressBar/xpStar/TextStyle_Notifs/level"
PROFILE_XP       = "/Canvas/ModalLayer/SelfProfileModal(Clone)/rootMain/contentMask/Content/bottomSection/midSection/cohort_parent/Level-Button/container/progressBar/Progressbar/TextStyle_Notifs/xpProgress"
PROFILE_PAWN     = "/Canvas/ModalLayer/SelfProfileModal(Clone)/rootMain/contentMask/Content/bottomSection/midSection/cohort_parent/Cosmetics-Button/container/InfoSection/CosmeticNameText/text"


# -----------------------------------------------------------------------
# PURCHASE POPUP
# -----------------------------------------------------------------------
PURCHASE_POPUP   = "/Canvas/ModalLayer/PurchaseNotifModal(Clone)/darkBG"
PURCHASE_FAIL    = "/Canvas/ModalLayer/PurchaseNotifModal(Clone)/rootMain/mask/failed/icon"
PURCHASE_OK      = "/Canvas/ModalLayer/PurchaseNotifModal(Clone)/rootMain/ButtonLayer/Okay Button/TouchArea"


# -----------------------------------------------------------------------
# LEGENDARY PAWN SALE
# -----------------------------------------------------------------------
PAWN_SALE_MODAL          = "/Canvas/ModalLayer/PawnCosmeticSaleMainModal(Clone)/darkbg"
PAWN_SALE_CLOSE          = "/Canvas/ModalLayer/PawnCosmeticSaleMainModal(Clone)/rootMain/CrossButton/touchArea"
PAWN_SALE_BUY            = "/Canvas/ModalLayer/PawnCosmeticSaleMainModal(Clone)/rootMain/CTA/TouchArea"
PAWN_SALE_NAME           = "/Canvas/ModalLayer/PawnCosmeticSaleMainModal(Clone)/rootMain/nameText/text"
PAWN_SALE_SUCCESS_MODAL  = "/Canvas/ModalLayer/PawnCosmeticSalePurchaseSuccessModal(Clone)/root/PawnRewardCard"
PAWN_SALE_EQUIP_BTN      = "/Canvas/ModalLayer/PawnCosmeticSalePurchaseSuccessModal(Clone)/root/PawnRewardCard/root/Equip Button/TouchArea"


# -----------------------------------------------------------------------
# SHOP PACKS
# -----------------------------------------------------------------------
_GOLD_BASE = "/Canvas/uiLayer/TableManager/layout/viewPort/content/ShopScreenRevamped/root/layout/ScrollParent/scrollView/viewport/content/golds/cardContent"
_GEM_BASE  = "/Canvas/uiLayer/TableManager/layout/viewPort/content/ShopScreenRevamped/root/layout/ScrollParent/scrollView/viewport/content/gems/cardContent"

def _pack(base, index):
    """Buy-button path for a shop card (taps to open Google Play console)."""
    slot = "ShopCard(Clone)" if index == 0 else f"ShopCard(Clone)[{index}]"
    return f"{base}/{slot}/SorryButtonType-Currency/TouchArea"

def _val(base, index):
    """Displayed pack value/amount (e.g. '4,000' gold / '50' gems)."""
    slot = "ShopCard(Clone)" if index == 0 else f"ShopCard(Clone)[{index}]"
    return f"{base}/{slot}/countText/actualValue/base"

def _price(base, index):
    """Purchase price / cost shown on the buy button (e.g. '$0.99')."""
    slot = "ShopCard(Clone)" if index == 0 else f"ShopCard(Clone)[{index}]"
    return f"{base}/{slot}/SorryButtonType-Currency/root/textContainer/priceText"

# Each entry: (fallback_name, buy_button_path, value_path, price_path)
#   fallback_name  — used for subset-run filtering and as a log fallback
#   buy_button_path — tap to open Google Play purchase console
#   value_path      — amount of gold/gems in the pack
#   price_path      — purchase cost shown on the card
GOLD_PACKS = [
    ("Gold 4000",  _pack(_GOLD_BASE, 0), _val(_GOLD_BASE, 0), _price(_GOLD_BASE, 0)),
    ("Gold 12.5K", _pack(_GOLD_BASE, 1), _val(_GOLD_BASE, 1), _price(_GOLD_BASE, 1)),
    ("Gold 42K",   _pack(_GOLD_BASE, 2), _val(_GOLD_BASE, 2), _price(_GOLD_BASE, 2)),
    ("Gold 90K",   _pack(_GOLD_BASE, 3), _val(_GOLD_BASE, 3), _price(_GOLD_BASE, 3)),
    ("Gold 250K",  _pack(_GOLD_BASE, 4), _val(_GOLD_BASE, 4), _price(_GOLD_BASE, 4)),
    ("Gold 500K",  _pack(_GOLD_BASE, 5), _val(_GOLD_BASE, 5), _price(_GOLD_BASE, 5)),
]

GEM_PACKS = [
    ("50 Gems",   _pack(_GEM_BASE, 0), _val(_GEM_BASE, 0), _price(_GEM_BASE, 0)),
    ("155 Gems",  _pack(_GEM_BASE, 1), _val(_GEM_BASE, 1), _price(_GEM_BASE, 1)),
    ("540 Gems",  _pack(_GEM_BASE, 2), _val(_GEM_BASE, 2), _price(_GEM_BASE, 2)),
    ("1100 Gems", _pack(_GEM_BASE, 3), _val(_GEM_BASE, 3), _price(_GEM_BASE, 3)),
    ("3000 Gems", _pack(_GEM_BASE, 4), _val(_GEM_BASE, 4), _price(_GEM_BASE, 4)),
    ("6000 Gems", _pack(_GEM_BASE, 5), _val(_GEM_BASE, 5), _price(_GEM_BASE, 5)),
]


# -------------------------------
# BANK
# -------------------------------
HOME_BANK = "/Canvas/uiLayer/TableManager/layout/viewPort/content/HomeScreen/topSections/lobbyWidgetSection/LHS_RHS_Content/IconsLHS/bankWidget/scaleAdjuster/root/Overlay Parent/BankIcon/WidgetIcon/Pivot/lockerParent/lockerClosed"

SHOP_BANK = "/Canvas/uiLayer/TableManager/layout/viewPort/content/ShopScreenRevamped/root/layout/ScrollParent/scrollView/viewport/content/Bank/bg/cardContent/bankShopCard(Clone)/root/Button"

# -------------------------------
# LOOTBOX
# -------------------------------
LOOTBOX_PACKS = [
    ("Common x1", "/Canvas/uiLayer/TableManager/layout/viewPort/content/ShopScreenRevamped/root/layout/ScrollParent/scrollView/viewport/content/lootboxes/bg/cardContent/CosmeticLootboxShopCard(Clone)/SorryButtonType-Currency/TouchArea"),
    ("Common x3", "/Canvas/uiLayer/TableManager/layout/viewPort/content/ShopScreenRevamped/root/layout/ScrollParent/scrollView/viewport/content/lootboxes/bg/cardContent/CosmeticLootboxShopCard(Clone)[1]/SorryButtonType-Currency/TouchArea"),
    ("Legendary x1", "/Canvas/uiLayer/TableManager/layout/viewPort/content/ShopScreenRevamped/root/layout/ScrollParent/scrollView/viewport/content/lootboxes/bg/cardContent/CosmeticLootboxShopCard(Clone)[2]/SorryButtonType-Currency/TouchArea"),
    ("Legendary x3", "/Canvas/uiLayer/TableManager/layout/viewPort/content/ShopScreenRevamped/root/layout/ScrollParent/scrollView/viewport/content/lootboxes/bg/cardContent/CosmeticLootboxShopCard(Clone)[3]/SorryButtonType-Currency/TouchArea"),
]

LOOTBOX_CONFIRM = "/Canvas/ModalLayer/SorryCommonModal(Clone)/rootMain/layout/CTA_Green/TouchArea"
LOOTBOX_AMMO = "/Canvas/ModalLayer/LootboxRewardsModal(Clone)/rootMain/scaleAdjuster/root/header/cosmeticAmmoBarHUD/text"
LOOTBOX_CLAIM = "/Canvas/ModalLayer/LootboxRewardsModal(Clone)/rootMain/scaleAdjuster/root/TapToContinueButton/ctaButton"

# -----------------------------------------------------------------------
# REWARD SUMMARY MODAL
# Appears after claiming all season pass rewards
# -----------------------------------------------------------------------
REWARD_SUMMARY_CTA = "/Canvas/ModalLayer/RewardSummaryModal(Clone)/rootMain/scaleAdjuster/footer/CTA/TouchArea"

# -----------------------------------------------------------------------
# LUCKY CARDS
# -----------------------------------------------------------------------

LUCKY_CARDS_ICON = "/Canvas/uiLayer/TableManager/layout/viewPort/content/HomeScreen/topSections/lobbyWidgetSection/LHS_RHS_Content/IconsRHS/LuckyCardsBtn/scaleAdjuster/root/Overlay Parent/WidgetIcon/Icon Parent/mainIcon"

LUCKY_CARDS_COUNTER = "/Canvas/ModalLayer/LuckyCardsModal(Clone)/rootMain/content/root/deckGrp/notificationCounterNodeRed/TextStyle_bodyText_large/text"

FTUE_MODAL = "/Canvas/ModalLayer/CommonNudgeModal(Clone)"

LUCKY_CARD_TOUCH_AREA = "/Canvas/ModalLayer/LuckyCardsModal(Clone)/rootMain/content/root/TouchArea"

SEND_GET_CARDS_DRAWER = "/Canvas/ModalLayer/LuckyCardsModal(Clone)/rootMain/invitometer/SendCTAHolder/sendCTA/TouchArea"

DRAWER_CLOSE = "/Canvas/ModalLayer/LuckyCardsSlidingPopup(Clone)/rootMain/scaleadjuster/closeCTA/touchArea"

LUCKY_CARDS_CLOSE = "/Canvas/ModalLayer/LuckyCardsModal(Clone)/rootMain/closeCTAGrp/closeCTA/touchArea"

# -----------------------------------------------------------------------
# SEASON PASS
# -----------------------------------------------------------------------

SEASON_PASS_ICON  = "/Canvas/uiLayer/TableManager/layout/viewPort/content/HomeScreen/topSections/lobbyWidgetSection/LHS_RHS_Content/IconsLHS/SeasonPassLobbyWidget/scaleAdjuster/root/Overlay Parent/WidgetIcon/Icon Parent/mainIcon"
SEASON_PASS_CLOSE = "/Canvas/ModalLayer/SeasonPassModal(Clone)/root/closeGrp/closeCTA/touchArea"

ACTIVATE_BTN_PATH = "/Canvas/ModalLayer/SeasonPassModal(Clone)/root/verticalLayout/mainSection/layout/seasonPassHeader/bonusPassHeader/banner/layout/seasonActivateBtn/activateCTA/TouchArea"

BUY_BTN_PATH = "/Canvas/ModalLayer/SeasonPassPurchaseModal(Clone)/rootMain/rewardsSection/SorryButtonType-Currency/root"

FREE_TIER1_PATH = "/Canvas/ModalLayer/SeasonPassModal(Clone)/root/verticalLayout/mainSection/layout/mask/scrollView/viewport/content/SeasonTierScollItem_1/freePass/FreeTierRewardItem/claimBtn/SorryButtonType-Text/TouchArea"

PAID_TIER1_PATH = "/Canvas/ModalLayer/SeasonPassModal(Clone)/root/verticalLayout/mainSection/layout/mask/scrollView/viewport/content/SeasonTierScollItem_1/bonusPass/BonusTierRewardItem/claimBtn/SorryButtonType-Text/TouchArea"

CLAIM_ALL_PATH = "/Canvas/ModalLayer/SeasonPassModal(Clone)/root/bottomContainer/claimAllSlidingPopup/content/claimAllCTA/TouchArea"

UNLOCK_ONE_TIER_BTN = "/Canvas/ModalLayer/SeasonPassModal(Clone)/root/verticalLayout/mainSection/layout/mask/scrollView/viewport/content/lockPivotScrollItem/unlockBtnTooltip/layout/unlockCTA/TouchArea"

UNLOCK_CONFIRM_BTN = "/Canvas/ModalLayer/SeasonPassTierUnlockModal(Clone)/rootMain/buyCTA/TouchArea"

SEASON_PASS_GEM_PRICE = (
    "/Canvas/ModalLayer/SeasonPassTierUnlockModal(Clone)"
    "/rootMain/buyCTA/root/textContainer/priceText"
)

SEASON_PASS_PURCHASE_OK = (
    "/Canvas/ModalLayer/PurchaseNotifModal(Clone)/rootMain/ButtonLayer/Okay Button/TouchArea"
)
SEASON_PASS_PURCHASE_MODAL = ("/Canvas/ModalLayer/PurchaseNotifModal(Clone)")

# -----------------------------------------------------------------------
# LOW GEM POPUP
# -----------------------------------------------------------------------

LOW_GEM_MODAL = "/Canvas/ModalLayer/LowGemSlidingPopup(Clone)"
LOW_GEM_PURCHASE = "/Canvas/ModalLayer/LowGemSlidingPopup(Clone)/rootMain/safeArea/cardContent/card/bg/greenCTA/TouchArea"

# -----------------------------------------------------------------------
# PAWN REWARDS MODAL
# Appears after claiming a paid tier reward in Season Pass
# -----------------------------------------------------------------------
# -----------------------------------------------------------------------
# BEACH BUDDIES (CoOp LiveOps Event)
# -----------------------------------------------------------------------
BB_START_MODAL          = "/Canvas/ModalLayer/CoOpEventStartPopup(Clone)/darkbg"
BB_LETS_GO              = "/Canvas/ModalLayer/CoOpEventStartPopup(Clone)/rootMain/CTA/TouchArea"
BB_SCREEN               = "/Canvas/ModalLayer/CommonNudgeModal(Clone)"
BB_INVITE_ICON          = "/Canvas/ModalLayer/CommonNudgeModal(Clone)/SorryButtonType-Misc(Clone)/touchArea"

BB_INVITE_MODAL         = "/Canvas/ModalLayer/CoOpEventInvitesFriendsModal(Clone)/rootMain"
BB_ACCEPT_INVITE        = "/Canvas/ModalLayer/CoOpEventInvitesFriendsModal(Clone)/rootMain/scaleadjuster/mid/inviteFriends/ScrollView/viewport/content/CoOpEventInvitesScrollItem_1/rootMain/Content/RightContent/layout/AcceptButton/touchArea"
BB_DENY_INVITE          = "/Canvas/ModalLayer/CoOpEventInvitesFriendsModal(Clone)/rootMain/scaleadjuster/mid/inviteFriends/ScrollView/viewport/content/CoOpEventInvitesScrollItem_7/rootMain/Content/RightContent/layout/RejectButton/touchArea"
BB_SEND_INVITE          = "/Canvas/ModalLayer/CoOpEventInvitesFriendsModal(Clone)/rootMain/scaleadjuster/mid/inviteFriends/ScrollView/viewport/content/CoOpEventInvitesScrollItem_2/rootMain/Content/RightContent/layout/SendButton/TouchArea"
BB_SEND_ALL             = "/Canvas/ModalLayer/CoOpEventInvitesFriendsModal(Clone)/rootMain/scaleadjuster/mid/inviteFriends/buttons/SorryButtonType-Text_SendToAll/TouchArea"
BB_INVITE_CLOSE         = "/Canvas/ModalLayer/CoOpEventInvitesFriendsModal(Clone)/rootMain/scaleadjuster/closeCTA/touchArea"

BB_CASTLE_1             = "/Canvas/ModalLayer/CoOpEventMainModal(Clone)/rootMain/mainContainer/zoomedOutState/objectivesContainer/scaleAdjuster/Obj1/root/scalingTransform/userInfo/root/bg"
BB_CASTLE_2             = "/Canvas/ModalLayer/CoOpEventMainModal(Clone)/rootMain/mainContainer/zoomedOutState/objectivesContainer/scaleAdjuster/Obj2/root/scalingTransform/userInfo/root/closed/SorryButtonType-Misc/touchArea"

BB_FREE_AMMO_MODAL      = "/Canvas/ModalLayer/GenericCommonModal(Clone)/rootMain/layout/baseBg"
BB_FREE_AMMO_COUNT      = "/Canvas/ModalLayer/GenericCommonModal(Clone)/rootMain/layout/CoOpEventInnerContent(Clone)/content/rewardArea/BaseRewardInstantiator/root/SpriteRewardItem_16/visualParent/rewardMain/textMain/amountText/text"
BB_AWESOME_BTN          = "/Canvas/ModalLayer/GenericCommonModal(Clone)/rootMain/layout/CoOpEventInnerContent(Clone)/buttonsGroup/SorryButtonType-Text/TouchArea"

BB_FTUE_SPIN_WHEEL      = "/Canvas/ModalLayer/CommonNudgeModal(Clone)/button(Clone)/buttonImage"
BB_SPIN_MULTIPLIER      = "/Canvas/ModalLayer/CommonNudgeModal(Clone)/Multiplier(Clone)/root/value_Normal"
BB_SPIN_WHEEL           = "/Canvas/ModalLayer/CoOpEventMainModal(Clone)/rootMain/mainContainer/zoomedInState/wheelContainer/root/spinButtonContainer/button/buttonImage"
BB_CLOSE                = "/Canvas/ModalLayer/CoOpEventMainModal(Clone)/rootMain/closeButton/SorryButtonType-Misc/touchArea"

# -----------------------------------------------------------------------
# BEACH BUDDIES — full event-play flow (test_12_beachbuddies)
# All confirmed paths for: open → per-castle spin/milestone/giftbox →
# invites → event-complete → close.  Kept separate from the legacy
# happy-flow BB_* constants above (which test_02 still imports).
# -----------------------------------------------------------------------
_BB_MAIN   = "/Canvas/ModalLayer/CoOpEventMainModal(Clone)/rootMain"
_BB_ZOUT   = _BB_MAIN + "/mainContainer/zoomedOutState"
_BB_ZIN    = _BB_MAIN + "/mainContainer/zoomedInState"

# Lobby icon (same as HF_BB_ICON — tap in lobby to open the event)
BB_ICON                 = "/Canvas/uiLayer/TableManager/layout/viewPort/content/HomeScreen/topSections/lobbyWidgetSection/LHS_RHS_Content/IconsLHS/CoOpEventLobbyWidget/scaleAdjuster/root/Overlay Parent/WidgetIcon/Icon Parent/mainIcon"

# Confirms the Beach Buddies event screen is open
BB_EVENT_BG             = _BB_MAIN + "/bg"

# Ammo counter on the event (zoomed-out) screen
BB_AMMO_EVENT           = _BB_ZOUT + "/ammoCount/CommonEventAmmoCount_1/layout/root/TextStyle_subText_medium_bold/text"

# Castle objectives — tap to open (Obj1 has no invite; Obj2-4 gate on invite)
BB_CASTLES = {
    1: _BB_ZOUT + "/objectivesContainer/scaleAdjuster/Obj1",
    2: _BB_ZOUT + "/objectivesContainer/scaleAdjuster/Obj2",
    3: _BB_ZOUT + "/objectivesContainer/scaleAdjuster/Obj3",
    4: _BB_ZOUT + "/objectivesContainer/scaleAdjuster/Obj4",
}

# Inside a castle (zoomed-in)
BB_AMMO_CASTLE          = _BB_ZIN + "/wheelContainer/root/bottomUI/CommonEventAmmoCount/layout/root/TextStyle_subText_medium_bold/text"
BB_MULT_NORMAL          = _BB_ZIN + "/wheelContainer/root/spinButtonContainer/Multiplier/root/value_Normal"
BB_MULT_HIGHEST         = _BB_ZIN + "/wheelContainer/root/spinButtonContainer/Multiplier/root/value_Highest"
BB_MULT_BUTTON          = _BB_ZIN + "/wheelContainer/root/spinButtonContainer/Multiplier"
BB_PROGRESS             = _BB_ZIN + "/ProgressBars/progressBar_1/root/TextStyle_caption_extraSmall_black/text"
BB_SPIN_BTN             = _BB_ZIN + "/wheelContainer/root/spinButtonContainer/button/buttonImage"

# Milestone reward screen (RewardSummaryModal) — autospin stops here
BB_MILESTONE_CTA        = "/Canvas/ModalLayer/RewardSummaryModal(Clone)/rootMain/scaleAdjuster/footer/CTA/TouchArea"
BB_MILESTONE_AMOUNT     = "/Canvas/ModalLayer/RewardSummaryModal(Clone)/rootMain/scaleAdjuster/rewardsSection/BaseRewardInstantiator(Clone)/root/SpriteRewardItem_14/visualParent/rewardMain/textMain/amountText/text"
# Robust fallback — the SpriteRewardItem_N index varies by reward type, so
# find the amount text anywhere beneath the reward modal (// = any descendant).
BB_MILESTONE_AMOUNT_ANY = "/Canvas/ModalLayer/RewardSummaryModal(Clone)//amountText/text"

# Giftbox reward screen — means the castle is fully built (up to 5s animation)
BB_GIFTBOX_BG           = "/Canvas/ModalLayer/GiftBoxRewardModal(Clone)/darkBG"
BB_GIFTBOX_COLLECT      = "/Canvas/ModalLayer/GiftBoxRewardModal(Clone)/rootMain/collectCTA/TouchArea"
BB_GIFTBOX_AMOUNT       = "/Canvas/ModalLayer/GiftBoxRewardModal(Clone)/rootMain/rewardsSection/BaseRewardInstantiator(Clone)/root/SpriteRewardItem_8/visualParent/rewardMain/textMain/amountText/text"
BB_GIFTBOX_AMOUNT_ANY   = "/Canvas/ModalLayer/GiftBoxRewardModal(Clone)//amountText/text"
# If this cardpack node is present, the giftbox awarded a card pack
BB_GIFTBOX_CARDPACK     = "/Canvas/ModalLayer/GiftBoxRewardModal(Clone)/rootMain/rewardsSection/BaseRewardInstantiator(Clone)[1]/root/CardPackRewardItem_2"

# Invite-friends modal (castles 2-4).  Accept button item index varies (1-15),
# so build the path per-index with BB_ACCEPT_INVITE_TMPL.format(n=...).
BB_INVITE_BG            = "/Canvas/ModalLayer/CoOpEventInvitesFriendsModal(Clone)/rootMain/scaleadjuster/bgMain"
BB_ACCEPT_INVITE_TMPL   = "/Canvas/ModalLayer/CoOpEventInvitesFriendsModal(Clone)/rootMain/scaleadjuster/mid/inviteFriends/ScrollView/viewport/content/CoOpEventInvitesScrollItem_{n}/rootMain/Content/RightContent/layout/AcceptButton/touchArea"

# Event-complete screen (RewardSummaryModal) — after ALL castles built (~5s anim)
BB_EVENT_COMPLETE_BG    = "/Canvas/ModalLayer/RewardSummaryModal(Clone)/darkBG"
BB_EVENT_COMPLETE_R1    = "/Canvas/ModalLayer/RewardSummaryModal(Clone)/rootMain/scaleAdjuster/rewardsSection/BaseRewardInstantiator(Clone)/root/SpriteRewardItem_23/visualParent/rewardMain/textMain/amountText/text"
BB_EVENT_COMPLETE_R2    = "/Canvas/ModalLayer/RewardSummaryModal(Clone)/rootMain/scaleAdjuster/rewardsSection/BaseRewardInstantiator(Clone)[1]/root/SpriteRewardItem_24/visualParent/rewardMain/textMain/amountText/text"
BB_EVENT_COMPLETE_R3_CARDPACK = "/Canvas/ModalLayer/RewardSummaryModal(Clone)/rootMain/scaleAdjuster/rewardsSection/BaseRewardInstantiator(Clone)[2]/root/CardPackRewardItem_8/root/single/main"
BB_EVENT_COMPLETE_CTA   = "/Canvas/ModalLayer/RewardSummaryModal(Clone)/rootMain/scaleAdjuster/footer/CTA/TouchArea"

# -----------------------------------------------------------------------
# PAWN REWARDS MODAL
# Appears after claiming a paid tier reward in Season Pass
# -----------------------------------------------------------------------
PAWN_REWARDS_MODAL    = "/Canvas/ModalLayer/PawnRewardsModal(Clone)"
PAWN_REWARDS_CONTINUE = "/Canvas/ModalLayer/PawnRewardsModal(Clone)/rootMain/scaleAdjuster/root/continueButton/Later_Button/TouchArea"
PAWN_REWARDS_EQUIP    = "/Canvas/ModalLayer/PawnRewardsModal(Clone)/rootMain/scaleAdjuster/root/rewardsSection/rewardContainer/PawnRewardCard(Clone)/root/Equip Button/TouchArea"

# -----------------------------------------------------------------------
# FTUE NEW GUEST LOGIN FLOW
# Paths for the new onboarding cinematic + in-game FTUE steps
# -----------------------------------------------------------------------
FTUE_INTRO_CINEMATIC = "/Canvas/ModalLayer/FTUEIntroCinematic/root/mask/introSpine"
FTUE_INTRO_SKIP      = "/Canvas/ModalLayer/FTUEIntroCinematic/root/skipButton/TouchArea"
FTUE_DIALOG_BOX      = "/Canvas/FTUE-InGame/container/scaleAdjuster/dialogBubbleNew/layout/Base"
FTUE_SKIP_BUTTON     = "/Canvas/FTUE-InGame/container/scaleAdjuster/skipButton/TouchArea"

MATCHMAKING_SCREEN   = "/TransitionCanvas/matchmakingScreen_new(Clone)/root/bgGrp/bg"

CARD_DRAW_BUTTON     = "/Canvas/GameplayLayer/2pGameplayLayer/SorryGameBoard/board/root/mainGameContent/buttonContent/withdrawButton_02"

INGAME_BURGER_MENU   = "/Canvas/hudLayer/settings/grp/leftGrp/burgerMenu/touchArea"
INGAME_HUD_QUIT      = "/Canvas/hudLayer/settings/grp/leftGrp/menuOptions/quit/touchArea"
QUIT_CONFIRM         = "/Canvas/ModalLayer/QuitGamePopup(Clone)/rootMain/CTA_Red/TouchArea"

BUILD_ACTIVE_CARD    = "/Canvas/uiLayer/btmContent/lobbyBtmContent/buildTray/root/content/header/buildingCards/buildCard_Revamped(Clone)/buildCardParent/card/activeCard"
BUILD_INFO_SCREEN    = "/Canvas/ModalLayer/BuildFtueInfoModal(Clone)/bg"
NEXT_BUILD_CARD      = "/Canvas/uiLayer/btmContent/lobbyBtmContent/buildTray/root/content/header/buildingCards/buildCard_Revamped(Clone)[1]/buildCardParent/card/activeCard"
BUILD_CLOSE          = "/Canvas/uiLayer/btmContent/lobbyBtmContent/buildTray/root/content/closeCTA/touchArea"

# -----------------------------------------------------------------------
# CITY BUILD  (test_11_city_build.py)
# Cards are indexed 0-4.  Use the helpers in the test to build paths:
#   Card 1 → buildCard_Revamped(Clone)
#   Card N → buildCard_Revamped(Clone)[N-1]   (N ≥ 2)
# -----------------------------------------------------------------------
CB_ICON          = "/Canvas/uiLayer/TableManager/layout/viewPort/content/HomeScreen/buttonsGrp/root/Buttons/buildCTA/buttonCTA"
CB_PROGRESS_BAR  = "/Canvas/uiLayer/btmContent/lobbyBtmContent/buildTray/root/content/header/progessBar/TextStyle_bodyText_02_extraSmall/text"
CB_CLOSE         = "/Canvas/uiLayer/btmContent/lobbyBtmContent/buildTray/root/content/closeCTA/touchArea"
CB_INFO_SCREEN   = "/Canvas/ModalLayer/BuildFtueInfoModal(Clone)/bg"   # alias → BUILD_INFO_SCREEN
CB_REWARD_SCREEN = "/Canvas/midUiLayer/cityCompletionScreen/darkBG"
CB_COLLECT       = "/Canvas/midUiLayer/cityCompletionScreen/rootMain/collectCTA/TouchArea"

# Card path segments — assembled dynamically via _cb_card_*() helpers
_CB_CARDS_BASE   = "/Canvas/uiLayer/btmContent/lobbyBtmContent/buildTray/root/content/header/buildingCards/"

BET_PLAY_BUTTON      = "/Canvas/uiLayer/TableManager/layout/viewPort/content/HomeScreen/buttonsGrp/root/Buttons/playCTA/rootMain/playCTA/TouchArea"
BET_FTUE_OVERLAY     = "/Canvas/ModalLayer/CommonNudgeModal(Clone)/BGButton"
BET_CLOSE            = "/Canvas/ModalLayer/betScreenRevamped(Clone)/root/layout/header/cross_button/touchArea"

PIGGY_BANK_INFO         = "/Canvas/ModalLayer/PiggyBankInfoModal(Clone)/bg"

# Piggy Bank purchase flow
PIGGY_BANK_ICON         = "/Canvas/uiLayer/TableManager/layout/viewPort/content/HomeScreen/topSections/lobbyWidgetSection/LHS_RHS_Content/IconsRHS/PiggyBankWidget"
PIGGY_BANK_MODAL        = "/Canvas/ModalLayer/PiggyBankModal(Clone)/rootMain"
PIGGY_BANK_BUY          = "/Canvas/ModalLayer/PiggyBankModal(Clone)/rootMain/content/ClaimButton/TouchArea"
PIGGY_BANK_CLOSE        = "/Canvas/ModalLayer/PiggyBankModal(Clone)/rootMain/header/Close Button/touchArea"
PIGGY_BANK_CLAIM_SCREEN = "/Canvas/ModalLayer/PiggyClaimModal(Clone)/darkBG"


# -----------------------------------------------------------------------
# INFO SCREENS  (tap-once-to-close overlays)
#
# Each entry is a 2-tuple: (friendly_name, AltTester_path)
# To add a new screen just append a tuple here — the handler picks it up
# automatically without any other code changes.
# -----------------------------------------------------------------------
INFO_SCREENS = [
    ("Leagues Info",         "/Canvas/ModalLayer/LeagueInfoModal(Clone)/bg"),
    ("Leaderboard Info",     "/Canvas/ModalLayer/LeaderboardInfoModal(Clone)/container/bg"),
    ("Treasure Island Info", "/Canvas/ModalLayer/fortuneislandinfoModal(Clone)/Darkbg"),
    ("BumpToSpin Info",      "/Canvas/ModalLayer/BumpToSpinInfoModal(Clone)/root/close/SorryButtonType-close/touchArea"),
    ("Beach Buddies Info",   "/Canvas/ModalLayer/CoOpEventInfoScreen(Clone)/bg"),
    ("Sky Rush Info",        "/Canvas/ModalLayer/LiveOpsRaceInfoModal(Clone)/darkBG"),
]


# -----------------------------------------------------------------------
# HAPPY FLOW — Lobby widget icons & feature modals
# Used exclusively by test_02_happy_flow.py.
# To add a new widget: add its paths here, then add a _do_<name> function
# in test_02_happy_flow.py and append it to FEATURES.
# -----------------------------------------------------------------------

# Season Pass icon / close are already SEASON_PASS_ICON / SEASON_PASS_CLOSE above.

# --- Treasure Island ---
HF_TI_ICON             = "/Canvas/uiLayer/TableManager/layout/viewPort/content/HomeScreen/topSections/lobbyWidgetSection/LHS_RHS_Content/IconsLHS/FortuneIslandLobbyWidget/scaleAdjuster/root/Overlay Parent/WidgetIcon/Icon Parent/mainIcon"
HF_TI_INFO_SCREEN      = "/Canvas/ModalLayer/fortuneislandinfoModal(Clone)/root/container/PlayerGrp/bottomSection"
HF_TI_FREE_AMMO_MODAL  = "/Canvas/ModalLayer/FortuneIslandFreeAmmoModal(Clone)/rootMain"
HF_TI_FREE_AMMO_COUNT  = "/Canvas/ModalLayer/FortuneIslandFreeAmmoModal(Clone)/rootMain/InnerPanel/Bg/SpriteRewardItem/visualParent/rewardMain/textMain/amountText/text"
HF_TI_AWESOME_BTN      = "/Canvas/ModalLayer/FortuneIslandFreeAmmoModal(Clone)/rootMain/GreenCTA/TouchArea"
HF_TI_TOTAL_AMMO       = "/Canvas/ModalLayer/FortuneIslandMainModal(Clone)/Container/InitialFtueHandler/highlightingParent/FIMainScreenAmmoUI/root/container/WidgetIcon/Icon Parent/mainIcon"
# NOTE: Chest FTUE uses a different modal name (FortuneIslasedMainModal — typo is in the game itself)
HF_TI_CHEST_FTUE       = "/Canvas/ModalLayer/FortuneIslasedMainModal(Clone)/Container/InitialFtueHandler/click"
# Kitty Bag, 2nd Chest, and final FTUE click all use the corrected modal name
HF_TI_FTUE_CLICK       = "/Canvas/ModalLayer/FortuneIslandMainModal(Clone)/Container/InitialFtueHandler/click"
HF_TI_LEVEL_COMPLETE   = "/Canvas/ModalLayer/FortuneIslandMainModal(Clone)/FortuneIslandLevelCompleteRewardsModal/ClickArea"
HF_TI_CLOSE            = "/Canvas/ModalLayer/FortuneIslandMainModal(Clone)/Container/closeButton/closeButton/touchArea"

# --- SkyRush / SoapBox ---
HF_SKYRUSH_ICON        = "/Canvas/uiLayer/TableManager/layout/viewPort/content/HomeScreen/topSections/lobbyWidgetSection/LHS_RHS_Content/IconsLHS/liveOpsRaceWidget/scaleAdjuster/root/Overlay Parent/WidgetIcon/Icon Parent/mainIcon"
HF_SKYRUSH_MODAL       = "/Canvas/ModalLayer/LiveOpsRaceStartPopup(Clone)"
HF_SKYRUSH_START       = "/Canvas/ModalLayer/LiveOpsRaceStartPopup(Clone)/rootMain/footerGrp/CTA/TouchArea"
HF_SKYRUSH_INFO        = "/Canvas/ModalLayer/LiveOpsRaceInfoModal(Clone)/darkBG"
HF_SKYRUSH_LEADERBOARD = "/Canvas/ModalLayer/LiveOpsRaceLeaderboardModal(Clone)"
HF_SKYRUSH_CLOSE       = "/Canvas/ModalLayer/LiveOpsRaceLeaderboardModal(Clone)/rootMain/closeCTA/touchArea"

# --- Leagues ---
HF_LEAGUE_ICON         = "/Canvas/uiLayer/TableManager/layout/viewPort/content/HomeScreen/topSections/lobbyWidgetSection/LHS_RHS_Content/IconsLHS/leagueWidget/scaleAdjuster/root/Overlay Parent/badgeContainer/leagueBadge_Bronze(Clone)/root/body/main"
HF_LEAGUE_RANK         = "/Canvas/ModalLayer/LeagueModal(Clone)/rootMain/layout/midSection/rewardTopInfo/heading/leagueHeading/text"
HF_LEAGUE_CLOSE        = "/Canvas/ModalLayer/LeagueModal(Clone)/rootMain/closeGrp/closeCTA/touchArea"
HF_LEAGUE_INFO         = "/Canvas/ModalLayer/LeagueInfoModal(Clone)/bg"

# --- Pie Duel ---
HF_PIEDUEL_ICON        = "/Canvas/uiLayer/TableManager/layout/viewPort/content/HomeScreen/topSections/lobbyWidgetSection/LHS_RHS_Content/IconsLHS/DuelEventLobbyButton/scaleAdjuster/root/Overlay Parent/WidgetIcon/Icon Parent/mainIcon"
HF_PIEDUEL_MODAL       = "/Canvas/ModalLayer/DuelEventMainModal(Clone)"
HF_PIEDUEL_CLOSE       = "/Canvas/ModalLayer/DuelEventMainModal(Clone)/rootMain/closeCTA/touchArea"
HF_PIEDUEL_INFO        = "/Canvas/ModalLayer/DuelEventInfoModal(Clone)/bg"

# --- Beach Buddies (icon only — close is BB_CLOSE above) ---
HF_BB_ICON             = "/Canvas/uiLayer/TableManager/layout/viewPort/content/HomeScreen/topSections/lobbyWidgetSection/LHS_RHS_Content/IconsLHS/CoOpEventLobbyWidget/scaleAdjuster/root/Overlay Parent/WidgetIcon/Icon Parent/mainIcon"
HF_BB_INFO             = "/Canvas/ModalLayer/CoOpEventInfoScreen(Clone)/bg"

# --- Ad Rewards ---
HF_AD_ICON             = "/Canvas/uiLayer/TableManager/layout/viewPort/content/HomeScreen/topSections/lobbyWidgetSection/LHS_RHS_Content/IconsLHS/rewardedAdsWidget/scaleAdjuster/root/Overlay Parent/rewardedAdsIcon/WidgetIcon/mainIcon"
HF_AD_CLOSE            = "/Canvas/ModalLayer/RewardedAdsProgressModal(Clone)/closeGrp/closeCTA/touchArea"

# --- EDLP ---
HF_EDLP_ICON           = "/Canvas/uiLayer/TableManager/layout/viewPort/content/HomeScreen/topSections/lobbyWidgetSection/LHS_RHS_Content/IconsRHS/EDLPPackBtn/scaleAdjuster/root/buttonArea"
HF_EDLP_CLOSE          = "/Canvas/ModalLayer/EdlpGold02(Clone)/rootMain/content/crossButton/touchArea"

# --- Welcome Pack ---
# Mutually exclusive with EDLP — only one is shown at a time.
# The happy-flow handler tries Welcome Pack first; if absent it falls back to EDLP.
HF_WELCOME_PACK_ICON   = "/Canvas/uiLayer/TableManager/layout/viewPort/content/HomeScreen/topSections/lobbyWidgetSection/LHS_RHS_Content/IconsRHS/welcomePackBtn /scaleAdjuster/root/buttonArea[1]"
HF_WELCOME_PACK_CLOSE  = "/Canvas/ModalLayer/WelcomePackModal(Clone)/rootMain/SorryButtonType-Misc/touchArea"

# --- Daily Tasks ---
HF_DAILY_TASKS_ICON    = "/Canvas/uiLayer/TableManager/layout/viewPort/content/HomeScreen/topSections/lobbyWidgetSection/LHS_RHS_Content/IconsRHS/dailyTaskBtn/scaleAdjuster/root/touchArea"
HF_DAILY_TASKS_CLOSE   = "/Canvas/ModalLayer/DailyTaskModal(Clone)/rootMain/closeButton/touchArea"

# --- Endless Sale (happy-flow aliases) ---
HF_ENDLESS_SALE_ICON   = "/Canvas/uiLayer/TableManager/layout/viewPort/content/HomeScreen/topSections/lobbyWidgetSection/LHS_RHS_Content/IconsRHS/mineRunWidget/scaleAdjuster/root/buttonArea"
HF_ENDLESS_SALE_CLOSE  = "/Canvas/ModalLayer/EndlessSalePopup(Clone)/closegrp/closeCTA/touchArea"

# --- Endless Sale (dedicated test paths) ---
ES_ICON            = HF_ENDLESS_SALE_ICON
ES_POPUP           = "/Canvas/ModalLayer/EndlessSalePopup(Clone)"
ES_CLOSE           = "/Canvas/ModalLayer/EndlessSalePopup(Clone)/closegrp/closeCTA/touchArea"
ES_AMMO_PROGRESS   = "/Canvas/ModalLayer/EndlessSalePopup(Clone)/container/header/progressBarMain/count/text"
ES_COMPLETE_SCREEN = "/Canvas/ModalLayer/EndlessSalePopup(Clone)/container/congratulationsContainer/darkBG"
# Current tile (slot1) — always the next claimable tile
ES_TILE_PRICE      = "/Canvas/ModalLayer/EndlessSalePopup(Clone)/container/rewardsTrack/root/slot1/EndlessSaleRewardPanel/buyCTA/root/textContainer/priceText"
ES_TILE_REWARD_1   = "/Canvas/ModalLayer/EndlessSalePopup(Clone)/container/rewardsTrack/root/slot1/EndlessSaleRewardPanel/rewardContainer/layout/BaseRewardInstantiator/root/SpriteRewardItem_10/visualParent/rewardMain/textMain/amountText/text"
ES_TILE_REWARD_2   = "/Canvas/ModalLayer/EndlessSalePopup(Clone)/container/rewardsTrack/root/slot1/EndlessSaleRewardPanel/rewardContainer/layout/BaseRewardInstantiator_1/root/SpriteRewardItem_19/visualParent/rewardMain/textMain/amountText/text"
ES_TILE_AMMO       = "/Canvas/ModalLayer/EndlessSalePopup(Clone)/container/rewardsTrack/root/slot1/EndlessSaleRewardPanel/rewardContainer/showelContainer/banner/textShadow/text"
ES_TILE_BUY_BTN    = "/Canvas/ModalLayer/EndlessSalePopup(Clone)/container/rewardsTrack/root/slot1/EndlessSaleRewardPanel/buyCTA/TouchArea"

# --- Puzzle Event ---
HF_PUZZLE_ICON         = "/Canvas/uiLayer/TableManager/layout/viewPort/content/HomeScreen/topSections/lobbyWidgetSection/LHS_RHS_Content/IconsRHS/PuzzleEventWidget/scaleAdjuster/root/Overlay Parent/WidgetIcon/Icon Parent/mainIcon"
HF_PUZZLE_FTUE_MODAL   = "/Canvas/ModalLayer/GenericCommonModal(Clone)/rootMain/layout/PopupCommonHeader"
HF_PUZZLE_AMMO_COUNT   = "/Canvas/ModalLayer/GenericCommonModal(Clone)/rootMain/layout/puzzleEventInnerContent(Clone)/content/rewardArea/BaseRewardInstantiator/root/SpriteRewardItem_72/visualParent/rewardMain/textMain/amountText/text"
HF_PUZZLE_COLLECT      = "/Canvas/ModalLayer/GenericCommonModal(Clone)/rootMain/layout/puzzleEventInnerContent(Clone)/buttonsGroup/SorryButtonType-Text/TouchArea"
HF_PUZZLE_PIECE_FTUE   = "/Canvas/ModalLayer/CommonNudgeModal(Clone)/Btn(Clone)"
HF_PUZZLE_ALL_ICON     = "/Canvas/ModalLayer/CommonNudgeModal(Clone)/buttonCTA(Clone)"
HF_PUZZLE_TOTAL_AMMO   = "/Canvas/ModalLayer/PuzzleEventModal(Clone)/Container/footer/PuzzleHUD/layout/root/TextStyle_subText_medium_bold/text"
HF_PUZZLE_CLOSE        = "/Canvas/ModalLayer/PuzzleEventModal(Clone)/Container/closeButton/closeGrpAnimate/SorryButtonType-Misc/touchArea"

# --- Legendary Pawn Sale (icon only — close is PAWN_SALE_CLOSE above) ---
HF_PAWN_ICON           = "/Canvas/uiLayer/TableManager/layout/viewPort/content/HomeScreen/topSections/lobbyWidgetSection/LHS_RHS_Content/IconsRHS/LegendaryPawnLobbyWidget/scaleAdjuster/root/Overlay Parent/bg"

# --- BumpToSpin (BTS) ---
# HF_BTS_ICON is intentionally blank — path not yet provided.
# The feature auto-skips when this is empty.  Fill in once the path is known.
HF_BTS_ICON            = "/Canvas/uiLayer/TableManager/layout/viewPort/content/HomeScreen/topSections/lobbyWidgetSection/LHS_RHS_Content/IconsLHS/BumpToSpinWidget/scaleAdjuster/root/Overlay Parent/WidgetIcon/Icon Parent/mainIcon"
HF_BTS_INFO            = "/Canvas/ModalLayer/BumpToSpinInfoModal(Clone)/root/close/SorryButtonType-close/touchArea"
HF_BTS_FTUE_MODAL      = "/Canvas/ModalLayer/FreeBTSAmmoClaimModal(Clone)"
HF_BTS_FREE_AMMO_COUNT = "/Canvas/ModalLayer/FreeBTSAmmoClaimModal(Clone)/rootMain/reward/BaseRewardInstantiator/root/SpriteRewardItem_136/visualParent/rewardMain/textMain/amountText/text"
HF_BTS_CLAIM           = "/Canvas/ModalLayer/FreeBTSAmmoClaimModal(Clone)/rootMain/CTA_Green/TouchArea"
HF_BTS_CLOSE           = "/Canvas/ModalLayer/BumpToSpinModal(Clone)/root/headerButtons/closeButton/SorryButtonType-close/touchArea"

# --- Social Lobby ---
HF_SOCIAL_ICON         = "/Canvas/uiLayer/btmContent/lobbyBtmContent/lobbyBtmGrp/footerSection/Icons_Layout/Soical/SoicalIcon/icon"
HF_SOCIAL_TAB_RECENT   = "/Canvas/uiLayer/TableManager/layout/viewPort/content/FriendsTab/rootMain/container/FriendsModal/tabsHandler/tabs/Recent/inactiveTab"
HF_SOCIAL_TAB_CHAT     = "/Canvas/uiLayer/TableManager/layout/viewPort/content/FriendsTab/rootMain/container/FriendsModal/tabsHandler/tabs/Chat/inactiveTab"
HF_SOCIAL_TAB_INVITE   = "/Canvas/uiLayer/TableManager/layout/viewPort/content/FriendsTab/rootMain/container/FriendsModal/tabsHandler/tabs/Invites/inactiveTab"
HF_SOCIAL_TAB_FRIENDS  = "/Canvas/uiLayer/TableManager/layout/viewPort/content/FriendsTab/rootMain/container/FriendsModal/tabsHandler/tabs/Friends/inactiveTab"


# -----------------------------------------------------------------------
# GAMEPLAY — Classic game mode paths
# Used by test_09_gameplay.py
# -----------------------------------------------------------------------

# Lobby → bet screen entry
GAME_PLAY_BUTTON    = "/Canvas/uiLayer/TableManager/layout/viewPort/content/HomeScreen/buttonsGrp/root/Buttons/playCTA/rootMain/playCTA/TouchArea"

# Bet screen — Classic mode tab
# Tap inactiveTab to switch to Classic; if already selected, inactiveTab won't exist
GAME_BET_CLASSIC_TAB  = "/Canvas/ModalLayer/betScreenRevamped(Clone)/root/layout/content/tabAndContent/tabsHandler/tabs/ScrollParent/scrollView/viewport/content/NormalBetscreenModesTab/inactiveTab"

# Bet screen — Fire & Ice mode tab
# Tap inactiveTab to switch to Fire & Ice (mirrors the Classic tab pattern).
GAME_BET_FIREICE_TAB  = "/Canvas/ModalLayer/betScreenRevamped(Clone)/root/layout/content/tabAndContent/tabsHandler/tabs/ScrollParent/scrollView/viewport/content/Fire&IceBetscreenModesTab_2/inactiveTab"

# Fire & Ice rules screens (Fire Rules and Ice Rules share the same modal paths;
# both are dismissed by tapping the CTA button — first tap = Fire, second = Ice)
GAME_FIREICE_RULES_SCREEN = "/Canvas/ModalLayer/FireAndIceInfoModal(Clone)/darkbg"
GAME_FIREICE_RULES_CTA    = "/Canvas/ModalLayer/FireAndIceInfoModal(Clone)/rootMain/CTA/TouchArea"
# Reads the currently-selected mode label (used to confirm Classic is active)
GAME_BET_MODE        = "/Canvas/ModalLayer/betScreenRevamped(Clone)/root/layout/content/tabAndContent/tabsHandler/tabs/ScrollParent/scrollView/viewport/content/NormalBetscreenModesTab/activeTab/gridLayout/text/TextStyle_Amount_T1_large/text"
GAME_BET_AMOUNT      = "/Canvas/ModalLayer/betScreenRevamped(Clone)/root/layout/content/tabAndContent/innerContent/pagesAndButtons/pages/Content/ClassicBetscreenModePageVariant/topRewardGrp/BaseRewardInstantiator/root/SpriteRewardItem_159/visualParent/rewardMain/textMain/amountText/text"
GAME_BET_PREV        = "/Canvas/ModalLayer/betScreenRevamped(Clone)/root/layout/content/tabAndContent/innerContent/pagesAndButtons/buttons/prev_button/touchArea"
GAME_BET_NEXT        = "/Canvas/ModalLayer/betScreenRevamped(Clone)/root/layout/content/tabAndContent/innerContent/pagesAndButtons/buttons/next_button/touchArea"
GAME_BET_PLAY_TEXT   = "/Canvas/ModalLayer/betScreenRevamped(Clone)/root/layout/content/tabAndContent/innerContent/pagesAndButtons/buttons/next_button/touchArea"
GAME_BET_PLAY_BTN    = "/Canvas/ModalLayer/betScreenRevamped(Clone)/root/layout/content/tabAndContent/innerContent/pagesAndButtons/buttons/play_button/TouchArea"

# In-game HUD
GAME_INGAME_GEM     = "/Canvas/hudLayer/commonHUD/root/Container/gemBar/text"

# In-game chat
GAME_EMOJI_BTN      = "/Canvas/midUiLayer/InGameChatModal/root/layout/InGameChatField/SorryButtonType-Misc/touchArea"
GAME_QUICK_CHAT     = "/Canvas/midUiLayer/InGameChatModal/root/layout/InGameChatField/quickChat/chatMsgs/container_top/msgButton/bg"
GAME_EMOJI_SEND     = "/Canvas/midUiLayer/InGameChatModal/root/layout/InGameChatField/quickChat/emojiContainer/emojiButton_5/emoji"
GAME_CHAT_MSG_BTN   = "/Canvas/midUiLayer/InGameChatModal/root/layout/InGameChatField/SorryButtonType-Misc_1/touchArea"
GAME_CHAT_INPUT     = "/Canvas/midUiLayer/InGameChatModal/root/layout/InGameChatField/TextBar/textArea/textViewport/PlaceHolderText"

# Card actions — Classic mode (2pGameplayLayer / SorryGameBoard)
GAME_CARD_DRAW      = "/Canvas/GameplayLayer/2pGameplayLayer/SorryGameBoard/board/root/mainGameContent/buttonContent/withdrawButton_02"
GAME_REDRAW_BTN     = "/Canvas/GameplayLayer/2pGameplayLayer/SorryGameBoard/board/root/mainGameContent/buttonContent/redrawButton_New/root/iconContent/root/arrowParent/arrow"
GAME_REDRAW_GEM     = "/Canvas/GameplayLayer/2pGameplayLayer/SorryGameBoard/board/root/mainGameContent/buttonContent/redrawButton_New/root/redraw /text"

# Card actions — Fire & Ice mode (2pFireAndIceGameplayLayer / FireAndIceGameBoard)
GAME_FIREICE_CARD_DRAW  = "/Canvas/GameplayLayer/2pFireAndIceGameplayLayer(Clone)/FireAndIceGameBoard/board/root/mainGameContent/buttonContent/withdrawButton_02"
GAME_FIREICE_REDRAW_BTN = "/Canvas/GameplayLayer/2pFireAndIceGameplayLayer(Clone)/FireAndIceGameBoard/board/root/mainGameContent/buttonContent/redrawButton_New/root/iconContent/root/arrowParent/arrow"
GAME_FIREICE_REDRAW_GEM = "/Canvas/GameplayLayer/2pFireAndIceGameplayLayer(Clone)/FireAndIceGameBoard/board/root/mainGameContent/buttonContent/withdrawButton_02/dynamicCards/root/root/WithdrawCard/front/sorry/Lower/TextStyle_bodyText_extraExtraLarge/text"

# Burger menu / quit
GAME_BURGER_MENU    = "/Canvas/hudLayer/settings/grp/leftGrp/burgerMenu/touchArea"
GAME_QUIT_ICON      = "/Canvas/hudLayer/settings/grp/leftGrp/menuOptions/quit/touchArea"
GAME_QUIT_CONFIRM   = "/Canvas/ModalLayer/QuitGamePopup(Clone)/rootMain/CTA_Red/TouchArea"

# Opponent profile (in-game)
GAME_OPP_PROFILE_BTN   = "/Canvas/GameplayLayer/2pGameplayLayer/PlayerContainer/opponentProfileHolder /root/ProfileButton"
GAME_OPP_ADD_FRIEND    = "/Canvas/ModalLayer/OppProfileModalV2(Clone)/rootMain/contentMask/Content/topSection/section-Name/addFriendCTA/touchArea"
GAME_OPP_BLOCK_BTN     = "/Canvas/ModalLayer/OppProfileModalV2(Clone)/rootMain/BlockBtn/TouchArea"
GAME_OPP_BLOCK_CONFIRM = "/Canvas/ModalLayer/SorryCommonModal(Clone)/rootMain/layout/CTA_Red/TouchArea"
GAME_OPP_UNBLOCK_BTN   = "/Canvas/ModalLayer/OppProfileModalV2(Clone)/rootMain/UnBlockBtn/TouchArea"
GAME_OPP_PROFILE_CLOSE = "/Canvas/ModalLayer/OppProfileModalV2(Clone)/rootMain/closeCTA/touchArea"