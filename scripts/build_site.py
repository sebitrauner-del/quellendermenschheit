#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Baut die komplette Webseite quellendermenschheit.de aus ALLEN FÜNF
Übersetzungsprojekten (Quellen der Menschheit / Bibliothek, Mahābhārata,
Āraṇyakas, Tantras & Āgamas, Mahāpurāṇas).

Jedes Projekt lebt in einem eigenen Claude-Artifact und wird als eigene
interaktive Unterseite (rehostete SPA) UNTER EINEM EIGENEN PFAD veröffentlicht,
plus statischen, crawlbaren Einzel-Werk-Seiten für SEO. Die Startseite der
Domain ist ein neues, schlankes Hub, das auf alle fünf Projekte verweist.

Aufruf:
    python3 build_site.py \
        --bibliothek raw_bibliothek.html \
        --mahabharata raw_mahabharata.html \
        --aranyakas raw_aranyakas.html \
        --tantras raw_tantras.html \
        --mahapuranas raw_mahapuranas.html \
        --out OUTPUT_DIR

Jede --<projekt> Quelle ist optional: fehlt eine, wird das jeweilige
Unterverzeichnis einfach nicht neu erzeugt (bestehender Stand bleibt liegen,
wenn OUTPUT_DIR schon existiert) - so kann die Automatisierung auch dann
weiterlaufen, wenn ein einzelnes Artifact gerade nicht erreichbar ist.
"""
import re, json, base64, gzip, html, os, argparse, sys

SITE = "https://quellendermenschheit.de"

# ---------------------------------------------------------------- Hilfsfunktionen

def esc(s):
    """Robust gegen die Formate, die in den Artifact-Daten historisch gewachsen
    sind: einzelne Strings, Zahlen, None - und gelegentlich Listen von Absätzen
    (z.B. eine mehrteilige Kapitel-Anmerkung)."""
    if not s:
        return ""
    if isinstance(s, (list, tuple)):
        s = " ".join(str(x) for x in s if x)
    elif not isinstance(s, str):
        s = str(s)
    return html.escape(s, quote=False)

def as_paragraphs(v):
    """Gibt eine Liste von Absatz-Strings zurueck - egal ob die Quelle einen
    einzelnen String oder bereits eine Liste geliefert hat."""
    if not v:
        return []
    if isinstance(v, str):
        return [v]
    if isinstance(v, (list, tuple)):
        return [x for x in v if x]
    return [str(v)]

def strip_wrapper(raw):
    """Extrahiert den Inhalt zwischen <body ...> und </body> aus einem
    per Artifact-Tool exportierten Roh-HTML (das die claude.ai-Seitenhülle
    <!doctype html><html><head>...</head><body>...</body></html> enthält)."""
    m_open = re.search(r"<body[^>]*>", raw, re.IGNORECASE)
    m_close = re.search(r"</body\s*>", raw, re.IGNORECASE)
    if not m_open or not m_close or m_close.start() <= m_open.end():
        sys.exit("ERROR: konnte <body>...</body>-Hülle nicht finden")
    return raw[m_open.end():m_close.start()]

def load_json_script(content, script_id):
    m = re.search(r'<script id="' + re.escape(script_id) + r'"[^>]*>(.*?)</script>', content, re.DOTALL)
    if not m:
        return None
    return json.loads(m.group(1))

def load_gzip_script(content, script_id):
    m = re.search(r'<script id="' + re.escape(script_id) + r'"[^>]*>(.*?)</script>', content, re.DOTALL)
    if not m:
        return None
    raw = base64.b64decode(m.group(1).strip())
    return json.loads(gzip.decompress(raw))

# ---------------------------------------------------------------- gemeinsames CSS für statische Lese-Seiten

def page_css(accent, accent_strong):
    return f"""
