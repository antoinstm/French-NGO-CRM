"""Exploration : passages des débats du Sénat qui touchent à l'IA, et parmi
eux ceux qui touchent à la superintelligence et aux risques extrêmes."""
import csv
import re
import unicodedata
import zipfile
from collections import Counter
from html.parser import HTMLParser

DEPUIS = "20240701"   # same window as the Assemblée exploration

EXPRESSIONS = {
    "superintelligence": r"super[- ]?intelligen",
    "IA générale": r"intelligences? artificielles? generales?|\bia generale",
    "extinction": r"extinction de l.(humanite|espece humaine)",
    "singularité technologique": r"singularite technologique",
    "auto-amélioration": r"auto[- ]?amelioration",
    "PauseIA": r"pause ?ia\b",
}
SIGLES = {"AGI": r"\bAGI\b", "IAG": r"\bIAG\b"}
SI_IA = {
    "perte de contrôle": r"perte de (la )?(controle|maitrise)",
    "risque existentiel": r"risques? existentiels?",
}
IA = r"intelligence artificielle|\bia\b"


def norm(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return s.lower()


class Interventions(HTMLParser):
    """Collects (attributes, spoken text) for each <cri:intervenant>.

    The Sénat files are HTML with extra cri: tags, not strict XML, so a
    tolerant HTML parser is used. Speaker labels and stage directions
    (« (Applaudissements…) ») are left out of the text."""
    SAUTER = {"cri:orateurnom", "cri:infoentreparentheses"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.courant, self.morceaux, self.sauter = None, [], 0
        self.resultats = []

    def fermer(self):
        if self.courant is not None:
            texte = " ".join(" ".join(self.morceaux).split())
            if texte:
                self.resultats.append((self.courant, texte))
        self.courant, self.morceaux = None, []

    def handle_starttag(self, tag, attrs):
        if tag == "cri:intervenant":
            self.fermer()
            self.courant = dict(attrs)
        elif tag in self.SAUTER:
            self.sauter += 1

    def handle_endtag(self, tag):
        if tag == "cri:intervenant":
            self.fermer()
        elif tag in self.SAUTER and self.sauter:
            self.sauter -= 1

    def handle_data(self, data):
        if self.courant is not None and not self.sauter:
            self.morceaux.append(data)


def decoder(brut):
    m = re.search(rb'encoding="([^"]+)"', brut[:200])
    return brut.decode(m.group(1).decode() if m else "utf-8", "replace")


def ecrire(nom_fichier, lignes):
    with open(nom_fichier, "w", newline="", encoding="utf-8") as out:
        w = csv.DictWriter(out, fieldnames=list(lignes[0]) if lignes else ["date"])
        w.writeheader()
        w.writerows(lignes)


z = zipfile.ZipFile("senat-cri.zip")
fichiers = sorted(n for n in z.namelist()
                  if re.fullmatch(r"cri/d\d{8}\.xml", n) and n[5:13] >= DEPUIS)
hits, ia, par_mot, orateurs_ia = [], [], Counter(), Counter()
nb_interventions = 0
for nom_fichier in fichiers:
    jour = f"{nom_fichier[5:9]}-{nom_fichier[9:11]}-{nom_fichier[11:13]}"
    parser = Interventions()
    parser.feed(decoder(z.read(nom_fichier)))
    parser.fermer()
    for attrs, brut in parser.resultats:
        qualite = attrs.get("qua", "")
        if qualite.startswith("présid") and "séance" in qualite:
            continue  # chairing the sitting, not taking a position
        nb_interventions += 1
        n = norm(brut)
        parle_ia = bool(re.search(IA, n))
        trouves = [k for k, rx in EXPRESSIONS.items() if re.search(rx, n)]
        trouves += [k for k, rx in SIGLES.items() if re.search(rx, brut)]
        if parle_ia:
            trouves += [k for k, rx in SI_IA.items() if re.search(rx, n)]
        if not (parle_ia or trouves):
            continue
        orateur = f"{attrs.get('civ', '')} {attrs.get('nom', '')}".strip()
        ligne = {"date": jour, "matricule": attrs.get("mat", ""),
                 "orateur": orateur, "qualite": qualite,
                 "mots": ", ".join(trouves), "texte": brut,
                 "fichier": nom_fichier}
        if parle_ia:
            ia.append(ligne)
            orateurs_ia[(ligne["matricule"], orateur)] += 1
        if trouves:
            hits.append(ligne)
            par_mot.update(trouves)

print(f"{len(fichiers)} jours de séance, du {fichiers[0][5:13]} au {fichiers[-1][5:13]}")
print(f"{nb_interventions} interventions lues (hors présidence de séance)")
print(f"{len(ia)} parlent d'IA, par {len(orateurs_ia)} orateurs différents")
print(f"{len(hits)} touchent aux risques extrêmes\n")
print("Par mot-clé :")
for k, v in par_mot.most_common():
    print(f"  {v:4}  {k}")
print("\nQui parle le plus d'IA en séance :")
for (mat, nom), v in orateurs_ia.most_common(15):
    print(f"  {v:4}  {mat:8}  {nom}")
print("\nInterventions sur l'IA par année :")
for annee, v in sorted(Counter(l["date"][:4] for l in ia).items()):
    print(f"  {annee}  {v}")

ecrire("resultats_senat.csv", hits)
ecrire("interventions_ia_senat.csv", ia)
print("\nDétail : resultats_senat.csv, interventions_ia_senat.csv")
