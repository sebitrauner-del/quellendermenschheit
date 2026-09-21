#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Baut quellendermenschheit.de als Bibliothek.

Leitgedanke: Die Seite IST die Bibliothek "Quellen der Menschheit". Sie wird
nach den klassischen Gattungen der Sanskrit-Literatur geordnet (Regale), nicht
nach den Uebersetzungsprojekten, aus denen die Daten technisch stammen.

Jedes Kapitel bekommt eine eigene, kleine Seite mit eigener URL - statt wie
frueher ganze Werke (bis 15 MB) in eine einzige Datei zu packen.

    /                                   Bibliothek
    /<regal>/                           Regal (z.B. /brahmanas/)
    /<regal>/<werk>/                    Werk: Titelblatt + Inhaltsverzeichnis
    /<regal>/<werk>/<abschnitt>/        Abschnitt (nur bei mehrteiligen Werken)
    /<regal>/<werk>/[...]/kapitel-N.html   Einzelkapitel
    /<regal>/<werk>/glossar.html        Glossar (wenn vorhanden)
    /leseansicht/<slug>.html            interaktive Leseansicht (die alten SPAs)
"""
import re, json, base64, gzip, html, os, sys, unicodedata

SITE = "https://quellendermenschheit.de"

# IndexNow: Bing, Yandex, Seznam und Naver akzeptieren damit eine direkte
# Meldung neuer und geaenderter Adressen, ohne Konto. Der Schluessel muss
# als Textdatei unter der Wurzel liegen - siehe scripts/indexnow.py.
INDEXNOW_KEY = "f2db99238091f8062578df5eed4bcba1a7bd49ad20aea37f"

# ================================================================ Grundfunktionen

def esc(s):
    """Vertraegt Strings, Zahlen, None und Listen von Absaetzen."""
    if not s:
        return ""
    if isinstance(s, (list, tuple)):
        s = " ".join(str(x) for x in s if x)
    elif not isinstance(s, str):
        s = str(s)
    return html.escape(s, quote=False)


def absaetze(v):
    if not v:
        return []
    if isinstance(v, str):
        return [v]
    if isinstance(v, (list, tuple)):
        return [x for x in v if x]
    return [str(v)]


_SLUG_ERSATZ = {
    "ā": "a", "ī": "i", "ū": "u", "ṛ": "r", "ṝ": "r", "ḷ": "l", "ḹ": "l",
    "ṅ": "n", "ñ": "n", "ṭ": "t", "ḍ": "d", "ṇ": "n", "ś": "s", "ṣ": "s",
    "ṃ": "m", "ḥ": "h", "ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
}


def slug(text, fallback="x"):
    if not text:
        return fallback
    t = str(text).strip().lower()
    for a, b in _SLUG_ERSATZ.items():
        t = t.replace(a, b)
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return t or fallback


def eindeutig(basis, vergeben):
    """Sorgt dafuer, dass ein Slug innerhalb seines Bereichs nur einmal vorkommt."""
    s = basis
    i = 2
    while s in vergeben:
        s = "%s-%d" % (basis, i)
        i += 1
    vergeben.add(s)
    return s


# ================================================================ Bibliotheks-Ordnung

REGALE = [
    # (Anzeigename, Slug, Beschreibung)
    ("Veda-Saṃhitās",    "veda",         "Die älteste Schicht: die Liedersammlungen und Opfersprüche selbst."),
    ("Brāhmaṇas",        "brahmanas",    "Die Prosawerke zum Ritual – Erklärung, Deutung und Erzählung des Opfers."),
    ("Āraṇyakas",        "aranyakas",    "Die „Waldtexte“ zwischen Ritual und Spekulation."),
    ("Upaniṣaden",       "upanishaden",  "Die philosophischen Schlusstexte des Veda und die Yoga-Upaniṣaden des Muktikā-Kanons."),
    ("Epen",             "epen",         "Die beiden großen Erzählwerke Indiens."),
    ("Purāṇas",          "puranas",      "Die achtzehn Mahāpurāṇas: Kosmologie, Genealogie, Mythos und Lehre."),
    ("Tantras & Āgamas", "tantras",      "Der tantrische Korpus – śaiva-siddhāntische Āgamas, śākta-Tantras und vaiṣṇavische Pāñcarātra-Saṃhitās."),
    ("Āyurveda",         "ayurveda",     "Die medizinischen Grundlagenwerke."),
    ("Haṭha-Yoga",       "yoga",         "Die klassischen Handbücher des Haṭha-Yoga."),
]
REGAL_SLUG = {name: s for name, s, _ in REGALE}
REGAL_BESCHREIBUNG = {name: d for name, _, d in REGALE}
REGAL_REIHENFOLGE = {name: i for i, (name, _, _) in enumerate(REGALE)}

_REGAL_ALIAS = {
    "veden": "Veda-Saṃhitās", "veda": "Veda-Saṃhitās", "saṃhitā": "Veda-Saṃhitās",
    "brāhmaṇa": "Brāhmaṇas", "brāhmaṇas": "Brāhmaṇas",
    "āraṇyaka": "Āraṇyakas", "āraṇyakas": "Āraṇyakas",
    "upaniṣad": "Upaniṣaden", "upaniṣaden": "Upaniṣaden",
    "epos": "Epen", "epen": "Epen",
    "purāṇa": "Purāṇas", "purāṇas": "Purāṇas",
    "tantra": "Tantras & Āgamas", "tantras": "Tantras & Āgamas",
    "tantras & āgamas": "Tantras & Āgamas", "āgama": "Tantras & Āgamas",
    "āyurveda": "Āyurveda",
    "haṭha-yoga": "Haṭha-Yoga", "yoga": "Haṭha-Yoga",
}


def regal_von(rohwert, fallback="Weitere Werke"):
    if not rohwert:
        return fallback
    return _REGAL_ALIAS.get(str(rohwert).strip().lower(), str(rohwert).strip())


# ================================================================ Quelle: Claude-Artifacts

def _huelle_entfernen(roh):
    a = re.search(r"<body[^>]*>", roh, re.IGNORECASE)
    e = re.search(r"</body\s*>", roh, re.IGNORECASE)
    if not a or not e or e.start() <= a.end():
        sys.exit("FEHLER: <body>...</body> nicht gefunden")
    return roh[a.end():e.start()]


def _json_script(inhalt, script_id):
    m = re.search(r'<script id="%s"[^>]*>(.*?)</script>' % re.escape(script_id), inhalt, re.DOTALL)
    return json.loads(m.group(1)) if m else None


def _gzip_script(inhalt, script_id):
    m = re.search(r'<script id="%s"[^>]*>(.*?)</script>' % re.escape(script_id), inhalt, re.DOTALL)
    if not m:
        return None
    return json.loads(gzip.decompress(base64.b64decode(m.group(1).strip())))


def _einheit_normalisieren(u):
    """Die Artifacts liefern Verse entweder als Objekt
    {n, sa, de, notes, wfw} oder platzsparend als Array
    [n, sa, de, notes, wfw]. Hier wird beides auf die Objektform gebracht."""
    if isinstance(u, dict):
        e = dict(u)
    elif isinstance(u, (list, tuple)):
        f = list(u) + [None] * (5 - len(u))
        e = {"n": f[0], "sa": f[1] or "", "de": f[2] or ""}
        if f[3]:
            e["notes"] = f[3]
        if f[4]:
            e["wfw"] = f[4]
    else:
        return {"n": "", "sa": "", "de": str(u)}
    n = e.get("n")
    if isinstance(n, str) and n.strip().isdigit():
        e["n"] = str(int(n.strip()))          # "001" -> "1", damit die Zaehlung einheitlich ist
    return e


def _abschnitte_bauen(divisions, werk_slug):
    """Normalisiert die 'divisions' eines Werks zu Abschnitten mit Kapiteln."""
    raus = []
    for d in divisions or []:
        kap_slugs = set()
        kapitel = []
        for ch in d.get("chapters", []) or []:
            num = ch.get("num")
            basis = "kapitel-%s" % num if num not in (None, "") else slug(ch.get("key") or ch.get("title_de") or "kapitel")
            kapitel.append({
                "num": num,
                "slug": eindeutig(slug(basis, "kapitel"), kap_slugs),
                "titel_sa": ch.get("title_sa") or "",
                "titel_de": ch.get("title_de") or "",
                "anmerkung": absaetze(ch.get("note") or ch.get("note_de")),
                "tabelle_html": ch.get("table_html") or "",
                "einheiten": [_einheit_normalisieren(u) for u in (ch.get("units") or [])],
            })
        raus.append({
            "key": d.get("key") or slug(d.get("name") or "teil"),
            "slug": slug(d.get("key") or d.get("name") or "teil"),
            "name": d.get("name") or d.get("key") or "",
            "beschreibung": d.get("desc") or "",
            "kapitel": kapitel,
        })
    return raus


def _werk_aus_buch(buch, *, regal, werk_slug, blurb="", leseansicht=None, alt_urls=(), titel=None):
    return {
        "regal": regal,
        "slug": werk_slug,
        "titel": titel or buch.get("title") or werk_slug,
        "untertitel": buch.get("subtitle") or "",
        "blurb": blurb or buch.get("subtitle") or "",
        "frontmatter": buch.get("frontmatter") or {},
        "glossar": buch.get("glossary") or [],
        "glossar_titel": buch.get("glossary_title") or "Glossar",
        "abschnitt_label": buch.get("division_label") or "Teil",
        "kapitel_label": buch.get("chapter_label") or "Kapitel",
        "einheit_label": buch.get("unit_label") or "Vers",
        "abschnitte": _abschnitte_bauen(buch.get("divisions", []), werk_slug),
        "leseansicht": leseansicht,
        "alt_urls": list(alt_urls),
    }


def werke_aus_bibliothek(pfad, leseansicht_slug="bibliothek"):
    """bibliothek.html und ramayana.html: mehrere Buecher in einem Artifact."""
    inhalt = _huelle_entfernen(open(pfad, encoding="utf-8").read())
    meta = _json_script(inhalt, "data-meta")
    werke = []
    for bm in meta["books"]:
        bid = bm["id"]
        buch = _gzip_script(inhalt, "data-" + bid)
        if buch is None:
            continue
        werke.append(_werk_aus_buch(
            buch,
            regal=regal_von(bm.get("group")),
            werk_slug=slug(bid),
            blurb=bm.get("blurb") or bm.get("subtitle") or "",
            leseansicht="/leseansicht/%s.html#/b/%s" % (leseansicht_slug, bid),
            alt_urls=["/bibliothek/%s.html" % bid],
        ))
    return werke


def _teile_zusammenfuehren(basis_divisions, weitere_divisions):
    """Haengt die Kapitel eines Fortsetzungs-Artifacts an die passenden Werkteile
    des Basis-Artifacts an. Zugeordnet wird ueber den Werkteil-Schluessel."""
    nach_key = {d.get("key"): d for d in basis_divisions}
    for d in weitere_divisions:
        kapitel = d.get("chapters") or []
        if not kapitel:
            continue
        k = d.get("key")
        if k in nach_key:
            nach_key[k].setdefault("chapters", []).extend(kapitel)
        else:
            basis_divisions.append(d)
            nach_key[k] = d


def _kapitel_sortieren(divisions):
    """Sortiert die Kapitel jedes Werkteils nach Nummer - aber nur, wenn alle
    Nummern Zahlen sind. Sonst bleibt die Reihenfolge, wie sie geliefert wurde.
    Stabil, damit mehrere Kapitel mit derselben Nummer ihre Ordnung behalten."""
    for d in divisions:
        kapitel = d.get("chapters") or []
        try:
            schluessel = [int(str(c.get("num")).strip()) for c in kapitel]
        except (TypeError, ValueError):
            continue
        d["chapters"] = [c for _, c in sorted(zip(schluessel, kapitel), key=lambda x: x[0])]


def werk_aus_einzelwerk(pfad, *, regal, werk_slug, alt_praefix, leseansicht_slug,
                        fortsetzungen=()):
    """mahabharata.html: EIN Werk, dessen divisions echte Werkteile sind.

    fortsetzungen: weitere Artifact-Dateien, die dieselben Werkteile fortsetzen
    (das Mahābhārata ist aus Groessengruenden auf mehrere Artifacts verteilt)."""
    inhalt = _huelle_entfernen(open(pfad, encoding="utf-8").read())
    buch = _json_script(inhalt, "data-book")

    for fpfad in fortsetzungen:
        finhalt = _huelle_entfernen(open(fpfad, encoding="utf-8").read())
        fbuch = _json_script(finhalt, "data-book")
        if fbuch:
            _teile_zusammenfuehren(buch.setdefault("divisions", []), fbuch.get("divisions", []))
    if fortsetzungen:
        _kapitel_sortieren(buch.get("divisions", []))

    w = _werk_aus_buch(
        buch, regal=regal, werk_slug=werk_slug,
        leseansicht=None if fortsetzungen else "/leseansicht/%s.html" % leseansicht_slug,
        alt_urls=["/%s/index.html" % alt_praefix],
    )
    if not w["abschnitt_label"] or w["abschnitt_label"] == "Teil":
        w["abschnitt_label"] = "Parva"
    for a in w["abschnitte"]:
        a["alt_url"] = "/%s/%s.html" % (alt_praefix, a["key"])
    return [w]


def werke_aus_sammlung(pfad, *, regal, alt_praefix, leseansicht_slug):
    """aranyakas.html / mahapuranas.html: jede division ist ein eigenes Werk."""
    inhalt = _huelle_entfernen(open(pfad, encoding="utf-8").read())
    buch = _json_script(inhalt, "data-book")
    werke = []
    for d in buch.get("divisions", []):
        key = d.get("key") or slug(d.get("name") or "werk")
        einzel = {
            "title": d.get("name") or key,
            "subtitle": d.get("desc") or "",
            "chapter_label": buch.get("chapter_label") or "Kapitel",
            "unit_label": buch.get("unit_label") or "Vers",
            "divisions": [{"key": key, "name": "", "desc": "", "chapters": d.get("chapters", [])}],
        }
        werke.append(_werk_aus_buch(
            einzel, regal=regal, werk_slug=slug(key),
            blurb=d.get("desc") or "",
            leseansicht="/leseansicht/%s.html#/d/%s" % (leseansicht_slug, key),
            alt_urls=["/%s/%s.html" % (alt_praefix, key)],
        ))
    return werke


def werke_aus_tantras(pfad, *, regal="Tantras & Āgamas", alt_praefix="tantras", leseansicht_slug="tantras"):
    """tantras.html: Gruppen aus Werken."""
    inhalt = _huelle_entfernen(open(pfad, encoding="utf-8").read())
    buch = _json_script(inhalt, "data-book")
    werke = []
    for g in buch.get("groups", []):
        gname = g.get("name") or ""
        for w in g.get("works", []):
            key = w.get("key")
            einzel = {
                "title": w.get("name") or key,
                "subtitle": w.get("desc") or "",
                "chapter_label": "Paṭala",
                "unit_label": "Vers",
                "divisions": [{"key": key, "name": "", "desc": "", "chapters": w.get("chapters", [])}],
            }
            werk = _werk_aus_buch(
                einzel, regal=regal, werk_slug=slug(key),
                blurb=w.get("desc") or "",
                leseansicht="/leseansicht/%s.html#/w/%s" % (leseansicht_slug, key),
                alt_urls=["/%s/%s.html" % (alt_praefix, key)],
            )
            werk["untergruppe"] = gname
            werke.append(werk)
    return werke


# ================================================================ Quelle: Markdown-Uebersetzungen

_H1        = re.compile(r"^#\s+(.*)$")
_H2        = re.compile(r"^##\s+(.*)$")
_KAPITEL   = re.compile(r"^(?:Teil|Kapitel|Adhyāya|Adhyaya|Paṭala|Patala|Sarga|Kāṇḍa|Kanda)\s*([0-9]+)\s*[:.\-–—]?\s*(.*)$", re.I)
_VERS      = re.compile(r"^(?:Vers|Verse|Strophe|Sūtra|Sutra|Abschnitt)\s*([0-9]+(?:\s*[-–—]\s*[0-9]+)?[a-z]?)\s*(?:\((.*?)\))?\s*$", re.I)
_UEBERS    = re.compile(r"^\*\*(?:Übersetzung|Uebersetzung|Übers)\.?\*\*\.?\s*(.*)$")
_ANM       = re.compile(r"^\[Anm\.?:\s*(.*)\]\s*$", re.S)
_FRONT     = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)


def _md_tabelle(zeilen):
    """Wandelt eine Markdown-Tabelle in [[wort, glosse], ...]."""
    paare = []
    for z in zeilen:
        if not z.strip().startswith("|"):
            continue
        zellen = [c.strip() for c in z.strip().strip("|").split("|")]
        if len(zellen) < 2:
            continue
        if set("".join(zellen)) <= set("-: "):      # Trennzeile
            continue
        if zellen[0].lower() in ("sanskrit", "wort", "pada"):   # Kopfzeile
            continue
        paare.append([zellen[0], " | ".join(zellen[1:]).strip()])
    return paare


def werk_aus_markdown(pfad, *, regal=None, werk_slug=None, status=None):
    roh = open(pfad, encoding="utf-8").read()

    kopf = {}
    m = _FRONT.match(roh)
    if m:
        for z in m.group(1).splitlines():
            if ":" in z:
                k, v = z.split(":", 1)
                kopf[k.strip().lower()] = v.strip()
        roh = roh[m.end():]

    regal = regal or regal_von(kopf.get("regal"))
    titel = kopf.get("titel") or ""
    untertitel = kopf.get("untertitel") or ""
    autor = kopf.get("autor") or ""
    status = status or kopf.get("umfang") or ""

    zeilen = roh.splitlines()
    vorwort, kapitel = [], []
    akt_kap, akt_vers = None, None
    puffer, tabelle = [], []

    def vers_abschliessen():
        nonlocal akt_vers, puffer, tabelle
        if akt_vers is None:
            return
        if tabelle:
            akt_vers["wfw"] = _md_tabelle(tabelle)
        rest = "\n".join(puffer).strip()
        if rest and not akt_vers.get("de"):
            akt_vers["de"] = rest
        akt_kap["units"].append(akt_vers)
        akt_vers, puffer, tabelle = None, [], []

    i = 0
    while i < len(zeilen):
        z = zeilen[i]
        m1 = _H1.match(z)
        if m1:
            kopfzeile = m1.group(1).strip()
            for trenn in ("—", "–", " - "):
                if trenn in kopfzeile and not titel:
                    t, a = kopfzeile.split(trenn, 1)
                    titel, autor = t.strip(), (autor or a.strip())
                    break
            if not titel:
                titel = kopfzeile
            i += 1; continue

        m2 = _H2.match(z)
        if m2:
            ueberschrift = m2.group(1).strip()
            mv = _VERS.match(ueberschrift)
            if mv and akt_kap is not None:
                vers_abschliessen()
                akt_vers = {"n": mv.group(1).strip(), "sa": "", "de": ""}
                if mv.group(2):
                    akt_vers["label"] = mv.group(2).strip()
                i += 1; continue
            mk = _KAPITEL.match(ueberschrift)
            vers_abschliessen()
            num = mk.group(1) if mk else str(len(kapitel) + 1)
            name = (mk.group(2).strip() if mk else ueberschrift)
            akt_kap = {"num": num, "title_de": name, "title_sa": "", "note": [], "units": []}
            kapitel.append(akt_kap)
            i += 1; continue

        if z.strip() == "---":
            i += 1; continue

        if akt_vers is not None:
            if z.startswith(">"):
                teil = z.lstrip(">").strip()
                akt_vers["sa"] = (akt_vers["sa"] + "\n" + teil).strip() if akt_vers["sa"] else teil
                i += 1; continue
            if z.strip().startswith("|"):
                tabelle.append(z); i += 1; continue
            mu = _UEBERS.match(z.strip())
            if mu:
                text = [mu.group(1).strip()]
                i += 1
                while i < len(zeilen) and zeilen[i].strip() and not zeilen[i].startswith(("#", ">", "|", "[Anm")) and zeilen[i].strip() != "---":
                    text.append(zeilen[i].strip()); i += 1
                akt_vers["de"] = " ".join(t for t in text if t).strip()
                continue
            if z.strip().startswith("[Anm"):
                anm = [z.strip()]
                i += 1
                while i < len(zeilen) and not anm[-1].rstrip().endswith("]") and zeilen[i].strip():
                    anm.append(zeilen[i].strip()); i += 1
                ganz = " ".join(anm)
                ma = _ANM.match(ganz)
                akt_vers["notes"] = (ma.group(1) if ma else ganz.strip("[]")).strip()
                continue
            if z.strip():
                puffer.append(z.strip())
            i += 1; continue

        if akt_kap is not None:
            if z.strip():
                akt_kap["note"].append(re.sub(r"\*\*(.*?)\*\*", r"\1", z.strip()))
        else:
            if z.strip():
                vorwort.append(re.sub(r"\*\*(.*?)\*\*", r"\1", z.strip()))
        i += 1

    vers_abschliessen()

    werk_slug = werk_slug or slug(kopf.get("slug") or titel)
    buch = {
        "title": titel,
        "subtitle": untertitel,
        "frontmatter": {"vorwort": vorwort} if vorwort else {},
        "chapter_label": kopf.get("kapitel_label") or "Teil",
        "unit_label": kopf.get("einheit_label") or "Vers",
        "divisions": [{"key": werk_slug, "name": "", "desc": "", "chapters": kapitel}],
    }
    werk = _werk_aus_buch(buch, regal=regal, werk_slug=werk_slug, blurb=untertitel or autor)
    werk["autor"] = autor
    werk["umfang_hinweis"] = status
    werk["quelle_datei"] = os.path.basename(pfad)
    return werk


# ================================================================ Pfade

# Wird zu Beginn von bauen() gefuellt: Regal -> Werke. Die Seitenleiste braucht
# die Nachbarwerke eines Werks, ohne dass jede Bau-Funktion sie durchreichen muss.
WERKE_NACH_REGAL = {}


def regal_pfad(regal):
    return "/%s/" % REGAL_SLUG.get(regal, slug(regal))


def werk_pfad(w):
    return "%s%s/" % (regal_pfad(w["regal"]), w["slug"])


def mehrteilig(w):
    return len(w["abschnitte"]) > 1


def abschnitt_pfad(w, a):
    return "%s%s/" % (werk_pfad(w), a["slug"]) if mehrteilig(w) else werk_pfad(w)


def kapitel_pfad(w, a, k):
    return "%s%s.html" % (abschnitt_pfad(w, a), k["slug"])


def alle_kapitel(w):
    """[(abschnitt, kapitel), ...] in Lesereihenfolge."""
    return [(a, k) for a in w["abschnitte"] for k in a["kapitel"]]


def werk_fertig(w):
    return sum(len(k["einheiten"]) for _, k in alle_kapitel(w))


# ================================================================ Stylesheet (einmal geladen, dann gecacht)

STIL = """
:root{--bg:#EAE4D8;--bg-el:#F5F1E7;--bg-card:#F2ECDE;--ink:#241E17;--ink-soft:#5B5142;
--ink-faint:#8A8069;--line:#D3C9B4;--gold:#8C6A2C;--gold-s:#6E5220;
--fd:"Spectral",Georgia,serif;--fb:"Source Sans 3",-apple-system,"Segoe UI",sans-serif}
@media(prefers-color-scheme:dark){:root{--bg:#1B1712;--bg-el:#242019;--bg-card:#221E17;
--ink:#ECE4D2;--ink-soft:#BDB093;--ink-faint:#847A63;--line:#3A3325;--gold:#C39B4E;--gold-s:#D9B972}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--fb);line-height:1.65;
-webkit-text-size-adjust:100%}
a{color:var(--gold-s)}
header.kopf{border-bottom:1px solid var(--line);background:var(--bg-el)}
header.kopf .innen{max-width:860px;margin:0 auto;padding:.9rem 1.25rem;display:flex;
justify-content:space-between;align-items:baseline;gap:1rem;flex-wrap:wrap}
header.kopf a.marke{font-family:var(--fd);font-weight:600;font-size:1.05rem;text-decoration:none;color:var(--ink)}
header.kopf nav a{font-size:.85rem;color:var(--ink-soft);text-decoration:none;margin-left:1rem}
header.kopf nav a:hover{color:var(--gold-s)}
nav.brot{max-width:860px;margin:0 auto;padding:.8rem 1.25rem 0;font-size:.82rem;color:var(--ink-faint)}
nav.brot a{color:var(--ink-faint);text-decoration:none}
nav.brot a:hover{text-decoration:underline}
main{max-width:860px;margin:0 auto;padding:1rem 1.25rem 4rem}
h1{font-family:var(--fd);font-size:clamp(1.6rem,4vw,2.2rem);line-height:1.25;margin:.6rem 0 .3rem}
h1 .sa{display:block;font-style:italic;font-weight:400;color:var(--ink-soft);font-size:.62em;margin-top:.35rem}
h2{font-family:var(--fd);font-size:1.35rem;margin:2.2rem 0 .6rem;padding-bottom:.25rem;border-bottom:1px solid var(--line)}
h3{font-family:var(--fd);font-size:1.1rem;margin:1.6rem 0 .4rem;color:var(--gold-s)}
p.unter{color:var(--ink-soft);font-size:1.02rem;margin:.3rem 0 1.2rem}
p.kicker{margin:.8rem 0 0;font-size:.82rem;font-weight:600;letter-spacing:.06em;
text-transform:uppercase;color:var(--gold-s)}
.hinweis{background:var(--bg-card);border-left:3px solid var(--gold);border-radius:0 8px 8px 0;
padding:.7rem 1rem;font-size:.88rem;color:var(--ink-soft);margin:1rem 0}
.hinweis p{margin:0 0 .5rem}.hinweis p:last-child{margin:0}
.knopf{display:inline-block;margin:.4rem .5rem .4rem 0;padding:.5rem 1rem;border:1px solid var(--gold);
border-radius:8px;text-decoration:none;color:var(--gold-s);font-weight:600;font-size:.9rem}
.knopf:hover{background:var(--gold);color:var(--bg-el)}
/* Verse */
article.vers{padding:.9rem 0;border-bottom:1px dashed var(--line)}
article.vers:last-child{border-bottom:0}
.vnr{font-size:.78rem;font-weight:700;color:var(--ink-faint);letter-spacing:.03em}
.vnr a{color:inherit;text-decoration:none}
.vnr .metrum{font-weight:400;font-style:italic;margin-left:.5rem}
p.sa{font-style:italic;color:var(--ink-soft);margin:.3rem 0;white-space:pre-line}
p.de{margin:.3rem 0}
p.anm{font-size:.85rem;color:var(--ink-faint);font-style:italic;margin:.4rem 0 0}
details.wfw{margin:.45rem 0 0}
details.wfw summary{cursor:pointer;font-size:.8rem;color:var(--gold-s);font-weight:600}
details.wfw dl{display:grid;grid-template-columns:max-content 1fr;gap:.25rem .9rem;margin:.6rem 0 0;
font-size:.86rem;background:var(--bg-card);padding:.7rem .9rem;border-radius:8px}
details.wfw dt{font-style:italic;font-weight:600}
details.wfw dd{margin:0;color:var(--ink-soft)}
/* Listen */
ul.liste{list-style:none;padding:0;margin:.8rem 0}
ul.liste li{display:flex;gap:.9rem;align-items:baseline;padding:.55rem 0;border-bottom:1px solid var(--line)}
ul.liste li .nr{flex:0 0 2.6rem;font-size:.78rem;color:var(--ink-faint)}
ul.liste li .titel{font-family:var(--fd);font-size:1rem}
ul.liste li .titel a{text-decoration:none;color:inherit}
ul.liste li .titel a:hover{color:var(--gold-s)}
ul.liste li .titel .de{display:block;font-family:var(--fb);font-size:.85rem;color:var(--ink-soft);font-style:normal}
ul.liste li .stand{margin-left:auto;font-size:.76rem;color:var(--ink-faint);white-space:nowrap}
ul.liste li .stand.offen{font-style:italic}
.regalkarte{display:block;padding:1rem 1.1rem;border:1px solid var(--line);border-radius:12px;
background:var(--bg-card);text-decoration:none;color:var(--ink);margin:0 0 .8rem}
.regalkarte:hover{border-color:var(--gold)}
.regalkarte .rt{font-family:var(--fd);font-weight:600;font-size:1.15rem;color:var(--gold-s)}
.regalkarte .rb{font-size:.88rem;color:var(--ink-soft);margin-top:.25rem}
.regalkarte .rz{font-size:.78rem;color:var(--ink-faint);margin-top:.4rem}
/* Blaettern */
nav.blaettern{display:flex;justify-content:space-between;gap:1rem;margin:2.5rem 0 0;
padding-top:1rem;border-top:1px solid var(--line);font-size:.9rem}
nav.blaettern a{text-decoration:none;max-width:45%}
nav.blaettern .vor{text-align:right;margin-left:auto}
dl.glossar{display:grid;grid-template-columns:max-content 1fr;gap:.4rem 1.1rem}
dl.glossar dt{font-weight:600;font-style:italic}
dl.glossar dd{margin:0;color:var(--ink-soft)}
table{border-collapse:collapse;width:100%;font-size:.88rem}
.tabelle-wrap{overflow-x:auto;margin:1rem 0}
th,td{border:1px solid var(--line);padding:.4rem .6rem;text-align:left;vertical-align:top}
th{background:var(--bg-card)}
footer.fuss{border-top:1px solid var(--line);margin-top:3rem;padding:1.8rem 1.25rem;
text-align:center;color:var(--ink-faint);font-size:.85rem}
footer.fuss a{color:var(--ink-faint)}
#suchfeld{width:100%;padding:.65rem .9rem;font-size:1rem;font-family:var(--fb);
border:1px solid var(--line);border-radius:9px;background:var(--bg-el);color:var(--ink)}
/* Zweispaltiges Geruest mit Seitenleiste.
   Der Inhalt steht im Quelltext VOR der Navigation; auf dem Bildschirm wird die
   Navigation per Raster nach links gesetzt. Auf schmalen Geraeten rutscht sie
   dadurch ans Seitenende, statt 300 Kapitellinks vor den Text zu schieben. */
