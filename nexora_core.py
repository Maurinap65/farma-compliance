# -*- coding: utf-8 -*-
"""
NEXORA Farma Compliance - core

Principi (invariati rispetto a NX6):
  1. Il testo delle norme non passa MAI dal modello: si risolve per chiave dal corpus.
  2. La severita' non e' decisa dal modello: si deriva dalle chiavi (tabella unica).
  3. La posizione si ancora al testo letterale contestato (quote), non a marker cablati.
  4. Nessuna logica specifica per un materiale: il motore non conosce TussanPlus.
  5. I gate BLOCCANO. valida() solleva ReportNonValido se strict=True.

Principi aggiunti in NX7 (ognuno nasce da un difetto osservato in un report reale):
  6. Il corpus non mente MAI su cio' che contiene. Una chiave non fornita dal file
     del cliente non puo' essere presentata come "vigente al" quella data.
  7. Niente si stampa nel report senza essere stato verificato sul materiale.
     Una quote che non si trova nel testo non viene mostrata.
  8. Il report non dichiara nulla per default. Se un dato manca, si dice che manca.
"""

import re
import json
import hashlib
from datetime import datetime

BUILD = "NX7-core"

# ----------------------------------------------------------------------------
# CORPUS
# ----------------------------------------------------------------------------
# NX6 scriveva questi testi in ASCII (pubblicita', e', puo'). Il testo del modello
# passa invece da polish_obj e arriva accentato: il PDF mescolava le due ortografie
# nello stesso paragrafo. Qui e' tutto accentato.

EMBED_NORME = {
    "art113_c1_a": "per pubblicit\u00e0 di medicinali: qualsiasi forma di informazione, di ricerca di mercato e di incentivazione alla prescrizione, alla fornitura, alla vendita o al consumo di medicinali;",
    "art114_c2": "La pubblicit\u00e0 di un medicinale \u00e8 conforme al riassunto delle caratteristiche del prodotto.",
    "art114_c3_a": "La pubblicit\u00e0 di un medicinale deve favorire l'uso razionale del medicinale, presentandolo in modo obiettivo e senza esagerarne le propriet\u00e0.",
    "art114_c3_b": "La pubblicit\u00e0 di un medicinale non pu\u00f2 essere ingannevole.",
    "art116_c1_a": "La pubblicit\u00e0 di un medicinale presso il pubblico \u00e8 realizzata in modo che la natura pubblicitaria del messaggio \u00e8 evidente e il prodotto \u00e8 chiaramente identificato come medicinale.",
    "art116_c1_b1": "la denominazione del medicinale e la denominazione comune della sostanza attiva;",
    "art116_c1_b2": "le informazioni indispensabili per un uso corretto del medicinale;",
    "art116_c1_b3": "un invito esplicito e chiaro a leggere attentamente le avvertenze figuranti, a seconda dei casi, nel foglio illustrativo o sull'imballaggio esterno.",
    "art117_c1_a": "induca a ritenere che la visita medica o l'intervento chirurgico siano superflui, in particolare offrendo una diagnosi o suggerendo un trattamento per corrispondenza;",
    "art117_c1_b": "induca a ritenere che gli effetti derivanti dall'assunzione del medicinale siano garantiti, non siano accompagnati da reazioni avverse o siano superiori o pari a quelli di un altro trattamento o medicinale;",
    "art117_c1_f": "comprenda una raccomandazione di scienziati, di operatori sanitari o di persone largamente note al pubblico;",
    "art117_c1_g": "assimili il medicinale ad un prodotto alimentare, ad un prodotto cosmetico o ad un altro prodotto di consumo;",
    "art117_c1_i": "possa indurre ad una errata autodiagnosi;",
    "art117_c1_l": "faccia riferimento, in termini impropri, allarmistici o ingannevoli, ad attestati di guarigione;",
    "art118_c1": "Nessuna pubblicit\u00e0 di medicinali presso il pubblico pu\u00f2 essere effettuata senza autorizzazione del Ministero della salute.",
    "art118_c8": "Decorsi quarantacinque giorni dalla presentazione della domanda senza osservazioni del Ministero della salute, la pubblicit\u00e0 si intende autorizzata.",
}

LABEL = {
    "art113_c1_a": "Art. 113 c.1 lett. a",
    "art114_c2": "Art. 114 c.2",
    "art114_c3_a": "Art. 114 c.3 lett. a",
    "art114_c3_b": "Art. 114 c.3 lett. b",
    "art116_c1_a": "Art. 116 c.1 lett. a",
    "art116_c1_b1": "Art. 116 c.1 lett. b n.1",
    "art116_c1_b2": "Art. 116 c.1 lett. b n.2",
    "art116_c1_b3": "Art. 116 c.1 lett. b n.3",
    "art117_c1_a": "Art. 117 c.1 lett. a",
    "art117_c1_b": "Art. 117 c.1 lett. b",
    "art117_c1_f": "Art. 117 c.1 lett. f",
    "art117_c1_g": "Art. 117 c.1 lett. g",
    "art117_c1_i": "Art. 117 c.1 lett. i",
    "art117_c1_l": "Art. 117 c.1 lett. l",
    "art118_c1": "Art. 118 c.1",
    "art118_c8": "Art. 118 c.8",
}

FONTE = "D.Lgs 219/2006"

# Chiavi citabili come contesto ma MAI come norma violata.
#   art113_c1_a e' la definizione di "pubblicita' di medicinali": una definizione non
#     si viola. In NX6 finiva in "Norma violata" per qualunque menzione dell'art. 113.
#   art118_c8 e' il silenzio-assenso a 45 giorni: e' una norma di favore per
#     l'inserzionista. In NX6 compariva sotto "ELEMENTI OBBLIGATORI MANCANTI" con
#     l'azione "integrare l'elemento obbligatorio", che e' un non senso.
NON_CONTESTABILI = {"art113_c1_a", "art118_c8"}


def _ordine_chiave(k):
    """Ordinamento canonico: articolo, comma, lettera, numero. NX6 stampava le
    norme nell'ordine in cui il modello aveva messo le chiavi, quindi lo stesso
    report citava "117 lett. b | 114 c.3 lett. a" in un rilievo e "117 b | 117 f"
    in un altro."""
    m = re.match(r"art(\d+)_c(\d+)_?([a-z]*)(\d*)", k)
    if not m:
        return (999, 999, "", 0)
    return (int(m.group(1)), int(m.group(2)), m.group(3), int(m.group(4) or 0))


def ordina_chiavi(ks):
    return sorted(ks, key=_ordine_chiave)


