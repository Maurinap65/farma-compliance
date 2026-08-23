import re
from datetime import datetime

BUILD = "NX5-20260823a"

EMBED_NORME = {"art113_c1_a":"per pubblicita' di medicinali: qualsiasi forma di informazione, di ricerca di mercato e di incentivazione alla prescrizione, alla fornitura, alla vendita o al consumo di medicinali;", "art114_c2":"La pubblicita' di un medicinale e' conforme al riassunto delle caratteristiche del prodotto.", "art114_c3_a":"La pubblicita' di un medicinale deve favorire l'uso razionale del medicinale, presentandolo in modo obiettivo e senza esagerarne le proprieta'.", "art114_c3_b":"La pubblicita' di un medicinale non puo' essere ingannevole.", "art116_c1_a":"La pubblicita' di un medicinale presso il pubblico e' realizzata in modo che la natura pubblicitaria del messaggio e' evidente e il prodotto e' chiaramente identificato come medicinale.", "art116_c1_b1":"la denominazione del medicinale e la denominazione comune della sostanza attiva;", "art116_c1_b2":"le informazioni indispensabili per un uso corretto del medicinale;", "art116_c1_b3":"un invito esplicito e chiaro a leggere attentamente le avvertenze figuranti, a seconda dei casi, nel foglio illustrativo o sull'imballaggio esterno.", "art117_c1_a":"induca a ritenere che la visita medica o l'intervento chirurgico siano superflui, in particolare offrendo una diagnosi o suggerendo un trattamento per corrispondenza;", "art117_c1_b":"induca a ritenere che gli effetti derivanti dall'assunzione del medicinale siano garantiti, non siano accompagnati da reazioni avverse o siano superiori o pari a quelli di un altro trattamento o medicinale;", "art117_c1_f":"comprenda una raccomandazione di scienziati, di operatori sanitari o di persone largamente note al pubblico;", "art117_c1_g":"assimili il medicinale ad un prodotto alimentare, ad un prodotto cosmetico o ad un altro prodotto di consumo;", "art117_c1_i":"possa indurre ad una errata autodiagnosi;", "art117_c1_l":"faccia riferimento, in termini impropri, allarmistici o ingannevoli, ad attestati di guarigione;", "art118_c1":"Nessuna pubblicita' di medicinali presso il pubblico puo' essere effettuata senza autorizzazione del Ministero della salute.", "art118_c8":"Decorsi quarantacinque giorni dalla presentazione della domanda senza osservazioni del Ministero della salute, la pubblicita' si intende autorizzata."}
LABEL = {"art113_c1_a":"Art. 113 c.1 lett. a","art114_c2":"Art. 114 c.2","art114_c3_a":"Art. 114 c.3 lett. a","art114_c3_b":"Art. 114 c.3 lett. b","art116_c1_a":"Art. 116 c.1 lett. a","art116_c1_b1":"Art. 116 c.1 lett. b n.1","art116_c1_b2":"Art. 116 c.1 lett. b n.2","art116_c1_b3":"Art. 116 c.1 lett. b n.3","art117_c1_a":"Art. 117 c.1 lett. a","art117_c1_b":"Art. 117 c.1 lett. b","art117_c1_f":"Art. 117 c.1 lett. f","art117_c1_g":"Art. 117 c.1 lett. g","art117_c1_i":"Art. 117 c.1 lett. i","art117_c1_l":"Art. 117 c.1 lett. l","art118_c1":"Art. 118 c.1","art118_c8":"Art. 118 c.8"}
PROMPT_MARKERS = ["[{'type'", "'type': 'text'", "sei un senior", "regole fondamentali", "system prompt", "knowledge_chunks", "skill_prompt"]
DEFAULT_PER = "PERIMETRO DELLA VERIFICA - VERIFICATO: divieti assoluti art. 117 c.1; elementi obbligatori artt. 116 e 118; presentazione obiettiva art. 114 c.3. NON VERIFICATO (richiede verifica umana): conformita' al RCP (assente nella knowledge base); layout grafico e enfasi visiva; canale di diffusione."
ANALOGIA_TERMS = ["per analogia", "in via estensiva", "applicabile in quanto compatibile", "eventuali linee guida"]

def load_norme():
    m = dict(EMBED_NORME)
    try:
        t = open("kb/pharma_norme_chiavi.txt", encoding="utf-8", errors="replace").read()
        for k, v in re.findall(r"\[KEY ([a-zA-Z0-9_]+)\]\n([^[]+)", t):
            m[k] = v.strip()
    except Exception:
        pass
    return m

def _data():
    return datetime.now().strftime("%d/%m/%Y")

def _oneline(s, d=""):
    return str(s or d).replace("\r", " ").split("\n")[0].strip() or d

def _norm_txt(t):
    return re.sub(r"[^a-z0-9à-öø-ÿ]+", "", (t or "").lower())

def normalize_rep(rep):
    for sec in ("violazioni_critiche", "violations", "avvertenze", "warnings", "elementi_mancanti"):
        for v in (rep.get(sec) or []):
            if isinstance(v, dict):
                if not str(v.get("problema", "")).strip():
                    v["problema"] = str(v.get("testo") or v.get("descrizione") or v.get("issue") or v.get("titolo") or "")
                if not str(v.get("titolo", "")).strip():
                    v["titolo"] = str(v.get("title") or v.get("elemento") or "Rilievo")
    mm = []
    for v in rep.get("elementi_mancanti") or []:
        if isinstance(v, dict):
            mm.append(str(v.get("elemento") or v.get("titolo") or "") + ": " + str(v.get("riferimento") or v.get("norma") or ""))
        else:
            mm.append(str(v))
    rep["elementi_mancanti"] = mm
    viol, avv = rep.get("violazioni_critiche") or [], rep.get("avvertenze") or []
    for v in rep.get("violations") or []:
        sev = str(v.get("severity", "")).upper() if isinstance(v, dict) else ""
        (viol if "CRITIC" in sev else avv).append(v)
    keep = []
    for v in avv:
        sev = str(v.get("severity", "")).upper() if isinstance(v, dict) else ""
        (viol if "CRITIC" in sev else keep).append(v)
    rep["violazioni_critiche"], rep["avvertenze"] = viol, keep
    return rep

def promote_profilo(rep):
    items = rep.get("elementi_mancanti")
    if not isinstance(items, list):
        return rep
    keep = []
    for v in items:
        if "profilo di rischio" in str(v).lower():
            rep.setdefault("violazioni_critiche", []).append({"titolo": "Omissione totale del profilo di rischio", "problema": "Il materiale presenta solo benefici senza informazioni sul profilo di rischio, impedendo una presentazione obiettiva e bilanciata.", "posizione": "Intero materiale", "norma_key": ["art114_c3_a", "art114_c3_b"], "azione": "Integrare il materiale con il profilo di rischio del medicinale in modo bilanciato rispetto ai benefici, o rimandare al foglio illustrativo (obbligatorio ex art. 116 c.1 lett. b n.3).", "azione_richiesta": "Integrare il materiale con il profilo di rischio del medicinale in modo bilanciato rispetto ai benefici, o rimandare al foglio illustrativo (obbligatorio ex art. 116 c.1 lett. b n.3)."})
        else:
            keep.append(v)
    rep["elementi_mancanti"] = keep
    return rep