.rahmen{max-width:1260px;margin:0 auto;display:grid;grid-template-columns:272px minmax(0,1fr);
gap:2.5rem;padding:0 1.25rem}
.rahmen>aside.nav{grid-column:1;grid-row:1}
.rahmen>.spalte{grid-column:2;grid-row:1;min-width:0}
.rahmen>.spalte>main{padding-left:0;padding-right:0}
aside.nav{position:sticky;top:1rem;align-self:start;max-height:calc(100vh - 2rem);
overflow-y:auto;overscroll-behavior:contain;font-size:.86rem;padding:1.5rem 0 2rem}
aside.nav .gruppe{margin:0 0 1.4rem}
aside.nav .gruppe>h2{font-family:var(--fd);font-size:.76rem;font-weight:600;text-transform:uppercase;
letter-spacing:.07em;color:var(--ink-faint);margin:0 0 .5rem;padding:0;border:0}
aside.nav ul{list-style:none;margin:0;padding:0}
aside.nav li{margin:0}
aside.nav a{display:block;padding:.24rem .5rem;border-radius:6px;text-decoration:none;
color:var(--ink-soft);line-height:1.35}
aside.nav a:hover{background:var(--bg-card);color:var(--gold-s)}
aside.nav a.aktiv{background:var(--bg-card);color:var(--gold-s);font-weight:600}
aside.nav a .nr{display:inline-block;min-width:2.1em;color:var(--ink-faint);font-size:.9em}
aside.nav .gruppe>h2 .anzahl{color:var(--ink-faint);font-weight:400;letter-spacing:0}
aside.nav .raster{display:flex;flex-wrap:wrap;gap:2px}
aside.nav .raster a{min-width:2.3em;text-align:center;padding:.2rem .25rem;font-variant-numeric:tabular-nums}
aside.nav a.aktiv .nr{color:inherit}
@media(max-width:980px){
.rahmen{grid-template-columns:minmax(0,1fr);gap:0}
.rahmen>aside.nav{grid-column:1;grid-row:2}
.rahmen>.spalte{grid-column:1;grid-row:1}
aside.nav{position:static;max-height:none;overflow:visible;border-top:1px solid var(--line);margin-top:2rem}
}
"""


# ================================================================ Seitengeruest

MARKE = "Quellen der Menschheit"

# Rollt die Seitenleiste so, dass der aktuelle Eintrag sichtbar ist - aber nur,
# wenn sie ueberhaupt eine eigene Bildlaufleiste hat (also am Rechner, nicht
# am Telefon, wo sie am Seitenende steht).
NAV_SKRIPT = ('<script>(function(){var a=document.getElementById("nav-aktuell"),'
              's=document.querySelector("aside.nav");if(a&&s&&s.scrollHeight>s.clientHeight+8)'
              '{s.scrollTop=a.offsetTop-s.clientHeight/2;}})();</script>')


def nav_gruppe(titel, eintraege, aktuell=None):
    """eintraege: Liste von (nummer_oder_leer, beschriftung, adresse)."""
    if not eintraege:
        return ""
    zeilen = []
    for nummer, label, href in eintraege:
        zeilen.append('<li><a href="%s"%s>%s%s</a></li>' % (
            href,
            ' class="aktiv"' if href == aktuell else "",
            '<span class="nr">%s</span>' % esc(nummer) if nummer not in (None, "") else "",
            esc(label)))
    return '<div class="gruppe"><h2>%s</h2><ul>%s</ul></div>' % (esc(titel), "".join(zeilen))


def anker_setzen(leiste):
    """Markiert den TIEFSTEN aktiven Eintrag als Sprungziel. Aktiv sind mehrere
    (Regal, Werk, Werkteil, Kapitel) - anrollen soll die Leiste aber zum Kapitel."""
    i = leiste.rfind('class="aktiv"')
    return leiste if i == -1 else leiste[:i] + 'id="nav-aktuell" ' + leiste[i:]


def nav_regale(aktuell=None):
    return nav_gruppe("Bibliothek", [("", name, regal_pfad(name)) for name, _, _ in REGALE], aktuell)


def nav_werke(regal, werke, aktuell=None):
    eintraege = [("", w["titel"], werk_pfad(w)) for w in sorted(werke, key=lambda x: x["titel"])]
    return nav_gruppe(regal, eintraege, aktuell)


def nav_teile(w, aktuell=None):
    if not mehrteilig(w):
        return ""
    return nav_gruppe(w["titel"], [("", a["name"] or a["key"], abschnitt_pfad(w, a))
                                   for a in w["abschnitte"]], aktuell)


# Ab dieser Kapitelzahl wird statt einer Titelliste ein Nummernraster gezeigt:
# 299 Zeilen mit Titeln sind weder ueberschaubar noch leichtgewichtig, 299
# Nummern nebeneinander dagegen schon.
RASTER_AB = 60


def nav_kapitel(w, a, aktuell=None):
    if not a["kapitel"]:
        return ""
    titel = (a["name"] or w["titel"]) if mehrteilig(w) else w["titel"]

    if len(a["kapitel"]) > RASTER_AB:
        zellen = []
        for k in a["kapitel"]:
            href = kapitel_pfad(w, a, k)
            ist = (href == aktuell)
            zellen.append('<a href="%s"%s>%s</a>' % (
                href, ' class="aktiv"' if ist else "", esc(k["num"])))
        return ('<div class="gruppe"><h2>%s <span class="anzahl">%d</span></h2>'
                '<div class="raster">%s</div></div>' % (esc(titel), len(a["kapitel"]), "".join(zellen)))

    eintraege = []
    for k in a["kapitel"]:
        name = k["titel_sa"] or k["titel_de"] or ""
        if len(name) > 42:
            name = name[:41] + "…"
        eintraege.append((k["num"], name, kapitel_pfad(w, a, k)))
    return nav_gruppe(titel, eintraege, aktuell)
SCHRIFTEN = ('<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
             '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
             'family=Spectral:ital,wght@0,400;0,600;1,400&family=Source+Sans+3:wght@400;600;700&display=swap">')


def _brot_ld(brotkrumen):
    eintraege = []
    for i, (label, href) in enumerate(brotkrumen, 1):
        e = {"@type": "ListItem", "position": i, "name": label}
        if href:
            e["item"] = SITE + href
        eintraege.append(e)
    return {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": eintraege}


def seite(*, titel, beschreibung, kanonisch, inhalt, brotkrumen=(), ld=None, kopf_extra="",
          seitenleiste=""):
    brot = ""
    if brotkrumen:
        teile = []
        for label, href in brotkrumen[:-1]:
            teile.append('<a href="%s">%s</a>' % (href, esc(label)))
        teile.append(esc(brotkrumen[-1][0]))
        brot = '<nav class="brot">%s</nav>' % " › ".join(teile)

    ld_bloecke = []
    if brotkrumen:
        ld_bloecke.append(_brot_ld(brotkrumen))
    if ld:
        ld_bloecke.append(ld)
    ld_html = "".join('<script type="application/ld+json">%s</script>' % json.dumps(b, ensure_ascii=False)
                      for b in ld_bloecke)

    beschreibung = (beschreibung or "").replace("\n", " ").strip()[:300]
    return """<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>%(titel)s</title>
