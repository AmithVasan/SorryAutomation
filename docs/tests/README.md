# Tests — index

One document per automated test. Tests are registered in
[`tests/test_registry.py`](../../tests/test_registry.py) and launched by
`run_this.py`. The **type** tags control which suites a test runs in
(`smoke` · `iap` · `regression` · `bat` · `complete`).

| # | Test | Doc | Function | Types | What it covers |
|---|------|-----|----------|-------|----------------|
| 01 | Guest Login | [test_01_guest_login.md](test_01_guest_login.md) | `test_guest_login` | smoke, regression, bat, complete | New-user guest login, FTUE walkthrough, level boost, reach lobby |
| 02 | Happy Flow | [test_02_happy_flow.md](test_02_happy_flow.md) | `test_happy_flow` | smoke | Smoke sanity: clear lobby popups and reach a stable home state |
| 03 | Shop Purchase | [test_03_shop.md](test_03_shop.md) | `test_shop_purchase` | smoke, iap, regression, complete | In-app purchase flow in the shop |
| 04 | Lucky Cards | [test_04_lucky_cards.md](test_04_lucky_cards.md) | `test_lucky_cards` | regression, complete | Lucky Cards feature flow |
| 05 | Piggy Bank | [test_05_piggy_bank.md](test_05_piggy_bank.md) | `test_piggy_bank` | iap, regression, complete | Piggy Bank collect / IAP flow |
| 06 | Legendary Pawn Sale | [test_06_pawn_sale.md](test_06_pawn_sale.md) | `test_pawn_sale` | iap, regression, complete | Legendary Pawn Sale offer flow |
| 07 | Endless Sale | [test_07_endless_sale.md](test_07_endless_sale.md) | `test_endless_sale` | smoke, iap, regression, complete | Endless Sale offer flow |
| 08 | Season Pass | [test_08_season_pass.md](test_08_season_pass.md) | `test_season_pass` | iap, regression, complete | Season Pass unlock / claim flow |
| 09 | Gamemode — Classic | [test_09_classicmode.md](test_09_classicmode.md) | `test_gameplay` | smoke, complete | Classic gameplay mode |
| 10 | Gamemode — Fire & Ice | [test_10_fireandicemode.md](test_10_fireandicemode.md) | `test_fire_and_ice` | smoke, complete | Fire & Ice gameplay mode |
| 11 | City Build | [test_11_city_build.md](test_11_city_build.md) | `test_city_build` | smoke, complete | City Build feature flow |
| 12 | Beach Buddies | [test_12_beachbuddies.md](test_12_beachbuddies.md) | `test_beach_buddies` | complete | Beach Buddies co-op event (ammo boost) |
| 13 | Treasure Island | [test_13_treasureisland.md](test_13_treasureisland.md) | `test_treasure_island` | complete | Treasure / Fortune Island event (ammo boost) |
| 14 | Bump To Spin | [test_14_bumptospin.md](test_14_bumptospin.md) | `test_bump_to_spin` | complete | Bump To Spin event (ammo boost, 3-way wallet) |
| 15 | Puzzle Theatre | [test_15_puzzletheatre.md](test_15_puzzletheatre.md) | `test_puzzle_theatre` | complete | Puzzle Theatre event (adaptive boards, ammo boost, 3-way wallet) |

_Purpose column is a quick label; see each doc for the authoritative flow._