:root{{
  --bg:#EAE4D8; --bg-elevated:#F5F1E7; --bg-card:#F2ECDE;
  --ink:#241E17; --ink-soft:#5B5142; --ink-faint:#8A8069;
  --line:#D3C9B4; --gold:{accent}; --gold-strong:{accent_strong};
  --font-display:"Spectral", Georgia, serif;
  --font-body:"Source Sans 3", -apple-system, "Segoe UI", sans-serif;
}}
@media (prefers-color-scheme: dark){{
  :root{{
    --bg:#1B1712; --bg-elevated:#242019; --bg-card:#221E17;
    --ink:#ECE4D2; --ink-soft:#BDB093; --ink-faint:#847A63;
    --line:#3A3325; --gold:{accent}; --gold-strong:{accent_strong};
  }}
}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);font-family:var(--font-body);line-height:1.6}}
a{{color:var(--gold-strong)}}
header.site{{padding:1.2rem 1.5rem;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:.5rem}}
header.site a.brand{{font-family:var(--font-display);font-weight:600;font-size:1.15rem;text-decoration:none;color:var(--ink)}}
header.site .crumbs{{font-size:.85rem;color:var(--ink-soft)}}
header.site .crumbs a{{color:var(--ink-soft)}}
main{{max-width:780px;margin:0 auto;padding:2rem 1.25rem 4rem}}
h1{{font-family:var(--font-display);font-size:2rem;margin:.2rem 0}}
h1 .sa{{display:block;font-style:italic;color:var(--ink-soft);font-size:1.15rem;font-weight:400;margin-top:.3rem}}
.subtitle{{color:var(--ink-soft);font-size:1.02rem;margin:.5rem 0 1.5rem}}
.cta{{display:inline-block;margin:.5rem .6rem .5rem 0;padding:.6rem 1.1rem;border:1px solid var(--gold);border-radius:8px;text-decoration:none;color:var(--gold-strong);font-weight:600}}
.cta:hover{{background:var(--gold);color:var(--bg-elevated)}}
section.frontmatter p{{margin:0 0 1rem}}
h2.section-title{{font-family:var(--font-display);border-bottom:1px solid var(--line);padding-bottom:.3rem;margin-top:2.5rem}}
h3.division-title{{font-family:var(--font-display);color:var(--gold-strong);margin-top:2rem}}
h4.chapter-title{{font-family:var(--font-display);margin-top:1.5rem}}
h4.chapter-title .de{{display:block;font-weight:400;font-style:italic;color:var(--ink-soft);font-size:.95rem}}
.chapter-note{{background:var(--bg-card);border-left:3px solid var(--gold);border-radius:0 8px 8px 0;padding:.7rem 1rem;font-size:.85rem;color:var(--ink-soft);margin:.6rem 0 1.2rem}}
.chapter-note p{{margin:0 0 .55rem}}
.chapter-note p:last-child{{margin-bottom:0}}
.unit{{margin:0 0 1.1rem;padding-bottom:1.1rem;border-bottom:1px dashed var(--line)}}
.unit .n{{color:var(--ink-faint);font-size:.85rem;font-weight:600}}
.unit .sa{{font-style:italic;color:var(--ink-soft);margin:.2rem 0}}
.unit .de{{margin:.2rem 0}}
.unit .notes{{font-size:.82rem;color:var(--ink-faint);font-style:italic;margin-top:.2rem}}
dl.glossary{{display:grid;grid-template-columns:max-content 1fr;gap:.4rem 1rem}}
dl.glossary dt{{font-weight:600;font-style:italic}}
dl.glossary dd{{margin:0}}
.work-list{{display:grid;gap:2px;margin-top:1rem}}
.wl-item{{display:flex;gap:12px;padding:10px 0;border-bottom:1px solid var(--line);align-items:baseline}}
.wl-num{{font-size:.75rem;color:var(--ink-faint);flex:0 0 26px}}
.wl-name{{font-family:var(--font-display);font-style:italic;font-weight:600;font-size:1rem}}
.wl-name a{{text-decoration:none;color:inherit}}
.wl-name a:hover{{color:var(--gold-strong)}}
.wl-status{{font-size:.78rem;color:var(--ink-faint);font-style:italic;margin-left:auto;white-space:nowrap}}
.wl-status.active{{color:var(--gold-strong);font-weight:600;font-style:normal}}
.group-heading{{font-family:var(--font-display);font-size:1.05rem;color:var(--gold-strong);text-transform:uppercase;letter-spacing:.04em;border-bottom:1px solid var(--line);padding-bottom:.3rem;margin-top:2rem}}
footer.site{{border-top:1px solid var(--line);padding:2rem 1.25rem;text-align:center;color:var(--ink-faint);font-size:.9rem}}
footer.site a{{color:var(--ink-faint)}}
"""

def render_frontmatter_html(fm):
    parts = []
    if fm:
        parts.append('<section class="frontmatter">')
        for key, label in (("vorwort", "Vorwort"), ("einfuehrung", "Einführung")):
            paras = as_paragraphs(fm.get(key))
            if paras:
                parts.append(f'<h2 class="section-title">{label}</h2>')
                for p in paras:
                    parts.append(f"<p>{esc(p)}</p>")
        parts.append("</section>")
    return "".join(parts)

def render_chapters_html(chapters, chapter_label, unit_label, show_division_title=None):
    parts = []
    if show_division_title:
        parts.append(f'<h3 class="division-title">{esc(show_division_title)}</h3>')
    for ch in chapters:
        ctitle_sa = ch.get("title_sa") or ""
        ctitle_de = ch.get("title_de") or ""
        parts.append(f'<h4 class="chapter-title">{esc(chapter_label)} {esc(str(ch.get("num","")))}: {esc(ctitle_sa)}<span class="de">{esc(ctitle_de)}</span></h4>')
        note_paras = as_paragraphs(ch.get("note"))
        if note_paras:
            inner = "".join(f"<p>{esc(p)}</p>" for p in note_paras)
            parts.append(f'<div class="chapter-note">{inner}</div>')
        for u in ch.get("units", []):
            notes = u.get("notes")
            parts.append(
                f'<div class="unit"><div class="n">{esc(unit_label)} {esc(str(u.get("n","")))}</div>'
                f'<div class="sa">{esc(u.get("sa",""))}</div>'
                f'<div class="de">{esc(u.get("de",""))}</div>'
                + (f'<div class="notes">{esc(notes)}</div>' if notes else "")
                + '</div>'
            )
    return "".join(parts)

def render_glossary_html(glossary, glossary_title):
    if not glossary:
        return ""
    parts = [f'<h2 class="section-title">{esc(glossary_title or "Glossar")}</h2>', '<dl class="glossary">']
    for g in glossary:
        term = g.get("term") or g.get("sa") or g.get("word") or ""
        expl = g.get("definition") or g.get("explanation") or g.get("de") or g.get("meaning") or ""
        if term or expl:
            parts.append(f"<dt>{esc(str(term))}</dt><dd>{esc(str(expl))}</dd>")
    parts.append("</dl>")
    return "".join(parts)

def render_static_page(*, title, subtitle, desc, canonical, reader_url, accent, accent_strong,
                        hub_label, hub_href, back_label, back_href,
                        body_head_extra, frontmatter_html, content_html, cta_label="Zur interaktiven Leseansicht (mit Kapitel-Navigation)"):
    return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{canonical}">
<meta property="og:type" content="book">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{canonical}">
<meta property="og:site_name" content="Quellen der Menschheit">
<meta name="twitter:card" content="summary">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Spectral:ital,wght@0,400;0,500;0,600;1,400;1,500&family=Source+Sans+3:wght@400;500;600;700&display=swap">
{body_head_extra}
<style>{page_css(accent, accent_strong)}</style>
</head>
<body>
<header class="site">
  <a class="brand" href="/index.html">Quellen der Menschheit</a>
  <div class="crumbs"><a href="{hub_href}">{esc(hub_label)}</a> &middot; <a href="{back_href}">{esc(back_label)}</a></div>
</header>
<main>
<h1>{esc(title.split(' – ')[0] if ' – ' in title else title)}</h1>
<p class="subtitle">{esc(subtitle)}</p>
<a class="cta" href="{reader_url}">{cta_label}</a>
{frontmatter_html}
{content_html}
</main>
<footer class="site">
  <p>Teil von <a href="/index.html">Quellen der Menschheit</a> &middot; zweisprachige Leseausgaben klassischer Sanskrit-Texte</p>
</footer>
</body>
</html>"""