<meta name="description" content="%(besch)s">
<link rel="canonical" href="%(kanon)s">
<meta property="og:type" content="article">
<meta property="og:title" content="%(otitel)s">
<meta property="og:description" content="%(besch)s">
<meta property="og:url" content="%(kanon)s">
<meta property="og:site_name" content="%(marke)s">
<meta property="og:locale" content="de_DE">
<meta name="twitter:card" content="summary">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>📜</text></svg>">
%(schriften)s
<link rel="stylesheet" href="/stil.css">
%(ld)s%(extra)s
</head>
<body>
<header class="kopf"><div class="innen">
  <a class="marke" href="/">%(marke)s</a>
  <nav><a href="/">Bibliothek</a><a href="/suche.html">Suche</a><a href="/ueber.html">Über</a></nav>
</div></header>
%(rahmen_auf)s%(brot)s
<main>
%(inhalt)s
</main>
%(rahmen_zu)s
<footer class="fuss">
  <p><a href="/">%(marke)s</a> · eigenständige deutsche Übersetzungen klassischer Sanskrit-Literatur.<br>
  Alle Übersetzungen sind gemeinfrei und werden fortlaufend erweitert.</p>
</footer>
</body>
</html>
""" % {
        "titel": esc(titel), "besch": esc(beschreibung), "kanon": SITE + kanonisch,
        "otitel": esc(titel.split(" | ")[0]), "marke": MARKE, "schriften": SCHRIFTEN,
        "ld": ld_html, "extra": kopf_extra, "brot": brot, "inhalt": inhalt,
        "rahmen_auf": '<div class="rahmen"><div class="spalte">' if seitenleiste else "",
        "rahmen_zu": ("</div><aside class=\"nav\">%s</aside></div>%s" % (seitenleiste, NAV_SKRIPT))
                     if seitenleiste else "",
    }


def schreiben(aus, pfad, text):
    """pfad beginnt mit / und ist relativ zur Site-Wurzel."""
    ziel = os.path.join(aus, pfad.lstrip("/"))
    os.makedirs(os.path.dirname(ziel), exist_ok=True)
    with open(ziel, "w", encoding="utf-8") as f:
        f.write(text)


def weiterleitung(aus, von_pfad, nach_pfad):
    """Kleine Weiterleitungsseite, damit alte URLs nicht ins Leere laufen."""
    ziel = SITE + nach_pfad
    schreiben(aus, von_pfad, """<!DOCTYPE html>