class Corpus:
    """Corpus normativo. La data di vigenza viene dal corpus, MAI dall'orologio,
    e vale SOLO per le chiavi effettivamente fornite dal corpus."""

    def __init__(self, norme=None, data_vigenza=None, origine="testi incorporati nel motore",
                 warnings=None, da_file=None):
        self.norme = dict(norme or EMBED_NORME)
        self.data_vigenza = data_vigenza
        self.origine = origine
        self.warnings = list(warnings or [])
        # Chiavi lette DAVVERO dal file. Le altre vengono dai testi incorporati e
        # non possono essere presentate come vigenti a una data verificata.
        self.da_file = set(da_file or ())

    @classmethod
    def load(cls, path="kb/pharma_norme_chiavi.txt"):
        """
        Formato atteso:
            # DATA_VIGENZA: 23/08/2026
            [KEY art117_c1_b]
            <testo letterale>
        """
        try:
            raw = open(path, encoding="utf-8").read()
        except FileNotFoundError:
            return cls(warnings=["Corpus da file non trovato (%s): in uso i testi incorporati "
                                 "nel motore. Nessuna vigenza verificata." % path])
        except Exception as e:
            return cls(warnings=["Corpus da file illeggibile (%s: %s): in uso i testi incorporati "
                                 "nel motore. Nessuna vigenza verificata." % (path, e)])

        norme = dict(EMBED_NORME)
        da_file, warn = set(), []
        # `[^\n]*` tollera un commento sulla stessa riga della chiave
        # ("[KEY art114_c2]   # Art. 114 c.2"): un file di corpus curato a mano ce
        # l'ha quasi sempre, e con \s*\n veniva scartato in silenzio.
        for k, v in re.findall(r"\[KEY ([a-zA-Z0-9_]+)\][^\n]*\n(.+?)(?=\n\[KEY |\Z)", raw, re.S):
            k = k.strip()
            if k not in LABEL:
                warn.append("Chiave sconosciuta nel corpus, ignorata: %s" % k)
                continue
            testo = v.strip()
            if not testo:
                warn.append("Chiave presente ma vuota nel corpus, ignorata: %s" % k)
                continue
            norme[k] = testo
            da_file.add(k)

        m = re.search(r"#\s*DATA_VIGENZA:\s*([0-9]{2}/[0-9]{2}/[0-9]{4})", raw)
        data = m.group(1) if m else None
        if not data:
            warn.append("Il corpus non dichiara DATA_VIGENZA: la vigenza non \u00e8 verificabile.")

        # NX6 calcolava questo controllo DOPO aver riempito `norme` con EMBED_NORME,
        # quindi era sempre vuoto: un file di corpus con 2 chiavi su 16 passava senza
        # un avviso, e il report dichiarava vigenti al 23/08/2026 sedici testi che
        # venivano dalle costanti del motore.
        assenti = [k for k in LABEL if k not in da_file]
        if assenti:
            warn.append("Chiavi non fornite dal corpus (%d su %d): %s. Per queste il motore usa "
                        "i testi incorporati e NON dichiara alcuna vigenza."
                        % (len(assenti), len(LABEL),
                           ", ".join(ordina_chiavi(assenti)) if len(assenti) <= 4
                           else "%s e altre %d" % (", ".join(ordina_chiavi(assenti)[:3]),
                                                   len(assenti) - 3)))

        return cls(norme, data, origine=path, warnings=warn, da_file=da_file)

    def ha(self, key):
        return key in self.norme

    def verificata(self, key):
        """Vero se il testo di questa chiave viene dal corpus del cliente E c'e' una
        data di vigenza dichiarata."""
        return bool(self.data_vigenza) and key in self.da_file

    def cita(self, key):
        """Citazione completa e opponibile. Il testo NON e' mai generato dal modello."""
        if key not in self.norme:
            raise KeyError("chiave normativa assente dal corpus: %s" % key)
        if self.verificata(key):
            vig = "testo vigente al %s" % self.data_vigenza
        elif key not in self.da_file:
            vig = "TESTO NON FORNITO DAL CORPUS: vigenza non verificata"
        else:
            vig = "VIGENZA NON DICHIARATA DAL CORPUS"
        return "%s, %s \u2014 %s, fonte Normattiva: \u00ab%s\u00bb" % (
            FONTE, LABEL[key], vig, self.norme[key])

    def cita_molte(self, keys):
        return " | ".join(self.cita(k) for k in ordina_chiavi(keys))

    def fingerprint(self):
        h = hashlib.sha256()
        for k in sorted(self.norme):
            h.update(k.encode() + b"\x00" + self.norme[k].encode() + b"\x00")
        return h.hexdigest()[:12]

    def descrizione(self):
        """Riga "STATO DEL CORPUS" costruita da cio' che il corpus contiene DAVVERO.
        NX6 la cablava: dichiarava Farmindustria e le FAQ AIFA ver. 230503 anche
        quando l'oggetto Corpus conteneva solo le 16 chiavi del D.Lgs 219/2006."""
        n_file, n_tot = len(self.da_file), len(LABEL)
        if n_file == n_tot and self.data_vigenza:
            copertura = "%d/%d chiavi dal corpus, testi vigenti al %s" % (
                n_file, n_tot, self.data_vigenza)
        elif n_file:
            copertura = ("%d/%d chiavi dal corpus (vigenti al %s); le restanti %d dai testi "
                         "incorporati nel motore, senza vigenza verificata"
                         % (n_file, n_tot, self.data_vigenza or "data non dichiarata",
                            n_tot - n_file))
        else:
            copertura = ("nessuna chiave fornita dal corpus: tutti i %d testi provengono dai "
                         "testi incorporati nel motore, senza vigenza verificata" % n_tot)
        return "%s \u2014 %s | Origine: %s | Impronta: %s" % (
            FONTE, copertura, self.origine, self.fingerprint())


# ----------------------------------------------------------------------------
# TABELLA DI SEVERITA' - unica fonte di verita'
# ----------------------------------------------------------------------------

CRITICA, AVVERTENZA, MANCANTE = "critica", "avvertenza", "mancante"
_RANK = {CRITICA: 3, AVVERTENZA: 2, MANCANTE: 1}

SEVERITA = {
    "art114_c2":   AVVERTENZA,   # conformita' al RCP: dipende da documento assente
    "art114_c3_a": CRITICA,
    "art114_c3_b": CRITICA,
    "art116_c1_a": CRITICA,
    "art116_c1_b1": MANCANTE,
    "art116_c1_b2": MANCANTE,
    "art116_c1_b3": MANCANTE,
    "art117_c1_a": CRITICA,
    "art117_c1_b": CRITICA,
    "art117_c1_f": CRITICA,
    "art117_c1_g": AVVERTENZA,   # assimilazione: dipende dal layout grafico
    "art117_c1_i": AVVERTENZA,   # autodiagnosi: valutazione interpretativa
    "art117_c1_l": CRITICA,
    "art118_c1":  MANCANTE,
}

# Rilievi che per natura riguardano l'intero materiale, non una riga.
# In NX7 questa lista e' un FALLBACK: si usa solo dopo che l'ancoraggio e' fallito.
DOC_WIDE = {"art114_c3_a", "art114_c3_b", "art116_c1_a", "art116_c1_b1",
            "art116_c1_b2", "art116_c1_b3", "art118_c1", "art118_c8"}

AZIONE_SUFFIX = [
    ("art117_c1_l", "sanabil",
     "Le attestazioni di guarigione sono vietate in assoluto: non sono sanabili."),
    ("art117_c1_f", "sanabil",
     "Il divieto \u00e8 assoluto: non \u00e8 sanabile con aggiunta di fonte o disclaimer."),
    ("art117_c1_b", "sanabil",
     "Il divieto \u00e8 assoluto: non \u00e8 sanabile con aggiunta di fonte o disclaimer."),
    ("art117_c1_a", "sanabil",
     "Il divieto \u00e8 assoluto: non consente riformulazioni."),
    ("art116_c1_a", "preminente",
     "La dicitura va collocata in posizione preminente."),
]

AZIONE_DEFAULT = {
    CRITICA:    "Eliminare o correggere l'elemento contestato secondo quanto descritto nel problema.",
    AVVERTENZA: "Verificare l'elemento contestato rispetto alla fonte indicata prima di ogni divulgazione.",
    MANCANTE:   "Integrare l'elemento obbligatorio conformemente alla norma citata.",
}