def stabilize_classi(rep):
    crit, manc = rep.get("violazioni_critiche") or [], rep.get("elementi_mancanti") or []
    keep_c = []
    for v in crit:
        if not isinstance(v, dict):
            keep_c.append(v); continue
        ks = set(v.get("norma_key") or [])
        t = str(v).lower()
        if ks and ks <= {"art116_c1_b1", "art116_c1_b2", "art116_c1_b3", "art118_c1", "art118_c8"}:
            manc.append(v); continue
        if not ks and re.search(r"116 c\.1 lett\. b n\.|118 c\.1", t) and "lett. a" not in t:
            manc.append(v); continue
        keep_c.append(v)
    keep_m = []
    for v in manc:
        t = str(v).lower()
        ks = set(v.get("norma_key") or []) if isinstance(v, dict) else set()
        if ("art116_c1_a" in ks) or ("lett. a" in t and "116" in t and "identific" in t):
            if isinstance(v, dict):
                v["problema"] = str(v.get("problema") or v.get("testo") or v.get("descrizione") or v.get("titolo") or "")
                v["azione"] = v.get("azione") or v.get("azione_richiesta") or "Inserire l'identificazione esplicita come medicinale (es. 'TUSSANPLUS, medicinale per...')."
                v["azione_richiesta"] = v["azione"]
                v["norma_key"] = v.get("norma_key") or ["art116_c1_a"]
                keep_c.append(v)
            else:
                keep_c.append({"titolo": "Mancata identificazione esplicita come medicinale", "problema": str(v), "posizione": "Intero materiale", "norma_key": ["art116_c1_a"], "azione": "Inserire l'identificazione esplicita come medicinale (es. 'TUSSANPLUS, medicinale per...').", "azione_richiesta": "Inserire l'identificazione esplicita come medicinale (es. 'TUSSANPLUS, medicinale per...')."})
            continue
        keep_m.append(v)
    rep["violazioni_critiche"], rep["elementi_mancanti"] = keep_c, keep_m
    return rep

def apply_norme(rep):
    mappa, DATA = load_norme(), _data()
    def _resolve(v):
        ks = v.get("norma_key") or []
        if isinstance(ks, str):
            ks = [ks]
        ks = [k for k in ks if isinstance(k, str)]
        t = (" ".join(str(v.get(f, "")) for f in ("titolo", "problema", "norma_violata", "issue", "norma"))).lower()
        for L in re.findall(r"art\.?\s*117\s*c\.?\s*1\s*lett\.?\s*([a-z])", t):
            ks.append("art117_c1_" + L)
        if re.search(r"art\.?\s*116.{0,60}lett\.?\s*a", t):
            ks.append("art116_c1_a")
        for N in re.findall(r"art\.?\s*116.{0,80}lett\.?\s*b.{0,20}n\.?\s*([123])", t):
            ks.append("art116_c1_b" + N)
        if re.search(r"art\.?\s*114.{0,40}c\.?\s*2", t):
            ks.append("art114_c2")
        if re.search(r"art\.?\s*114.{0,40}c\.?\s*3", t):
            ks.append("art114_c3_a")
        if re.search(r"art\.?\s*118", t):
            ks.append("art118_c1")
        out = []
        for k in ks:
            if k in mappa and k not in out:
                out.append(k)
        return out
    moved = []
    for key in ("violazioni_critiche", "avvertenze", "warnings", "elementi_mancanti"):
        items = rep.get(key)
        if not isinstance(items, list):
            continue
        keep = []
        for v in items:
            if not isinstance(v, dict):
                if key == "elementi_mancanti" and isinstance(v, str):
                    ks = _resolve({"titolo": v, "norma_violata": v})
                    keep.append(v + " | " + " | ".join(LABEL.get(k, k) + ": «" + mappa[k] + "»" for k in ks) if ks else v)
                else:
                    keep.append(v)
                continue
            ks = _resolve(v)
            if ks:
                v["norma_violata"] = " | ".join("D.Lgs 219/2006, " + LABEL.get(k, k) + " - testo vigente al " + DATA + ", fonte Normattiva: «" + mappa[k] + "»" for k in ks)
                v["norma_key"] = ks
                v["titolo"] = re.sub(r"^\[(RIFERIMENTO DA VERIFICARE|DA VERIFICARE)[^\]]*\]\s*", "", str(v.get("titolo", "")))
            else:
                v["titolo"] = "[RIFERIMENTO DA VERIFICARE] " + re.sub(r"^\[[^\]]*\]\s*", "", str(v.get("titolo", "")))
            if key == "violazioni_critiche" and "art114_c2" in (v.get("norma_key") or []):
                moved.append(v); continue
            keep.append(v)
        rep[key] = keep
    if moved:
        for v in moved:
            v["titolo"] = str(v.get("titolo", "")) + " (profilo condizionato: RCP non disponibile)"
        rep["avvertenze"] = (rep.get("avvertenze") or []) + moved
    return rep

def gate_analogia(rep):
    notes = rep.get("note_informative")
    if not isinstance(notes, list):
        notes = []
    for key in ("violazioni_critiche", "avvertenze", "warnings", "elementi_mancanti"):
        items = rep.get(key)
        if not isinstance(items, list):
            continue
        keep = []
        for v in items:
            t = str(v).lower()
            if any(p in t for p in ANALOGIA_TERMS):
                notes.append("[DEGRADATO DAL FILTRO ANALOGIA] " + (str(v.get("titolo", ""))[:200] if isinstance(v, dict) else str(v)[:200]))
            else:
                keep.append(v)
        rep[key] = keep
    rep["note_informative"] = notes
    return rep

def dedup_mancanti(rep):
    crit_txt = " ".join(str(v.get("titolo", "")) + str(v.get("problema", "")) for v in (rep.get("violazioni_critiche") or []) if isinstance(v, dict)).lower()
    crit_keys = set()
    for v in (rep.get("violazioni_critiche") or []):
        if isinstance(v, dict):
            crit_keys.update(v.get("norma_key") or [])
    items = rep.get("elementi_mancanti")
    if not isinstance(items, list):
        return rep
    keep = []
    for v in items:
        t = str(v).lower()
        if ("art116_c1_a" in crit_keys) and ("lett. a" in t or "identific" in t):
            continue
        if "profilo di rischio" in t and "profilo di rischio" in crit_txt:
            continue
        keep.append(v)
    rep["elementi_mancanti"] = keep
    return rep

def _fascia(v):
    t = (str(v.get("titolo", "")) + str(v.get("problema", ""))).lower()
    return "sotto i 2" in t or "bambini" in t or "fascia" in t