<html lang="de"><head><meta charset="UTF-8">
<title>Umgezogen – %(marke)s</title>
<link rel="canonical" href="%(ziel)s">
<meta name="robots" content="noindex,follow">
<meta http-equiv="refresh" content="0; url=%(ziel)s">
</head><body>
<p>Diese Seite ist umgezogen: <a href="%(ziel)s">%(ziel)s</a></p>
<script>location.replace("%(ziel)s");</script>
</body></html>
""" % {"ziel": ziel, "marke": MARKE})


# ================================================================ Einzelseiten

def _vers_html(u, einheit_label, idx):
    n = u.get("n", idx)
    anker = "v%s" % slug(str(n), str(idx))
    teile = ['<article class="vers" id="%s">' % anker]
    metrum = ' <span class="metrum">%s</span>' % esc(u["label"]) if u.get("label") else ""
    teile.append('<div class="vnr"><a href="#%s">%s %s</a>%s</div>' % (anker, esc(einheit_label), esc(n), metrum))
    if u.get("sa"):
        teile.append('<p class="sa">%s</p>' % esc(u["sa"]))
    if u.get("de"):
        teile.append('<p class="de">%s</p>' % esc(u["de"]))
    wfw = u.get("wfw")
    if wfw:
        paare = []
        for paar in wfw:
            if isinstance(paar, (list, tuple)) and len(paar) >= 2:
                paare.append("<dt>%s</dt><dd>%s</dd>" % (esc(paar[0]), esc(paar[1])))
            elif isinstance(paar, dict):
                paare.append("<dt>%s</dt><dd>%s</dd>" % (esc(paar.get("w") or paar.get("sa")),
                                                         esc(paar.get("g") or paar.get("de"))))
        if paare:
            teile.append('<details class="wfw"><summary>Wort für Wort</summary><dl>%s</dl></details>' % "".join(paare))
    if u.get("notes"):
        teile.append('<p class="anm">%s</p>' % esc(u["notes"]))
    teile.append("</article>")
    return "".join(teile)


def baue_kapitel(aus, w, a, k, vorher, nachher, urls):
    pfad = kapitel_pfad(w, a, k)
    kap_bez = "%s %s" % (w["kapitel_label"], k["num"]) if k["num"] not in (None, "") else w["kapitel_label"]
    kopfzeile = k["titel_sa"] or k["titel_de"] or kap_bez
    voll = "%s, %s" % (w["titel"], kap_bez)
    if mehrteilig(w) and a["name"]:
        voll = "%s, %s, %s" % (w["titel"], a["name"], kap_bez)

    erste_de = next((u.get("de") for u in k["einheiten"] if u.get("de")), "")
    beschreibung = "%s%s %s" % (voll, (" – " + k["titel_de"]) if k["titel_de"] else "", erste_de)

    brot = [(MARKE, "/"), (w["regal"], regal_pfad(w["regal"])), (w["titel"], werk_pfad(w))]
    if mehrteilig(w):
        brot.append((a["name"] or a["key"], abschnitt_pfad(w, a)))
    brot.append((kap_bez, None))

    # Werk und Werkteil stehen ueber der Ueberschrift: "Kapitel 23" allein sagt
    # weder Leserinnen noch Suchmaschinen etwas.
    inhalt = ['<p class="kicker">%s%s</p>' % (
        esc(w["titel"]), esc(" · " + a["name"]) if (mehrteilig(w) and a["name"]) else "")]
    inhalt.append('<h1>%s' % esc(kap_bez if not k["titel_sa"] else "%s: %s" % (kap_bez, k["titel_sa"])))
    if k["titel_de"]:
        inhalt.append('<span class="sa">%s</span>' % esc(k["titel_de"]))
    inhalt.append("</h1>")
    if k["anmerkung"]:
        inhalt.append('<div class="hinweis">%s</div>' % "".join("<p>%s</p>" % esc(p) for p in k["anmerkung"]))
    if k["tabelle_html"]:
        inhalt.append('<div class="tabelle-wrap">%s</div>' % k["tabelle_html"])
    if k["einheiten"]:
        inhalt.append("".join(_vers_html(u, w["einheit_label"], i) for i, u in enumerate(k["einheiten"], 1)))
    else:
        inhalt.append('<div class="hinweis"><p>Dieses Kapitel ist noch nicht übersetzt.</p></div>')
    if w.get("leseansicht"):
        inhalt.append('<p><a class="knopf" href="%s">Interaktive Leseansicht des ganzen Werks</a></p>' % w["leseansicht"])
    elif w.get("leseansichten"):
        inhalt.append('<p><a class="knopf" href="%s">Alle Leseansichten des Werks</a></p>' % werk_pfad(w))

    blaettern = []
    if vorher:
        blaettern.append('<a class="zurueck" href="%s">← %s</a>' % (vorher[0], esc(vorher[1])))
    if nachher:
        blaettern.append('<a class="vor" href="%s">%s →</a>' % (nachher[0], esc(nachher[1])))
    if blaettern:
        inhalt.append('<nav class="blaettern">%s</nav>' % "".join(blaettern))

    ld = {"@context": "https://schema.org", "@type": "Chapter",
          "name": voll, "inLanguage": "de", "url": SITE + pfad,
          "isPartOf": {"@type": "Book", "name": w["titel"], "url": SITE + werk_pfad(w)},
          "translator": {"@type": "Organization", "name": MARKE}}

    # Der Titel traegt die Begriffe, nach denen tatsaechlich gesucht wird:
    # Werk, Werkteil, Kapitelnummer und - wenn vorhanden - der Kapitelname.
    titel_teile = [w["titel"]]
    if mehrteilig(w) and a["name"]:
        titel_teile.append(a["name"])
    titel_teile.append(kap_bez)
    seiten_titel = ", ".join(titel_teile)
    kap_name = k["titel_sa"] or k["titel_de"]
    if kap_name:
        seiten_titel += ": %s" % kap_name
    leiste = anker_setzen(nav_regale(regal_pfad(w["regal"]))
              + nav_werke(w["regal"], WERKE_NACH_REGAL.get(w["regal"], [w]), werk_pfad(w))
              + nav_teile(w, abschnitt_pfad(w, a))
              + nav_kapitel(w, a, pfad))
    schreiben(aus, pfad, seite(
        titel="%s – %s" % (seiten_titel, MARKE),
        beschreibung=beschreibung, kanonisch=pfad, inhalt="\n".join(inhalt),
        brotkrumen=brot, ld=ld, seitenleiste=leiste))
    urls.append((pfad, 0.6))


def _kapitel_liste(w, a):
    zeilen = []
    for k in a["kapitel"]:
        stand = ('<span class="stand">%d %s</span>' % (len(k["einheiten"]), w["einheit_label"] + ("e" if len(k["einheiten"]) != 1 else ""))
                 if k["einheiten"] else '<span class="stand offen">noch nicht übersetzt</span>')
        titel = k["titel_sa"] or k["titel_de"] or "%s %s" % (w["kapitel_label"], k["num"])
        de = '<span class="de">%s</span>' % esc(k["titel_de"]) if (k["titel_de"] and k["titel_sa"]) else ""
        zeilen.append('<li><span class="nr">%s</span><span class="titel">'
                      '<a href="%s">%s</a>%s</span>%s</li>'
                      % (esc(k["num"]), kapitel_pfad(w, a, k), esc(titel), de, stand))
    return '<ul class="liste">%s</ul>' % "".join(zeilen)


def baue_abschnitt(aus, w, a, urls):
    pfad = abschnitt_pfad(w, a)
    brot = [(MARKE, "/"), (w["regal"], regal_pfad(w["regal"])), (w["titel"], werk_pfad(w)), (a["name"] or a["key"], None)]
    inhalt = ['<h1>%s</h1>' % esc(a["name"] or a["key"])]
    inhalt.append('<p class="unter">%s · %d %s</p>' % (esc(w["titel"]), len(a["kapitel"]),
                                                        esc(w["kapitel_label"] + ("s" if len(a["kapitel"]) != 1 else ""))))
    if a["beschreibung"]:
        inhalt.append('<div class="hinweis"><p>%s</p></div>' % esc(a["beschreibung"]))
    inhalt.append(_kapitel_liste(w, a))
    leiste = anker_setzen(nav_regale(regal_pfad(w["regal"]))
              + nav_werke(w["regal"], WERKE_NACH_REGAL.get(w["regal"], [w]), werk_pfad(w))
              + nav_teile(w, pfad))
    schreiben(aus, pfad + "index.html", seite(
        titel="%s – %s | %s" % (a["name"] or a["key"], w["titel"], MARKE),
        beschreibung="%s, %s: %d %s in deutscher Übersetzung. %s" % (
            w["titel"], a["name"], len(a["kapitel"]), w["kapitel_label"], a["beschreibung"]),
        kanonisch=pfad, inhalt="\n".join(inhalt), brotkrumen=brot, seitenleiste=leiste))
    urls.append((pfad, 0.7))


def baue_werk(aus, w, urls):
    pfad = werk_pfad(w)
    anzahl_kap = sum(len(a["kapitel"]) for a in w["abschnitte"])
    anzahl_einh = werk_fertig(w)
    brot = [(MARKE, "/"), (w["regal"], regal_pfad(w["regal"])), (w["titel"], None)]

    inhalt = ['<h1>%s' % esc(w["titel"])]
    if w.get("autor"):
        inhalt.append('<span class="sa">%s</span>' % esc(w["autor"]))
    inhalt.append("</h1>")
    if w["untertitel"]:
        inhalt.append('<p class="unter">%s</p>' % esc(w["untertitel"]))
    inhalt.append('<p class="unter">%s · %d %s · %s %s</p>' % (
        esc(w["regal"]), anzahl_kap, esc(w["kapitel_label"] + ("s" if anzahl_kap != 1 else "")),
        "{:,}".format(anzahl_einh).replace(",", "."), esc(w["einheit_label"] + "e")))
    if w.get("umfang_hinweis"):
        inhalt.append('<div class="hinweis"><p>Umfang dieser Ausgabe: %s</p></div>' % esc(w["umfang_hinweis"]))
    knoepfe = []
    if w.get("leseansicht"):
        knoepfe.append('<a class="knopf" href="%s">Interaktive Leseansicht</a>' % w["leseansicht"])
    for label, url in w.get("leseansichten", []):
        knoepfe.append('<a class="knopf" href="%s">Leseansicht %s</a>' % (url, esc(label)))
    if w["glossar"]:
        knoepfe.append('<a class="knopf" href="%sglossar.html">Glossar</a>' % pfad)
    if knoepfe:
        inhalt.append("<p>%s</p>" % "".join(knoepfe))

    fm = w["frontmatter"] or {}
    for schluessel, label in (("vorwort", "Vorwort"), ("einfuehrung", "Einführung")):
        ps = absaetze(fm.get(schluessel))
        if ps:
            inhalt.append("<h2>%s</h2>" % label)
            inhalt.extend("<p>%s</p>" % esc(p) for p in ps)

    inhalt.append("<h2>Inhalt</h2>")
    if mehrteilig(w):
        zeilen = []
        for a in w["abschnitte"]:
            n = len(a["kapitel"])
            voll = sum(1 for k in a["kapitel"] if k["einheiten"])
            stand = ('<span class="stand">%d von %d übersetzt</span>' % (voll, n)) if n else '<span class="stand offen">noch nicht begonnen</span>'
            zeilen.append('<li><span class="nr"></span><span class="titel">'
                          '<a href="%s">%s</a></span>%s</li>' % (abschnitt_pfad(w, a), esc(a["name"] or a["key"]), stand))
        inhalt.append('<ul class="liste">%s</ul>' % "".join(zeilen))
    elif w["abschnitte"]:
        inhalt.append(_kapitel_liste(w, w["abschnitte"][0]))

    ld = {"@context": "https://schema.org", "@type": "Book",
          "name": w["titel"], "inLanguage": "de", "url": SITE + pfad,
          "description": (w["blurb"] or w["untertitel"] or "")[:300],
          "translator": {"@type": "Organization", "name": MARKE},
          "isPartOf": {"@type": "Collection", "name": MARKE, "url": SITE + "/"}}
    if w.get("autor"):
        ld["author"] = {"@type": "Person", "name": w["autor"]}

    leiste = anker_setzen(nav_regale(regal_pfad(w["regal"]))
              + nav_werke(w["regal"], WERKE_NACH_REGAL.get(w["regal"], [w]), pfad))
    schreiben(aus, pfad + "index.html", seite(
        titel="%s – deutsche Übersetzung | %s" % (w["titel"], MARKE),
        beschreibung="%s – vollständige deutsche Übersetzung, %s für %s, mit Sanskrit im Original. %s" % (
            w["titel"], w["einheit_label"], w["einheit_label"], w["blurb"] or w["untertitel"] or ""),
        kanonisch=pfad, inhalt="\n".join(inhalt), brotkrumen=brot, ld=ld, seitenleiste=leiste))
    urls.append((pfad, 0.8))

    if w["glossar"]:
        eintraege = []
        for g in w["glossar"]:
            begriff = g.get("term") or g.get("sa") or g.get("word") or ""
            erkl = g.get("definition") or g.get("explanation") or g.get("de") or g.get("gloss") or g.get("meaning") or ""
            kurz = g.get("gloss") if (g.get("gloss") and g.get("definition")) else ""
            lat = g.get("latin")
            zusatz = " ".join(x for x in [kurz, ("(%s)" % lat) if lat else ""] if x)
            if begriff or erkl:
                eintraege.append("<dt>%s</dt><dd>%s%s</dd>" % (
                    esc(begriff), esc(erkl), (" <em>%s</em>" % esc(zusatz)) if zusatz else ""))
        gpfad = pfad + "glossar.html"
        schreiben(aus, gpfad, seite(
            titel="%s – %s | %s" % (w["glossar_titel"], w["titel"], MARKE),
            beschreibung="%s zur deutschen Übersetzung der %s: %d Begriffe." % (
                w["glossar_titel"], w["titel"], len(eintraege)),
            kanonisch=gpfad,
            inhalt='<h1>%s</h1><p class="unter">%s · %d Begriffe</p><dl class="glossar">%s</dl>' % (
                esc(w["glossar_titel"]), esc(w["titel"]), len(eintraege), "".join(eintraege)),
            brotkrumen=[(MARKE, "/"), (w["regal"], regal_pfad(w["regal"])), (w["titel"], pfad), (w["glossar_titel"], None)],
            seitenleiste=leiste))
        urls.append((gpfad, 0.5))


# ================================================================ Regale, Startseite, Suche, Stand

def baue_regal(aus, regal, werke, urls):
    pfad = regal_pfad(regal)
    werke = sorted(werke, key=lambda w: w["titel"])
    zeilen = []
    for w in werke:
        einh = werk_fertig(w)
        stand = ('<span class="stand">%s %s</span>' % ("{:,}".format(einh).replace(",", "."), esc(w["einheit_label"] + "e"))
                 if einh else '<span class="stand offen">noch nicht begonnen</span>')
        blurb = '<span class="de">%s</span>' % esc((w["blurb"] or "")[:150]) if w["blurb"] else ""
        zeilen.append('<li><span class="nr"></span><span class="titel">'
                      '<a href="%s">%s</a>%s</span>%s</li>' % (werk_pfad(w), esc(w["titel"]), blurb, stand))
    gesamt = sum(werk_fertig(w) for w in werke)
    inhalt = ['<h1>%s</h1>' % esc(regal),
              '<p class="unter">%s</p>' % esc(REGAL_BESCHREIBUNG.get(regal, "")),
              '<p class="unter">%d Werke · %s übersetzte Abschnitte</p>' % (len(werke), "{:,}".format(gesamt).replace(",", ".")),
              '<ul class="liste">%s</ul>' % "".join(zeilen)]
    schreiben(aus, pfad + "index.html", seite(
        titel="%s – deutsche Übersetzungen | %s" % (regal, MARKE),
        beschreibung="%s in eigenständiger deutscher Übersetzung: %d Werke, zweisprachig mit Sanskrit. %s" % (
            regal, len(werke), REGAL_BESCHREIBUNG.get(regal, "")),
        kanonisch=pfad, inhalt="\n".join(inhalt),
        brotkrumen=[(MARKE, "/"), (regal, None)],
        seitenleiste=anker_setzen(nav_regale(pfad))))
    urls.append((pfad, 0.9))


INTRO = ("Quellen der Menschheit ist eine offene Bibliothek eigenständiger deutscher Übersetzungen "
         "klassischer Sanskrit-Literatur. Jeder Text wird Vers für Vers direkt aus dem Original "
         "erarbeitet – mit dem Sanskrit daneben und einer ausklappbaren Wort-für-Wort-Analyse, "
         "ohne vorhandene Übersetzungen als Vorlage.")


def baue_startseite(aus, nach_regal, urls):
    karten = []
    werke_gesamt = einheiten_gesamt = 0
    for regal, _, beschreibung in REGALE:
        werke = nach_regal.get(regal, [])
        if not werke:
            continue
        einh = sum(werk_fertig(w) for w in werke)
        werke_gesamt += len(werke); einheiten_gesamt += einh
        karten.append('<a class="regalkarte" href="%s"><div class="rt">%s</div>'
                      '<div class="rb">%s</div><div class="rz">%d Werke · %s übersetzte Abschnitte</div></a>'
                      % (regal_pfad(regal), esc(regal), esc(beschreibung), len(werke),
                         "{:,}".format(einh).replace(",", ".")))
    inhalt = ['<h1>%s</h1>' % MARKE,
              '<p class="unter">%s</p>' % esc(INTRO),
              '<p class="unter">%d Werke in %d Regalen · %s übersetzte Verse und Textabschnitte</p>'
              % (werke_gesamt, len(karten), "{:,}".format(einheiten_gesamt).replace(",", ".")),
              '<p><a class="knopf" href="/suche.html">Bibliothek durchsuchen</a>'
              '<a class="knopf" href="/stand.html">Stand der Übersetzungen</a></p>',
              "<h2>Regale</h2>"] + karten
    schreiben(aus, "/index.html", seite(
        titel="%s – deutsche Übersetzungen klassischer Sanskrit-Literatur" % MARKE,
        beschreibung=INTRO, kanonisch="/", inhalt="\n".join(inhalt),
        ld={"@context": "https://schema.org", "@type": "WebSite", "name": MARKE,
            "description": INTRO, "inLanguage": "de", "url": SITE + "/",
            "potentialAction": {"@type": "SearchAction",
                                "target": SITE + "/suche.html?q={search_term_string}",
                                "query-input": "required name=search_term_string"}}))
    urls.append(("/", 1.0))


def baue_suche(aus, werke, urls):
    index = []
    for w in werke:
        index.append({"t": w["titel"], "u": werk_pfad(w), "r": w["regal"], "k": "Werk"})
        for a, k in alle_kapitel(w):
            if not k["einheiten"]:
                continue
            bez = "%s %s" % (w["kapitel_label"], k["num"])
            titel = k["titel_sa"] or k["titel_de"] or bez
            index.append({"t": "%s – %s" % (bez, titel), "u": kapitel_pfad(w, a, k),
                          "r": w["regal"], "k": w["titel"] + ((", " + a["name"]) if (mehrteilig(w) and a["name"]) else "")})
    schreiben(aus, "/suchindex.json", json.dumps(index, ensure_ascii=False, separators=(",", ":")))

    skript = """