# ---------------------------------------------------------------- SPA-Rehosting (interaktive Unterseiten)

NAV_CSS_TEMPLATE = """
.topbar-nav{{ display:flex; gap:14px; flex:0 0 auto; }}
.topbar-nav-link{{ font-size:13px; font-weight:600; color:var(--ink-soft); text-decoration:none; white-space:nowrap; }}
.topbar-nav-link:hover{{ color:{accent_strong}; }}
@media(max-width:720px){{ .topbar-nav{{ display:none; }} }}
#werke-uebersicht{{ max-width:1040px; margin:0 auto; padding:28px 18px 6px; }}
#werke-uebersicht h1{{ font-family:var(--font-display); font-size:26px; margin:0 0 10px; }}
#werke-uebersicht .lead{{ color:var(--ink-soft); font-size:15px; max-width:70ch; margin:0 0 26px; line-height:1.6; }}
.werke-group{{ margin-bottom:26px; }}
.werke-group h2{{ font-family:var(--font-display); font-size:15px; text-transform:uppercase; letter-spacing:.06em; color:{accent_strong}; border-bottom:1px solid var(--line); padding-bottom:6px; margin:0 0 12px; }}
.werke-grid{{ display:grid; grid-template-columns:repeat(auto-fill,minmax(240px,1fr)); gap:14px; }}
.werk-card{{ display:block; padding:14px 15px; border:1px solid var(--line); border-radius:10px; background:var(--bg-card); text-decoration:none; color:var(--ink); }}
.werk-card:hover{{ border-color:{accent}; }}
.werk-card .wt{{ font-family:var(--font-display); font-weight:600; font-size:15px; }}
.werk-card .wb{{ font-size:12.5px; color:var(--ink-soft); margin-top:4px; line-height:1.5; }}
"""

def build_spa_page(raw_content, *, title, desc, canonical, ld_json, accent, accent_strong,
                    home_nav_label, home_nav_href, overview_html):
    """Verwandelt den nackten <body>-Inhalt eines Artifacts in eine eigenständige,
    SEO-fähige index.html: fügt doctype/head/meta/JSON-LD hinzu, öffnet <body>,
    setzt einen 'Startseite'-Navigationslink in die Topbar, und injiziert eine
    für Suchmaschinen/No-JS sofort sichtbare (für JS-Browser sofort wieder
    versteckte) Übersichtssektion direkt nach der Kopfzeile."""
    content = raw_content

    # alten bloßen <title>...</title> am Anfang entfernen (wird durch head-Prolog ersetzt)
    content = re.sub(r'^\s*<title>[^<]*</title>\s*\n?', "", content, count=1)

    head = f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{canonical}">
