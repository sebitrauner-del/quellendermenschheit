# quellendermenschheit.de

Die Bibliothek **Quellen der Menschheit** – eigenständige deutsche Übersetzungen
klassischer Sanskrit-Literatur.

Die Seite ist die Bibliothek. Geordnet wird nach den klassischen **Gattungen**
(Regalen), nicht nach den Übersetzungsprojekten, aus denen die Daten technisch
stammen.

## Aufbau der Seite

```
/                                  Bibliothek – alle Regale
/<regal>/                          Regal, z. B. /brahmanas/
/<regal>/<werk>/                   Werk: Titelblatt, Vorwort, Inhaltsverzeichnis
/<regal>/<werk>/<teil>/            Werkteil (nur bei mehrteiligen Werken)
/<regal>/<werk>/[...]/kapitel-N.html   ein Kapitel
/<regal>/<werk>/glossar.html       Glossar
/suche.html                        Suche über Werke und Kapitel
/stand.html                        Stand der Übersetzungen (automatisch erzeugt)
/leseansicht/<name>.html           die interaktiven Leseansichten (noindex)
```

Regale: `veda`, `brahmanas`, `aranyakas`, `upanishaden`, `epen`, `puranas`,
`tantras`, `ayurveda`, `yoga`.

Jedes Kapitel ist eine eigene, kleine Seite (Schnitt ~31 KB) mit eigener URL,
Breadcrumb, canonical und JSON-LD. Alle alten Adressen aus der früheren
Projekt-Struktur werden weitergeleitet.

## Neu bauen und veröffentlichen

```bash
python3 scripts/publish.py -m "Beschreibung der Änderung"
```

Das baut nach `neu/`, druckt einen Vollständigkeitsbericht und lädt das Ergebnis
hoch. Nur bauen, ohne Upload:

```bash
python3 scripts/publish.py --nur-bauen
```

## Wo die Texte herkommen

`raw/` enthält die Rohdateien der sechs Claude-Artifacts:
`bibliothek.html`, `ramayana.html`, `mahabharata.html`, `aranyakas.html`,
`tantras.html`, `mahapuranas.html`.

Diese Dateien holt Claude mit dem Artifact-Werkzeug (`action: read`), das die
vollständige HTML-Datei ablegt – ein `curl` auf die Artifact-URL liefert nur die
App-Hülle und funktioniert nicht.

Markdown-Übersetzungen werden in `scripts/bibliothek.py` unter `MD_QUELLEN`
eingetragen. Erwartetes Format:

```markdown
# Werktitel — Autor (Jahr)
## Teil 1: Überschrift des Abschnitts

## Vers 1 (Metrum)

> sanskrit zeile eins
> sanskrit zeile zwei

| Sanskrit | Glosse |
|---|---|
| wort | Bedeutung (Grammatik) |

**Übersetzung.** Der deutsche Text.

[Anm.: Anmerkung des Übersetzers.]
```

Optional kann am Dateianfang ein Kopfblock zwischen `---`-Zeilen stehen
(`regal:`, `slug:`, `titel:`, `untertitel:`, `autor:`, `umfang:`).

## Zugang

Der GitHub-Token liegt in `~/.config/quellendermenschheit/github-token`
(Rechte 600). `scripts/publish.py` liest ihn von dort oder aus `$GH_TOKEN`.

Auf diesem Rechner ist kein `git` installiert; der Upload läuft über die
GitHub Git-Data-API.