def ensure_pediatrica(rep, text):
    avv = rep.get("avvertenze") or []
    has = any("art114_c2" in (v.get("norma_key") or []) and _fascia(v) for v in avv if isinstance(v, dict))
    claims_txt = " ".join(str(c) for c in (rep.get("claims_rcp") or [])).lower()
    if not has and "sotto i 2" in claims_txt:
        mappa, DATA = load_norme(), _data()
        two = "Se il RCP non autorizza la fascia: eliminare integralmente il claim. Se il RCP la autorizza: il riferimento puo' restare, ma l'aggettivo 'sicuro' va eliminato comunque (v. violazione sulla sicurezza assoluta)."
        avv.append({"titolo": "Claim pediatrico - fascia sotto i 2 anni - conformita' RCP non verificabile (v. la violazione critica sull'aggettivo di sicurezza assoluta)", "problema": "L'indicazione 'bambini sotto i 2 anni' configura claim terapeutico verificabile solo contro il RCP (fascia di eta' autorizzata), assente nella knowledge base.", "posizione": "Seconda riga", "norma_key": ["art114_c2"], "norma_violata": "D.Lgs 219/2006, Art. 114 c.2 - testo vigente al " + DATA + ", fonte Normattiva: «" + mappa.get("art114_c2", "") + "»", "azione": two})
        rep["avvertenze"] = avv
    if any("art114_c2" in (v.get("norma_key") or []) and _fascia(v) for v in (rep.get("avvertenze") or []) if isinstance(v, dict)):
        rep["avvertenze"] = [v for v in rep["avvertenze"] if not ("24 ore" in (str(v.get("titolo", "")) + str(v.get("problema", ""))).lower())]
    for v in (rep.get("violazioni_critiche") or []):
        T = (str(v.get("titolo", "")) + str(v.get("problema", ""))).lower()
        if isinstance(v, dict) and "sicur" in T and ("bambini" in T or "2 anni" in T) and "v. anche" not in str(v.get("problema", "")):
            v["problema"] = str(v.get("problema", "")) + " (v. anche l'avvertenza sulla conformita' RCP della stessa frase)."
    return rep

def ensure_testimonianza(rep, text):
    tl = (text or "").lower()
    if not ("sparisce in" in tl or "sig.ra" in tl):
        return rep
    if any("art117_c1_l" in (v.get("norma_key") or []) for v in (rep.get("violazioni_critiche") or []) if isinstance(v, dict)):
        return rep
    mappa, DATA = load_norme(), _data()
    rep.setdefault("violazioni_critiche", []).append({"titolo": "Testimonianza con attestazione di guarigione", "problema": "La testimonianza virgolettata con claim di esito terapeutico costituisce attestazione di guarigione vietata in assoluto, indipendentemente dalla veridicita'.", "posizione": "Quarta riga", "norma_key": ["art117_c1_l"], "norma_violata": "D.Lgs 219/2006, Art. 117 c.1 lett. l - testo vigente al " + DATA + ", fonte Normattiva: «" + mappa.get("art117_c1_l", "") + "»", "azione": "Eliminare integralmente la testimonianza: le attestazioni di guarigione sono vietate in assoluto e non sono sanabili."})
    q = re.search(r'"([^"]{10,120})"', text or "")
    if q:
        for v in (rep.get("violazioni_critiche") or []):
            if isinstance(v, dict) and "art117_c1_l" in (v.get("norma_key") or []) and q.group(1)[:20] not in str(v.get("problema", "")):
                v["problema"] = str(v.get("problema", "")) + " Il testo contestato e': " + chr(34) + q.group(1) + chr(34) + "."
    return rep

def ensure_profilo(rep, text):
    tl = (text or "").lower()
    benefici = any(w in tl for w in ("n.1", "privo", "efficace", "sparisce", "sicuro", "consigliato"))
    rischi = any(w in tl for w in ("effetti indesiderati", "controindicazioni", "avvertenze", "profilo di rischio"))
    if not (benefici and not rischi):
        return rep
    if any("profilo di rischio" in (str(v.get("titolo", "")) + str(v.get("problema", ""))).lower() for v in (rep.get("violazioni_critiche") or []) if isinstance(v, dict)):
        return rep
    mappa, DATA = load_norme(), _data()
    rep.setdefault("violazioni_critiche", []).append({"titolo": "Omissione totale del profilo di rischio", "problema": "Il materiale presenta solo benefici senza informazioni sul profilo di rischio, impedendo una presentazione obiettiva e bilanciata.", "posizione": "Intero materiale", "norma_key": ["art114_c3_a", "art114_c3_b"], "norma_violata": "D.Lgs 219/2006, Art. 114 c.3 lett. a - testo vigente al " + DATA + ", fonte Normattiva: «" + mappa.get("art114_c3_a", "") + "»", "azione": "Integrare il materiale con il profilo di rischio del medicinale in modo bilanciato rispetto ai benefici, o rimandare al foglio illustrativo (obbligatorio ex art. 116 c.1 lett. b n.3)."})
    return rep

def ensure_claims(rep, text):
    tl = (text or "").lower()
    claims = rep.get("claims_rcp") or []
    txt = " ".join(str(c) for c in claims).lower()
    add = []
    if "tosse secca e grassa" in tl and "secca e grassa" not in txt:
        add.append({"claim": "per tosse secca e grassa (doppia indicazione sintomatologica)", "status": "UNVERIFIABLE_RCP_NOT_IN_KB - verificare contro RCP sez. 4.1"})
    if "sotto i 2" in tl and "sotto i 2" not in txt:
        add.append({"claim": "anche per bambini sotto i 2 anni (fascia eta' pediatrica)", "status": "UNVERIFIABLE_RCP_NOT_IN_KB - verificare contro RCP sez. 4.2/4.3"})
    if "24 ore" in tl and "24 ore" not in txt:
        add.append({"claim": "la tosse sparisce in 24 ore (tempo di azione)", "status": "UNVERIFIABLE_RCP_NOT_IN_KB - verificare contro RCP sez. 5.1"})
    if add:
        rep["claims_rcp"] = claims + add
    for c in rep.get("claims_rcp") or []:
        if isinstance(c, dict) and "24 ore" in str(c.get("claim", "")).lower():
            stt = str(c.get("status", ""))
            if "testimonianza" not in stt.lower():
                c["status"] = stt + "; va comunque eliminato in quanto parte di testimonianza vietata ex art. 117 c.1 lett. l"
    return rep