<meta property="og:type" content="website">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{canonical}">
<meta property="og:site_name" content="Quellen der Menschheit">
<meta name="twitter:card" content="summary">
<script type="application/ld+json">
{json.dumps(ld_json, ensure_ascii=False)}
</script>
"""
    content = head + content.lstrip("\n")

    # </head> vor <div id="app-root"> setzen, <body> öffnen
    marker = '<div id="app-root">'
    idx = content.find(marker)
    if idx == -1:
        sys.exit("ERROR: <div id=\"app-root\"> Marker nicht gefunden")
    content = content[:idx] + "</head>\n<body>\n" + content[idx:]

    # Nav-Link "Startseite" (zurück zum Hub) in die Topbar einfügen
    nav_links = (f'<nav class="topbar-nav">'
                 f'<a href="{home_nav_href}" class="topbar-nav-link">{esc(home_nav_label)}</a>'
                 f'</nav>\n    ')
    tb_marker = '<div class="topbar-actions">'
    idx2 = content.find(tb_marker)
    if idx2 == -1:
        sys.exit("ERROR: topbar-actions Marker nicht gefunden")
    content = content[:idx2] + nav_links + content[idx2:]

    # Nav-CSS injizieren -- MUSS passieren bevor wir das </style> in Body wickeln,
    # daher: direkt vor </style>\n<div id="app-root"> Marker suchen.
    nav_css = NAV_CSS_TEMPLATE.format(accent=accent, accent_strong=accent_strong)
    style_marker = "</style>\n<div id=\"app-root\">"
    if style_marker in content:
        content = content.replace(style_marker, nav_css + style_marker, 1)
    else:
        # bereits umgewickelt (</head>\n<body>\n davor) -> gegen die Variante mit Body-Tag matchen
        alt_marker = "</style>\n</head>\n<body>\n<div id=\"app-root\">"
        content = content.replace(alt_marker, nav_css + "</style>\n</head>\n<body>\n<div id=\"app-root\">", 1)

    # statische Übersichtssektion nach </header> einfügen + sofort per Script verstecken
    header_close = "</header>"
    idx3 = content.find(header_close)
    if idx3 == -1:
        sys.exit("ERROR: </header> Marker nicht gefunden")
    idx3end = idx3 + len(header_close)
    hide_script = f'<script>document.getElementById("werke-uebersicht").style.display="none";</script>'
    content = content[:idx3end] + overview_html + hide_script + content[idx3end:]

    if not content.rstrip().endswith("</html>"):
        content += "\n</body>\n</html>\n"
    return content

# ---------------------------------------------------------------- Projekt 1: Bibliothek ("Quellen der Menschheit")

def build_bibliothek(raw_path, out_dir, extra_raw_paths=None):
    """extra_raw_paths: optionale Liste weiterer Artifact-Roh-HTML-Dateien, die -
    wie z.B. das eigenständige Rāmāyaṇa-Artifact - dieselbe data-meta/data-<id>-
    Struktur verwenden, aber aus Größengründen in einem eigenen Artifact leben.
    Ihre Bücher werden der Bibliotheks-Übersicht ganz normal als weitere
    Werke/Gruppen hinzugefügt."""
    with open(raw_path, encoding="utf-8") as f:
        raw = f.read()
    content = strip_wrapper(raw)
    meta = load_json_script(content, "data-meta")
    books_meta = list(meta["books"])
    # (Buch-Metadaten, Roh-Content in dem das zugehörige data-<id>-Gzip-Script steht)
    sources = [(bm, content) for bm in books_meta]

    for extra_path in (extra_raw_paths or []):
        with open(extra_path, encoding="utf-8") as f:
            eraw = f.read()
        econtent = strip_wrapper(eraw)
        emeta = load_json_script(econtent, "data-meta")
        for ebm in emeta["books"]:
            books_meta.append(ebm)
            sources.append((ebm, econtent))

    accent, accent_strong = "#8C6A2C", "#6E5220"
    base = os.path.join(out_dir, "bibliothek")
    os.makedirs(base, exist_ok=True)

    HOME_DESC = ("Quellen der Menschheit ist eine öffentliche, kostenlose Bibliothek "
                 "eigenständiger deutscher Übersetzungen klassischer Sanskrit- und "
                 "vedischer Texte – zweisprachig, Vers für Vers, direkt aus dem Original "
                 "erarbeitet.")

    generated = []
    for bm, src_content in sources:
        book_id = bm["id"]
        book = load_gzip_script(src_content, "data-" + book_id)
        title = book["title"]
        subtitle = book.get("subtitle") or ""
        desc = (bm.get("blurb") or bm.get("subtitle") or subtitle or "")[:280]
        canonical = f"{SITE}/bibliothek/{book_id}.html"
        reader_url = f"{SITE}/bibliothek/index.html#/b/{book_id}"

        divisions = book.get("divisions", [])
        multi_div = len(divisions) > 1
        chapters_html_parts = []
        for div in divisions:
            chapters_html_parts.append(render_chapters_html(
                div.get("chapters", []),
                book.get("chapter_label") or "Kapitel",
                book.get("unit_label") or "Vers",
                show_division_title=div.get("name") if multi_div else None,
            ))
        content_html = "".join(chapters_html_parts) + render_glossary_html(book.get("glossary"), book.get("glossary_title"))

        page = render_static_page(
            title=f"{title} – deutsche Übersetzung | Quellen der Menschheit",
            subtitle=subtitle, desc=desc, canonical=canonical, reader_url=reader_url,
            accent=accent, accent_strong=accent_strong,
            hub_label="Quellen der Menschheit (Startseite)", hub_href="/index.html",
            back_label="Zur Bibliothek", back_href="/bibliothek/index.html",
            body_head_extra=f"""<script type="application/ld+json">{json.dumps({
                "@context": "https://schema.org", "@type": "Book", "name": title, "description": desc,
                "inLanguage": "de", "url": canonical,
                "isPartOf": {"@type": "CreativeWorkSeries", "name": "Quellen der Menschheit", "url": SITE + "/index.html"},
                "translator": {"@type": "Organization", "name": "Quellen der Menschheit"},
            }, ensure_ascii=False)}</script>""",
            frontmatter_html=render_frontmatter_html(book.get("frontmatter")),
            content_html=content_html,
        )
        with open(os.path.join(base, f"{book_id}.html"), "w", encoding="utf-8") as f:
            f.write(page)
        generated.append(bm)

    # Übersicht (gruppiert) für die statische Fallback-Sektion auf der SPA-Startseite
    groups = {}
    order = []
    for b in books_meta:
        g = b.get("group") or "Werke"
        groups.setdefault(g, []).append(b)
        if g not in order:
            order.append(g)
    group_html = []
    for g in order:
        cards = []
        for b in groups[g]:
            cards.append(
                f'<a class="werk-card" href="/bibliothek/{b["id"]}.html">'
                f'<div class="wt">{esc(b["title"])}</div>'
                f'<div class="wb">{esc(b.get("blurb") or b.get("subtitle") or "")}</div>'
                f'</a>'
            )
        group_html.append(f'<div class="werke-group"><h2>{esc(g)}</h2><div class="werke-grid">{"".join(cards)}</div></div>')
    overview_html = f"""
