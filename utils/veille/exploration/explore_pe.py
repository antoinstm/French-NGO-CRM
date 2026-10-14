"""Exploration : interventions en plénière des eurodéputé·es français·es qui
parlent d'IA, et parmi elles celles qui touchent aux risques extrêmes."""
import csv
import json
import re
import sqlite3
import time
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter

API = "https://data.europarl.europa.eu/api/v2/speeches"
CRM_DB = "../French-NGO-CRM/meetings.db"
# The API also searches translations, but both languages are queried so that
# nothing is lost if one index lags behind.
RECHERCHES = [("intelligence artificielle", "fr"), ("artificial intelligence", "en")]
PAGE = 50
XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"

# Every speech fetched already talks about AI, and plenary speeches are short
# (one or two minutes), so no proximity check is needed here.
EXPRESSIONS = {
    "superintelligence": r"super[- ]?intelligen",
    "IA générale": r"intelligences? artificielles? generales?|\bia generale"
                   r"|artificial general intelligence",
    "risque existentiel": r"risques? existentiels?|existential risks?",
    "extinction": r"extinction de l.(humanite|espece humaine)|human extinction",
    "perte de contrôle": r"perte de (la )?(controle|maitrise)|loss of control",
    "singularité": r"singularite technologique|technological singularity",
    "auto-amélioration": r"auto[- ]?amelioration|self[- ]improv",
    "PauseIA": r"pause ?(ia|ai)\b",
}
# Exact case, and not glued to a hyphen (« AGI-SON » at the Sénat).
SIGLES = {"AGI": r"(?<![\w-])AGI(?![\w-])", "IAG": r"(?<![\w-])IAG(?![\w-])"}


def norm(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return s.lower()


def eurodeputes_fr():
    """{European Parliament id: name}, read from the CRM's own fiches."""
    con = sqlite3.connect(f"file:{CRM_DB}?mode=ro", uri=True)
    ids = {}
    for nom, url in con.execute(
            "SELECT name, fiche_url FROM persons "
            "WHERE fiche_url LIKE '%europarl.europa.eu/meps/%'"):
        m = re.search(r"/meps/\w+/(\d+)", url)
        if m:
            ids[m.group(1)] = nom
    con.close()
    return ids


def appel(params):
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "PauseIA-veille-exploration"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return {} if r.status == 204 else json.load(r)


def toutes(texte, langue):
    """{speech id: (metadata, xml text)} for every match, page after page.
    Texts and metadata come in two separate lists whose order differs, so
    they are joined on the id, never on the position."""
    resultats, offset = {}, 0
    while True:
        rep = appel({"text": texte, "search-language": langue,
                     "parliamentary-term": 10, "sort-by": "sitting-date:desc",
                     "format": "application/ld+json",
                     "include-output": "highlighted_text",
                     "offset": offset, "limit": PAGE})
        donnees = rep.get("data", [])
        meta = {d["id"]: d for d in donnees}
        for h in rep.get("searchResults", {}).get("hits", []):
            resultats[h["id"]] = (meta.get(h["id"]),
                                  h.get("highlights", {}).get("xml_text", ""))
        if len(donnees) < PAGE:
            return resultats
        offset += PAGE
        time.sleep(0.5)   # well under the 500 requests / 5 min limit


def lire(xml_text):
    """(person id, name, language, spoken text) from one speech's XML."""
    racine = ET.fromstring(xml_text)
    speech = racine.find(".//speech")
    langue = speech.get(XML_LANG, "") if speech is not None else ""
    personne = racine.find(".//person")
    pid = nom = ""
    if personne is not None:
        pid = personne.get("refersTo", "").rsplit("/", 1)[-1]
        nom = personne.text or ""
    corps = racine.find(".//blockContainer")   # the words, without the speaker line
    source = corps if corps is not None else racine
    return pid, nom, langue, " ".join(" ".join(source.itertext()).split())


def ecrire(nom_fichier, lignes):
    with open(nom_fichier, "w", newline="", encoding="utf-8") as out:
        w = csv.DictWriter(out, fieldnames=list(lignes[0]) if lignes else ["date"])
        w.writeheader()
        w.writerows(lignes)


fr = eurodeputes_fr()
print(f"{len(fr)} eurodéputé·es français·es dans le CRM")
tout = {}
for texte, langue in RECHERCHES:
    r = toutes(texte, langue)
    print(f"« {texte} » ({langue}) : {len(r)} interventions")
    tout.update(r)
print(f"{len(tout)} interventions distinctes, toutes nationalités\n")

ia, hits, erreurs = [], [], 0
par_mot, orateurs, langues = Counter(), Counter(), Counter()
for id_, (meta, xml_text) in tout.items():
    try:
        pid, nom, langue, texte = lire(xml_text)
    except ET.ParseError:
        erreurs += 1
        continue
    if pid not in fr:
        continue
    n = norm(texte)
    trouves = [k for k, rx in EXPRESSIONS.items() if re.search(rx, n)]
    trouves += [k for k, rx in SIGLES.items() if re.search(rx, texte)]
    origine = ", ".join(
        u.rsplit("/", 1)[-1]
        for r in (meta or {}).get("recorded_in_a_realization_of", [])
        for u in r.get("originalLanguage", []))
    ligne = {"date": (meta or {}).get("activity_date", ""), "id_pe": pid,
             "orateur": fr[pid], "langue": langue, "origine": origine,
             "mots": ", ".join(trouves), "texte": texte, "id": id_}
    ia.append(ligne)
    orateurs[(pid, fr[pid])] += 1
    langues[(langue, origine)] += 1
    if trouves:
        hits.append(ligne)
        par_mot.update(trouves)

print(f"{len(ia)} interventions d'eurodéputé·es français·es, "
      f"par {len(orateurs)} orateurs différents")
if ia:
    print(f"longueur moyenne du texte : {sum(len(l['texte']) for l in ia) // len(ia)} caractères")
print(f"{len(hits)} touchent aux risques extrêmes ; XML illisibles : {erreurs}\n")
print("Langues :", dict(langues))
print("\nPar mot-clé :")
for k, v in par_mot.most_common():
    print(f"  {v:4}  {k}")
print("\nQui parle le plus d'IA :")
for (pid, nom), v in orateurs.most_common(15):
    print(f"  {v:4}  {pid:7} {nom}")
print("\nPar année :")
for annee, v in sorted(Counter(l["date"][:4] for l in ia).items()):
    print(f"  {annee}  {v}")

ecrire("resultats_pe.csv", hits)
ecrire("interventions_ia_pe.csv", ia)
print("\nDétail : resultats_pe.csv, interventions_ia_pe.csv")