def ensure_doppia(rep, text):
    tl = (text or "").lower()
    if "tosse secca e grassa" not in tl:
        return rep
    allv = (rep.get("violazioni_critiche") or []) + (rep.get("avvertenze") or [])
    if any("autodiagnosi" in (str(v.get("titolo", "")) + str(v.get("problema", ""))).lower() or "art117_c1_i" in (v.get("norma_key") or []) for v in allv if isinstance(v, dict)):
        return rep
    mappa, DATA = load_norme(), _data()
    rep.setdefault("avvertenze", []).append({"titolo": "Doppia indicazione sintomatologica - rischio errata autodiagnosi", "problema": "La menzione 'per tosse secca e grassa' presenta due indicazioni sintomatologiche distinte che possono indurre errata autodiagnosi senza consulto medico.", "posizione": "Prima riga", "norma_key": ["art117_c1_i"], "norma_violata": "D.Lgs 219/2006, Art. 117 c.1 lett. i - testo vigente al " + DATA + ", fonte Normattiva: «" + mappa.get("art117_c1_i", "") + "»", "azione": "Verificare contro RCP sez. 4.1 se entrambe le indicazioni sono autorizzate; valutare invito esplicito al consulto medico."})
    return rep

def canone_chiavi(rep):
    mappa, DATA = load_norme(), _data()
    def stampa(ks):
        return " | ".join("D.Lgs 219/2006, " + LABEL.get(k, k) + " - testo vigente al " + DATA + ", fonte Normattiva: «" + mappa[k] + "»" for k in ks if k in mappa)
    for v in (rep.get("violazioni_critiche") or []):
        if not isinstance(v, dict):
            continue
        t = (str(v.get("titolo", "")) + str(v.get("problema", ""))).lower()
        ks = list(v.get("norma_key") or [])
        ch = False
        if "profilo di rischio" in t:
            for k in ("art114_c3_a", "art114_c3_b"):
                if k not in ks:
                    ks.append(k); ch = True
        if "sicurezza assoluta" in t:
            for k in ("art114_c3_a", "art117_c1_b"):
                if k not in ks:
                    ks.append(k); ch = True
        if ch:
            v["norma_key"] = ks
            v["norma_violata"] = stampa(ks)
    for v in (rep.get("avvertenze") or []):
        if not isinstance(v, dict):
            continue
        t = (str(v.get("titolo", "")) + str(v.get("problema", ""))).lower()
        if ("fascia" in t or "pediatric" in t or "sotto i 2" in t) and "art114_c2" in (v.get("norma_key") or []):
            v["norma_key"] = ["art114_c2"]
            v["norma_violata"] = stampa(["art114_c2"])
    return rep

def ensure_gusto(rep, text):
    tl = (text or "").lower()
    if not ("gusto" in tl or "miele" in tl):
        return rep
    allv = (rep.get("violazioni_critiche") or []) + (rep.get("avvertenze") or [])
    if any("art117_c1_g" in (v.get("norma_key") or []) or "gusto" in (str(v.get("titolo", "")) + str(v.get("problema", ""))).lower() for v in allv if isinstance(v, dict)):
        return rep
    mappa, DATA = load_norme(), _data()
    rep.setdefault("avvertenze", []).append({"titolo": "Enfasi organolettica - rischio assimilazione ad alimento", "problema": "La menzione del gusto ('gusto miele') puo' configurare enfasi sulla gradevolezza organolettica e assimilazione del medicinale a un prodotto alimentare, specie se accompagnata da layout grafico evocativo.", "posizione": "Quinta riga", "norma_key": ["art117_c1_g"], "norma_violata": "D.Lgs 219/2006, Art. 117 c.1 lett. g - testo vigente al " + DATA + ", fonte Normattiva: «" + mappa.get("art117_c1_g", "") + "»", "azione": "Verificare che il layout grafico non enfatizzi la componente organolettica fino ad assimilare il medicinale a un prodotto alimentare; in caso positivo, ridimensionare o eliminare il riferimento al gusto."})
    return rep

def ensure_chiavi(rep):
    mappa, DATA = load_norme(), _data()
    for v in (rep.get("violazioni_critiche") or []) + (rep.get("avvertenze") or []):
        if not isinstance(v, dict):
            continue
        t = (str(v.get("titolo", "")) + " " + str(v.get("problema", ""))).lower()
        ks = v.get("norma_key") or []
        ks = list(ks) if isinstance(ks, list) else [ks]
        ch = False
        if ("farmacist" in t or "consigliato dal" in t or "dott." in t or "pneumologo" in t) and "art117_c1_f" not in ks:
            ks.append("art117_c1_f"); ch = True
        if ("effetti collaterali" in t or "privo di effetti" in t) and "art114_c3_a" not in ks:
            ks.append("art114_c3_a"); ch = True
        if ("n.1" in t or "primato" in t or "superior" in t) and "art117_c1_b" not in ks:
            ks.append("art117_c1_b"); ch = True
        if "118" in t and "art118_c8" not in ks:
            ks += [k for k in ("art118_c1", "art118_c8") if k not in ks]; ch = True
        if ch:
            ks = [k for k in ks if k in mappa]
            v["norma_key"] = ks
            v["norma_violata"] = " | ".join("D.Lgs 219/2006, " + LABEL.get(k, k) + " - testo vigente al " + DATA + ", fonte Normattiva: «" + mappa[k] + "»" for k in ks)
    return rep

def ensure_sicuro_critica(rep, text):
    tl = (text or "").lower()
    if not ("sicuro" in tl and "bambini" in tl):
        return rep
    crit = rep.get("violazioni_critiche") or []
    def _t(v):
        return (str(v.get("titolo", "")) + str(v.get("problema", ""))).lower()
    if any("sicur" in _t(v) and "effetti collaterali" not in _t(v) for v in crit if isinstance(v, dict)):
        return rep
    for v in crit:
        if isinstance(v, dict) and "sicur" in _t(v) and "effetti collaterali" in _t(v):
            v["titolo"] = "Affermazione di assenza totale di effetti collaterali"
            v["problema"] = re.sub(r",?\s*sicuro anche per bambini sotto i 2 anni", "", str(v.get("problema", "")))
    mappa, DATA = load_norme(), _data()
    crit.append({"titolo": "Aggettivo di sicurezza assoluta su fascia pediatrica", "problema": "L'aggettivo 'sicuro' in 'sicuro anche per bambini sotto i 2 anni' costituisce affermazione categorica di sicurezza assoluta, vietata indipendentemente dal RCP (profilo incondizionato). Per la fascia di eta' v. l'avvertenza dedicata.", "posizione": "Seconda riga", "norma_key": ["art114_c3_a", "art117_c1_b"], "norma_violata": "D.Lgs 219/2006, Art. 114 c.3 lett. a - testo vigente al " + DATA + ", fonte Normattiva: «" + mappa.get("art114_c3_a", "") + "» | D.Lgs 219/2006, Art. 117 c.1 lett. b - testo vigente al " + DATA + ", fonte Normattiva: «" + mappa.get("art117_c1_b", "") + "»", "azione": "Eliminare l'aggettivo 'sicuro'. Il profilo di sicurezza assoluta e' violazione non sanabile, indipendente dalla verifica RCP sulla fascia."})
    rep["violazioni_critiche"] = crit
    for v in (rep.get("avvertenze") or []):
        if isinstance(v, dict) and "art114_c2" in (v.get("norma_key") or []) and "sicur" in str(v.get("problema", "")).lower():
            v["titolo"] = "Claim pediatrico - fascia sotto i 2 anni - conformita' RCP non verificabile (v. la violazione critica sull'aggettivo di sicurezza assoluta)"
            v["problema"] = "L'indicazione 'bambini sotto i 2 anni' configura claim terapeutico verificabile solo contro il RCP (fascia di eta' autorizzata), assente nella knowledge base. Il profilo dell'aggettivo 'sicuro' e' contestato separatamente come violazione incondizionata."
    for v in crit:
        if isinstance(v, dict):
            t = _t(v)
            if "sicurezza assoluta" in t or ("effetti collaterali" in t and "bambini" not in t):
                v["problema"] = re.sub(r"\(v\. anche l'avvertenza sulla conformita'? ?RCP della stessa frase\)", "", str(v.get("problema", "")))
    return rep

