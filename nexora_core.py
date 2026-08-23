"""
NEXORA Farma Compliance - core
Riscrittura: tabella di regole al posto della pipeline di patch sequenziali.

Principi:
  1. Il testo delle norme non passa MAI dal modello: si risolve per chiave dal corpus.
  2. La severita' non e' decisa dal modello: si deriva dalle chiavi (tabella unica).
  3. La posizione si ancora al testo letterale contestato (quote), non a marker cablati.
  4. Nessuna logica specifica per un materiale: il motore non conosce TussanPlus.
  5. I gate BLOCCANO. validate() solleva ReportNonValido se strict=True.
"""

import re
import json
import hashlib
from datetime import datetime

BUILD = "NX6-core"

# ----------------------------------------------------------------------------
# CORPUS
# ----------------------------------------------------------------------------

EMBED_NORME = {
    "art113_c1_a": "per pubblicita' di medicinali: qualsiasi forma di informazione, di ricerca di mercato e di incentivazione alla prescrizione, alla fornitura, alla vendita o al consumo di medicinali;",
    "art114_c2": "La pubblicita' di un medicinale e' conforme al riassunto delle caratteristiche del prodotto.",
    "art114_c3_a": "La pubblicita' di un medicinale deve favorire l'uso razionale del medicinale, presentandolo in modo obiettivo e senza esagerarne le proprieta'.",
    "art114_c3_b": "La pubblicita' di un medicinale non puo' essere ingannevole.",
    "art116_c1_a": "La pubblicita' di un medicinale presso il pubblico e' realizzata in modo che la natura pubblicitaria del messaggio e' evidente e il prodotto e' chiaramente identificato come medicinale.",
    "art116_c1_b1": "la denominazione del medicinale e la denominazione comune della sostanza attiva;",
    "art116_c1_b2": "le informazioni indispensabili per un uso corretto del medicinale;",
    "art116_c1_b3": "un invito esplicito e chiaro a leggere attentamente le avvertenze figuranti, a seconda dei casi, nel foglio illustrativo o sull'imballaggio esterno.",
    "art117_c1_a": "induca a ritenere che la visita medica o l'intervento chirurgico siano superflui, in particolare offrendo una diagnosi o suggerendo un trattamento per corrispondenza;",
    "art117_c1_b": "induca a ritenere che gli effetti derivanti dall'assunzione del medicinale siano garantiti, non siano accompagnati da reazioni avverse o siano superiori o pari a quelli di un altro trattamento o medicinale;",
    "art117_c1_f": "comprenda una raccomandazione di scienziati, di operatori sanitari o di persone largamente note al pubblico;",
    "art117_c1_g": "assimili il medicinale ad un prodotto alimentare, ad un prodotto cosmetico o ad un altro prodotto di consumo;",
    "art117_c1_i": "possa indurre ad una errata autodiagnosi;",
    "art117_c1_l": "faccia riferimento, in termini impropri, allarmistici o ingannevoli, ad attestati di guarigione;",
    "art118_c1": "Nessuna pubblicita' di medicinali presso il pubblico puo' essere effettuata senza autorizzazione del Ministero della salute.",
    "art118_c8": "Decorsi quarantacinque giorni dalla presentazione della domanda senza osservazioni del Ministero della salute, la pubblicita' si intende autorizzata.",
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


class Corpus:
    """Corpus normativo. La data di vigenza viene dal corpus, MAI dall'orologio."""

    def __init__(self, norme=None, data_vigenza=None, origine="embedded", warnings=None):
        self.norme = dict(norme or EMBED_NORME)
        self.data_vigenza = data_vigenza          # None = non dichiarata
        self.origine = origine
        self.warnings = list(warnings or [])

    @classmethod
    def load(cls, path="kb/pharma_norme_chiavi.txt"):
        """
        Formato atteso:
            # DATA_VIGENZA: 23/08/2026
            [KEY art117_c1_b]
            <testo letterale>
        Se il file manca o non dichiara la data, si ricade sull'embedded
        e lo si DICHIARA nei warnings: nessun fallback silenzioso.
        """
        try:
            raw = open(path, encoding="utf-8").read()
        except FileNotFoundError:
            return cls(warnings=["Corpus da file non trovato (%s): uso testi embedded. "
                                 "Data di vigenza non dichiarata." % path])
        except Exception as e:
            return cls(warnings=["Corpus da file illeggibile (%s: %s): uso testi embedded. "
                                 "Data di vigenza non dichiarata." % (path, e)])

        norme = dict(EMBED_NORME)
        warn = []
        for k, v in re.findall(r"\[KEY ([a-zA-Z0-9_]+)\]\s*\n(.+?)(?=\n\[KEY |\Z)", raw, re.S):
            k = k.strip()
            if k not in LABEL:
                warn.append("Chiave sconosciuta nel corpus, ignorata: %s" % k)
                continue
            norme[k] = v.strip()

        m = re.search(r"#\s*DATA_VIGENZA:\s*([0-9]{2}/[0-9]{2}/[0-9]{4})", raw)
        data = m.group(1) if m else None
        if not data:
            warn.append("Il corpus non dichiara DATA_VIGENZA: la vigenza non e' verificabile.")

        mancanti = [k for k in LABEL if k not in norme]
        if mancanti:
            warn.append("Chiavi assenti dal corpus: %s" % ", ".join(sorted(mancanti)))

        return cls(norme, data, origine=path, warnings=warn)

    def ha(self, key):
        return key in self.norme

    def cita(self, key):
        """Citazione completa e opponibile. Il testo NON e' mai generato."""
        if key not in self.norme:
            raise KeyError("chiave normativa assente dal corpus: %s" % key)
        vig = ("testo vigente al %s" % self.data_vigenza) if self.data_vigenza \
            else "VIGENZA NON DICHIARATA DAL CORPUS"
        return "%s, %s - %s, fonte Normattiva: \u00ab%s\u00bb" % (
            FONTE, LABEL[key], vig, self.norme[key])

    def cita_molte(self, keys):
        return " | ".join(self.cita(k) for k in keys)

    def fingerprint(self):
        h = hashlib.sha256()
        for k in sorted(self.norme):
            h.update(k.encode() + b"\x00" + self.norme[k].encode() + b"\x00")
        return h.hexdigest()[:12]


# ----------------------------------------------------------------------------
# TABELLA DI SEVERITA' - unica fonte di verita'
# ----------------------------------------------------------------------------
# critica    = violazione accertabile sul testo, indipendente da fonti esterne
# avvertenza = accertamento subordinato a una variabile non risolta (RCP, layout)
# mancante   = omissione di un elemento obbligatorio di contenuto

CRITICA, AVVERTENZA, MANCANTE = "critica", "avvertenza", "mancante"
_RANK = {CRITICA: 3, AVVERTENZA: 2, MANCANTE: 1}

SEVERITA = {
    "art113_c1_a": AVVERTENZA,
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
    "art118_c8":  MANCANTE,
}

# Rilievi che per natura riguardano l'intero materiale, non una riga
DOC_WIDE = {"art114_c3_a", "art114_c3_b", "art116_c1_a", "art116_c1_b1",
            "art116_c1_b2", "art116_c1_b3", "art118_c1", "art118_c8"}

# Coda operativa: (chiave, marcatore semantico, testo).
# Si applica AL PIU' UNA coda per marcatore, e mai se il marcatore e' gia' presente
# nell'azione del modello. Ordine = priorita'.
AZIONE_SUFFIX = [
    ("art117_c1_l", "sanabil",
     "Le attestazioni di guarigione sono vietate in assoluto: non sono sanabili."),
    ("art117_c1_f", "sanabil",
     "Il divieto e' assoluto: non e' sanabile con aggiunta di fonte o disclaimer."),
    ("art117_c1_b", "sanabil",
     "Il divieto e' assoluto: non e' sanabile con aggiunta di fonte o disclaimer."),
    ("art117_c1_a", "sanabil",
     "Il divieto e' assoluto: non consente riformulazioni."),
    ("art116_c1_a", "preminente",
     "La dicitura va collocata in posizione preminente."),
]

AZIONE_DEFAULT = {
    CRITICA:    "Eliminare o correggere l'elemento contestato secondo quanto descritto nel problema.",
    AVVERTENZA: "Verificare l'elemento contestato rispetto alla fonte indicata prima di ogni divulgazione.",
    MANCANTE:   "Integrare l'elemento obbligatorio conformemente alla norma citata.",
}

# ----------------------------------------------------------------------------
# GATE
# ----------------------------------------------------------------------------

PROMPT_MARKERS = [
    "[{'type'", '[{"type"', "'type': 'text'", '"type": "text"',
    "sei un senior", "system prompt", "knowledge_chunks", "skill_prompt",
    "regole fondamentali", "<|", "assistant:", "role:",
]
ANALOGIA_TERMS = [
    "per analogia", "in via estensiva", "applicabile in quanto compatibile",
    "eventuali linee guida", "analogicamente", "mutatis mutandis",
]
RE_CHIAVE_NUDA = re.compile(r"\bart\d{3}_c\d[a-z0-9_]*\b")
RE_SERIALIZZATO = re.compile(r"[\[{]\s*['\"]\w+['\"]\s*:")

CAMPI_OBBLIGATORI = ("titolo", "problema", "norma_violata", "azione")
# Solo questi finiscono sotto gli occhi del cliente: solo questi vanno ispezionati
# per leak di chiavi, prompt e strutture serializzate.
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
    return _s(v, d).replace("\r", " ").split("\n")[0].strip() or d


def _keys(v):
    ks = v.get("norma_key") or v.get("norma_keys") or []
    if isinstance(ks, str):
        ks = [ks]
    return [k for k in ks if isinstance(k, str) and k in LABEL]


_RE_ART = r"\bart(?:icol[oi]|t)?\.?\s*%s\b"
_RE_LETT = r"lett(?:era|ere)?\.?\s*([a-z])\)?\b"


def _lettere(c):
    """Estrae le lettere citate, incluse le elencazioni: 'lettere b) e f)', 'lett. a e b'.
    Le lettere non presenti nel corpus vengono scartate a valle."""
    out = []
    for m in re.finditer(r"lett(?:era|ere)?\.?", c):
        finestra = c[m.end():m.end() + 28]
        finestra = re.split(r"lett(?:era|ere)?\.?", finestra)[0]
        for L in re.findall(r"(?<![a-z])([a-z])(?![a-z])", finestra):
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
    Gestisce elencazioni ("lett. b e lett. f") e riferimenti puntati
    ("art. 116 c.1 lett. b n.3").
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

    for m in re.finditer(_RE_ART % "118", t):
        c = _coda(t, m.end(), ["113", "114", "116", "117", "119"])
        ks.append("art118_c1")
        if re.search(r"(?:c\.?|comma)\s*8\b", c):
            ks.append("art118_c8")

    if re.search(_RE_ART % "113", t):
        ks.append("art113_c1_a")

    out = []
    for k in ks:
        if k in LABEL and k not in out:
            out.append(k)
    return out


def normalizza(rep):
    """
    Accetta lo schema legacy (violazioni_critiche / avvertenze / violations /
    elementi_mancanti) e lo converte in un'unica lista `rilievi`.
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
            d["norma_key"] = _keys(d) or _estrai_chiavi_da_testo(d)
            d["azione"] = _s(d.get("azione") or d.get("azione_richiesta"))
            d["quote"] = _s(d.get("quote") or d.get("testo_contestato"))
            d["_origine"] = sez
            rilievi.append(d)

    rep = dict(rep)
    rep["rilievi"] = rilievi
    for k in ("violazioni_critiche", "violations", "avvertenze", "warnings", "elementi_mancanti"):
        rep.pop(k, None)

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
    return rep


def deduplica(rep):
    """Due rilievi sono lo stesso rilievo se hanno stesse chiavi e stessa quote."""
    visti, keep = set(), []
    for v in rep["rilievi"]:
        sig = (tuple(sorted(v["norma_key"])), _norm(v.get("quote")) or _norm(v["titolo"])[:60])
        if sig in visti:
            continue
        visti.add(sig)
        keep.append(v)
    rep["rilievi"] = keep
    return rep


def _norm(t):
    return re.sub(r"[^a-z0-9]+", "", _s(t).lower())


# ----------------------------------------------------------------------------
# CLASSIFICAZIONE
# ----------------------------------------------------------------------------

def classifica(rep):
    """Assegna la severita' da tabella. Il modello non decide la gravita'."""
    for v in rep["rilievi"]:
        ks = v["norma_key"]
        if not ks:
            v["severita"] = AVVERTENZA
            v["_no_key"] = True
            continue
        sev = max((SEVERITA.get(k, AVVERTENZA) for k in ks), key=lambda s: _RANK[s])
        # override esplicito del modello, solo verso il basso e solo se motivato
        if v.get("dipende_da_rcp") and sev == CRITICA and set(ks) <= {"art114_c2"}:
            sev = AVVERTENZA
        v["severita"] = sev
    return rep


def cita_norme(rep, corpus):
    """Il campo norma_violata viene SEMPRE ricostruito dal corpus."""
    for v in rep["rilievi"]:
        ks = [k for k in v["norma_key"] if corpus.ha(k)]
        v["norma_key"] = ks
        v["norma_violata"] = corpus.cita_molte(ks) if ks else ""
    return rep


def ancora_posizioni(rep, testo):
    """
    Posizione derivata dal testo letterale contestato.
    Nessun marker cablato: se la quote non c'e', si dichiara.
    """
    righe = [l for l in _s(testo).split("\n") if l.strip()]

    def trova(q):
        qn = _norm(q)
        if not qn or len(qn) < 6:
            return None
        for i, riga in enumerate(righe, 1):
            if qn in _norm(riga):
                # frase che contiene la quote, non troncamento fisso
                frasi = re.split(r"(?<=[.!?])\s+", riga)
                for f in frasi:
                    if qn in _norm(f):
                        f = f.strip()
                        return "Riga %d (%s)" % (i, f if len(f) <= 90 else f[:87] + "...")
                return "Riga %d" % i
        return None

    for v in rep["rilievi"]:
        if v["severita"] == MANCANTE or set(v["norma_key"]) <= DOC_WIDE:
            v["posizione"] = "Intero materiale"
            continue
        p = trova(v.get("quote")) or trova(v.get("problema"))
        if p:
            v["posizione"] = p
        elif _s(v.get("posizione")):
            v["posizione"] = _s(v["posizione"])
            v["_pos_non_ancorata"] = True
        else:
            v["posizione"] = "Non localizzato nel testo fornito"
            v["_pos_non_ancorata"] = True
    return rep


def rimandi_incrociati(rep):
    """
    Due rilievi sulla STESSA quote con severita' diverse si rimandano a vicenda.
    Meccanismo generico: nessun caso particolare cablato.
    """
    per_quote = {}
    for v in rep["rilievi"]:
        q = _norm(v.get("quote"))
        if q and len(q) > 8:
            per_quote.setdefault(q, []).append(v)

    ordinati = ordina(rep)
    numero = {id(v): (sev, i) for sev, lst in ordinati.items()
              for i, v in enumerate(lst, 1)}
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
            if v["severita"] == MANCANTE:
                a = "Integrare il materiale con: %s." % v["titolo"].rstrip(".").lower()
            else:
                a = AZIONE_DEFAULT[v["severita"]]
        usati = set()
        for k, marker, testo in AZIONE_SUFFIX:
            if k not in v["norma_key"] or marker in usati:
                continue
            usati.add(marker)
            if marker not in a.lower():
                a = (a.rstrip() + " " + testo).strip()
        v["azione"] = pulisci(a)
        v["problema"] = pulisci(v["problema"])
        v["titolo"] = pulisci(v["titolo"])
    return rep


def pulisci(s):
    s = _s(s)
    s = s.replace("...", "\x00")
    s = re.sub(r"\.(\s*\.)+", ".", s)      # ". ." e ".."
    s = s.replace("\x00", "...")
    s = re.sub(r"\s{2,}", " ", s)
    s = re.sub(r"\s+([,.;:])", r"\1", s)
    return s.strip()


def degrada_senza_norma(rep):
    """
    Nessun rilievo senza norma citabile: se le chiavi non si risolvono,
    l'elemento scende fra le note informative invece di bloccare la build.
    E' la stessa regola che il prompt gia' impone al modello.
    """
    keep = []
    for v in rep["rilievi"]:
        if v["norma_key"]:
            keep.append(v)
            continue
        rep["note_informative"].append(
            "[SENZA NORMA CITABILE] " + v["titolo"][:180] +
            " - il rilievo non e' agganciato ad alcuna norma presente nel corpus: "
            "non costituisce contestazione e richiede valutazione umana.")
    rep["rilievi"] = keep
    return rep


def filtro_analogia(rep):
    keep = []
    for v in rep["rilievi"]:
        blob = (v["titolo"] + " " + v["problema"] + " " + _s(v.get("norma_violata")) + " " + v["azione"]).lower()
        if any(t in blob for t in ANALOGIA_TERMS):
            rep["note_informative"].append(
                "[DEGRADATO DAL FILTRO ANALOGIA] " + v["titolo"][:180] +
                " - il rilievo si fondava su un'estensione analogica e non su una norma "
                "direttamente applicabile: richiede valutazione umana.")
            continue
        keep.append(v)
    rep["rilievi"] = keep
    return rep


def pulisci_note(rep):
    """Una nota che non segnala nulla non e' una nota."""
    corpo = _norm(" ".join(v["titolo"] + v["problema"] for v in rep["rilievi"]))
    out, visti = [], set()
    for s in rep["note_informative"]:
        s = pulisci(s)
        if len(_norm(s)) < 25:
            continue
        # una nota che dichiara l'assenza di rilievi non e' una nota
        if re.search(r"(?i)\bnon\s+(presenta|presentano|sono\s+presenti|risultano|vi\s+sono|"
                     r"e'\s+present\w+|contiene|compaiono)\b.{0,60}"
                     r"(oltre a quell|particolar|ulterior|altri element|di rilievo|"
                     r"gia'? contestat)", s):
            continue
        s = re.sub(r"(?i)\s*informazione non presente nei documenti caricati\.?\s*", " ", s)
        s = re.sub(r"(?i)\s*verifica manuale richiesta\.?\s*$", "", s).strip()
        n = _norm(s)
        if not n or n in visti:
            continue
        if len(n) > 40 and n[:60] in corpo:      # duplica un rilievo gia' contestato
            continue
        visti.add(n)
        out.append(s if s.endswith((".", "!", "?")) else s + ".")
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

    scan({k: v for k, v in rep.items() if k != "rilievi"}, "rep")

    g = ordina(rep)
    nome = {CRITICA: "violazione critica", AVVERTENZA: "avvertenza", MANCANTE: "elemento mancante"}
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
                if not corpus.ha(k):
                    p.append("%s: chiave '%s' assente dal corpus" % (eti, k))

    for i, c in enumerate(rep.get("claims_rcp") or [], 1):
        if not _s(c.get("claim")):
            p.append("claim RCP n.%d: vuoto" % i)

    if not corpus.data_vigenza:
        p.append("corpus: DATA_VIGENZA non dichiarata, le citazioni non sono opponibili")

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
    rep = filtro_analogia(rep)
    rep = ancora_posizioni(rep, testo)
    rep = completa_azioni(rep)
    rep = rimandi_incrociati(rep)
    rep = pulisci_note(rep)
    problemi = valida(rep, corpus, strict=strict)
    return rep, problemi, corpus


# ----------------------------------------------------------------------------
# RENDER
# ----------------------------------------------------------------------------

def azioni_raccomandate(rep):
    g = ordina(rep)
    az = ["Sospendere immediatamente la divulgazione del materiale fino al completamento delle azioni correttive."]
    for i, v in enumerate(g[CRITICA], 1):
        az.append("%s (violazione critica n. %d)" % (v["azione"], i))
    for i, v in enumerate(g[MANCANTE], 1):
        az.append("%s (elemento mancante n. %d)" % (v["azione"], i))
    for i, v in enumerate(g[AVVERTENZA], 1):
        az.append("%s (avvertenza n. %d)" % (v["azione"], i))
    for c in rep.get("claims_rcp") or []:
        sez = (" - sezioni %s" % c["sezioni_rcp"]) if c["sezioni_rcp"] else ""
        az.append("Verificare contro il RCP autorizzato il claim: %s%s" % (c["claim"], sez))
    az.append("Sottoporre il materiale revisionato a validazione umana prima della divulgazione.")
    return az


def codice_report(rep, corpus):
    seme = json.dumps(rep, sort_keys=True, default=str) + corpus.fingerprint()
    return "NX-FARMA-%s-%s" % (datetime.now().strftime("%Y%m%d-%H%M"),
                               hashlib.sha256(seme.encode()).hexdigest()[:8].upper())


def render_md(rep, corpus, meta=None):
    meta = meta or {}
    c, w, m, r = conta(rep)
    g = ordina(rep)
    vig = corpus.data_vigenza or "NON DICHIARATA"
    L = []

    L.append("# REPORT DI COMPLIANCE - Farma Compliance")
    L.append("Data di emissione: %s | Motore: NEXORA Deep Engine | Build %s"
             % (datetime.now().strftime("%d/%m/%Y %H:%M"), BUILD))
    L.append("MATERIALE ANALIZZATO: " + _oneline(meta.get("source_desc"), "Testo inserito dall'utente"))
    L.append("NON ANALIZZATO: " + _oneline(meta.get("not_analyzed"), "Nessuna immagine fornita"))
    L.append("STATO DEL CORPUS: %s; Codice Deontologico Farmindustria; FAQ AIFA D&R ver. 230503 "
             "| Testi vigenti al: %s | Origine: %s | Impronta: %s"
             % (FONTE, vig, corpus.origine, corpus.fingerprint()))
    if corpus.warnings:
        L.append("AVVISI SUL CORPUS: " + " ".join(corpus.warnings))
    L.append("STATO COMPLESSIVO: %s | Tipo materiale: %s"
             % (_oneline(rep.get("stato"), "CRITICAL_FAIL" if c else "NO_FINDINGS"),
                _oneline(rep.get("tipo_materiale"), "da confermare")))
    L.append("CODICE REPORT: " + (meta.get("codice") or codice_report(rep, corpus)))

    L.append("## RIEPILOGO ESECUTIVO")
    L.append("Rilievi: %d violazioni critiche, %d avvertenze, %d elementi obbligatori mancanti; "
             "%d claim richiedono verifica contro il RCP." % (c, w, m, r))
    if g[CRITICA]:
        L.append("Azioni prioritarie: 1) sospendere immediatamente la divulgazione; "
                 "2) " + g[CRITICA][0]["azione"].rstrip(".").lower() + "; "
                 "3) integrare gli elementi obbligatori mancanti.")

    def blocco(v, etichetta, campo_norma):
        L.append("%s - %s" % (etichetta, v["titolo"]))
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
            L.append("ELEMENTO MANCANTE %d - %s" % (i, v["titolo"]))
            L.append("Norma: " + v["norma_violata"])
            L.append("Azione richiesta: " + v["azione"])

    if rep.get("claims_rcp"):
        L.append("## CLAIM DA VERIFICARE CONTRO RCP")
        for c_ in rep["claims_rcp"]:
            sez = (" - verificare sezioni %s" % c_["sezioni_rcp"]) if c_["sezioni_rcp"] else ""
            L.append("- \u00ab%s\u00bb - %s%s" % (c_["claim"], c_["status"], sez))

    if rep.get("note_informative"):
        L.append("## NOTE INFORMATIVE (segnalazioni al revisore, NON costituiscono contestazioni)")
        for i, s in enumerate(rep["note_informative"], 1):
            L.append("%d. %s" % (i, s))

    L.append("## AZIONI RACCOMANDATE")
    for i, a in enumerate(azioni_raccomandate(rep), 1):
        L.append("%d. %s" % (i, a))

    L.append("## NOTA PER IL REVISORE UMANO")
    nv = ["conformita' al RCP del prodotto (documento non presente nella knowledge base)",
          "layout grafico, enfasi visiva, immagini e dimensioni dei caratteri",
          "canale di diffusione previsto",
          "identita' e consenso dei soggetti eventualmente citati nel materiale"]
    non_anc = [v["titolo"] for v in rep["rilievi"] if v.get("_pos_non_ancorata")]
    if non_anc:
        nv.append("posizione esatta di: " + "; ".join(non_anc[:5]))
    L.append("PERIMETRO DELLA VERIFICA - VERIFICATO: presenza degli elementi obbligatori ex art. 116; "
             "divieti di contenuto ex art. 117 c.1; principi di presentazione ex art. 114 c.3; "
             "obbligo di autorizzazione ex art. 118. NON VERIFICATO (richiede verifica umana): "
             + "; ".join(nv) + ".")
    L.append("Le decisioni finali sulla conformita' del materiale e sulle azioni correttive restano "
             "di competenza esclusiva del Responsabile del Servizio Scientifico. Validazione umana "
             "richiesta prima dell'uso.")
    L.append("DISCLAIMER: Report generato automaticamente dal sistema di Compliance QA.")
    L.append("TESTI NORMATIVI: consultabili su Normattiva (www.normattiva.it) - ricerca "
             "'Decreto Legislativo 219/2006', testo vigente al %s. NEXORA Deep Engine svolge "
             "l'analisi; Normattiva e' la fonte pubblica di verifica del testo di legge. "
             "NEXORA non e' affiliata a Normattiva." % vig)

    return pulisci_md("\n\n".join(L))


def pulisci_md(s):
    s = s.replace("...", "\x00")
    s = re.sub(r"\.(\s*\.)+", ".", s)
    s = s.replace("\x00", "...")
    return s


def make_pdf(md):
    """UTF-8 vero: niente encode latin-1, niente spezzatura a meta' parola."""
    try:
        from fpdf import FPDF
    except ImportError:
        return None
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.add_page()
    font = "Helvetica"
    for path, name in (("DejaVuSans.ttf", "DejaVu"), ("fonts/DejaVuSans.ttf", "DejaVu")):
        try:
            pdf.add_font(name, "", path)
            pdf.add_font(name, "B", path)
            font = name
            break
        except Exception:
            continue
    for riga in md.split("\n"):
        if not riga.strip():
            pdf.ln(3)
            continue
        if riga.startswith("# "):
            pdf.set_font(font, "B", 14)
            riga = riga[2:]
        elif riga.startswith("## "):
            pdf.ln(2)
            pdf.set_font(font, "B", 10)
            riga = riga[3:]
        else:
            pdf.set_font(font, "", 9)
        if font == "Helvetica":
            riga = riga.encode("latin-1", "replace").decode("latin-1")
        pdf.multi_cell(0, 4.6, riga)      # wrapping a parola, non a 100 caratteri
    return bytes(pdf.output())
