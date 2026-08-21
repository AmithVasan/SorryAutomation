# Lucky Cards

`tests/test_04_lucky_cards.py` · `test_lucky_cards(unity_driver, driver=None)` · types: `regression, complete`

## Purpose
Opens the Lucky Cards lobby feature, taps up to three available cards to claim their rewards, and logs a before/after comparison of the player's gold and gems as read from both the UI and Unity's in-memory data.

## Preconditions
- An active `unity_driver` (AltTester) session on a screen where the Lucky Cards icon and the Home HUD wallet text (`HOME_GOLD_TEXT` / `HOME_GEMS_TEXT`) are already visible — the test does not navigate Home first, it only calls `clear_all_popups()` before reading the wallet and opening the feature (tests/test_04_lucky_cards.py:291-299).
- At least one Lucky Card must be available; if the counter reads `0` (or is unreadable), the test raises and fails.

## Flow
1. Initialize the `steps` log list and log "Starting Lucky Cards Test" (tests/test_04_lucky_cards.py:266-289).
2. `clear_all_popups(unity_driver)` to dismiss anything already on screen (tests/test_04_lucky_cards.py:291).
3. Capture the "before" wallet via `get_wallet_values()`: reads `HOME_GOLD_TEXT` / `HOME_GEMS_TEXT` (10 s `wait_for_safe` each) through `parse_amount`, and separately calls `get_wallet_from_data()` (`utils/helpers.py`) to read gold/gems/pips straight from Unity's `UserManager` via AltTester's `call_static_method` (tests/test_04_lucky_cards.py:35-64, 297-299).
4. `open_lucky_cards()`: clears popups, waits up to 15 s for `LUCKY_CARDS_ICON` (raises `"Lucky Cards icon not found"` if missing), `safe_tap`s it, sleeps 3 s, clears popups again (tests/test_04_lucky_cards.py:71-93, 313).
5. `handle_ftue()`: waits up to 5 s for `FTUE_MODAL`; if absent, returns immediately. If present, waits up to 5 s for `SEND_GET_CARDS_DRAWER` and taps it, then waits up to 5 s for `DRAWER_CLOSE` and taps it. Per an in-code comment it deliberately only closes the invite drawer and does **not** tap a card during FTUE. Any exception here is caught and only logged as a warning (tests/test_04_lucky_cards.py:100-158, 316).
6. `get_available_cards()`: waits up to 10 s for `LUCKY_CARDS_COUNTER` and parses it with `int()`; returns `0` if the element is missing or unparsable (tests/test_04_lucky_cards.py:165-181, 322-329).
7. If `available_cards <= 0`, raises `"No Lucky Cards available"` (tests/test_04_lucky_cards.py:331-335).
8. `cards_to_tap = min(3, available_cards)` — the test always attempts at most three cards (tests/test_04_lucky_cards.py:338-341).
9. Loops `cards_to_tap` times calling `tap_single_card(unity_driver, i+1)`: waits up to 10 s for `LUCKY_CARD_TOUCH_AREA` (raises if missing), `safe_tap`s it, sleeps 2 s, then spends up to 8 s repeatedly calling `handle_one_popup()` to dismiss reward popup(s), stopping as soon as one pass finds nothing left to close (tests/test_04_lucky_cards.py:188-226, 354-363). After each successful tap it polls (every ~1 s, up to 10 s) via `wait_for_safe(..., timeout=2)` for the touch area to reappear for the next card, plus a flat 2 s pause (tests/test_04_lucky_cards.py:366-386). If a single card's tap raises, the exception is caught, logged as a warning, and the loop just continues to the next card without incrementing `successful_taps` (tests/test_04_lucky_cards.py:388-392).
10. Logs how many cards were tapped successfully — this step is logged with status `"PASS"` unconditionally, even if `successful_taps` is `0` (tests/test_04_lucky_cards.py:394-398).
11. Sleeps 3 s for reward animations (tests/test_04_lucky_cards.py:404).
12. `close_lucky_cards()`: waits up to 15 s for `LUCKY_CARDS_CLOSE` (raises if missing), `safe_tap`s it, sleeps 3 s, clears popups (tests/test_04_lucky_cards.py:233-259, 410).
13. Captures the "after" wallet via `get_wallet_values()` again (tests/test_04_lucky_cards.py:416-418).
14. Computes UI-based `gold_earned`/`gems_earned` (simple subtraction) and Data-based equivalents (`"N/A"` if either snapshot's Data value is `None`), and logs a comparison block — no assertion is made on any of these values (tests/test_04_lucky_cards.py:428-460).
15. On success, returns `{"name": "Lucky Cards", "status": "PASS", "duration": <seconds>, "steps": steps, "unity_driver": unity_driver}` (tests/test_04_lucky_cards.py:467-476).
16. Any exception raised anywhere above (steps 3-14) is caught by the function's outer `try/except`, appended as a `"FAIL"` step, and returned in the same dict shape with `"status": "FAIL"` (tests/test_04_lucky_cards.py:478-494).

## Key element paths

| Purpose | Constant | Path |
|---|---|---|
| Lucky Cards lobby icon | `LUCKY_CARDS_ICON` | `/Canvas/uiLayer/TableManager/layout/viewPort/content/HomeScreen/topSections/lobbyWidgetSection/LHS_RHS_Content/IconsRHS/LuckyCardsBtn/scaleAdjuster/root/Overlay Parent/WidgetIcon/Icon Parent/mainIcon` |
| Remaining-cards counter | `LUCKY_CARDS_COUNTER` | `/Canvas/ModalLayer/LuckyCardsModal(Clone)/rootMain/content/root/deckGrp/notificationCounterNodeRed/TextStyle_bodyText_large/text` |
| FTUE nudge modal | `FTUE_MODAL` | `/Canvas/ModalLayer/CommonNudgeModal(Clone)` |
| Card tap target | `LUCKY_CARD_TOUCH_AREA` | `/Canvas/ModalLayer/LuckyCardsModal(Clone)/rootMain/content/root/TouchArea` |
| FTUE "send/get cards" drawer CTA | `SEND_GET_CARDS_DRAWER` | `/Canvas/ModalLayer/LuckyCardsModal(Clone)/rootMain/invitometer/SendCTAHolder/sendCTA/TouchArea` |
| FTUE drawer close | `DRAWER_CLOSE` | `/Canvas/ModalLayer/LuckyCardsSlidingPopup(Clone)/rootMain/scaleadjuster/closeCTA/touchArea` |
| Lucky Cards modal close | `LUCKY_CARDS_CLOSE` | `/Canvas/ModalLayer/LuckyCardsModal(Clone)/rootMain/closeCTAGrp/closeCTA/touchArea` |
| Home gold counter (UI) | `HOME_GOLD_TEXT` | `/Canvas/uiLayer/TableManager/layout/viewPort/content/HomeScreen/topSections/commonHUD/root/Container/coinBar/text` |
| Home gems counter (UI) | `HOME_GEMS_TEXT` | `/Canvas/uiLayer/TableManager/layout/viewPort/content/HomeScreen/topSections/commonHUD/root/Container/gemBar/text` |

## Data & DB interactions
No MongoDB access. The test performs a two-way (UI vs. in-memory) wallet read for comparison only, never an assertion: (1) `HOME_GOLD_TEXT` / `HOME_GEMS_TEXT` parsed with `parse_amount`, and (2) `get_wallet_from_data()` (`utils/helpers.py:50-88`), which calls `UserManager.GetGold` / `GetGems` / `GetPips` through AltTester's `call_static_method`, falling back to `call_component_method` on a found `UserManager` component. Both snapshots and their deltas are only logged and appended to `steps`.

## Pass / fail criteria
- **PASS**: no exception propagates — the icon opens, `available_cards > 0`, and the close button is found at the end. Returns `{"status": "PASS", ...}`.
- **FAIL**: an exception is raised — Lucky Cards icon not found, `available_cards <= 0` ("No Lucky Cards available"), card touch area or close button not found on their required (non-per-card) waits. Returns `{"status": "FAIL", ...}` with the exception message appended as a step.
- Both outcomes share the same dict shape: `{"name", "status", "duration", "steps", "unity_driver"}`. The harness (`run_this.py:979-984`) reads and honors this dict's own `status` field directly, rather than assuming PASS just because the function returned normally.
- Per-card tap failures inside the tap loop do **not** fail the test by themselves — they are caught and logged, so the test can still report PASS with `successful_taps == 0`.

## Notes & known flakiness
- Actual signature is `test_lucky_cards(unity_driver, driver, run_type=None)`. Neither `driver` nor `run_type` is referenced anywhere in the function body, and the harness's only call site invokes it as `test_func(unity_driver, driver)` (`run_this.py:969`), so `run_type` is always `None` in practice.
- The test assumes it is already on a screen showing both the Lucky Cards icon and the Home wallet HUD — it does not tap `HOME_BUTTON` first (contrast with the Piggy Bank / Pawn Sale tests).
- `tap_single_card`'s post-tap popup-clear loop (up to 8 s) plus the "wait for next card" loop (up to 10 s, polled every ~1 s) mean each card can take close to 20 s end-to-end before the next is attempted, so 3 cards can add up to roughly a minute.
- The UI-vs-Data wallet comparison is purely informational; a mismatch between the two sources does not fail the test.
- FTUE handling is narrowly scoped to the invite drawer only, by design (see the in-code comment "DO NOT TAP CARD HERE").