STATI_AMMESSI = {"COMPLIANT", "NEEDS_REVISION", "CRITICAL_FAIL", "OUT_OF_SCOPE", "NO_FINDINGS"}

STATUS_CLAIM = {
    "UNVERIFIABLE_RCP_NOT_IN_KB": "non verificabile: RCP non presente nella knowledge base",
    "CONFORME_RCP": "conforme al RCP",
    "VIOLAZIONE_RCP": "in contrasto con il RCP",
}

# ----------------------------------------------------------------------------
# GATE
# ----------------------------------------------------------------------------

PROMPT_MARKERS = [
    "[{'type'", '[{"type"', "'type': 'text'", '"type": "text"',
    "sei un senior", "system prompt", "knowledge_chunks", "skill_prompt",
    "regole fondamentali", "<|", "assistant:", "role:",
    "pseudonimizza=", "temperatura 0", "zero allucinazioni",
    "note_informative", "norma_key", "stato_complessivo",
]
ANALOGIA_TERMS = [
    "per analogia", "in via estensiva", "applicabile in quanto compatibile",
    "eventuali linee guida", "analogicamente", "mutatis mutandis",
]
RE_CHIAVE_NUDA = re.compile(r"\bart\d{3}_c\d[a-z0-9_]*\b")
RE_SERIALIZZATO = re.compile(r"[\[{]\s*['\"]\w+['\"]\s*:")

CAMPI_OBBLIGATORI = ("titolo", "problema", "norma_violata", "azione")
CAMPI_VISIBILI = ("titolo", "problema", "norma_violata", "azione", "posizione", "quote")


class ReportNonValido(Exception):
    def __init__(self, problemi):
        self.problemi = problemi
        super().__init__("Report bloccato dai gate:\n- " + "\n- ".join(problemi))


# ----------------------------------------------------------------------------
# NORMALIZZAZIONE
# ----------------------------------------------------------------------------

def _s(v, d=""):
    return str(v if v is not None else d).strip()


def _oneline(v, d=""):
    if isinstance(v, (list, tuple)):
        v = " - ".join(_s(x) for x in v if _s(x))
    return _s(v, d).replace("\r", " ").split("\n")[0].strip() or d


def _keys(v):
    ks = v.get("norma_key") or v.get("norma_keys") or []
    if isinstance(ks, str):
        ks = [ks]
    return [k for k in ks if isinstance(k, str) and k in LABEL]


_RE_ART = r"\bart(?:icol[oi]|t)?\.?\s*%s\b"


def _lettere(c):
    """Estrae le lettere citate, incluse le elencazioni: 'lettere b) e f)'.

    L'apostrofo NON chiude una lettera: in "lett. b), che vieta l'uso di..." la `l`
    di `l'uso` veniva letta come lettera citata e produceva art117_c1_l, cioe' gli
    attestati di guarigione, con la coda "vietate in assoluto: non sono sanabili".
    E' lo stesso difetto gia' corretto in _virgolettati e mai propagato qui.
    """
    out = []
    for m in re.finditer(r"lett(?:era|ere)?\.?", c):
        finestra = c[m.end():m.end() + 28]
        finestra = re.split(r"lett(?:era|ere)?\.?", finestra)[0]
        for L in re.findall(r"(?<![a-z\u00e0-\u00ff])([a-z])(?![a-z\u00e0-\u00ff'\u2019])", finestra):
            if L not in out:
                out.append(L)
    return out


def _coda(t, fine, altri, n=140):
    """Testo che segue un riferimento di articolo, troncato al riferimento successivo."""
    c = t[fine:fine + n]
    return re.split("|".join(_RE_ART % a for a in altri), c)[0]


def _estrai_chiavi_da_testo(v):
    """
    Fallback quando il modello non fornisce norma_key: deduce le chiavi da
    riferimenti testuali. NON genera mai testo di legge, solo etichette.
    """
    t = " ".join(_s(v.get(f)) for f in
                 ("norma_key", "titolo", "problema", "norma_violata", "norma", "riferimento")).lower()
    ks = []

    for m in re.finditer(_RE_ART % "117", t):
        for L in _lettere(_coda(t, m.end(), ["113", "114", "116", "118", "119"])):
            if ("art117_c1_" + L) in LABEL:
                ks.append("art117_c1_" + L)

    for m in re.finditer(_RE_ART % "116", t):
        c = _coda(t, m.end(), ["113", "114", "117", "118", "119"])
        for N in re.findall(r"lett(?:era|ere)?\.?\s*b\)?[\s.]*(?:n\.?|numero)?\s*([123])\b", c):
            ks.append("art116_c1_b" + N)
        if re.search(r"lett(?:era|ere)?\.?\s*a\)?\b", c):
            ks.append("art116_c1_a")

    for m in re.finditer(_RE_ART % "114", t):
        c = _coda(t, m.end(), ["113", "116", "117", "118", "119"])
        if re.search(r"(?:c\.?|comma)\s*2\b", c):
            ks.append("art114_c2")
        if re.search(r"(?:c\.?|comma)\s*3\b", c):
            lett = _lettere(c)
            if "b" in lett:
                ks.append("art114_c3_b")
            if "a" in lett or not lett:
                ks.append("art114_c3_a")

    # NX6 aggiungeva art118_c1 a OGNI menzione dell'art. 118, comma compreso o no:
    # un rilievo che citava il solo c.8 usciva con entrambi i commi.
    for m in re.finditer(_RE_ART % "118", t):
        c = _coda(t, m.end(), ["113", "114", "116", "117", "119"])
        commi = set(re.findall(r"(?:c\.?|comma|commi)\s*([0-9]+)", c))
        if "8" in commi:
            ks.append("art118_c8")
        if "1" in commi or not commi:
            ks.append("art118_c1")

    for m in re.finditer(_RE_ART % "113", t):
        c = _coda(t, m.end(), ["114", "116", "117", "118", "119"])
        if re.search(r"(?:c\.?|comma)\s*1\b", c) and "a" in _lettere(c):
            ks.append("art113_c1_a")

    out = []
    for k in ks:
        if k in LABEL and k not in out:
            out.append(k)
    return ordina_chiavi(out)


