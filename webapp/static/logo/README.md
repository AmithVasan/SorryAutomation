# Per-project logos

Drop a logo image here and it automatically replaces the "🎮 &lt;project&gt;"
title in the webapp header for that project. **No code change, no server
restart** — the page probes for the file on the client each time a project is
selected. If no file is found, the header falls back to the emoji + name.

## File naming

Name the file `<slug>.<ext>` where `<slug>` is the project name lowercased with
every run of non-alphanumeric characters turned into a single hyphen:

| Project              | Drop file named            |
|----------------------|----------------------------|
| Sorry! World         | `sorry-world.png`          |
| Backgammon Friends   | `backgammon-friends.png`   |
| Ludo Star            | `ludo-star.png`            |
| LS - Clubs           | `ls-clubs.png`             |
| Parchisi Star        | `parchisi-star.png`        |

Accepted extensions (tried in this order): **png, svg, webp, jpg, jpeg**.

## Tips
- Transparent **PNG** or **SVG** looks best on the dark header.
- Any size works — it's scaled to 40px tall (max 260px wide), aspect preserved.
- To change a logo later, just replace the file (same name) and reload the page.
