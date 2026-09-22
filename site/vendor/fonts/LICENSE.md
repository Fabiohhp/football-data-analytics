# Vendored fonts

Both families are licensed under the **SIL Open Font License, Version 1.1**, which
permits redistribution alongside this repository.

| File | Family | Source |
|------|--------|--------|
| `archivo-v25-*.woff2` | Archivo (variable: wdth 62–125, wght 100–900) | https://fonts.google.com/specimen/Archivo |
| `ibm-plex-mono-v20-*.woff2` | IBM Plex Mono (400, 500) | https://fonts.google.com/specimen/IBM+Plex+Mono |

The `v25` / `v20` in each filename is the upstream version Google Fonts served, so a
future update is a visible change rather than a silent one (CLAUDE.md §9).

They are **vendored, not linked**. The dashboard makes no request to any other host
at runtime: it works offline, and it cannot change appearance because a CDN did.
Subsets are `latin` and `latin-ext` only — enough for every club and player name in
the big-5 leagues (Mbappé, Alavés, Mönchengladbach, Saint-Étienne).

To refresh them, re-download the URLs that Google Fonts' CSS API returns for:

    https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@62..125,100..900&family=IBM+Plex+Mono:wght@400;500