<section id="werke-uebersicht">
  <h1>Quellen der Menschheit</h1>
  <p class="lead">{esc(HOME_DESC)} Direkter Einstieg in jedes Werk:</p>
  {''.join(group_html)}
</section>
"""
    spa = build_spa_page(
        content, title="Quellen der Menschheit – deutsche Übersetzungen klassischer Sanskrit-Texte",
        desc=HOME_DESC, canonical=f"{SITE}/bibliothek/index.html", accent=accent, accent_strong=accent_strong,
        ld_json={"@context": "https://schema.org", "@type": "CreativeWorkSeries", "name": "Quellen der Menschheit",
                 "description": HOME_DESC, "inLanguage": "de", "url": f"{SITE}/bibliothek/index.html"},
        home_nav_label="Alle 5 Projekte", home_nav_href="/index.html",
        overview_html=overview_html,
    )
    with open(os.path.join(base, "index.html"), "w", encoding="utf-8") as f:
        f.write(spa)

    return {
        "slug": "bibliothek", "title": "Quellen der Menschheit", "subtitle": HOME_DESC,
        "accent": accent, "accent_strong": accent_strong, "favicon": "📜",
        "url": f"{SITE}/bibliothek/index.html",
        "works": [{"title": b["title"], "url": f"{SITE}/bibliothek/{b['id']}.html", "done": True} for b in books_meta],
        "urls_for_sitemap": [f"{SITE}/bibliothek/index.html"] + [f"{SITE}/bibliothek/{b['id']}.html" for b in books_meta],
    }

# ---------------------------------------------------------------- Projekte 2/3/5: ein Werk, mehrere Divisions

def build_single_divisions_project(raw_path, out_dir, *, slug, favicon, accent, accent_strong, home_nav_label):
    with open(raw_path, encoding="utf-8") as f:
        raw = f.read()
    content = strip_wrapper(raw)
    book = load_json_script(content, "data-book")
    title = book["title"]
    subtitle = book.get("subtitle") or ""
    divisions = book.get("divisions", [])
    base = os.path.join(out_dir, slug)
    os.makedirs(base, exist_ok=True)

    work_entries = []
    for div in divisions:
        key = div["key"]
        name = div.get("name") or key
        chapters = div.get("chapters", [])
        done = len(chapters) > 0
        canonical = f"{SITE}/{slug}/{key}.html"
        reader_url = f"{SITE}/{slug}/index.html#/d/{key}"
        desc = (div.get("desc") or subtitle or "")[:280]
        if chapters:
            content_html = render_chapters_html(chapters, "Kapitel", "Vers")
            note_html = ""
        else:
            content_html = ""
            note_html = '<p class="subtitle"><em>Die Übersetzung dieses Werkteils ist noch nicht begonnen.</em></p>'
        page = render_static_page(
            title=f"{name} – deutsche Übersetzung | {title}",
            subtitle=div.get("desc") or "", desc=desc, canonical=canonical, reader_url=reader_url,
            accent=accent, accent_strong=accent_strong,
            hub_label="Quellen der Menschheit (Startseite)", hub_href="/index.html",
            back_label=title, back_href=f"/{slug}/index.html",
            body_head_extra=f"""<script type="application/ld+json">{json.dumps({
                "@context": "https://schema.org", "@type": "Book", "name": name, "description": desc,
                "inLanguage": "de", "url": canonical,
                "isPartOf": {"@type": "CreativeWorkSeries", "name": title, "url": f"{SITE}/{slug}/index.html"},
                "translator": {"@type": "Organization", "name": "Quellen der Menschheit"},
            }, ensure_ascii=False)}</script>""",
            frontmatter_html=note_html,
            content_html=content_html,
        )
        with open(os.path.join(base, f"{key}.html"), "w", encoding="utf-8") as f:
            f.write(page)
        work_entries.append({"key": key, "name": name, "desc": div.get("desc") or "", "done": done})

    # statische Übersicht für die SPA-Startseite
    cards = []
    for w in work_entries:
        status = '<span class="wl-status active">im Aufbau / fertig</span>' if w["done"] else '<span class="wl-status">noch nicht begonnen</span>'
        cards.append(
            f'<div class="wl-item"><div class="wl-name"><a href="/{slug}/{w["key"]}.html">{esc(w["name"])}</a></div>{status}</div>'
        )
    overview_html = f"""