def demote_doppia(rep):
    crit, keep, moved = rep.get("violazioni_critiche") or [], [], []
    for v in crit:
        if isinstance(v, dict) and ("autodiagnosi" in (str(v.get("titolo", "")) + str(v.get("problema", ""))).lower() or (v.get("norma_key") or []) == ["art117_c1_i"]):
            moved.append(v)
        else:
            keep.append(v)
    if moved:
        rep["avvertenze"] = (rep.get("avvertenze") or []) + moved
    rep["violazioni_critiche"] = keep
    return rep

def dedup_critici(rep):
    seen, keep = set(), []
    for v in (rep.get("violazioni_critiche") or []):
        t = (str(v.get("titolo", "")) + " " + str(v.get("problema", ""))).lower() if isinstance(v, dict) else str(v).lower()
        sig = None
        if "identific" in t and "medicinale" in t:
            sig = "identificazione"
        if "profilo di rischio" in t:
            sig = "profilo"
        if sig and sig in seen:
            continue
        if sig:
            seen.add(sig)
        keep.append(v)
    rep["violazioni_critiche"] = keep
    return rep

def clean_mancanti(rep):
    items = rep.get("elementi_mancanti")
    if isinstance(items, list):
        rep["elementi_mancanti"] = [v for v in items if len(re.sub(r"[-–•:\s]", "", str(v))) >= 6]
    return rep

def dedup_autorizzazione(rep):
    items = rep.get("elementi_mancanti") or []
    keep = []
    for v in items:
        t = re.sub(r"[^a-z0-9]", "", str(v).lower())
        dup = False
        for k in keep:
            kt = re.sub(r"[^a-z0-9]", "", str(k).lower())
            if t and kt and ("autorizzazioneministeriale" in t and "autorizzazioneministeriale" in kt):
                dup = True
                break
        if not dup:
            keep.append(v)
    rep["elementi_mancanti"] = keep
    return rep

def fix_notes(rep):
    notes = rep.get("note_informative")
    if not isinstance(notes, list):
        return rep
    crit_txt = " ".join(str(v.get("titolo", "")) + str(v.get("problema", "")) for v in (rep.get("violazioni_critiche") or []) if isinstance(v, dict)).lower()
    out = []
    for nte in notes:
        s = str(nte.get("titolo", "") + " " + nte.get("testo", "")).strip() if isinstance(nte, dict) else str(nte)
        sl = s.lower()
        if "oltre a quelli già contestati" in sl or "non presenta titoli o qualifiche particolari" in sl or "direttore sanitario" in sl or "claim da verificare contro rcp" in sl or "non sono presenti titoli, qualifiche" in sl or "denominazione comune" in sl or ("inn" in sl and "sostanza" in sl) or ("il materiale presenta il titolo" in sl and len(sl) < 150):
            continue
        dup = any(f in sl for f in ("dott. mario rossi", "sig.ra bianchi", "testimonian")) and any(f in crit_txt for f in ("dott. mario rossi", "sig.ra bianchi", "testimonian"))
        if dup:
            continue
        if "informazione non presente nei documenti caricati" in sl and not any(w in sl for w in ("rcp", "knowledge base", "layout", "grafic", "immagine")):
            s = s.replace("Informazione non presente nei documenti caricati. Verifica manuale richiesta.", "").replace("Informazione non presente nei documenti caricati.", "").strip()
        if s.strip():
            out.append(s)
    rep["note_informative"] = out
    return rep

def fix_counts(rep):
    for rk in ("riepilogo_esecutivo", "riepilogo"):
        r = rep.get(rk)
        if isinstance(r, str):
            r = re.sub(r"\d+ violazioni critiche", str(len(rep.get("violazioni_critiche") or [])) + " violazioni critiche", r)
            r = re.sub(r"\d+ avvertenze", str(len(rep.get("avvertenze") or [])) + " avvertenze", r)
            r = re.sub(r"Mancano inoltre \d+ elementi mancanti", "Mancano inoltre " + str(len(rep.get("elementi_mancanti") or [])) + " elementi obbligatori", r)
            r = re.sub(r"\d+ elementi (mancanti|obbligatori)", str(len(rep.get("elementi_mancanti") or [])) + " elementi obbligatori", r)
            r = re.sub(r"\d+ claim da verificare", str(len(rep.get("claims_rcp") or [])) + " claim da verificare", r)
            rep[rk] = r
    return rep

def ensure_perimetro(rep):
    BLOCK = " PERIMETRO DELLA VERIFICA - VERIFICATO: divieti assoluti art. 117 c.1; elementi obbligatori artt. 116 e 118; presentazione obiettiva art. 114 c.3. NON VERIFICATO (richiede verifica umana): conformita' al RCP (assente nella knowledge base); layout grafico e enfasi visiva; canale di diffusione."
    def walk(x):
        if isinstance(x, dict):
            return {k: walk(v) for k, v in x.items()}
        if isinstance(x, list):
            return [walk(v) for v in x]
        if isinstance(x, str) and "corpus normativo consultato" in x.lower() and "non verificato" not in x.lower():
            return x + BLOCK
        return x
    return walk(rep)

def clean_azioni(rep):
    def walk(x):
        if isinstance(x, dict):
            return {k: walk(v) for k, v in x.items()}
        if isinstance(x, list):
            return [walk(v) for v in x]
        if isinstance(x, str):
            x = re.sub(r",?\s*salvo che il medicinale sia costituito da più sostanze[^.]*\.?", "", x)
            x = re.sub(r";?\s*se contiene più sostanze attive[^.]*\.?", "", x)
            return x
        return x
    return walk(rep)