<script>
let D=[];const F=document.getElementById('suchfeld'),E=document.getElementById('ergebnis');
const norm=s=>s.toLowerCase().normalize('NFD').replace(/[\\u0300-\\u036f]/g,'');
fetch('/suchindex.json').then(r=>r.json()).then(d=>{D=d;E.innerHTML='<p class="unter">'+d.length.toLocaleString('de-DE')+' Einträge bereit.</p>';los()});
function los(){const q=norm(F.value.trim());if(q.length<2){E.innerHTML='<p class="unter">Mindestens zwei Zeichen eingeben.</p>';return}
const t=D.filter(x=>norm(x.t).includes(q)||norm(x.k).includes(q)||norm(x.r).includes(q)).slice(0,200);
E.innerHTML=t.length?'<ul class="liste">'+t.map(x=>'<li><span class="nr"></span><span class="titel"><a href="'+x.u+'">'+x.t+'</a><span class="de">'+x.k+'</span></span><span class="stand">'+x.r+'</span></li>').join('')+'</ul>':'<p class="unter">Nichts gefunden.</p>'}
F.addEventListener('input',los);
const p=new URLSearchParams(location.search).get('q');if(p){F.value=p}
</script>"""
    inhalt = ('<h1>Bibliothek durchsuchen</h1>'
              '<p class="unter">Werke, Kapitel und Abschnitte. Der Volltext jedes Kapitels steht auf der jeweiligen Seite.</p>'
              '<input id="suchfeld" type="search" placeholder="Werk, Kapitel oder Regal…" autofocus>'
              '<div id="ergebnis"><p class="unter">Index wird geladen…</p></div>' + skript)
    schreiben(aus, "/suche.html", seite(
        titel="Suche | %s" % MARKE,
        beschreibung="Durchsuche die Bibliothek Quellen der Menschheit nach Werken und Kapiteln.",
        kanonisch="/suche.html", inhalt=inhalt, brotkrumen=[(MARKE, "/"), ("Suche", None)]))
    urls.append(("/suche.html", 0.4))


def pruefe_vollstaendigkeit(werke):
    """Sucht die Stellen, an denen Text fehlt: ganz leere Werke, leere Werkteile
    (z.B. ein Parva ohne ein einziges Kapitel) und Kapitel ohne Verse."""
    luecken = []
    for w in werke:
        kap = alle_kapitel(w)
        leere_teile = [a for a in w["abschnitte"] if not a["kapitel"]]
        leere_kapitel = [(a, k) for a, k in kap if not k["einheiten"]]
        eintrag = {"werk": w, "leere_teile": leere_teile, "leere_kapitel": leere_kapitel,
                   "teile_gesamt": len(w["abschnitte"]), "kapitel_gesamt": len(kap)}
        if not kap:
            eintrag["art"] = "ohne Inhalt"
        elif len(leere_kapitel) == len(kap):
            eintrag["art"] = "noch nicht begonnen"
        elif leere_kapitel or leere_teile:
            eintrag["art"] = "teilweise übersetzt"
        else:
            continue
        luecken.append(eintrag)
    return luecken


def luecken_text(l):
    """Ein Satz, der die Luecke eines Werks beschreibt."""
    w = l["werk"]
    if l["art"] in ("ohne Inhalt", "noch nicht begonnen"):
        return l["art"]
    teile = []
    if l["leere_teile"]:
        teile.append("%d von %d %s ohne ein einziges Kapitel"
                     % (len(l["leere_teile"]), l["teile_gesamt"], w["abschnitt_label"] + "s"))
    if l["leere_kapitel"]:
        teile.append("%d von %d %s ohne Verse"
                     % (len(l["leere_kapitel"]), l["kapitel_gesamt"], w["kapitel_label"] + "s"))
    return "; ".join(teile)


def baue_stand(aus, werke, luecken, urls):
    nach_regal = {}
    for w in werke:
        nach_regal.setdefault(w["regal"], []).append(w)
    luecke_von = {id(l["werk"]): l for l in luecken}
    teile = ['<h1>Stand der Übersetzungen</h1>',
             '<p class="unter">Diese Übersicht wird bei jedem Bau der Seite neu erzeugt. '
             'Sie zeigt offen, was fertig ist und was noch aussteht.</p>']
    for regal, _, _ in REGALE:
        ws = nach_regal.get(regal)
        if not ws:
            continue
        teile.append("<h2>%s</h2>" % esc(regal))
        zeilen = []
        for w in sorted(ws, key=lambda x: x["titel"]):
            kap = alle_kapitel(w)
            voll = sum(1 for _, k in kap if k["einheiten"])
            l = luecke_von.get(id(w))
            if not l:
                stand = '<span class="stand">vollständig · %d %s</span>' % (len(kap), esc(w["kapitel_label"]))
            else:
                stand = '<span class="stand offen">%s</span>' % esc(luecken_text(l))
            zeilen.append('<li><span class="nr"></span><span class="titel"><a href="%s">%s</a></span>%s</li>'
                          % (werk_pfad(w), esc(w["titel"]), stand))
        teile.append('<ul class="liste">%s</ul>' % "".join(zeilen))
    schreiben(aus, "/stand.html", seite(
        titel="Stand der Übersetzungen | %s" % MARKE,
        beschreibung="Welche Werke der Bibliothek Quellen der Menschheit vollständig übersetzt sind und welche noch im Aufbau.",
        kanonisch="/stand.html", inhalt="\n".join(teile), brotkrumen=[(MARKE, "/"), ("Stand", None)]))
    urls.append(("/stand.html", 0.4))


def baue_ueber(aus, urls):
    inhalt = """<h1>Über diese Bibliothek</h1>