<section id="werke-uebersicht">
  <h1>{esc(title)}</h1>
  <p class="lead">{esc(subtitle)}</p>
  <div class="work-list">{''.join(cards)}</div>
</section>
"""
    spa = build_spa_page(
        content, title=f"{title} – deutsche Übersetzung | Quellen der Menschheit", desc=subtitle,
        canonical=f"{SITE}/{slug}/index.html", accent=accent, accent_strong=accent_strong,
        ld_json={"@context": "https://schema.org", "@type": "Book", "name": title, "description": subtitle,
                 "inLanguage": "de", "url": f"{SITE}/{slug}/index.html",
                 "isPartOf": {"@type": "CreativeWorkSeries", "name": "Quellen der Menschheit", "url": f"{SITE}/index.html"}},
        home_nav_label=home_nav_label, home_nav_href="/index.html",
        overview_html=overview_html,
    )
    with open(os.path.join(base, "index.html"), "w", encoding="utf-8") as f:
        f.write(spa)

    return {
        "slug": slug, "title": title, "subtitle": subtitle,
        "accent": accent, "accent_strong": accent_strong, "favicon": favicon,
        "url": f"{SITE}/{slug}/index.html",
        "works": [{"title": w["name"], "url": f"{SITE}/{slug}/{w['key']}.html", "done": w["done"]} for w in work_entries],
        "urls_for_sitemap": [f"{SITE}/{slug}/index.html"] + [f"{SITE}/{slug}/{w['key']}.html" for w in work_entries],
    }

# ---------------------------------------------------------------- Projekt 4: Tantras & Āgamas (Gruppen aus Werken)

def build_tantras(raw_path, out_dir, *, slug="tantras", favicon="🔱", accent="#7A2E2E", accent_strong="#5C2020"):
    with open(raw_path, encoding="utf-8") as f:
        raw = f.read()
    content = strip_wrapper(raw)
    book = load_json_script(content, "data-book")
    title = book["title"]
    subtitle = book.get("subtitle") or ""
    groups = book.get("groups", [])
    base = os.path.join(out_dir, slug)
    os.makedirs(base, exist_ok=True)

    all_works = []
    group_html_parts = []
    for g in groups:
        gkey = g["key"]
        gname = g.get("name") or gkey
        gdesc = g.get("desc") or ""
        cards = []
        for w in g.get("works", []):
            wkey = w["key"]
            wname = w.get("name") or wkey
            chapters = w.get("chapters", [])
            done = len(chapters) > 0
            canonical = f"{SITE}/{slug}/{wkey}.html"
            reader_url = f"{SITE}/{slug}/index.html#/w/{wkey}"
            desc = (w.get("desc") or gdesc or subtitle or "")[:280]
            if chapters:
                content_html = render_chapters_html(chapters, "Paṭala/Kapitel", "Vers")
                note_html = f'<p class="subtitle">{esc(w.get("desc") or "")}</p>' if w.get("desc") else ""
            else:
                content_html = ""
                note_html = '<p class="subtitle"><em>Die Übersetzung dieses Werks ist noch nicht begonnen.</em></p>'
            page = render_static_page(
                title=f"{wname} – deutsche Übersetzung | {title}",
                subtitle=w.get("desc") or "", desc=desc, canonical=canonical, reader_url=reader_url,
                accent=accent, accent_strong=accent_strong,
                hub_label="Quellen der Menschheit (Startseite)", hub_href="/index.html",
                back_label=title, back_href=f"/{slug}/index.html",
                body_head_extra=f"""<script type="application/ld+json">{json.dumps({
                    "@context": "https://schema.org", "@type": "Book", "name": wname, "description": desc,
                    "inLanguage": "de", "url": canonical, "author": w.get("author") or None,
                    "isPartOf": {"@type": "CreativeWorkSeries", "name": title, "url": f"{SITE}/{slug}/index.html"},
                    "translator": {"@type": "Organization", "name": "Quellen der Menschheit"},
                }, ensure_ascii=False)}</script>""",
                frontmatter_html=note_html,
                content_html=content_html,
            )
            with open(os.path.join(base, f"{wkey}.html"), "w", encoding="utf-8") as f:
                f.write(page)
            all_works.append({"key": wkey, "name": wname, "done": done})
            status = '<span class="wl-status active">im Aufbau / fertig</span>' if done else '<span class="wl-status">noch nicht begonnen</span>'
            cards.append(f'<div class="wl-item"><div class="wl-name"><a href="/{slug}/{wkey}.html">{esc(wname)}</a></div>{status}</div>')
        group_html_parts.append(f'<div class="group-heading">{esc(gname)}</div><p class="subtitle">{esc(gdesc)}</p><div class="work-list">{"".join(cards)}</div>')

    overview_html = f"""