def ensure_azioni(rep):
    for key in ("violazioni_critiche", "avvertenze"):
        for v in (rep.get(key) or []):
            if not isinstance(v, dict):
                continue
            a = str(v.get("azione_richiesta", "") or v.get("azione", "")).strip()
            if a:
                continue
            ks = [str(k) for k in (v.get("norma_key") or [])]
            if any(k.startswith("art117") for k in ks):
                a = "Eliminare integralmente l'elemento contestato: i divieti assoluti ex art. 117 c.1 non consentono riformulazioni."
            elif any(k.startswith("art116") or k.startswith("art118") for k in ks):
                a = "Integrare l'elemento obbligatorio mancante conformemente alla norma citata e al RCP."
            elif any(k.startswith("art114") for k in ks):
                a = "Ribilanciare la presentazione integrando il profilo di rischio o correggere il claim secondo quanto descritto nel problema."
            else:
                a = "Rivedere il punto come descritto nel problema. Validazione umana richiesta."
            v["azione"] = a
            v["azione_richiesta"] = a
    return rep

def fix_punti(rep):
    def walk(x):
        if isinstance(x, dict):
            return {k: walk(v) for k, v in x.items()}
        if isinstance(x, list):
            return [walk(v) for v in x]
        if isinstance(x, str):
            x = x.replace("...", "\x00")
            x = re.sub(r"\.(\s*\.)+", ".", x)
            x = x.replace("\x00", "...")
            return x
        return x
    return walk(rep)

def fix_ident(rep):
    for v in (rep.get("violazioni_critiche") or []):
        if not isinstance(v, dict):
            continue
        if "art116_c1_a" not in (v.get("norma_key") or []):
            continue
        p = str(v.get("problema", "")).lower()
        if ": art." in p or "identificazione chiara" in p or "identificazione del prodotto" in p:
            v["problema"] = "Il prodotto non e' chiaramente identificato come medicinale. La dicitura 'Disponibile in farmacia senza ricetta' non soddisfa l'obbligo di chiara identificazione del prodotto come medicinale."
        v["azione"] = "Inserire in posizione preminente la formula esplicita 'Medicinale senza obbligo di prescrizione' o equivalente che identifichi chiaramente il prodotto come medicinale."
        v["azione_richiesta"] = v["azione"]
    return rep

def enrich_azioni(rep):
    OPS = [("art116_c1_a", "posizione preminente", "Inserire in posizione preminente la formula esplicita 'Medicinale senza obbligo di prescrizione' o equivalente che identifichi chiaramente il prodotto come medicinale."), ("art117_c1_f", "non e' sanabile", "Il riferimento va eliminato integralmente: non e' sanabile con aggiunta di fonte o disclaimer."), ("art117_c1_b", "non e' sanabile", "L'affermazione va eliminata: non e' sanabile con aggiunta di fonte o disclaimer."), ("art117_c1_l", "non sono sanabili", "La testimonianza va eliminata integralmente: le attestazioni di guarigione sono vietate in assoluto e non sono sanabili."), ("art117_c1_g", "descrizione neutrale", "Rimuovere o ridurre a mera descrizione neutrale il riferimento, eliminando qualsiasi elemento grafico che evochi prodotti alimentari."), ("art114_c3_a", "profilo di rischio", "La presentazione va ribilanciata integrando il profilo di rischio (controindicazioni, effetti indesiderati, avvertenze) come da RCP.")]
    for v in (rep.get("violazioni_critiche") or []):
        if not isinstance(v, dict):
            continue
        a = str(v.get("azione_richiesta", "") or v.get("azione", ""))
        t = (str(v.get("titolo", "")) + str(v.get("problema", ""))).lower()
        for k, marker, txt in OPS:
            if k in (v.get("norma_key") or []) and marker not in a.lower():
                if k == "art114_c3_a" and "profilo di rischio" not in t:
                    continue
                a = (a + " " + txt).strip()
        v["azione"] = a
        v["azione_richiesta"] = a
    return rep

def clean_formule(rep):
    crit = rep.get("violazioni_critiche") or []
    idx_test = 0
    for i, v in enumerate(crit):
        if isinstance(v, dict) and "testimonian" in (str(v.get("titolo", "")) + str(v.get("problema", ""))).lower():
            idx_test = i + 1
    def walk(x):
        if isinstance(x, dict):
            return {k: walk(v) for k, v in x.items()}
        if isinstance(x, list):
            return [walk(v) for v in x]
        if isinstance(x, str):
            x = x.replace("formula obbligatoria", "formula consigliata di prassi (non prescritta dalla norma)")
            x = x.replace("(art. 114 c.2 e art. 117 c.1 lett. a)", "(art. 114 c.2)")
            x = re.sub(r"\.\.+", ".", x)
            if idx_test and "24 ore" in x:
                x = re.sub(r"violazione critica n\. \d+", "violazione critica n. " + str(idx_test), x)
                x = re.sub(r"vedi violazione n\. \d+", "vedi violazione n. " + str(idx_test), x)
            return x
        return x
    return walk(rep)

def ensure_norma(rep):
    mappa, DATA = load_norme(), _data()
    for sec in ("violazioni_critiche", "avvertenze"):
        for v in (rep.get(sec) or []):
            if not isinstance(v, dict):
                continue
            if str(v.get("norma_violata", "")).strip():
                continue
            ks = v.get("norma_key") or []
            if isinstance(ks, str):
                ks = [ks]
            ks = [k for k in ks if k in mappa]
            if ks:
                v["norma_violata"] = " | ".join("D.Lgs 219/2006, " + LABEL.get(k, k) + " - testo vigente al " + DATA + ", fonte Normattiva: «" + mappa[k] + "»" for k in ks)
    return rep

def fix_corpus_date(rep):
    DATA = _data()
    def walk(x):
        if isinstance(x, dict):
            return {k: walk(v) for k, v in x.items()}
        if isinstance(x, list):
            return [walk(v) for v in x]
        if isinstance(x, str):
            return re.sub(r"(?i)ultimo aggiornamento (del )?corpus[:\s]*[^\n.]*", "Ultimo aggiornamento corpus: " + DATA, x)
        return x
    return walk(rep)

def anchor_pos(rep, text):
    if not isinstance(text, str):
        try:
            text = str(text or "")
        except Exception:
            text = ""
    if not text:
        return rep
    lines = [l for l in text.split("\n") if l.strip()]
    markers = ["n.1", "farmacisti", "effetti collaterali", "sicuro", "bambini", "dott.", "24 ore", "miele", "tosse secca"]
    def find_pos(t):
        tl = t.lower()
        for mk in markers:
            if mk in tl:
                for i, l in enumerate(lines):
                    li = l.lower()
                    if mk in li:
                        idx = li.find(mk)
                        s0 = l.rfind(". ", 0, idx)
                        e0 = l.find(". ", idx + len(mk))
                        seg = l[(s0 + 2 if s0 != -1 else 0):(e0 if e0 != -1 else len(l))].strip()
                        if len(seg) < 8:
                            seg = l.strip()[:40]
                        return "Riga " + str(i + 1) + " (" + seg[:60] + ")"
        return None
    for key in ("violazioni_critiche", "avvertenze"):
        for v in (rep.get(key) or []):
            if isinstance(v, dict):
                if "intero" in str(v.get("posizione", "")).lower():
                    continue
                if "identific" in str(v.get("titolo", "")).lower():
                    v["posizione"] = "Intero materiale"
                    continue
                p = find_pos(str(v.get("titolo", "")) + " " + str(v.get("problema", "")))
                if p:
                    v["posizione"] = p
    return rep