def normalizza(rep):
    """
    Accetta lo schema legacy e lo converte in un'unica lista `rilievi`.
    NON appiattisce nulla in stringhe: la struttura viene preservata.
    """
    rilievi = []
    for sez in ("violazioni_critiche", "violations", "avvertenze", "warnings",
                "elementi_mancanti", "rilievi"):
        for v in (rep.get(sez) or []):
            if isinstance(v, dict):
                d = dict(v)
            else:
                d = {"titolo": _s(v)[:120], "problema": _s(v)}
            if not _s(d.get("problema")):
                d["problema"] = _s(d.get("testo") or d.get("descrizione")
                                   or d.get("issue") or d.get("elemento") or d.get("titolo"))
            if not _s(d.get("titolo")):
                d["titolo"] = _s(d.get("title") or d.get("elemento") or "Rilievo")
            d["titolo"] = re.sub(r"^\[[^\]]{0,60}\]\s*", "", d["titolo"]).strip()
            d["norma_key"] = ordina_chiavi(_keys(d) or _estrai_chiavi_da_testo(d))
            d["azione"] = _s(d.get("azione") or d.get("azione_richiesta"))
            d["quote"] = _s(d.get("quote") or d.get("testo_contestato"))
            d["_origine"] = sez
            rilievi.append(d)

    rep = dict(rep)
    rep["rilievi"] = rilievi
    for k in ("violazioni_critiche", "violations", "avvertenze", "warnings", "elementi_mancanti"):
        rep.pop(k, None)

    # NX6 leggeva rep["stato"], che il prompt non produce: lo stato del modello
    # veniva scartato e sostituito da un default calcolato sui conteggi, quindi un
    # OUT_OF_SCOPE usciva come NO_FINDINGS con il perimetro "VERIFICATO" al seguito.
    stato = _oneline(rep.get("stato") or rep.get("stato_complessivo")).upper()
    rep["stato"] = stato if stato in STATI_AMMESSI else ""

    claims = []
    for c in (rep.get("claims_rcp") or []):
        if isinstance(c, dict):
            claims.append({"claim": _s(c.get("claim")),
                           "sezioni_rcp": _s(c.get("sezioni_rcp") or c.get("sezioni")),
                           "status": _s(c.get("status"), "UNVERIFIABLE_RCP_NOT_IN_KB")})
        else:
            claims.append({"claim": _s(c), "sezioni_rcp": "",
                           "status": "UNVERIFIABLE_RCP_NOT_IN_KB"})
    rep["claims_rcp"] = [c for c in claims if c["claim"]]

    notes = []
    for n in (rep.get("note_informative") or []):
        s = (_s(n.get("titolo")) + " " + _s(n.get("testo"))).strip() if isinstance(n, dict) else _s(n)
        if s:
            notes.append(s)
    rep["note_informative"] = notes
    rep["_fusioni"] = list(rep.get("_fusioni") or [])
    return rep


def _norm(t):
    return re.sub(r"[^a-z0-9]+", "", _s(t).lower())


def deduplica(rep):
    """
    Due rilievi sono lo stesso rilievo se hanno stesse chiavi, stessa quote E
    titoli sovrapponibili.

    NX6 non guardava il titolo: la firma era (chiavi, quote). Sulla stessa frase,
    sotto le stesse lettere, "Assenza totale di effetti collaterali" e "Aggettivo
    sicuro" - che il prompt impone come rilievi SEPARATI - collassavano in uno solo
    e il secondo spariva senza lasciare traccia nel report.
    """
    keep, gruppi = [], {}
    for v in rep["rilievi"]:
        sig = (tuple(v["norma_key"]), _norm(v.get("quote")) or _norm(v["titolo"])[:60])
        prec = gruppi.get(sig)
        if prec is not None:
            ta, tb = _token(prec["titolo"]), _token(v["titolo"])
            simile = bool(ta and tb) and len(ta & tb) / min(len(ta), len(tb)) >= 0.75
            if simile:
                rep["_fusioni"].append(
                    "\u00ab%s\u00bb assorbito in \u00ab%s\u00bb (stessa norma, stessa frase, "
                    "stesso oggetto)" % (v["titolo"], prec["titolo"]))
                continue
            # Stessa norma e stessa frase ma oggetti diversi: sono DUE rilievi.
            sig = sig + (_norm(v["titolo"])[:40],)
            if sig in gruppi:
                continue
        gruppi[sig] = v
        keep.append(v)
    rep["rilievi"] = keep
    return rep


def unisci_documentwide(rep):
    """
    Due rilievi senza quote, con chiavi in rapporto di contenimento e titoli
    sovrapponibili, sono lo stesso rilievo espresso due volte dal modello.
    """
    cand = [v for v in rep["rilievi"] if not _s(v.get("quote"))]
    scarta = set()
    for i, a in enumerate(cand):
        for b in cand[i + 1:]:
            if id(a) in scarta or id(b) in scarta:
                continue
            ka, kb = set(a["norma_key"]), set(b["norma_key"])
            if not ka or not kb or not (ka <= kb or kb <= ka):
                continue
            ta, tb = _token(a["titolo"]), _token(b["titolo"])
            if not ta or not tb:
                continue
            soglia = 0.3 if ka == kb else 0.6
            if len(ta & tb) / min(len(ta), len(tb)) < soglia:
                continue
            peggiore = a if (len(ka), len(_s(a["problema"]))) < (len(kb), len(_s(b["problema"]))) else b
            migliore = b if peggiore is a else a
            rep["_fusioni"].append(
                "\u00ab%s\u00bb assorbito in \u00ab%s\u00bb (rilievo sull'intero materiale, "
                "stesse norme)" % (peggiore["titolo"], migliore["titolo"]))
            scarta.add(id(peggiore))
    if scarta:
        rep["rilievi"] = [v for v in rep["rilievi"] if id(v) not in scarta]
    return rep


# ----------------------------------------------------------------------------
# CLASSIFICAZIONE
# ----------------------------------------------------------------------------

def classifica(rep):
    """Assegna la severita' da tabella. Il modello non decide la gravita'."""
    for v in rep["rilievi"]:
        ks = [k for k in v["norma_key"] if k in SEVERITA]
        if not ks:
            v["severita"] = AVVERTENZA
            v["_no_key"] = True
            continue
        sev = max((SEVERITA[k] for k in ks), key=lambda s: _RANK[s])
        if v.get("dipende_da_rcp") and sev == CRITICA and set(ks) <= {"art114_c2"}:
            sev = AVVERTENZA
        v["severita"] = sev
    return rep


def cita_norme(rep, corpus):
    """Il campo norma_violata viene SEMPRE ricostruito dal corpus, in ordine canonico.
    Le chiavi non contestabili vengono rimosse: possono stare in una nota, non in
    "Norma violata"."""
    for v in rep["rilievi"]:
        ks = [k for k in v["norma_key"] if corpus.ha(k)]
        scartate = [k for k in ks if k in NON_CONTESTABILI]
        ks = ordina_chiavi([k for k in ks if k not in NON_CONTESTABILI])
        if scartate:
            v["_chiavi_non_contestabili"] = scartate
        v["norma_key"] = ks
        v["norma_violata"] = corpus.cita_molte(ks) if ks else ""
    return rep


_COPPIE = [("\u00ab", "\u00bb"), ("\u201c", "\u201d"), ('"', '"'), ("\u2018", "\u2019")]


def _virgolettati(t):
    """Frammenti fra virgolette, dal piu' lungo al piu' corto.
    L'apostrofo italiano (un'attestazione, dell'AIC) NON e' un delimitatore."""
    t = _s(t)
    fr = []
    for ap, ch in _COPPIE:
        fr += re.findall("%s([^%s]{8,160})%s" % (re.escape(ap), re.escape(ch), re.escape(ch)), t)
    fr += re.findall(r"(?<![A-Za-z\u00c0-\u00ff])'([^']{8,160})'(?![A-Za-z\u00c0-\u00ff])", t)
    return sorted({f.strip() for f in fr if f.strip()}, key=len, reverse=True)