<section id="werke-uebersicht">
  <h1>{esc(title)}</h1>
  <p class="lead">{esc(subtitle)}</p>
  {''.join(group_html_parts)}
</section>
"""
    spa = build_spa_page(
        content, title=f"{title} – deutsche Übersetzung | Quellen der Menschheit", desc=subtitle,
        canonical=f"{SITE}/{slug}/index.html", accent=accent, accent_strong=accent_strong,
        ld_json={"@context": "https://schema.org", "@type": "Book", "name": title, "description": subtitle,
                 "inLanguage": "de", "url": f"{SITE}/{slug}/index.html",
                 "isPartOf": {"@type": "CreativeWorkSeries", "name": "Quellen der Menschheit", "url": f"{SITE}/index.html"}},
        home_nav_label="Alle 5 Projekte", home_nav_href="/index.html",
        overview_html=overview_html,
    )
    with open(os.path.join(base, "index.html"), "w", encoding="utf-8") as f:
        f.write(spa)

    return {
        "slug": slug, "title": title, "subtitle": subtitle,
        "accent": accent, "accent_strong": accent_strong, "favicon": favicon,
        "url": f"{SITE}/{slug}/index.html",
        "works": [{"title": w["name"], "url": f"{SITE}/{slug}/{w['key']}.html", "done": w["done"]} for w in all_works],
        "urls_for_sitemap": [f"{SITE}/{slug}/index.html"] + [f"{SITE}/{slug}/{w['key']}.html" for w in all_works],
    }

# ---------------------------------------------------------------- Hub-Startseite, Sitemap, robots.txt, CNAME

HUB_INTRO = ("„Quellen der Menschheit“ versammelt eigenständige, gemeinfreie deutsche Übersetzungen "
             "klassischer Sanskrit- und vedischer Literatur – jeweils Vers für Vers direkt aus dem "
             "Original erarbeitet, mit ausklappbarer Wort-für-Wort-Analyse, ohne vorhandene "
             "Übersetzungen als Ausgangspunkt zu verwenden. Das Vorhaben gliedert sich in fünf "
             "parallele, teils mehrjährige Übersetzungsprojekte, die fortlaufend weiterwachsen.")

def build_hub(projects, out_dir):
    cards = []
    for p in projects:
        n_done = sum(1 for w in p["works"] if w.get("done"))
        n_total = len(p["works"])
        status = f"{n_done} von {n_total} Werken im Aufbau/fertig" if n_total else "im Aufbau"
        cards.append(f"""
<a class="proj-card" href="/{p['slug']}/index.html" style="--pc:{p['accent']};--pcs:{p['accent_strong']}">
  <div class="pc-icon">{p['favicon']}</div>
  <div class="pc-title">{esc(p['title'])}</div>
  <div class="pc-desc">{esc((p['subtitle'] or '')[:220])}</div>
  <div class="pc-status">{esc(status)}</div>
