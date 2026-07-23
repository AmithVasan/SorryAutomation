# Per-project background images

Drop a background image here named by the project's **slug** and it's picked up
automatically by the web GUI (no code change). If no image is found for a
project, the GUI falls back to that project's color gradient.

## Filenames (slug)
| Project            | File                      |
|--------------------|---------------------------|
| Sorry! World       | `sorry-world.jpg`         |
| Backgammon Friends | `backgammon-friends.jpg`  |
| Ludo Star          | `ludo-star.jpg`           |
| LS - Clubs         | `ls-clubs.jpg`            |
| Parchisi Star      | `parchisi-star.jpg`       |

`.jpg`, `.jpeg`, `.webp`, and `.png` are all accepted (first one found wins, in
that order). New project? slug = lowercase, non-alphanumerics → `-`
(e.g. "My New Game!" → `my-new-game`).

## Specs (works on all browsers + screen sizes)
- **Format:** JPEG preferred (universal, small). WebP is fine too (smaller).
- **Resolution:** **2560 × 1440** (16:9 landscape) recommended; 3840 × 2160 for
  4K/Retina crispness.
- **Size:** keep under ~1 MB each (JPEG quality ~80 ≈ 300–700 KB).
- **Composition:** keep the subject centered — the image is shown with
  `background-size: cover`, so edges crop differently across screens. A dark
  scrim is layered on top automatically for text readability.

Images placed here are committed with the repo (they're app assets).
