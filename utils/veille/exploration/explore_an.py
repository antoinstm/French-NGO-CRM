"""Exploration : passages des débats de l'AN qui touchent à l'IA, et parmi
eux ceux qui touchent à la superintelligence et aux risques extrêmes."""
import csv
import glob
import re
import unicodedata
import xml.etree.ElementTree as ET
from collections import Counter

NS = "http://schemas.assemblee-nationale.fr/referentiel"
ns = {"a": NS}

# Matched on lowercased, accent-stripped text.
EXPRESSIONS = {
    "superintelligence": r"super[- ]?intelligen",
    "IA générale": r"intelligences? artificielles? generales?|\bia generale",
    "extinction": r"extinction de l.(humanite|espece humaine)",
    "singularité technologique": r"singularite technologique",
    "auto-amélioration": r"auto[- ]?amelioration",
    "PauseIA": r"pause ?ia\b",
}
# Acronyms: exact case on the raw text, « agi » being a French past participle.
SIGLES = {"AGI": r"\bAGI\b", "IAG": r"\bIAG\b"}
# Too common on their own (« perte de contrôle des finances publiques »):
# kept only when the same paragraph also talks about AI.
SI_IA = {"perte de contrôle": r"perte de (la )?(controle|maitrise)",
         "risque existentiel": r"risques? existentiels?",
         }
IA = r"intelligence artificielle|\bia\b"


def norm(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return s.lower()


def texte(el):
    """Spoken text only: drops the <italique> stage directions (applause…)."""
    parts = [el.text or ""]
    for child in el:
        if child.tag != f"{{{NS}}}italique":
            parts.append(texte(child))
        parts.append(child.tail or "")
    return " ".join(" ".join(parts).split())


def ecrire(nom_fichier, lignes):
    with open(nom_fichier, "w", newline="", encoding="utf-8") as out:
        w = csv.DictWriter(out, fieldnames=list(lignes[0]) if lignes else ["date"])
        w.writeheader()
        w.writerows(lignes)


hits, ia, par_mot, orateurs_ia = [], [], Counter(), Counter()
nb_paragraphes = 0
for f in sorted(glob.glob("an/xml/compteRendu/*.xml")):
    root = ET.parse(f).getroot()
    jour = root.findtext("a:metadonnees/a:dateSeance", namespaces=ns)[:8]
    jour = f"{jour[:4]}-{jour[4:6]}-{jour[6:]}"
    for p in root.iter(f"{{{NS}}}paragraphe"):
        el = p.find("a:texte", ns)
        if el is None:
            continue
        nom = p.findtext("a:orateurs/a:orateur/a:nom", default="", namespaces=ns)
        if p.get("roledebat") == "president" or nom in ("Mme la présidente", "M. le président"):
            continue  # chairing the sitting, not taking a position
        nb_paragraphes += 1
        brut = texte(el)
        n = norm(brut)
        parle_ia = bool(re.search(IA, n))
        trouves = [k for k, rx in EXPRESSIONS.items() if re.search(rx, n)]
        trouves += [k for k, rx in SIGLES.items() if re.search(rx, brut)]
        if parle_ia:
            trouves += [k for k, rx in SI_IA.items() if re.search(rx, n)]
        if not (parle_ia or trouves):
            continue
        nom = p.findtext("a:orateurs/a:orateur/a:nom", default="", namespaces=ns)
        ligne = {"date": jour, "id_acteur": p.get("id_acteur", ""),
                 "orateur": nom, "mots": ", ".join(trouves), "texte": brut,
                 "id_syceron": p.get("id_syceron"), "fichier": f.split("/")[-1]}
        if parle_ia:
            ia.append(ligne)
            orateurs_ia[(ligne["id_acteur"], nom)] += 1
        if trouves:
            hits.append(ligne)
            par_mot.update(trouves)

print(f"{nb_paragraphes} paragraphes lus")
print(f"{len(ia)} parlent d'IA, par {len(orateurs_ia)} orateurs différents")
print(f"{len(hits)} touchent aux risques extrêmes\n")
print("Par mot-clé :")
for k, v in par_mot.most_common():
    print(f"  {v:4}  {k}")
print("\nQui parle le plus d'IA en séance :")
for (acteur, nom), v in orateurs_ia.most_common(15):
    print(f"  {v:4}  {acteur:10}  {nom}")
print("\nParagraphes sur l'IA par année :")
for annee, v in sorted(Counter(l["date"][:4] for l in ia).items()):
    print(f"  {annee}  {v}")

ecrire("resultats_an.csv", hits)
ecrire("paragraphes_ia_an.csv", ia)
print("\nDétail : resultats_an.csv (risques extrêmes), paragraphes_ia_an.csv (tout l'IA)")