def ancora_posizioni(rep, testo):
    """
    Posizione e testo contestato derivati dal materiale reale.

    NX6 saltava del tutto questa funzione per i rilievi MANCANTE o document-wide:
    impostava "Intero materiale" e usciva. La quote del modello restava quella
    grezza e render_md la stampava come "Testo contestato" senza che nessuno avesse
    verificato che esistesse nel materiale. Qui si verifica SEMPRE: se il frammento
    non si trova, non si stampa.
    """
    righe = [l for l in _s(testo).split("\n") if l.strip()]

    def trova(q):
        qn = _norm(q)
        if not qn or len(qn) < 6:
            return None
        for i, riga in enumerate(righe, 1):
            if qn in _norm(riga):
                for f in re.split(r"(?<=[.!?])\s+", riga):
                    if qn in _norm(f):
                        f = f.strip()
                        return "Riga %d (%s)" % (i, f if len(f) <= 90 else f[:87] + "\u2026")
                riga = riga.strip()
                return "Riga %d (%s)" % (i, riga if len(riga) <= 90 else riga[:87] + "\u2026")
        return None

    for v in rep["rilievi"]:
        quote_modello = _s(v.get("quote"))
        cand = [c for c in ([quote_modello] + _virgolettati(v.get("problema"))
                            + _virgolettati(v.get("posizione"))) if c]
        p, scelta = None, None
        for c in sorted(set(cand), key=len, reverse=True):
            t = trova(c)
            if t:
                p, scelta = t, c
                break

        if scelta:
            v["quote"] = scelta
            v["posizione"] = p
            continue

        if quote_modello:
            v["_quote_non_verificata"] = quote_modello
            v["quote"] = ""
        if v["severita"] == MANCANTE or (v["norma_key"] and set(v["norma_key"]) <= DOC_WIDE):
            v["posizione"] = "Intero materiale"
        elif _s(v.get("posizione")):
            v["posizione"] = _s(v["posizione"])
            v["_pos_non_ancorata"] = True
        else:
            v["posizione"] = "Non localizzato nel testo fornito"
            v["_pos_non_ancorata"] = True
    return rep


def rimandi_incrociati(rep):
    """Due rilievi sulla STESSA quote si rimandano a vicenda. Meccanismo generico."""
    per_quote = {}
    for v in rep["rilievi"]:
        q = _norm(v.get("quote"))
        if q and len(q) > 8:
            per_quote.setdefault(q, []).append(v)

    ordinati = ordina(rep)
    numero = {id(v): (sev, i) for sev, lst in ordinati.items() for i, v in enumerate(lst, 1)}
    nome = {CRITICA: "violazione critica", AVVERTENZA: "avvertenza", MANCANTE: "elemento mancante"}

    for q, gruppo in per_quote.items():
        if len(gruppo) < 2:
            continue
        for v in gruppo:
            altri = []
            for w in gruppo:
                if w is v:
                    continue
                sev, i = numero.get(id(w), (None, None))
                if sev:
                    altri.append("%s n. %d" % (nome[sev], i))
            if altri and "v. anche" not in v["problema"]:
                v["problema"] = v["problema"].rstrip() + \
                    " Sulla stessa frase v. anche: %s." % ", ".join(altri)
    return rep


def completa_azioni(rep):
    for v in rep["rilievi"]:
        a = _s(v.get("azione"))
        if not a:
            if v["severita"] == MANCANTE or v.get("_origine") == "elementi_mancanti":
                a = "Integrare il materiale con: %s." % _minuscola_iniziale(v["titolo"].rstrip("."))
            else:
                a = AZIONE_DEFAULT[v["severita"]]
        usati = set()
        for k, marker, testo in AZIONE_SUFFIX:
            if k not in v["norma_key"] or marker in usati:
                continue
            usati.add(marker)
            if marker in a.lower() or _gia_detto(testo, a):
                continue
            a = a.rstrip()
            if a and a[-1] not in ".;:!?":
                a += "."
            a = (a + " " + testo).strip()
        v["azione"] = pulisci(a)
        if _norm(v["problema"]) == _norm(v["titolo"]):
            v["problema"] = "Il materiale non contiene: %s." % _minuscola_iniziale(v["titolo"].rstrip("."))
        v["problema"] = pulisci(v["problema"])
        v["titolo"] = pulisci(v["titolo"])
    return rep