<p class="unter">%s</p>
<h2>Wie die Übersetzungen entstehen</h2>
<p>Jeder Text wird direkt aus dem Sanskrit erarbeitet, Vers für Vers, ohne eine vorhandene Übersetzung
als Ausgangspunkt. Zu jedem Vers stehen der Sanskrit-Text in wissenschaftlicher Umschrift (IAST),
die deutsche Übersetzung und – wo vorhanden – eine ausklappbare Wort-für-Wort-Analyse.
Unsichere Lesarten sind mit [?] gekennzeichnet, Ergänzungen des Übersetzers mit [Anm.: …].</p>
<h2>Aufbau</h2>
<p>Die Bibliothek ist nach den klassischen Gattungen der Sanskrit-Literatur geordnet. Jedes Kapitel
hat eine eigene Seite mit eigener Adresse, damit einzelne Stellen auffindbar und zitierbar sind.
Der <a href="/stand.html">Stand der Übersetzungen</a> zeigt offen, was fertig ist und was noch aussteht.</p>
<h2>Nutzung</h2>
<p>Alle Übersetzungen sind gemeinfrei. Sie dürfen ohne Rückfrage kopiert, zitiert und weiterverwendet werden.</p>
""" % esc(INTRO)
    schreiben(aus, "/ueber.html", seite(
        titel="Über | %s" % MARKE, beschreibung=INTRO, kanonisch="/ueber.html",
        inhalt=inhalt, brotkrumen=[(MARKE, "/"), ("Über", None)]))
    urls.append(("/ueber.html", 0.3))


def baue_sitemap(aus, urls):
    """Eine Sitemap je Regal plus ein Sitemap-Index. Das haelt die einzelnen
    Dateien klein und macht in der Search Console sichtbar, welcher Teil der
    Bibliothek indexiert ist und welcher nicht."""
    regal_slugs = {sl for _, sl, _ in REGALE}
    gruppen = {}
    for pfad, prio in urls:
        erstes = pfad.strip("/").split("/")[0] if pfad != "/" else ""
        gruppe = erstes if erstes in regal_slugs else "seiten"
        gruppen.setdefault(gruppe, []).append((pfad, prio))

    heute = __import__("datetime").date.today().isoformat()
    sitemaps = []
    for gruppe in sorted(gruppen):
        eintraege = "".join(
            '<url><loc>%s%s</loc><priority>%.1f</priority></url>' % (SITE, pfad, prio)
            for pfad, prio in gruppen[gruppe])
        name = "/sitemaps/%s.xml" % gruppe
        schreiben(aus, name,
                  '<?xml version="1.0" encoding="UTF-8"?>\n'
                  '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">%s</urlset>\n' % eintraege)
        sitemaps.append((name, len(gruppen[gruppe])))

    index = "".join('<sitemap><loc>%s%s</loc><lastmod>%s</lastmod></sitemap>' % (SITE, name, heute)
                    for name, _ in sitemaps)
    schreiben(aus, "/sitemap.xml",
              '<?xml version="1.0" encoding="UTF-8"?>\n'
              '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">%s</sitemapindex>\n' % index)
    schreiben(aus, "/robots.txt", "User-agent: *\nAllow: /\n\nSitemap: %s/sitemap.xml\n" % SITE)
    print("Sitemaps: %s" % ", ".join("%s (%d)" % (n.split("/")[-1], z) for n, z in sitemaps))


# ================================================================ Leseansicht (die bisherigen interaktiven Apps)

def baue_leseansicht(roh_pfad, aus, kurz, titel, zurueck_pfad):
    """Rehostet die App aus dem Artifact. Bewusst noindex + canonical auf die
    Werkseite: der Inhalt steht als Einzelkapitel schon crawlbar in der Bibliothek,
    die App waere nur ein riesiges Duplikat."""
    inhalt = _huelle_entfernen(open(roh_pfad, encoding="utf-8").read())
    kopf = """<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>%s – Leseansicht | %s</title>
