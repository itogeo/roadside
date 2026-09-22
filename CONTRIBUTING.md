# Contributing

You don't need to know git to help.

**Found a marker that's missing or wrong?** Use the links on the site — "Fix this entry" on any marker, or
"Add a missing marker" in the footer. They open a short form that files a GitHub issue. Once a maintainer
adds the `accepted` label, the monthly rebuild folds it into the dataset automatically.

**Want to add your state?** See [docs/adding-a-state.md](docs/adding-a-state.md). For most states it's one
20-line JSON file.

**Photos** must be freely licensed (CC BY, CC BY-SA, CC0, or public domain). Wikimedia Commons is the best
place to put them; link the Commons page in the issue.

**Text** stays as written on the sign, including language that has aged badly. Corrections should fix
transcription errors, not editorialize; add context in `notes` instead.

**Code** is Python (stdlib where possible) and one HTML file. Keep it that way — the whole point is that
anyone can fork this and it just runs.