def _tronca(t, n):
    t = _s(t).strip().rstrip(".;")
    if len(t) <= n:
        return t
    taglio = t[:n]
    sp = taglio.rfind(" ")
    return (taglio[:sp] if sp > n // 2 else taglio).rstrip(" ,;.") + "\u2026"


def _prima_frase(t, maxlen=150):
    """Prima frase compiuta. Un punto e' fine frase solo se la parola che lo precede
    ha almeno 5 lettere: esclude Dott., es., art., sez., n., lett."""
    t = _s(t).strip()
    for m in re.finditer(r"([A-Za-z\u00c0-\u00ff]+)['\"\u00bb\u201d)]*\.\s+(?=[A-Z\u00c0-\u00dd])", t):
        if len(m.group(1)) >= 5:
            return t[:m.end()].strip()
    return _tronca(t, maxlen)


def _token(t):
    return {w for w in re.findall(r"[a-z\u00e0-\u00ff]{4,}", _s(t).lower())}


def _gia_detto(nuovo, esistente, soglia=0.6):
    a, b = _token(nuovo), _token(esistente)
    return bool(a) and len(a & b) / len(a) >= soglia


def _minuscola_iniziale(t):
    """Abbassa solo la prima lettera: preserva acronimi come INN, AIC, RCP."""
    t = _s(t)
    return (t[0].lower() + t[1:]) if t else t


def _caporali(s):
    """Una sola convenzione di virgolettatura in tutto il report.

    NX6 lasciava passare le virgolette del modello: nello stesso rilievo la stessa
    frase compariva come <<X>> in "Testo contestato", "X" in "Posizione" e 'X' in
    "Problema". Tre convenzioni in quattro righe.
    """
    s = re.sub(r'"([^"\n]{2,200})"', "\u00ab\\1\u00bb", s)
    s = re.sub(r'\u201c([^\u201d\n]{2,200})\u201d', "\u00ab\\1\u00bb", s)
    # apice singolo solo se non e' un'elisione (l'uso, un'attestazione)
    s = re.sub(r"(?<![A-Za-z\u00c0-\u00ff])'([^'\n]{2,200})'(?![A-Za-z\u00c0-\u00ff])",
               "\u00ab\\1\u00bb", s)
    return s


def pulisci(s):
    s = _s(s)
    s = s.replace("...", "\x00")
    s = re.sub(r"\.(\s*\.)+", ".", s)
    s = s.replace("\x00", "\u2026")
    s = re.sub(r"\s{2,}", " ", s)
    s = re.sub(r"\s+([,.;:])", r"\1", s)
    return _caporali(s.strip())


def degrada_senza_norma(rep):
    """Nessun rilievo senza norma citabile: se le chiavi non si risolvono,
    l'elemento scende fra le note informative invece di bloccare la build."""
    keep = []
    for v in rep["rilievi"]:
        if v["norma_key"]:
            keep.append(v)
            continue
        motivo = "non \u00e8 agganciato ad alcuna norma contestabile presente nel corpus"
        if v.get("_chiavi_non_contestabili"):
            motivo = ("richiama solo %s, che non \u00e8 una disposizione contestabile"
                      % ", ".join(LABEL[k] for k in v["_chiavi_non_contestabili"]))
        rep["note_informative"].append(
            "[SENZA NORMA CITABILE] " + v["titolo"][:180] + " \u2014 il rilievo " + motivo +
            ": non costituisce contestazione e richiede valutazione umana.")
    rep["rilievi"] = keep
    return rep


def filtro_analogia(rep):
    keep = []
    for v in rep["rilievi"]:
        blob = (v["titolo"] + " " + v["problema"] + " " + _s(v.get("norma_violata"))
                + " " + v["azione"]).lower()
        if any(t in blob for t in ANALOGIA_TERMS):
            rep["note_informative"].append(
                "[DEGRADATO DAL FILTRO ANALOGIA] " + v["titolo"][:180] +
                " \u2014 il rilievo si fondava su un'estensione analogica e non su una norma "
                "direttamente applicabile: richiede valutazione umana.")
            continue
        keep.append(v)
    rep["rilievi"] = keep
    return rep


def note_da_quote_non_verificate(rep):
    """Una quote prodotta dal modello ma assente dal materiale e' un segnale, non un
    dettaglio: va detta al revisore invece di essere stampata come testo del cliente."""
    for v in rep["rilievi"]:
        if v.get("_quote_non_verificata"):
            rep["note_informative"].append(
                "[FRAMMENTO NON RITROVATO] Per il rilievo \u00ab%s\u00bb il sistema non ha "
                "ritrovato nel materiale il frammento indicato in analisi: non \u00e8 stato "
                "riportato nel report. Verificare manualmente la collocazione."
                % v["titolo"][:120])
    return rep


def pulisci_note(rep):
    """Una nota che non segnala nulla non e' una nota."""
    corpo = _norm(" ".join(v["titolo"] + v["problema"] for v in rep["rilievi"]))
    chiavi_gia_contestate = {k for v in rep["rilievi"] for k in v["norma_key"]}
    out, visti = [], set()
    for s in rep["note_informative"]:
        s = pulisci(s)
        if len(_norm(s)) < 25:
            continue
        if any(m in s.lower() for m in PROMPT_MARKERS):
            continue
        if re.search(r"(?i)\bnon\s+(presenta|presentano|sono\s+presenti|risultano|vi\s+sono|"
                     r"\u00e8\s+present\w+|e'\s+present\w+|contiene|compaiono)\b.{0,60}"
                     r"(oltre a quell|particolar|ulterior|altri element|di rilievo|"
                     r"gi[\u00e0a]'? contestat)", s):
            continue
        s = re.sub(r"(?i)\s*informazione non presente nei documenti caricati\.?\s*", " ", s)
        s = re.sub(r"(?i)\s*verifica manuale richiesta\.?\s*$", "", s).strip()
        n = _norm(s)
        if not n or n in visti:
            continue
        if len(n) > 40 and n[:60] in corpo:
            continue
        kn = set(_estrai_chiavi_da_testo({"problema": s}))
        if kn and kn <= chiavi_gia_contestate:
            continue
        visti.add(n)
        out.append(s if s.endswith((".", "!", "?", "\u2026")) else s + ".")
    rep["note_informative"] = out
    return rep


def ordina(rep):
    g = {CRITICA: [], AVVERTENZA: [], MANCANTE: []}
    for v in rep["rilievi"]:
        g[v["severita"]].append(v)
    return g


def conta(rep):
    g = ordina(rep)
    return (len(g[CRITICA]), len(g[AVVERTENZA]), len(g[MANCANTE]),
            len(rep.get("claims_rcp") or []))


def stato_report(rep):
    """Lo stato dichiarato dal modello se ammissibile, altrimenti derivato dai
    conteggi. Un OUT_OF_SCOPE non viene mai sovrascritto."""
    c, w, m, _ = conta(rep)
    if _s(rep.get("stato")).upper() == "OUT_OF_SCOPE":
        return "OUT_OF_SCOPE"
    if c:
        return "CRITICAL_FAIL"
    if w or m:
        return "NEEDS_REVISION"
    return "NO_FINDINGS"


# ----------------------------------------------------------------------------
# VALIDAZIONE (bloccante)
# ----------------------------------------------------------------------------

def valida(rep, corpus, strict=True):
    p = []

    def scan(x, path):
        if isinstance(x, dict):
            for k, v in x.items():
                if str(k).startswith("_"):
                    continue
                scan(v, path + "." + str(k))
        elif isinstance(x, list):
            for i, v in enumerate(x):
                scan(v, "%s[%d]" % (path, i))
        elif isinstance(x, str):
            low = x.lower()
            if any(m in low for m in PROMPT_MARKERS):
                p.append("%s: contiene marcatori di prompt" % path)
            if RE_SERIALIZZATO.search(x):
                p.append("%s: contiene una struttura serializzata" % path)
            if RE_CHIAVE_NUDA.search(x):
                p.append("%s: contiene una chiave interna del corpus (%s)"
                         % (path, RE_CHIAVE_NUDA.search(x).group(0)))
            if any(t in low for t in ANALOGIA_TERMS):
                p.append("%s: contiene un'estensione analogica" % path)

    scan({k: v for k, v in rep.items() if k not in ("rilievi", "_fusioni")}, "rep")

    g = ordina(rep)
    nome = {CRITICA: "violazione critica", AVVERTENZA: "avvertenza", MANCANTE: "elemento mancante"}
    citate = set()
    for sev, lst in g.items():
        for i, v in enumerate(lst, 1):
            eti = "%s n.%d" % (nome[sev], i)
            scan({f: v.get(f) for f in CAMPI_VISIBILI}, eti)
            for f in CAMPI_OBBLIGATORI:
                if not _s(v.get(f)):
                    p.append("%s: campo '%s' vuoto" % (eti, f))
            if not v["norma_key"]:
                p.append("%s: nessuna chiave normativa risolta" % eti)
            for k in v["norma_key"]:
                citate.add(k)
                if not corpus.ha(k):
                    p.append("%s: chiave '%s' assente dal corpus" % (eti, k))
                if k in NON_CONTESTABILI:
                    p.append("%s: '%s' non \u00e8 una disposizione contestabile" % (eti, LABEL[k]))
            if _s(v.get("quote")) and _s(v.get("posizione")) == "Intero materiale":
                p.append("%s: dichiara \u00abIntero materiale\u00bb ma riporta un testo "
                         "contestato puntuale" % eti)

    for i, c in enumerate(rep.get("claims_rcp") or [], 1):
        if not _s(c.get("claim")):
            p.append("claim RCP n.%d: vuoto" % i)

    if not corpus.data_vigenza:
        p.append("corpus: DATA_VIGENZA non dichiarata, le citazioni non sono opponibili")

    # Nessuna norma puo' essere citata come vigente se il testo non viene dal corpus
    # del cliente. Questo e' il gate che in NX6 mancava del tutto.
    non_verificate = ordina_chiavi([k for k in citate if not corpus.verificata(k)])
    if non_verificate:
        p.append("corpus: %d norme citate nel report non provengono dal corpus fornito (%s): "
                 "il report non pu\u00f2 dichiararne la vigenza"
                 % (len(non_verificate), ", ".join(LABEL[k] for k in non_verificate)))

    if strict and p:
        raise ReportNonValido(p)
    return p


# ----------------------------------------------------------------------------
# PIPELINE
# ----------------------------------------------------------------------------

def pipeline(rep, testo, corpus=None, strict=True):
    corpus = corpus or Corpus.load()
    rep = normalizza(rep)
    rep = deduplica(rep)
    rep = classifica(rep)
    rep = cita_norme(rep, corpus)
    rep = degrada_senza_norma(rep)
    rep = unisci_documentwide(rep)
    rep = filtro_analogia(rep)
    rep = ancora_posizioni(rep, testo)
    rep = completa_azioni(rep)
    rep = rimandi_incrociati(rep)
    rep = note_da_quote_non_verificate(rep)
    rep = pulisci_note(rep)
    problemi = valida(rep, corpus, strict=strict)
    return rep, problemi, corpus


# ----------------------------------------------------------------------------
# RENDER
# ----------------------------------------------------------------------------

def azioni_raccomandate(rep):
    g = ordina(rep)
    az = ["Sospendere immediatamente la divulgazione del materiale fino al completamento "
          "delle azioni correttive."]
    for i, v in enumerate(g[CRITICA], 1):
        az.append("%s (violazione critica n. %d)" % (v["azione"], i))
    for i, v in enumerate(g[MANCANTE], 1):
        az.append("%s (elemento mancante n. %d)" % (v["azione"], i))
    for i, v in enumerate(g[AVVERTENZA], 1):
        az.append("%s (avvertenza n. %d)" % (v["azione"], i))
    for c in rep.get("claims_rcp") or []:
        sez = (" \u2014 sezioni %s" % c["sezioni_rcp"]) if c["sezioni_rcp"] else ""
        az.append("Verificare contro il RCP autorizzato il claim: \u00ab%s\u00bb%s"
                  % (c["claim"], sez))
    az.append("Sottoporre il materiale revisionato a validazione umana prima della divulgazione.")
    return az


def codice_report(rep, corpus, quando=None):
    """Codice stabile: stesso report + stesso corpus = stesso codice.

    NX6 metteva datetime.now() con i minuti nel prefisso e ricalcolava il codice a
    ogni rerun di Streamlit: lo stesso report scaricato a cavallo del minuto usciva
    con due codici diversi, e il PDF archiviato su disco ne aveva un terzo.
    """
    quando = quando or datetime.now()
    seme = json.dumps({k: v for k, v in rep.items() if not str(k).startswith("_")},
                      sort_keys=True, default=str) + corpus.fingerprint()
    return "NX-FARMA-%s-%s" % (quando.strftime("%Y%m%d"),
                               hashlib.sha256(seme.encode()).hexdigest()[:8].upper())


def _plurale(n, singolare, plurale):
    return "%d %s" % (n, singolare if n == 1 else plurale)


def render_md(rep, corpus, meta=None):
    meta = meta or {}
    c, w, m, r = conta(rep)
    g = ordina(rep)
    stato = stato_report(rep)
    fuori_ambito = stato == "OUT_OF_SCOPE"
    quando = meta.get("quando") or datetime.now()
    L = []

    L.append("# REPORT DI COMPLIANCE \u2014 Farma Compliance")
    L.append("Data di emissione: %s | Motore: NEXORA Deep Engine | Build %s"
             % (quando.strftime("%d/%m/%Y %H:%M"), BUILD))
    L.append("MATERIALE ANALIZZATO: " + _oneline(meta.get("source_desc"), "Non dichiarato"))
    # NX6 stampava "Nessuna immagine fornita" come default: con un'immagine caricata
    # e nessun URL fallito, il report affermava il contrario del vero.
    L.append("NON ANALIZZATO: " + _oneline(
        meta.get("not_analyzed"), "Nulla: tutto il materiale caricato \u00e8 stato analizzato"))
    L.append("STATO DEL CORPUS: " + corpus.descrizione())
    if corpus.warnings:
        L.append("AVVISI SUL CORPUS: " + " ".join(corpus.warnings))
    L.append("STATO COMPLESSIVO: %s | Tipo materiale: %s"
             % (stato, _oneline(rep.get("tipo_materiale"), "da confermare")))
    L.append("CODICE REPORT: " + (meta.get("codice") or codice_report(rep, corpus, quando)))

    L.append("## RIEPILOGO ESECUTIVO")
    if fuori_ambito:
        L.append("Il materiale \u00e8 risultato fuori dall'ambito del corpus normativo caricato: "
                 "non \u00e8 stato espresso alcun giudizio di conformit\u00e0.")
    else:
        L.append("Rilievi: %s, %s, %s; %s verifica contro il RCP."
                 % (_plurale(c, "violazione critica", "violazioni critiche"),
                    _plurale(w, "avvertenza", "avvertenze"),
                    _plurale(m, "elemento obbligatorio mancante",
                             "elementi obbligatori mancanti"),
                    _plurale(r, "claim richiede", "claim richiedono")))
        if g[CRITICA]:
            prima = _prima_frase(g[CRITICA][0]["azione"]).rstrip(".")
            terza = ("3) integrare gli elementi obbligatori mancanti." if g[MANCANTE]
                     else "3) sottoporre il materiale revisionato a validazione umana.")
            L.append("Azioni prioritarie: 1) sospendere immediatamente la divulgazione; "
                     "2) " + _minuscola_iniziale(prima) + "; " + terza)

    def blocco(v, etichetta, campo_norma):
        L.append("### %s \u2014 %s" % (etichetta, v["titolo"]))
        L.append("Posizione: " + v["posizione"])
        if v.get("quote"):
            L.append("Testo contestato: \u00ab%s\u00bb" % v["quote"])
        L.append("Problema: " + v["problema"])
        L.append(campo_norma + ": " + v["norma_violata"])
        L.append("Azione richiesta: " + v["azione"])

    if g[CRITICA]:
        L.append("## VIOLAZIONI CRITICHE")
        for i, v in enumerate(g[CRITICA], 1):
            blocco(v, "VIOLAZIONE CRITICA %d" % i, "Norma violata")
    if g[AVVERTENZA]:
        L.append("## AVVERTENZE")
        for i, v in enumerate(g[AVVERTENZA], 1):
            blocco(v, "AVVERTENZA %d" % i, "Norma di riferimento")
    if g[MANCANTE]:
        L.append("## ELEMENTI OBBLIGATORI MANCANTI")
        for i, v in enumerate(g[MANCANTE], 1):
            L.append("### ELEMENTO MANCANTE %d \u2014 %s" % (i, v["titolo"]))
            L.append("Norma: " + v["norma_violata"])
            L.append("Azione richiesta: " + v["azione"])

    if rep.get("claims_rcp"):
        L.append("## CLAIM DA VERIFICARE CONTRO RCP")
        for c_ in rep["claims_rcp"]:
            sez = (" \u2014 verificare sezioni %s" % c_["sezioni_rcp"]) if c_["sezioni_rcp"] else ""
            L.append("- \u00ab%s\u00bb \u2014 %s%s"
                     % (c_["claim"], STATUS_CLAIM.get(c_["status"], c_["status"]), sez))

    if rep.get("note_informative"):
        L.append("## NOTE INFORMATIVE (segnalazioni al revisore, NON costituiscono contestazioni)")
        for i, s in enumerate(rep["note_informative"], 1):
            L.append("%d. %s" % (i, s))

    if rep.get("_fusioni"):
        L.append("## RILIEVI ACCORPATI")
        L.append("Il sistema ha unito i rilievi seguenti perch\u00e9 riferiti allo stesso "
                 "oggetto. L'elenco \u00e8 riportato per tracciabilit\u00e0.")
        for i, s in enumerate(rep["_fusioni"], 1):
            L.append("%d. %s" % (i, s))

    L.append("## AZIONI RACCOMANDATE")
    if fuori_ambito:
        L.append("1. Caricare il corpus normativo pertinente al materiale prima di ripetere "
                 "la verifica.")
        L.append("2. Sottoporre il materiale a validazione umana.")
    else:
        for i, a in enumerate(azioni_raccomandate(rep), 1):
            L.append("%d. %s" % (i, a))

    L.append("## NOTA PER IL REVISORE UMANO")
    nv = ["conformit\u00e0 al RCP del prodotto (documento non presente nella knowledge base)",
          "layout grafico, enfasi visiva, immagini e dimensioni dei caratteri",
          "canale di diffusione previsto",
          "identit\u00e0 e consenso dei soggetti eventualmente citati nel materiale"]
    non_anc = [v["titolo"] for v in rep["rilievi"] if v.get("_pos_non_ancorata")]
    if non_anc:
        nv.append("posizione esatta di: " + "; ".join(non_anc[:5]))
    non_ver = ordina_chiavi({k for v in rep["rilievi"] for k in v["norma_key"]
                             if not corpus.verificata(k)})
    if non_ver:
        nv.append("testo e vigenza di: " + "; ".join(LABEL[k] for k in non_ver)
                  + " (non forniti dal corpus caricato)")
    if fuori_ambito:
        L.append("PERIMETRO DELLA VERIFICA \u2014 Il materiale \u00e8 stato classificato fuori "
                 "ambito: NON \u00e8 stata svolta alcuna verifica di merito sugli elementi "
                 "obbligatori n\u00e9 sui divieti di contenuto. NON VERIFICATO (richiede "
                 "verifica umana): " + "; ".join(nv) + ".")
    else:
        L.append("PERIMETRO DELLA VERIFICA \u2014 VERIFICATO: presenza degli elementi "
                 "obbligatori ex art. 116; divieti di contenuto ex art. 117 c.1; principi di "
                 "presentazione ex art. 114 c.3; obbligo di autorizzazione ex art. 118. NON "
                 "VERIFICATO (richiede verifica umana): " + "; ".join(nv) + ".")
    L.append("Le decisioni finali sulla conformit\u00e0 del materiale e sulle azioni correttive "
             "restano di competenza esclusiva del Responsabile del Servizio Scientifico. "
             "Validazione umana richiesta prima dell'uso.")
    L.append("DISCLAIMER: Report generato automaticamente dal sistema di Compliance QA.")
    vig = corpus.data_vigenza or "data non dichiarata dal corpus"
    L.append("TESTI NORMATIVI: consultabili su Normattiva (www.normattiva.it) \u2014 ricerca "
             "\u00abDecreto Legislativo 219/2006\u00bb. Il corpus caricato dichiara i testi "
             "vigenti al %s. NEXORA Deep Engine svolge l'analisi; Normattiva \u00e8 la fonte "
             "pubblica di verifica del testo di legge. NEXORA non \u00e8 affiliata a "
             "Normattiva." % vig)

    return pulisci_md("\n\n".join(L))


def pulisci_md(s):
    s = s.replace("...", "\x00")
    s = re.sub(r"\.(\s*\.)+", ".", s)
    return s.replace("\x00", "\u2026")


# ----------------------------------------------------------------------------
# PDF
# ----------------------------------------------------------------------------

_TRAD_LATIN1 = {ord(k): v for k, v in {
    "\u2014": "-", "\u2013": "-", "\u2212": "-",
    "\u2018": "'", "\u2019": "'", "\u201a": "'",
    "\u201c": '"', "\u201d": '"', "\u201e": '"',
    "\u2026": "...", "\u2022": "-", "\u00a0": " ",
    "\u2192": "->", "\u2265": ">=", "\u2264": "<=",
}.items()}

PERCORSI_FONT = ("fonts/DejaVuSans.ttf", "assets/fonts/DejaVuSans.ttf", "DejaVuSans.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
PERCORSI_FONT_B = ("fonts/DejaVuSans-Bold.ttf", "assets/fonts/DejaVuSans-Bold.ttf",
                   "DejaVuSans-Bold.ttf",
                   "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")


def _ascii_safe(s):
    """Ultima rete se il font Unicode manca: latin-1 contiene tutte le accentate."""
    return s.translate(_TRAD_LATIN1).encode("latin-1", "replace").decode("latin-1")


def font_unicode_disponibile(font_dir=None):
    """Da chiamare all'avvio dell'app: se e' False il PDF esce in latin-1 e il primo
    carattere fuori tabella diventera' "?" nel documento del cliente."""
    import os
    p = list(PERCORSI_FONT)
    if font_dir:
        p.insert(0, os.path.join(font_dir, "DejaVuSans.ttf"))
    return any(os.path.exists(x) for x in p)


def make_pdf(md, codice="", logo="assets/logo.png", font_dir=None):
    """
    Rispetto a NX6:
      - allineamento a sinistra (multi_cell giustificava, con fiumi bianchi);
      - gerarchia visiva: i titoli dei rilievi (###) escono in grassetto;
      - intestazione riservata al logo, che quindi non puo' sovrapporsi al testo;
      - pie' di pagina con codice report e numerazione: un PDF di compliance che si
        separa in quattro fogli anonimi non e' un artefatto tracciabile;
      - il font Unicode si cerca in piu' percorsi.
    """
    try:
        from fpdf import FPDF
    except ImportError:
        return None
    import os

    percorsi = list(PERCORSI_FONT)
    percorsi_b = list(PERCORSI_FONT_B)
    if font_dir:
        percorsi.insert(0, os.path.join(font_dir, "DejaVuSans.ttf"))
        percorsi_b.insert(0, os.path.join(font_dir, "DejaVuSans-Bold.ttf"))

    logo_ok = bool(logo) and os.path.exists(logo)
    # Logo allineato al margine destro. La larghezza si ricava dalle proporzioni
    # reali dell'immagine, cosi' il bordo destro resta allineato al testo
    # qualunque logo venga messo in assets/.
    ALT_LOGO = 18.0
    larg_logo = ALT_LOGO * 1.75
    if logo_ok:
        try:
            from PIL import Image as _Im
            with _Im.open(logo) as _i:
                larg_logo = ALT_LOGO * (_i.width / float(_i.height))
        except Exception:
            pass
    alt_header = 30 if logo_ok else 12

    class Report(FPDF):
        nx_font = "Helvetica"

        def header(self):
            if logo_ok:
                try:
                    self.image(logo, x=self.w - self.r_margin - larg_logo,
                               y=8, h=ALT_LOGO)
                except Exception:
                    pass

        def footer(self):
            self.set_y(-12)
            try:
                self.set_font(self.nx_font, "", 7)
            except Exception:
                self.set_font("Helvetica", "", 7)
            testo = "%s  |  pagina %d di {nb}" % (codice or "-", self.page_no())
            if self.nx_font == "Helvetica":
                testo = _ascii_safe(testo)
            self.cell(0, 6, testo, align="C")

    pdf = Report()
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.set_top_margin(alt_header)

    for p, pb in zip(percorsi, percorsi_b):
        try:
            pdf.add_font("DejaVu", "", p)
            pdf.add_font("DejaVu", "B", pb if os.path.exists(pb) else p)
            pdf.nx_font = "DejaVu"
            break
        except Exception:
            continue

    font = pdf.nx_font
    try:
        pdf.alias_nb_pages()
    except Exception:
        pass
    pdf.add_page()

    for riga in md.split("\n"):
        if not riga.strip():
            pdf.ln(2.5)
            continue
        if riga.startswith("# "):
            pdf.set_font(font, "B", 14)
            riga, h = riga[2:], 6.5
        elif riga.startswith("## "):
            pdf.ln(2)
            pdf.set_font(font, "B", 10.5)
            riga, h = riga[3:], 5.2
        elif riga.startswith("### "):
            pdf.ln(1.5)
            pdf.set_font(font, "B", 9.5)
            riga, h = riga[4:], 4.8
        else:
            pdf.set_font(font, "", 9)
            h = 4.6
        if font == "Helvetica":
            riga = _ascii_safe(riga)
        pdf.multi_cell(0, h, riga, align="L")
    return bytes(pdf.output())