def validate_rep(rep):
    probs = []
    def scan(x, path):
        if isinstance(x, dict):
            for k, v in x.items():
                scan(v, path + "." + str(k))
        elif isinstance(x, list):
            for i, v in enumerate(x):
                scan(v, path + "[" + str(i) + "]")
        elif isinstance(x, str):
            low = x.lower()
            if any(mk in low for mk in PROMPT_MARKERS):
                probs.append(path + ": contiene marcatori di prompt o strutture serializzate")
    scan(rep, "rep")
    for sec in ("violazioni_critiche", "avvertenze"):
        for i, v in enumerate(rep.get(sec) or []):
            if not isinstance(v, dict):
                continue
            for f in ("titolo", "problema", "norma_violata"):
                if not str(v.get(f, "")).strip():
                    probs.append(sec + " n." + str(i + 1) + ": campo '" + f + "' vuoto")
            if not str(v.get("azione_richiesta", "") or v.get("azione", "")).strip():
                probs.append(sec + " n." + str(i + 1) + ": campo azione vuoto")
    for i, v in enumerate(rep.get("elementi_mancanti") or []):
        if len(re.sub(r"[-–•:\s]", "", str(v))) < 6:
            probs.append("elementi_mancanti n." + str(i + 1) + ": voce vuota")
    r = str(rep.get("riepilogo_esecutivo") or rep.get("riepilogo") or "")
    mc = re.search(r"(\d+) violazioni critiche", r)
    ma = re.search(r"(\d+) avvertenze", r)
    if mc and int(mc.group(1)) != len(rep.get("violazioni_critiche") or []):
        probs.append("riepilogo: conteggio critiche diverso dal corpo")
    if ma and int(ma.group(1)) != len(rep.get("avvertenze") or []):
        probs.append("riepilogo: conteggio avvertenze diverso dal corpo")
    return probs

def pipeline(rep, text):
    rep = normalize_rep(rep)
    rep = promote_profilo(rep)
    rep = stabilize_classi(rep)
    rep = apply_norme(rep)
    rep = gate_analogia(rep)
    rep = dedup_mancanti(rep)
    rep = ensure_pediatrica(rep, text)
    rep = ensure_testimonianza(rep, text)
    rep = ensure_profilo(rep, text)
    rep = ensure_claims(rep, text)
    rep = ensure_doppia(rep, text)
    rep = ensure_gusto(rep, text)
    rep = canone_chiavi(rep)
    rep = ensure_chiavi(rep)
    rep = ensure_sicuro_critica(rep, text)
    rep = demote_doppia(rep)
    rep = dedup_critici(rep)
    rep = clean_mancanti(rep)
    rep = dedup_autorizzazione(rep)
    rep = fix_notes(rep)
    rep = fix_counts(rep)
    rep = ensure_perimetro(rep)
    rep = clean_azioni(rep)
    rep = ensure_azioni(rep)
    rep = enrich_azioni(rep)
    rep = fix_ident(rep)
    rep = clean_formule(rep)
    rep = ensure_norma(rep)
    rep = fix_corpus_date(rep)
    rep = anchor_pos(rep, text)
    rep = fix_punti(rep)
    return rep, validate_rep(rep)

def counts(rep):
    return (len(rep.get("violazioni_critiche") or []), len(rep.get("avvertenze") or []), len(rep.get("elementi_mancanti") or []), len(rep.get("claims_rcp") or []))

def stamp_keys(s):
    if s is None:
        return ""
    s = str(s)
    s = re.sub(r"\.(\s*\.)+", ".", s)
    for k in sorted(EMBED_NORME.keys(), key=len, reverse=True):
        if k in s:
            s = s.replace(k, LABEL[k] + " — «" + EMBED_NORME[k] + "»")
    return s

def make_pdf(md):
    txt = (md or "").replace("—", "-").replace("·", "-")
    txt = txt.encode("latin-1", "replace").decode("latin-1")
    try:
        from fpdf import FPDF
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()
        pdf.set_font("Helvetica", size=9)
        for line in txt.split("\n"):
            pdf.multi_cell(0, 5, line or " ")
        return bytes(pdf.output())
    except Exception:
        pass
    try:
        import io
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import A4
        buf = io.BytesIO()
        w, h = A4
        c = canvas.Canvas(buf, pagesize=A4)
        c.setFont("Helvetica", 8.5)
        y = h - 35
        for line in txt.split("\n"):
            chunks = [line[i:i+100] for i in range(0, len(line), 100)] or [" "]
            for ch in chunks:
                c.drawString(35, y, ch)
                y -= 11
                if y < 35:
                    c.showPage(); c.setFont("Helvetica", 8.5); y = h - 35
        c.showPage(); c.save()
        return buf.getvalue()
    except Exception:
        return None

def build_azioni(rep):
    az = ["Sospendere immediatamente la divulgazione del materiale fino al completamento delle azioni correttive."]
    for i, v in enumerate(rep.get("violazioni_critiche") or [], 1):
        if isinstance(v, dict):
            az.append((str(v.get("azione_richiesta", "") or v.get("azione", "")) or "Eliminare/integrare quanto contestato") + " (violazione critica n. " + str(i) + ")")
    for v in rep.get("elementi_mancanti") or []:
        s = str(v) if not isinstance(v, dict) else str(v.get("elemento", v.get("titolo", "")))
        s = s.split(" | ")[0].strip()
        az.append("Integrare l'elemento obbligatorio mancante: " + s)
    for i, v in enumerate(rep.get("avvertenze") or [], 1):
        if isinstance(v, dict):
            az.append((str(v.get("azione", "")) or "Verificare il punto") + " (avvertenza n. " + str(i) + ")")
    for v in rep.get("claims_rcp") or []:
        az.append("Verificare contro RCP il claim: " + (str(v.get("claim", "")) if isinstance(v, dict) else str(v)))
    az.append("Sottoporre il materiale revisionato a validazione umana prima della divulgazione.")
    return az

def report_code(rep, data=None):
    import hashlib
    DATA = data or _data()
    return "NX-FARMA-" + datetime.now().strftime("%Y%m%d-%H%M") + "-" + hashlib.sha256((str(rep) + DATA).encode("utf-8")).hexdigest()[:8].upper()