<meta name="robots" content="noindex,follow">
<link rel="canonical" href="%s%s">
""" % (esc(titel), MARKE, SITE, zurueck_pfad)

    marker = '<div id="app-root">'
    i = inhalt.find(marker)
    if i == -1:
        seite_html = kopf + "</head>\n<body>\n" + inhalt + "\n</body>\n</html>\n"
    else:
        seite_html = kopf + inhalt[:i] + "</head>\n<body>\n" + inhalt[i:]
        if not seite_html.rstrip().endswith("</html>"):
            seite_html += "\n</body>\n</html>\n"

    # Rueckweg in die Bibliothek in die Topbar haengen (wenn die App eine hat)
    tb = '<div class="topbar-actions">'
    j = seite_html.find(tb)
    if j != -1:
        nav = ('<nav style="display:flex;align-items:center"><a href="%s" '
               'style="font-size:13px;font-weight:600;color:inherit;opacity:.75;'
               'text-decoration:none;white-space:nowrap;margin-right:.9rem">← Bibliothek</a></nav>' % zurueck_pfad)
        seite_html = seite_html[:j] + nav + seite_html[j:]
    schreiben(aus, "/leseansicht/%s.html" % kurz, seite_html)


# ================================================================ Hauptlauf

def werke_entdoppeln(werke):
    """Gleicher Slug im gleichen Regal: der Eintrag mit mehr Text gewinnt,
    die Weiterleitungen des anderen werden uebernommen."""
    nach_schluessel = {}
    reihenfolge = []
    for w in werke:
        s = (w["regal"], w["slug"])
        if s not in nach_schluessel:
            nach_schluessel[s] = w
            reihenfolge.append(s)
            continue
        alt = nach_schluessel[s]
        gewinner, verlierer = (w, alt) if werk_fertig(w) > werk_fertig(alt) else (alt, w)
        gewinner["alt_urls"] = list(dict.fromkeys(gewinner["alt_urls"] + verlierer["alt_urls"]))
        if not gewinner.get("leseansicht") and verlierer.get("leseansicht"):
            gewinner["leseansicht"] = verlierer["leseansicht"]
        nach_schluessel[s] = gewinner
        print("   Doppelt: %s / %s -> %d statt %d Abschnitte" % (
            w["regal"], w["slug"], werk_fertig(gewinner), werk_fertig(verlierer)))
    return [nach_schluessel[s] for s in reihenfolge]


def bauen(raw_dir, aus, md_quellen=()):
    werke = []
    def hole(datei):
        p = os.path.join(raw_dir, datei)
        return p if os.path.exists(p) else None

    if hole("bibliothek.html"):
        print("== Bibliothek =="); werke += werke_aus_bibliothek(hole("bibliothek.html"), "bibliothek")
    if hole("ramayana.html"):
        print("== Rāmāyaṇa =="); werke += werke_aus_bibliothek(hole("ramayana.html"), "ramayana")
    if hole("mahabharata.html"):
        print("== Mahābhārata ==")
        fortsetzungen = [hole(f) for f in ("mahabharata2.html", "mahabharata3.html", "mahabharata4.html")]
        fortsetzungen = [f for f in fortsetzungen if f]
        mb = werk_aus_einzelwerk(
            hole("mahabharata.html"), regal="Epen", werk_slug="mahabharata",
            alt_praefix="mahabharata", leseansicht_slug="mahabharata",
            fortsetzungen=fortsetzungen)
        if fortsetzungen:
            mb[0]["leseansichten"] = [("Teil 1", "/leseansicht/mahabharata.html")] + [
                ("Teil %d" % (i + 2), "/leseansicht/mahabharata%d.html" % (i + 2))
                for i in range(len(fortsetzungen))]
        werke += mb
    if hole("aranyakas.html"):
        print("== Āraṇyakas =="); werke += werke_aus_sammlung(
            hole("aranyakas.html"), regal="Āraṇyakas", alt_praefix="aranyakas", leseansicht_slug="aranyakas")
    if hole("mahapuranas.html"):
        print("== Mahāpurāṇas =="); werke += werke_aus_sammlung(
            hole("mahapuranas.html"), regal="Purāṇas", alt_praefix="mahapuranas", leseansicht_slug="mahapuranas")
    if hole("tantras.html"):
        print("== Tantras & Āgamas =="); werke += werke_aus_tantras(hole("tantras.html"))

    for q in md_quellen:
        print("== Markdown: %s ==" % os.path.basename(q["datei"]))
        werke.append(werk_aus_markdown(q["datei"], regal=q.get("regal"),
                                       werk_slug=q.get("slug"), status=q.get("umfang")))

    werke = werke_entdoppeln(werke)

    nach_regal = {}
    for w in werke:
        nach_regal.setdefault(w["regal"], []).append(w)
    WERKE_NACH_REGAL.clear()
    WERKE_NACH_REGAL.update(nach_regal)

    urls = []
    geschrieben = set()
    baue_startseite(aus, nach_regal, urls); geschrieben.add("/index.html")
    for regal in nach_regal:
        baue_regal(aus, regal, nach_regal[regal], urls)
        geschrieben.add(regal_pfad(regal) + "index.html")

    for w in werke:
        baue_werk(aus, w, urls); geschrieben.add(werk_pfad(w) + "index.html")
        kap = alle_kapitel(w)
        for idx, (a, k) in enumerate(kap):
            vorher = nachher = None
            if idx > 0:
                pa, pk = kap[idx - 1]
                vorher = (kapitel_pfad(w, pa, pk), "%s %s" % (w["kapitel_label"], pk["num"]))
            if idx < len(kap) - 1:
                na, nk = kap[idx + 1]
                nachher = (kapitel_pfad(w, na, nk), "%s %s" % (w["kapitel_label"], nk["num"]))
            baue_kapitel(aus, w, a, k, vorher, nachher, urls)
            geschrieben.add(kapitel_pfad(w, a, k))
        if mehrteilig(w):
            for a in w["abschnitte"]:
                baue_abschnitt(aus, w, a, urls)
                geschrieben.add(abschnitt_pfad(w, a) + "index.html")

    baue_suche(aus, werke, urls)
    luecken = pruefe_vollstaendigkeit(werke)
    baue_stand(aus, werke, luecken, urls)
    baue_ueber(aus, urls)
    baue_sitemap(aus, urls)
    schreiben(aus, "/stil.css", STIL)
    schreiben(aus, "/%s.txt" % INDEXNOW_KEY, INDEXNOW_KEY)
    schreiben(aus, "/CNAME", "quellendermenschheit.de\n")

    # Weiterleitungen von den alten Adressen
    umgeleitet = 0
    for w in werke:
        for alt in w["alt_urls"]:
            if alt in geschrieben:
                continue
            weiterleitung(aus, alt, werk_pfad(w)); umgeleitet += 1
        for a in w["abschnitte"]:
            alt = a.get("alt_url")
            if alt and alt not in geschrieben:
                weiterleitung(aus, alt, abschnitt_pfad(w, a)); umgeleitet += 1
    for alt, ziel in (("/bibliothek/index.html", "/"),
                      ("/mahapuranas/index.html", regal_pfad("Purāṇas")),
                      ("/mahabharata/index.html", "/epen/mahabharata/")):
        if alt not in geschrieben:
            weiterleitung(aus, alt, ziel); umgeleitet += 1

    return werke, urls, luecken, umgeleitet


LESEANSICHTEN = [
    # (Kurzname, Rohdatei, Titel, Rueckweg in die Bibliothek)
    ("bibliothek",  "bibliothek.html",  "Quellen der Menschheit", "/"),
    ("ramayana",    "ramayana.html",    "Rāmāyaṇa",               "/epen/ramayana/"),
    ("mahabharata", "mahabharata.html", "Mahābhārata",            "/epen/mahabharata/"),
    ("mahabharata2", "mahabharata2.html", "Mahābhārata (Teil 2)",  "/epen/mahabharata/"),
    ("mahabharata3", "mahabharata3.html", "Mahābhārata (Teil 3)",  "/epen/mahabharata/"),
    ("mahabharata4", "mahabharata4.html", "Mahābhārata (Teil 4)",  "/epen/mahabharata/"),
    ("aranyakas",   "aranyakas.html",   "Āraṇyakas",              "/aranyakas/"),
    ("tantras",     "tantras.html",     "Tantras & Āgamas",       "/tantras/"),
    ("mahapuranas", "mahapuranas.html", "Mahāpurāṇas",            "/puranas/"),
]

MD_QUELLEN = [
    {"datei": "/home/main/Downloads/satcakranirupana_verse_00-13.md",
     "regal": "Tantras & Āgamas", "slug": "satcakranirupana",
     "umfang": "Verse 0–13 (Einleitung, Nāḍīs, Mūlādhāra-Cakra). Der vollständige Text hat 55 Verse."},
]


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Baut die Bibliothek quellendermenschheit.de")
    ap.add_argument("--raw", default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "raw"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--ohne-leseansicht", action="store_true",
                    help="die grossen interaktiven Apps nicht mitkopieren (schnellerer Testbau)")
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)
    md = [q for q in MD_QUELLEN if os.path.exists(q["datei"])]
    werke, urls, luecken, umgeleitet = bauen(a.raw, a.out, md)

    if not a.ohne_leseansicht:
        for kurz, datei, titel, zurueck in LESEANSICHTEN:
            p = os.path.join(a.raw, datei)
            if os.path.exists(p):
                baue_leseansicht(p, a.out, kurz, titel, zurueck)

    kapitel = sum(len(alle_kapitel(w)) for w in werke)
    einheiten = sum(werk_fertig(w) for w in werke)
    print()
    print("Werke:        %d" % len(werke))
    print("Kapitel:      %d" % kapitel)
    print("Einheiten:    %s" % "{:,}".format(einheiten).replace(",", "."))
    print("URLs Sitemap: %d" % len(urls))
    print("Weiterleitungen: %d" % umgeleitet)
    print()
    print("=== VOLLSTÄNDIGKEIT ===")
    if not luecken:
        print("Keine Lücken gefunden.")
    else:
        nicht_begonnen = [l for l in luecken if l["art"] in ("noch nicht begonnen", "ohne Inhalt")]
        teilweise = [l for l in luecken if l["art"] == "teilweise übersetzt"]
        print("%d Werke teilweise übersetzt, %d noch nicht begonnen." % (len(teilweise), len(nicht_begonnen)))
        print()
        for l in teilweise:
            w = l["werk"]
            print("  TEILWEISE  %-18s %-34s %s" % (w["regal"][:18], w["titel"][:34], luecken_text(l)))
            for teil in l["leere_teile"][:40]:
                print("               fehlt ganz: %s" % (teil["name"] or teil["key"]))
        if nicht_begonnen:
            print()
            print("  Noch nicht begonnen (%d):" % len(nicht_begonnen))
            for l in nicht_begonnen:
                w = l["werk"]
                print("    %-18s %s" % (w["regal"][:18], w["titel"]))
    print()
    print("Fertig in", a.out)


if __name__ == "__main__":
    main()
