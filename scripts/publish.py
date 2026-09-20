#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Baut die Bibliothek und laedt sie nach sebitrauner-del/quellendermenschheit (main).

    python3 scripts/publish.py                 # bauen, pruefen, hochladen
    python3 scripts/publish.py --nur-bauen     # nur nach neu/ bauen
    python3 scripts/publish.py -m "Nachricht"

Auf diesem Rechner ist kein git installiert. Der Upload laeuft ueber die
GitHub Git-Data-API. Damit aus tausenden Kapitelseiten nicht tausende
Einzelanfragen werden, gehen kleine Dateien gebuendelt als Tree-Eintraege mit
Inline-Inhalt hoch; nur die wenigen grossen Leseansichten bekommen eigene Blobs.
"""
import os, sys, json, base64, time, shutil, argparse, subprocess
import urllib.request, urllib.error

BASE       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUS        = os.path.join(BASE, "neu")
TOKEN_FILE = os.path.expanduser("~/.config/quellendermenschheit/github-token")
REPO       = "sebitrauner-del/quellendermenschheit"
API        = "https://api.github.com/repos/" + REPO

GROSS_AB      = 1_000_000      # ab dieser Groesse eigener Blob
BUENDEL_BYTES = 4_000_000      # Ziel-Groesse eines Tree-Pakets


def token():
    t = os.environ.get("GH_TOKEN")
    if t:
        return t.strip()
    if os.path.exists(TOKEN_FILE):
        return open(TOKEN_FILE, encoding="utf-8").read().strip()
    sys.exit("Kein Token: weder $GH_TOKEN noch %s" % TOKEN_FILE)


def call(pfad, daten=None, methode=None, tok=None, versuche=5):
    url = pfad if pfad.startswith("http") else API + pfad
    koerper = json.dumps(daten).encode() if daten is not None else None
    for i in range(versuche):
        req = urllib.request.Request(url, data=koerper, method=methode or ("POST" if koerper else "GET"))
        req.add_header("Authorization", "Bearer " + tok)
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=900) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            text = e.read().decode()[:600]
            if e.code in (502, 503, 504, 429) and i < versuche - 1:
                time.sleep(5 * (i + 1)); continue
            sys.exit("HTTP %s auf %s\n%s" % (e.code, url, text))
        except Exception:
            if i < versuche - 1:
                time.sleep(5 * (i + 1)); continue
            raise


def bauen():
    if os.path.isdir(AUS):
        shutil.rmtree(AUS)
    r = subprocess.run([sys.executable, os.path.join(BASE, "scripts", "bibliothek.py"), "--out", AUS],
                       capture_output=True, text=True)
    sys.stdout.write(r.stdout)
    if r.returncode != 0:
        sys.stderr.write(r.stderr)
        sys.exit("Bau fehlgeschlagen.")
    # Bauskript und Kurzanleitung mitveroeffentlichen, damit das Repo sich selbst erklaert
    os.makedirs(os.path.join(AUS, "scripts"), exist_ok=True)
    shutil.copy(os.path.join(BASE, "scripts", "bibliothek.py"), os.path.join(AUS, "scripts", "bibliothek.py"))
    shutil.copy(os.path.join(BASE, "scripts", "publish.py"), os.path.join(AUS, "scripts", "publish.py"))
    for name in ("README.md",):
        q = os.path.join(BASE, name)
        if os.path.exists(q):
            shutil.copy(q, os.path.join(AUS, name))
    return r.stdout


def dateien_sammeln(wurzel):
    raus = []
    for dirpath, _, filenames in os.walk(wurzel):
        for fn in filenames:
            voll = os.path.join(dirpath, fn)
            raus.append((os.path.relpath(voll, wurzel).replace(os.sep, "/"), voll, os.path.getsize(voll)))
    raus.sort()
    return raus


def hochladen(nachricht):
    tok = token()
    kopf = call("/git/ref/heads/main", tok=tok)
    eltern = kopf["object"]["sha"]
    print("Eltern-Commit:", eltern)

    dateien = dateien_sammeln(AUS)
    gesamt = sum(g for _, _, g in dateien)
    print("%d Dateien, %.1f MB" % (len(dateien), gesamt / 1048576))

    eintraege = []
    for rel, voll, groesse in dateien:
        if groesse >= GROSS_AB:
            roh = open(voll, "rb").read()
            blob = call("/git/blobs", {"content": base64.b64encode(roh).decode(), "encoding": "base64"}, tok=tok)
            eintraege.append({"path": rel, "mode": "100644", "type": "blob", "sha": blob["sha"]})
            print("  Blob  %-40s %6.1f MB" % (rel, groesse / 1048576), flush=True)
        else:
            eintraege.append({"path": rel, "mode": "100644", "type": "blob",
                              "content": open(voll, encoding="utf-8").read()})

    # In Paketen hochladen; das erste Paket ohne base_tree, damit alte Dateien
    # verschwinden, die es in diesem Bau nicht mehr gibt.
    baum = None
    paket, paket_bytes, nr = [], 0, 0
    def paket_senden(p, basis):
        daten = {"tree": p}
        if basis:
            daten["base_tree"] = basis
        return call("/git/trees", daten, tok=tok)["sha"]

    for e in eintraege:
        groesse = len(e.get("content", "").encode()) if "content" in e else 100
        if paket and paket_bytes + groesse > BUENDEL_BYTES:
            nr += 1
            baum = paket_senden(paket, baum)
            print("  Paket %2d: %4d Dateien, %5.1f MB -> %s" % (nr, len(paket), paket_bytes / 1048576, baum[:8]), flush=True)
            paket, paket_bytes = [], 0
        paket.append(e); paket_bytes += groesse
    if paket:
        nr += 1
        baum = paket_senden(paket, baum)
        print("  Paket %2d: %4d Dateien, %5.1f MB -> %s" % (nr, len(paket), paket_bytes / 1048576, baum[:8]), flush=True)

    c = call("/git/commits", {"message": nachricht, "tree": baum, "parents": [eltern]}, tok=tok)
    call("/git/refs/heads/main", {"sha": c["sha"], "force": False}, methode="PATCH", tok=tok)
    print("Commit:", c["sha"])
    print("GitHub Pages baut jetzt.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--nur-bauen", action="store_true")
    ap.add_argument("-m", "--message", default="Bibliothek neu gebaut")
    a = ap.parse_args()
    bauen()
    if a.nur_bauen:
        print("Nur gebaut - liegt in", AUS)
    else:
        hochladen(a.message)