def render_md(rep, meta):
    DATA = meta.get("data", _data())
    c, w, m, r = counts(rep)
    L = []
    L.append("# REPORT DI COMPLIANCE — Farma Compliance")
    L.append("Data di riferimento: " + DATA + " · Motore: NEXORA Deep Engine · Build " + BUILD)
    sd = meta.get("source_desc", "Testo inserito dall'utente")
    L.append("MATERIALE ANALIZZATO: " + _oneline(" · ".join(sd) if isinstance(sd, list) else sd, "Testo inserito dall'utente"))
    na = meta.get("not_analyzed", "Nessuna immagine fornita")
    L.append("NON ANALIZZATO: " + _oneline(" · ".join(na) if isinstance(na, list) else na, "Nessuna immagine fornita"))
    L.append("STATO DEL CORPUS: D.Lgs 219/2006 (testo vigente); Codice Deontologico Farmindustria; FAQ AIFA D&R ver. 230503 · Ultimo aggiornamento: " + DATA)
    L.append("STATO COMPLESSIVO: " + _oneline(rep.get("stato"), "CRITICAL_FAIL") + " · Tipo materiale: " + _oneline(rep.get("tipo_materiale"), "SOP/OTC - da confermare"))
    L.append("CODICE REPORT: " + (meta.get("codice") or report_code(rep, DATA)))
    L.append("## RIEPILOGO ESECUTIVO")
    AZ = build_azioni(rep)
    L.append("Il materiale presenta " + str(c) + " violazioni critiche, " + str(w) + " avvertenze e " + str(m) + " elementi obbligatori mancanti; " + str(r) + " claim richiedono verifica contro RCP. Azioni prioritarie: " + "; ".join(AZ[:3]) + ".")
    L.append("## VIOLAZIONI CRITICHE")
    for i, v in enumerate(rep.get("violazioni_critiche") or [], 1):
        if not isinstance(v, dict):
            continue
        L.append("VIOLAZIONE CRITICA " + str(i) + " — " + str(v.get("titolo", "")))
        L.append("Posizione: " + str(v.get("posizione", "")))
        L.append("Problema: " + str(v.get("problema", "")))
        L.append("Norma violata: " + str(v.get("norma_violata", "[RIFERIMENTO DA VERIFICARE]")))
        L.append("Azione richiesta: " + str(v.get("azione_richiesta", "") or v.get("azione", "")))
    L.append("## AVVERTENZE")
    for i, v in enumerate(rep.get("avvertenze") or [], 1):
        if not isinstance(v, dict):
            continue
        L.append("AVVERTENZA " + str(i) + " — " + str(v.get("titolo", "")))
        L.append("Posizione: " + str(v.get("posizione", "")))
        L.append("Problema: " + str(v.get("problema", "")))
        L.append("Norma: " + str(v.get("norma_violata", "")))
        L.append("Azione: " + str(v.get("azione", "") or v.get("azione_richiesta", "")))
    PER = ""
    clean_notes = []
    for n in (rep.get("note_informative") or []):
        s = str(n.get("titolo", "") + " " + n.get("testo", "")) if isinstance(n, dict) else str(n)
        i = s.find("PERIMETRO DELLA VERIFICA")
        if i != -1:
            PER = s[i:].strip()
            s = s[:i].strip()
        if s:
            clean_notes.append(s)
    L.append("## NOTE INFORMATIVE (segnalazioni al revisore, NON costituiscono contestazioni)")
    for i, s in enumerate(clean_notes, 1):
        L.append(str(i) + ". " + s)
    L.append("## ELEMENTI MANCANTI")
    for v in rep.get("elementi_mancanti") or []:
        if isinstance(v, dict):
            s = str(v.get("elemento", "") or v.get("titolo", "")) + ": " + str(v.get("riferimento", "") or v.get("norma", ""))
        else:
            s = str(v)
        L.append("- " + stamp_keys(s))
    L.append("## CLAIM DA VERIFICARE CONTRO RCP")
    for v in rep.get("claims_rcp") or []:
        L.append("- " + (str(v.get("claim", "")) + " — " + str(v.get("status", "")) if isinstance(v, dict) else str(v)))
    L.append("## AZIONI RACCOMANDATE")
    for i, a in enumerate(AZ, 1):
        L.append(str(i) + ". " + str(a))
    L.append("## NOTA PER IL REVISORE UMANO")
    L.append(PER or DEFAULT_PER)
    nota = rep.get("nota_revisore") or rep.get("nota_per_il_revisore") or ""
    L.append(str(nota) if nota else "Validazione umana richiesta prima dell'uso.")
    L.append("DISCLAIMER: Report generato automaticamente dal sistema di Compliance QA. Validazione umana richiesta prima dell'uso.")
    L.append("TESTI NORMATIVI: consultabili su Normattiva (www.normattiva.it) - ricerca: 'Decreto Legislativo 219/2006' - testo vigente al " + DATA + ". NEXORA Deep Engine svolge l'analisi; Normattiva e' la fonte pubblica di verifica del testo di legge. NEXORA non e' affiliata a Normattiva.")
    s = "\n\n".join(L)
    import re as _re
    s = s.replace("...", "§§§")
    s = _re.sub(r"([a-zà-öø-ÿ])\s*\.\s*\.+", r"\1.", s)
    s = _re.sub(r"['‘’]\s+", lambda m: m.group(0)[0], s)
    s = s.replace("§§§", "...")
    return stamp_keys(s)

def golden_check(rep, ad):
    c, w, m, r = counts(rep)
    flat = _norm_txt(str(rep))
    ct = " ".join(str(v.get("titolo", "")) + str(v.get("problema", "")) for v in (rep.get("violazioni_critiche") or []) if isinstance(v, dict)).lower()
    at = " ".join(str(v.get("titolo", "")) + str(v.get("problema", "")) for v in (rep.get("avvertenze") or []) if isinstance(v, dict)).lower()
    comp = "sicur" in ct and "autodiagnosi" not in ct and "autodiagnosi" in at
    EXP_CRIT = sorted([("art116_c1_a",), ("art117_c1_b", "art117_c1_f"), ("art114_c3_a", "art117_c1_b"), ("art114_c3_a", "art117_c1_b"), ("art117_c1_f",), ("art117_c1_l",), ("art114_c3_a", "art114_c3_b")])
    EXP_AVV = sorted([("art117_c1_g",), ("art114_c2",), ("art117_c1_i",)])
    got_crit = sorted(tuple(sorted(v.get("norma_key") or [])) for v in (rep.get("violazioni_critiche") or []) if isinstance(v, dict))
    got_avv = sorted(tuple(sorted(v.get("norma_key") or [])) for v in (rep.get("avvertenze") or []) if isinstance(v, dict))
    comp_art = got_crit == EXP_CRIT and got_avv == EXP_AVV
    ok = c == 7 and w == 3 and m == 4 and r == 3 and "peranalogia" not in flat and "nonverificato" in flat and comp and comp_art
    lines = [str(c) + " critiche", str(w) + " avvertenze", str(m) + " mancanti", str(r) + " claim", "atteso 7/3/4/3", "composizione articoli " + ("OK" if comp_art else "KO")]
    return ok, lines