</a>""")
    html_out = f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Quellen der Menschheit – deutsche Übersetzungen klassischer Sanskrit-Texte</title>
<meta name="description" content="{esc(HUB_INTRO)}">
<link rel="canonical" href="{SITE}/index.html">
<meta property="og:type" content="website">
<meta property="og:title" content="Quellen der Menschheit">
<meta property="og:description" content="{esc(HUB_INTRO)}">
<meta property="og:url" content="{SITE}/index.html">
<meta property="og:site_name" content="Quellen der Menschheit">
<meta name="twitter:card" content="summary">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Spectral:ital,wght@0,400;0,500;0,600;1,400;1,500&family=Source+Sans+3:wght@400;500;600;700&display=swap">
<script type="application/ld+json">{json.dumps({
    "@context": "https://schema.org", "@type": "WebSite", "name": "Quellen der Menschheit",
    "description": HUB_INTRO, "inLanguage": "de", "url": f"{SITE}/index.html",
}, ensure_ascii=False)}</script>
<style>
:root{{--bg:#EAE4D8;--bg-elevated:#F5F1E7;--bg-card:#F2ECDE;--ink:#241E17;--ink-soft:#5B5142;--ink-faint:#8A8069;--line:#D3C9B4;--font-display:"Spectral",Georgia,serif;--font-body:"Source Sans 3",-apple-system,"Segoe UI",sans-serif}}
@media(prefers-color-scheme:dark){{:root{{--bg:#1B1712;--bg-elevated:#242019;--bg-card:#221E17;--ink:#ECE4D2;--ink-soft:#BDB093;--ink-faint:#847A63;--line:#3A3325}}}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);font-family:var(--font-body);line-height:1.6}}
header.hero{{max-width:900px;margin:0 auto;padding:3.5rem 1.5rem 1.5rem}}
header.hero h1{{font-family:var(--font-display);font-size:clamp(2rem,5vw,3rem);margin:0 0 .8rem}}
header.hero p{{color:var(--ink-soft);font-size:1.05rem;max-width:68ch;line-height:1.7}}
.projects{{max-width:900px;margin:0 auto;padding:1rem 1.5rem 4rem;display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:18px}}
.proj-card{{display:block;padding:20px 20px 18px;border:1px solid var(--line);border-radius:14px;background:var(--bg-card);text-decoration:none;color:var(--ink);transition:border-color .15s}}
.proj-card:hover{{border-color:var(--pc,#8C6A2C)}}
.pc-icon{{font-size:1.6rem;margin-bottom:.4rem}}
.pc-title{{font-family:var(--font-display);font-weight:600;font-size:1.25rem;color:var(--pcs,#6E5220);margin-bottom:.4rem}}
.pc-desc{{font-size:.88rem;color:var(--ink-soft);line-height:1.55;margin-bottom:.7rem}}
.pc-status{{font-size:.78rem;color:var(--ink-faint);font-style:italic}}
footer.site{{border-top:1px solid var(--line);padding:2rem 1.25rem;text-align:center;color:var(--ink-faint);font-size:.9rem}}
</style>
</head>
<body>
<header class="hero">
  <h1>Quellen der Menschheit</h1>
  <p>{esc(HUB_INTRO)}</p>
</header>
<section class="projects">
{''.join(cards)}
</section>
<footer class="site"><p>Alle Übersetzungen sind gemeinfrei und werden fortlaufend erweitert.</p></footer>
</body>
</html>
"""
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(html_out)

def build_sitemap_and_robots(projects, out_dir):
    urls = [f"{SITE}/index.html"]
    for p in projects:
        urls.extend(p["urls_for_sitemap"])
    entries = "\n".join(f"  <url><loc>{u}</loc></url>" for u in urls)
    sitemap = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{entries}
</urlset>
"""
    with open(os.path.join(out_dir, "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write(sitemap)
    robots = f"""User-agent: *
Allow: /

Sitemap: {SITE}/sitemap.xml
"""
    with open(os.path.join(out_dir, "robots.txt"), "w", encoding="utf-8") as f:
        f.write(robots)
    with open(os.path.join(out_dir, "CNAME"), "w", encoding="utf-8") as f:
        f.write("quellendermenschheit.de\n")
    print(f"TOTAL URLs im sitemap.xml: {len(urls)}")

# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bibliothek")
    ap.add_argument("--ramayana", help="eigenständiges Rāmāyaṇa-Artifact (wird der Bibliothek als weiteres Werk hinzugefügt, nur wirksam zusammen mit --bibliothek)")
    ap.add_argument("--mahabharata")
    ap.add_argument("--aranyakas")
    ap.add_argument("--tantras")
    ap.add_argument("--mahapuranas")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    projects = []

    if args.bibliothek:
        print("== Bibliothek (Quellen der Menschheit) =="); projects.append(build_bibliothek(
            args.bibliothek, args.out,
            extra_raw_paths=[args.ramayana] if args.ramayana else None))
    elif args.ramayana:
        print("WARNUNG: --ramayana angegeben, aber --bibliothek fehlt - Rāmāyaṇa wird in diesem Lauf übersprungen (braucht die Bibliothek als Trägerseite).")
    if args.mahabharata:
        print("== Mahābhārata =="); projects.append(build_single_divisions_project(
            args.mahabharata, args.out, slug="mahabharata", favicon="🐚",
            accent="#4A3468", accent_strong="#332249", home_nav_label="Alle 5 Projekte"))
    if args.aranyakas:
        print("== Āraṇyakas =="); projects.append(build_single_divisions_project(
            args.aranyakas, args.out, slug="aranyakas", favicon="🌲",
            accent="#2F5233", accent_strong="#213B25", home_nav_label="Alle 5 Projekte"))
    if args.tantras:
        print("== Tantras & Āgamas =="); projects.append(build_tantras(args.tantras, args.out))
    if args.mahapuranas:
        print("== Mahāpurāṇas =="); projects.append(build_single_divisions_project(
            args.mahapuranas, args.out, slug="mahapuranas", favicon="🕉️",
            accent="#6B4A1E", accent_strong="#4F3512", home_nav_label="Alle 5 Projekte"))

    if not projects:
        sys.exit("Keine Quelle angegeben - nichts zu tun.")

    build_hub(projects, args.out)
    build_sitemap_and_robots(projects, args.out)
    print("FERTIG.")

if __name__ == "__main__":
    main()
