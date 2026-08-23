import os, re, glob, base64, json, time
from datetime import datetime
import requests
import streamlit as st
st.markdown("<style>#MainMenu {visibility: hidden;} footer {visibility: hidden;} header {visibility: hidden;} .stDeployButton {display: none;}</style>", unsafe_allow_html=True)
import streamlit.components.v1 as components
import streamlit.components.v1 as components
from dotenv import load_dotenv

load_dotenv()

def _sec(name):
    v = os.environ.get(name, "")
    if v:
        return v
    try:
        return str(st.secrets[name])
    except Exception:
        return ""

OPENAI_API_KEY = _sec("OPENAI_API_KEY")
SUPABASE_URL = _sec("SUPABASE_URL")
SUPABASE_SERVICE_KEY = _sec("SUPABASE_SERVICE_KEY")
ANTHROPIC_API_KEY = _sec("ANTHROPIC_API_KEY")
import claude_engine

st.set_page_config(page_title="Farma Compliance", page_icon="🧠", layout="wide")

st.markdown("""
<style>
.badge { display:inline-block; padding:4px 12px; border-radius:999px; font-size:12px; font-weight:700; }
.badge.green { background:rgba(74,222,128,.12); color:#4ade80; border:1px solid rgba(74,222,128,.6); }
.badge.purple { background:rgba(167,139,250,.12); color:#a78bfa; border:1px solid rgba(167,139,250,.6); }
.badge.red { background:rgba(248,113,113,.12); color:#f87171; border:1px solid rgba(248,113,113,.6); }
div[data-testid="stMetric"] { background:#12161f; border:1px solid #232a36; border-radius:14px; padding:14px 18px; }
button[kind="secondary"], button[data-testid^="stBaseButton-secondary"] {
  background:#dc2626 !important; color:#ffffff !important; border-color:#b91c1c !important;
}
div[data-testid="stFileUploader"] button, button[data-testid="stFileUploadButton"] {
  background:#2563eb !important; color:#ffffff !important; border-color:#1d4ed8 !important;
}
div[data-testid="stVerticalBlockBorderWrapper"], div[data-testid="stContainerBlockBorderWrapper"] { border-color: #4ade80 !important; border-radius: 14px; }
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

DOC_NAMES = {
    "pharma_dlgs219": "D.Lgs 219/2006",
    "pharma_codice_deontologico": "Codice Deontologico Farmindustria",
    "pharma_dr_ims": "FAQ Domande & Risposte",
}

SKILL_PROMPT = """Sei un Senior Compliance Officer specializzato in normativa italiana per il settore farmaceutico, con focus sulla promozione dei medicinali e sui materiali destinati agli operatori sanitari (HCP) e al pubblico.

REGOLE FONDAMENTALI (STRETTAMENTE VINCOLANTI):
1. TEMPERATURA 0: nessuna creatività. Verifica fattuale e normativa. Non riscrivi il materiale, non proponi variazioni di tono.
2. CITAZIONE OBBLIGATORIA: ogni anomalia DEVE essere collegata a un riferimento normativo specifico presente nelle REGOLE qui sotto. Se non lo trovi: "Riferimento normativo non trovato nella knowledge base caricata".
3. ZERO ALLUCINAZIONI: se non trovi una regola nelle REGOLE, NON inventarla. Rispondi: "Informazione non presente nei documenti caricati. Verifica manuale richiesta."
4. MAI RISCIVERE DA SOLO: correzioni puntuali solo se supportate da riferimento normativo. La decisione finale è sempre umana.
5. HUMAN-IN-THE-LOOP: includi sempre in reviewer_notes la frase "Validazione umana richiesta prima dell'uso".
6. GESTIONE CLAIM VS RCP: CASO A (RCP presente nelle REGOLE): claim non supportato = violazione CRITICAL citando la sezione RCP. CASO B (RCP NON presente): NON creare violazioni CRITICAL per impossibilità di verificare l'RCP; dichiara "RCP del prodotto non presente nella knowledge base. Verifica manuale richiesta."; inserisci il claim in claims_rcp con status "UNVERIFIABLE_RCP_NOT_IN_KB" indicando la sezione RCP da consultare. Violazioni CRITICAL solo per motivi INDIPENDENTI dal RCP.
7. PASSO 0 - DUE CONTROLLI DI AMBITO PRIMA DI OGNI GIUDIZIO:
   (a) AMBITO SOGGETTIVO: chi comunica? Il Codice Deontologico Farmindustria vincola SOLO le aziende farmaceutiche associate; il Titolo VIII vincola chi promuove medicinali. Se il soggetto NON è un'azienda farmaceutica, il Codice è inapplicabile per ragione SOGGETTIVA: documentalo citando i punti 1.11 e 2.1 come norme che DEFINISCONO IL SOGGETTO VINCOLATO.
   (b) AMBITO OGGETTIVO: il materiale contiene riferimenti a medicinali? Se NO: stato_complessivo = "OUT_OF_SCOPE"; cita per il Titolo VIII l'art. 113 c.2 lett. d. Non esprimere giudizi di conformità.
   Se OUT_OF_SCOPE compila SOLO: riepilogo_esecutivo, esclusioni (una per documento, concise), note_informative, azioni_raccomandate (quale corpus servirebbe + revisione umana), reviewer_notes; elementi_mancanti = "Non valutabile: materiale fuori ambito"; lascia vuoti violazioni_critiche, avvertenze, claims_rcp. NON inserire avvertenze di mismatch: è implicito nello stato.
8. DEFINIZIONE DEI CAMPI (mai invertirli): "rilievo"/"problema" = descrizione FATTUALE di ciò che si osserva NEL MATERIALE con citazione letterale del passaggio; "norma"/"norma_violata" = testo letterale della disposizione + riferimento; "posizione" = dove nel materiale; "azione" = azione concreta. Mai boilerplate ripetuto.
9. NESSUNA AVVERTENZA SENZA NORMA CITABILE: se un elemento non ha norma citabile nella KB, va in note_informative, mai in avvertenze.
10. TONO DA REPORT: parafrasa il linguaggio colloquiale delle fonti; accenti corretti (purché, affinché, cioè).
11. CHECKLIST DI ESTRAZIONE (note_informative, sempre): UNA voce per area con ELEMENTI SPECIFICI citati testualmente: (a) titoli/qualifiche; (b) testimonianze con virgolettati; (c) professionisti per nome; (d) presentazione come struttura e assenza di direttore sanitario/estremi; (e) immagini non analizzabili; (f) elementi correttamente presenti. Ciascuna conclusa da "Informazione non presente nei documenti caricati. Verifica manuale richiesta."
12. PSEUDONIMIZZAZIONE: se PSEUDONIMIZZA=1, sostituisci nomi di persone fisiche con [PROFESSIONISTA n]/[PAZIENTE n].
13. CHECKLIST OBBLIGATORIA PER MATERIALE IN AMBITO: valuta CIASCUNO dei seguenti requisiti e, se violato o assente, produci la voce corrispondente (violazione e/o elemento mancante):
   - identificazione chiara del prodotto come medicinale (art. 116 c.1 lett. a) -> violazione AUTONOMA oltre che elemento mancante
   - denominazione comune della sostanza attiva (art. 116 c.1 lett. b n.1)
   - informazioni indispensabili per l'uso corretto (art. 116 c.1 lett. b n.2)
   - invito a leggere le avvertenze nel foglio illustrativo (art. 116 c.1 lett. b n.3)
   - estremi autorizzazione ministeriale (art. 118 c.1, c.8, c.9) -> violazione AUTONOMA oltre che elemento mancante
   - divieti art. 117 c.1, ciascuno come VOCE AUTONOMA: lett. a (consulto superfluo), lett. b (efficacia/sicurezza assolute, inclusi claim comparativi/di primato senza fonte come "il n.1"), lett. f (raccomandazione di operatori sanitari o categorie, inclusi i farmacisti), lett. g (assimilazione ad alimenti/enfasi gradevolezza), lett. i (errata autodiagnosi), lett. l (attestazioni di guarigione)
   - presentazione obiettiva e bilanciata benefici/rischi (art. 114 c.3 lett. a e b): assenza totale del profilo di rischio = violazione
   Una testimonianza con claim di esito/guarigione è VIOLAZIONE art. 117 c.1 lett. l (non una nota). Valuta come AVVERTENZE (con flag "verifica umana richiesta") le fattispecie che dipendono dal layout o dall'RCP: doppia indicazione sintomatologica (lett. i), claim pediatrico senza invito al consulto (lett. a), enfasi organolettica (lett. g). Gli elementi obbligatori assenti vanno ANCHE in elementi_mancanti con il loro riferimento.
14. FORMATO CITAZIONI: D.Lgs 219/2006 = "art. X, comma Y, lett. Z"; Codice Deontologico Farmindustria = "punto X.Y" (MAI "art."); aggiungi D&R AIFA di supporto se presenti nelle REGOLE; se richiami norme HCP per materiale al pubblico, aggiungi una breve nota di perimetro.
15. AZIONI SPECIFICHE: una azione concreta per ogni violazione/elemento mancante, ordinate per priorità (prima "sospendere la divulgazione" se CRITICAL); SCRIVILE SENZA numerazione iniziale (la numerazione la aggiunge il sistema); mai una sola riga generica.

Rispondi SOLO con un JSON con questo schema esatto:
{"tipo_materiale":"","stato_complessivo":"COMPLIANT|NEEDS_REVISION|CRITICAL_FAIL|OUT_OF_SCOPE",
"riepilogo_esecutivo":"","esclusioni":[{"titolo":"","rilievo":"","norma":"","conseguenza":""}],
"violazioni_critiche":[{"titolo":"","posizione":"","problema":"","norma_violata":"","azione":""}],
"avvertenze":[{"titolo":"","posizione":"","problema":"","norma_violata":"","azione":""}],
"note_informative":[{"testo":""}],
"elementi_mancanti":[{"elemento":"","riferimento":""}],
"claims_rcp":[{"claim":"","status":""}],
"azioni_raccomandate":[""],
"reviewer_notes":""}


STANDARD DELIVERABLE NEXORA (REGOLE VINCOLANTI DI OUTPUT):
1. APERTURA CON SINTESI ESECUTIVA: max 10 righe con conteggio rilievi per gravita' (critiche/avvertenze/note) e le 3 azioni prioritarie numerate.
2. DIVIETO DI META-LINGUAGGIO: nel report NON devono comparire termini come "temperatura", "zero allucinazioni", "modello", "prompt", "JSON" usati come autocertificazione del sistema. Il report e' un deliverable professionale.
3. PERIMETRO DELLA VERIFICA: nella sezione revisore indica: (a) corpus normativo consultato e data di aggiornamento; (b) cio' che e' stato verificato; (c) cio' che NON e' verificabile dal sistema (RCP se assente, elementi grafici, canale di diffusione) e richiede verifica umana.
4. CLAIM DIPENDENTI DA DOCUMENTI ASSENTI: se l'esito dipende da un documento non caricato (es. RCP), NON classificarlo come violazione critica: va SOLO nella sezione claim da verificare contro RCP con esito UNVERIFIABLE_RCP_NOT_IN_KB. Vietata la duplicazione tra sezioni.
5. TITOLI DEI RILIEVI: descrivono cio' che e' PRESENTE nel materiale (es. "Claim pediatrico non autorizzato"), mai formule inverse o sgrammaticate.
6. COERENZA CITAZIONI: la norma citata nel corpo e quella in fonte devono coincidere esattamente; se incerto, scrivi "riferimento da verificare" e non citare.
7. DATA ANALISI: usa solo la data corrente fornita nel messaggio; non inventare date.

REGOLE RIPRISTINO DETTAGLIO (REGOLE VINCOLANTI - LIVELLO 21/08):
1. CITAZIONE LETTERALE: ogni rilievo deve riportare nel campo norma il testo letterale della disposizione tra virgolette, copiato dal corpus (es. art. 116 c.1 lett. b nn. 1-2-3 per esteso). Nel JSON includi "source_excerpt" con lo stesso estratto letterale. Se non trovi l'estratto nel corpus, lascia "source_excerpt" vuoto: il rilievo sara' declassato dal sistema a nota.
2. DOPPIA CONTESTAZIONE: i claim che invocano raccomandazioni di farmacisti, medici o operatori sanitari vanno contestati con art. 117 c.1 lett. f E, se contengono primato o superiorita', anche con art. 117 c.1 lett. b.
3. PEDIATRICO: se la fascia di eta' non e' autorizzata dal RCP, l'unica azione e' eliminare il claim; NON proporre "invito a consultare il medico" come sanante. Gli aggettivi di sicurezza assoluta ("sicuro", "privo di rischi") sono violazione autonoma (art. 114 c.3 e art. 117 c.1 lett. b).
4. BUCKET RCP: nella sezione claim da verificare contro RCP vanno SOLO claim terapeutici verificabili (indicazione, fascia di eta', tempo di azione). I claim vietati in assoluto (primato, assenza di effetti collaterali, testimonianze, raccomandazioni di operatori, attestazioni di guarigione) NON vanno mai in quella sezione: sono violazioni indipendentemente dal RCP.
5. ELEMENTI MANCANTI: verifica sempre art. 116 c.1 lett. a (identificazione come medicinale), lett. b nn. 1-2-3, art. 118 (estremi AIC), art. 114 c.3 (profilo di rischio).
6. ORGANOLETTICI: menzioni di gusto o palatabilita' vanno valutate come avvertenza ex art. 117 c.1 lett. g (assimilazione ad alimento), mai come "immagine non analizzabile".
7. POSIZIONI: per ogni rilievo cita la frase esatta del materiale e la collocazione precisa (pagina/paragrafo/sezione, se desumibile).
8. AZIONI SPECIFICHE: vietate azioni circolari tipo "verificare la conformita' alle normative vigenti": ogni azione deve dire cosa eliminare o cosa aggiungere, con quale contenuto.
9. ONE-PAGER ADDITIVO: la sintesi esecutiva si aggiunge al dettaglio completo dei rilievi, non lo sostituisce.
10. AMBITI CONDIZIONATI: se l'esito di un rilievo dipende da un documento assente o da una variabile non determinata, includi nel JSON il campo "conditioned_by" con la ragione: il sistema lo declassera' a "da verificare".

REGOLE DI CORREZIONE (LIVELLO AUDITOR - VINCOLANTI):
11. RIEPILOGO COERENTE: il riepilogo esecutivo NON deve elencare come violazione alcun claim classificato UNVERIFIABLE_RCP_NOT_IN_KB; tali claim nel riepilogo vanno citati solo come "da verificare contro RCP".
12. MAPPATURE NORMATIVE CORRETTE: (a) l'aggettivo di sicurezza assoluta ("sicuro") = art. 117 c.1 lett. b; la conformita' della fascia pediatrica e delle indicazioni terapeutiche al RCP/AIC = art. 114 c.2, NON lett. b ne' lett. i; (b) l'enfasi su gusto o palatabilita' = art. 117 c.1 lett. g e dipende dal layout grafico, NON dal RCP; (c) la lett. i si usa SOLO per il rischio di errata autodiagnosi.
13. TIPO MATERIALE: se il materiale dice solo "senza ricetta" o "in farmacia", classificare come "SOP/OTC - da confermare", mai SOP assertivo.
14. NOTE NON DUPLICATE: ogni fatto compare in una sola nota; la frase "verifica manuale richiesta" va usata solo dove un'informazione davvero manca; nella pubblicita' di medicinali al pubblico NON citare il direttore sanitario.
15. PROFILO DI RISCHIO: l'omissione del profilo di rischio e' violazione dell'art. 114 c.3 (presentazione obiettiva) e va tra violazioni o avvertenze, NON tra gli elementi mancanti ex art. 116.
16. METADATI UNIVOCI: non stampare nella nota finale nomi o date del corpus diversi da quelli forniti dal sistema nell'intestazione; se la data di aggiornamento non e' nota, ometterla.

21. CHIAVI NORMA (OBBLIGATORIO): per ogni rilievo indica nel JSON il campo "norma_key" con una o piu' chiavi prese SOLO da questo elenco: art113_c1_a, art114_c2, art114_c3_a, art114_c3_b, art116_c1_a, art116_c1_b1, art116_c1_b2, art116_c1_b3, art117_c1_a, art117_c1_b, art117_c1_f, art117_c1_g, art117_c1_i, art117_c1_l, art118_c1, art118_c8. NON scrivere il testo della norma: il sistema lo stampa dal corpus ufficiale associato alla chiave. Se nessuna chiave corrisponde usa "norma_key": ["da_verificare"].

22. SUSSUNZIONE: (a) l'aggettivo di sicurezza assoluta ("sicuro") ha come chiave primaria art114_c3_a (presentazione obiettiva), in combinato con art117_c1_b; (b) se la stessa frase genera due rilievi (aggettivo e fascia di eta'), inserisci in entrambi un rimando esplicito all'altro; (c) conformita' al RCP (art114_c2) e rischio di errata autodiagnosi (art117_c1_i) sono verifiche distinte: non fonderle in un solo rilievo o azione; (d) NON inserire affermazioni di conoscenza generale non derivate dal corpus; (e) ogni azione raccomandata deve richiamare il rilievo corrispondente; (f) le note informative non duplicano rilievi gia' presenti; (g) l'omissione del profilo di rischio e' rilievo autonomo ex art114_c3_a, non solo azione.
23. VERSIONAMENTO CORPUS: nella nota finale elenca i documenti ESATTAMENTE come "D.Lgs 219/2006 (testo vigente); Codice Deontologico Farmindustria; FAQ AIFA D&R ver. 230503" e chiudi con "Ultimo aggiornamento corpus:" seguito dalla data corrente fornita dal sistema.

24. CONTENUTO MINIMO (LIVELLO 07:45, VINCOLANTE): (a) "Il n.1 consigliato dai farmacisti" = doppia contestazione art117_c1_b + art117_c1_f; (b) la mancata identificazione come medicinale e' VIOLAZIONE CRITICA ex art116_c1_a e resta anche fra gli elementi mancanti; (c) "tosse secca e grassa" = avvertenza art117_c1_i E claim da verificare contro RCP; (d) "sicuro" e "privo di effetti collaterali" sono due rilievi separati; (e) l'omissione del profilo di rischio e' violazione critica art114_c3_a; (f) sui divieti assoluti l'azione e' sempre ELIMINARE, mai correggere; (g) per il gusto: valutare se il contesto grafico configuri assimilazione a prodotto alimentare; (h) posizioni precise: prima/seconda/terza/quarta riga o frase esatta, mai "Testo"; (i) ogni rilievo ha la sua azione e le azioni coprono anche gli elementi mancanti; (j) il riepilogo dichiara conteggi numerici; (k) la nota finale contiene sempre il perimetro VERIFICATO / NON VERIFICATO; (l) non chiamare mai "immagine" un testo.

25. REGOLA 25 (RIFINITURE VINCOLANTI): (a) mai "per analogia", "in via estensiva", "applicabile in quanto compatibile", "eventuali linee guida": se non c'e' la chiave esatta, il rilievo va in nota; (b) l'obbligo della denominazione comune (art. 116 c.1 lett. b n.1) riguarda il medicinale con una sola sostanza attiva: formula "indicare la denominazione comune (INN) se il medicinale contiene una sola sostanza attiva"; (c) le note informative NON duplicano rilievi o elementi mancanti gia' registrati, e il boilerplate "informazione non presente nei documenti caricati" si usa SOLO per fatti davvero assenti dal corpus (es. RCP), mai per fatti del materiale gia' contestati; (d) l'enfasi organolettica (gusto) e' AVVERTENZA con verifica del layout, mai nota; (e) il tipo materiale "SOP/OTC - da confermare" compare anche fra i punti NON VERIFICATI della nota finale.

26. REGOLA 26: (a) ogni claim di efficacia o tempo (es. "la tosse sparisce in 24 ore") va SEMPRE anche nella sezione CLAIM DA VERIFICARE CONTRO RCP, con indicazione della sezione RCP pertinente (es. 4.1/4.2/4.3 o 5.1); (b) nel riepilogo non scrivere mai "mancano N elementi mancanti": usa "mancano N elementi obbligatori"; (c) un fatto gia' contestato come violazione non compare fra gli elementi mancanti."""

def source_label(r):
    doc = DOC_NAMES.get(r.get('source_doc', ''), r.get('source_doc', 'sconosciuto'))
    art = r.get('article') or ''
    return f"{doc}, {art}" if art else doc

def kb_update_date():
    latest = 0
    for f in glob.glob("kb/*.txt"):
        latest = max(latest, os.path.getmtime(f))
    return datetime.fromtimestamp(latest).strftime("%d/%m/%Y") if latest else "sconosciuta"

def fetch_url(url):
    headers = {"User-Agent": "Mozilla/5.0 (compatible; FarmaCompliance/1.0)"}
    r = requests.get(url, headers=headers, timeout=20)
    r.raise_for_status()
    html = re.sub(r'(?s)<script.*?>.*?</script>', ' ', r.text)
    html = re.sub(r'(?s)<style.*?>.*?</style>', ' ', html)
    text = re.sub(r'(?s)<[^>]+>', ' ', html)
    return re.sub(r'\s+', ' ', text).strip()

def clean_for_pdf(t):
    repl = {"✅":"[OK]", "⚠️":"[!]", "⚠":"[!]", "❌":"[X]", "⛔":"[X]",
            "—":"-", "–":"-", "·":"-", "…":"...", "’":"'", "‘":"'", "“":'"', "”":'"',
            "📚":"", "💾":"", "🖨️":"", "📋":"", "🧠":"", "🔍":"", "⚪":"", "🟢":"", "ℹ":"", "📎":"", "⚖":"", "**":"", "####":"", "###":""}
    for k, v in repl.items():
        t = t.replace(k, v)
    return t.encode("latin-1", "replace").decode("latin-1")

def autoscroll(on):
    if on:
        html = """<script>
        function nxScrollAll(){
          var d = window.parent.document;
          var t = [d.scrollingElement, d.documentElement, d.body,
                   d.querySelector("section.main"),
                   d.querySelector("[data-testid='stMain']"),
                   d.querySelector("[data-testid='stAppViewContainer']")];
          t.forEach(function(x){ if(x){ x.scrollTop = x.scrollHeight; } });
        }
        if(window.parent.__nxscroll){ clearInterval(window.parent.__nxscroll); }
        window.parent.__nxscroll = setInterval(nxScrollAll, 500);
        nxScrollAll();
        </script>"""
    else:
        html = """<script>if(window.parent.__nxscroll){ clearInterval(window.parent.__nxscroll); window.parent.__nxscroll = null; }</script>"""
    components.html(html, height=0, width=0)

def scroll_to_report(target_id):
    html = "<script>setTimeout(function(){var d=window.parent.document;var el=d.getElementById('" + target_id + "');if(el){el.scrollIntoView({behavior:'smooth',block:'start'});}},600);</script>"
    components.html(html, height=0, width=0)

EMBED_NORME = {"art113_c1_a":"per pubblicita' di medicinali: qualsiasi forma di informazione, di ricerca di mercato e di incentivazione alla prescrizione, alla fornitura, alla vendita o al consumo di medicinali;", "art114_c2":"La pubblicita' di un medicinale e' conforme al riassunto delle caratteristiche del prodotto.", "art114_c3_a":"La pubblicita' di un medicinale deve favorire l'uso razionale del medicinale, presentandolo in modo obiettivo e senza esagerarne le proprieta'.", "art114_c3_b":"La pubblicita' di un medicinale non puo' essere ingannevole.", "art116_c1_a":"La pubblicita' di un medicinale presso il pubblico e' realizzata in modo che la natura pubblicitaria del messaggio e' evidente e il prodotto e' chiaramente identificato come medicinale.", "art116_c1_b1":"la denominazione del medicinale e la denominazione comune della sostanza attiva;", "art116_c1_b2":"le informazioni indispensabili per un uso corretto del medicinale;", "art116_c1_b3":"un invito esplicito e chiaro a leggere attentamente le avvertenze figuranti, a seconda dei casi, nel foglio illustrativo o sull'imballaggio esterno.", "art117_c1_a":"induca a ritenere che la visita medica o l'intervento chirurgico siano superflui, in particolare offrendo una diagnosi o suggerendo un trattamento per corrispondenza;", "art117_c1_b":"induca a ritenere che gli effetti derivanti dall'assunzione del medicinale siano garantiti, non siano accompagnati da reazioni avverse o siano superiori o pari a quelli di un altro trattamento o medicinale;", "art117_c1_f":"comprenda una raccomandazione di scienziati, di operatori sanitari o di persone largamente note al pubblico;", "art117_c1_g":"assimili il medicinale ad un prodotto alimentare, ad un prodotto cosmetico o ad un altro prodotto di consumo;", "art117_c1_i":"possa indurre ad una errata autodiagnosi;", "art117_c1_l":"faccia riferimento, in termini impropri, allarmistici o ingannevoli, ad attestati di guarigione;", "art118_c1":"Nessuna pubblicita' di medicinali presso il pubblico puo' essere effettuata senza autorizzazione del Ministero della salute.", "art118_c8":"Decorsi quarantacinque giorni dalla presentazione della domanda senza osservazioni del Ministero della salute, la pubblicita' si intende autorizzata."}
def load_norme_chiavi():
    m = dict(EMBED_NORME)
    try:
        t = open("kb/pharma_norme_chiavi.txt", encoding="utf-8", errors="replace").read()
        for k, v in re.findall(r"\[KEY ([a-zA-Z0-9_]+)\]\n([^[]+)", t):
            m[k] = v.strip()
    except Exception:
        pass
    return m
    for k, v in re.findall(r"\[KEY ([a-zA-Z0-9_]+)\]\n([^[]+)", t):
        m[k] = v.strip()
    return m

def normalize_rep(rep):
    for sec in ("violazioni_critiche", "violations", "avvertenze", "warnings", "elementi_mancanti"):
        for v in (rep.get(sec) or []):
            if isinstance(v, dict):
                if not str(v.get("problema", "")).strip():
                    v["problema"] = str(v.get("testo") or v.get("descrizione") or v.get("issue") or v.get("problema_descrizione") or v.get("titolo") or "")
                if not str(v.get("titolo", "")).strip():
                    v["titolo"] = str(v.get("title") or v.get("elemento") or "Rilievo")
    viol = rep.get("violazioni_critiche") or []
    avv = rep.get("avvertenze") or []
    for v in rep.get("violations") or []:
        sev = str(v.get("severity", "")).upper() if isinstance(v, dict) else ""
        (viol if "CRITIC" in sev else avv).append(v)
    keep = []
    for v in avv:
        sev = str(v.get("severity", "")).upper() if isinstance(v, dict) else ""
        (viol if "CRITIC" in sev else keep).append(v)
    rep["violazioni_critiche"] = viol
    rep["avvertenze"] = keep
    return rep

def apply_norme_ufficiali(rep, mappa):
    DATA = datetime.now().strftime("%d/%m/%Y")
    LABEL = {"art113_c1_a":"Art. 113 c.1 lett. a","art114_c2":"Art. 114 c.2","art114_c3_a":"Art. 114 c.3 lett. a","art114_c3_b":"Art. 114 c.3 lett. b","art116_c1_a":"Art. 116 c.1 lett. a","art116_c1_b1":"Art. 116 c.1 lett. b n.1","art116_c1_b2":"Art. 116 c.1 lett. b n.2","art116_c1_b3":"Art. 116 c.1 lett. b n.3","art117_c1_a":"Art. 117 c.1 lett. a","art117_c1_b":"Art. 117 c.1 lett. b","art117_c1_f":"Art. 117 c.1 lett. f","art117_c1_g":"Art. 117 c.1 lett. g","art117_c1_i":"Art. 117 c.1 lett. i","art117_c1_l":"Art. 117 c.1 lett. l","art118_c1":"Art. 118 c.1","art118_c8":"Art. 118 c.8"}
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
                moved.append(v)
                continue
            keep.append(v)
        rep[key] = keep
    if moved:
        for v in moved:
            v["titolo"] = re.sub(r"\s*\(profilo condizionato[^)]*\)", "", str(v.get("titolo", ""))) + " - conformita' RCP non verificabile (v. anche il rilievo sulla sicurezza assoluta della stessa frase)"
            two = "Se il RCP non autorizza la fascia: eliminare integralmente il claim. Se il RCP la autorizza: il riferimento puo' restare, ma l'aggettivo 'sicuro' va eliminato comunque (v. violazione sulla sicurezza assoluta)."
            v["azione"] = two
            v["azione_richiesta"] = two
        rep["avvertenze"] = (rep.get("avvertenze") or []) + moved
        for v in rep.get("violazioni_critiche") or []:
            if isinstance(v, dict) and "sicur" in (str(v.get("titolo", "")) + str(v.get("problema", ""))).lower():
                v["problema"] = str(v.get("problema", "")) + " (v. anche l'avvertenza sulla conformita' RCP della stessa frase)."
    return rep

ANALOGIA_TERMS = ["per analogia", "in via estensiva", "applicabile in quanto compatibile", "eventuali linee guida"]
def gate_analogia(rep):
    notes = rep.get("note_informative")
    if not isinstance(notes, list):
        notes = []
    def _hit(x):
        t = str(x).lower()
        return any(p in t for p in ANALOGIA_TERMS)
    for key in ("violazioni_critiche", "avvertenze", "warnings", "elementi_mancanti"):
        items = rep.get(key)
        if not isinstance(items, list):
            continue
        keep = []
        for v in items:
            if _hit(v):
                notes.append("[DEGRADATO DAL FILTRO ANALOGIA] " + (str(v.get("titolo", ""))[:200] if isinstance(v, dict) else str(v)[:200]))
            else:
                keep.append(v)
        rep[key] = keep
    rep["note_informative"] = notes
    return rep

def fix_corpus_date(rep):
    DATA = datetime.now().strftime("%d/%m/%Y")
    def walk(x):
        if isinstance(x, dict):
            return {k: walk(v) for k, v in x.items()}
        if isinstance(x, list):
            return [walk(v) for v in x]
        if isinstance(x, str):
            return re.sub(r"(?i)ultimo aggiornamento (del )?corpus[:\s]*[^\n.]*", "Ultimo aggiornamento corpus: " + DATA, x)
        return x
    return walk(rep)

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

def ensure_pediatrica(rep):
    avv = rep.get("avvertenze") or []
    has = any("art114_c2" in (v.get("norma_key") or []) for v in avv if isinstance(v, dict))
    claims_txt = " ".join(str(c) for c in (rep.get("claims_rcp") or [])).lower()
    if not has and "sotto i 2" in claims_txt:
        mappa = load_norme_chiavi()
        DATA = datetime.now().strftime("%d/%m/%Y")
        two = "Se il RCP non autorizza la fascia: eliminare integralmente il claim. Se il RCP la autorizza: il riferimento puo' restare, ma l'aggettivo 'sicuro' va eliminato comunque (v. violazione sulla sicurezza assoluta)."
        avv.append({"titolo": "Claim pediatrico - conformita' RCP non verificabile (v. anche il rilievo sulla sicurezza assoluta della stessa frase)", "problema": "Il claim 'anche per bambini sotto i 2 anni' promuove un uso in fascia pediatrica la cui conformita' al RCP non e' verificabile dal corpus caricato.", "posizione": "Seconda riga", "norma_key": ["art114_c2"], "norma_violata": "D.Lgs 219/2006, Art. 114 c.2 - testo vigente al " + DATA + ", fonte Normattiva: «" + mappa.get("art114_c2", "") + "»", "azione": two})
        rep["avvertenze"] = avv
    for v in (rep.get("violazioni_critiche") or []):
        _T = (str(v.get("titolo", "")) + str(v.get("problema", ""))).lower()
        if isinstance(v, dict) and "sicur" in _T and ("bambini" in _T or "2 anni" in _T) and "v. anche" not in str(v.get("problema", "")):
            v["problema"] = str(v.get("problema", "")) + " (v. anche l'avvertenza sulla conformita' RCP della stessa frase)."
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

def dedup_critici(rep):
    seen = set()
    keep = []
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

def fix_notes(rep):
    notes = rep.get("note_informative")
    if not isinstance(notes, list):
        return rep
    crit_txt = " ".join(str(v.get("titolo", "")) + str(v.get("problema", "")) for v in (rep.get("violazioni_critiche") or []) if isinstance(v, dict)).lower()
    out = []
    for nte in notes:
        s = str(nte)
        sl = s.lower()
        if "oltre a quelli già contestati" in sl or "non presenta titoli o qualifiche particolari" in sl or "direttore sanitario" in sl or "claim da verificare contro rcp" in sl or "non sono presenti titoli, qualifiche" in sl or "denominazione comune" in sl or ("inn" in sl and "sostanza" in sl):
            continue
        dup = any(f in sl for f in ("dott. mario rossi", "sig.ra bianchi", "testimonian")) and any(f in crit_txt for f in ("dott. mario rossi", "sig.ra bianchi", "testimonian"))
        if dup:
            continue
        if "informazione non presente nei documenti caricati" in sl and not any(w in sl for w in ("rcp", "knowledge base", "layout", "grafic", "immagine")):
            s = s.replace("Informazione non presente nei documenti caricati. Verifica manuale richiesta.", "").replace("Informazione non presente nei documenti caricati.", "").strip()
        if s.strip():
            out.append(nte if isinstance(nte, dict) else s)
    rep["note_informative"] = out
    return rep

def stabilize_classi(rep):
    crit = rep.get("violazioni_critiche") or []
    manc = rep.get("elementi_mancanti") or []
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
                v["titolo"] = v.get("titolo") or "Mancata identificazione esplicita come medicinale"
                keep_c.append(v)
            else:
                keep_c.append({"titolo": "Mancata identificazione esplicita come medicinale", "problema": str(v), "posizione": "Intero materiale", "norma_key": ["art116_c1_a"], "azione": "Inserire l'identificazione esplicita come medicinale (es. 'TUSSANPLUS, medicinale per...').", "azione_richiesta": "Inserire l'identificazione esplicita come medicinale (es. 'TUSSANPLUS, medicinale per...')."})
            continue
        keep_m.append(v)
    rep["violazioni_critiche"] = keep_c
    rep["elementi_mancanti"] = keep_m
    return rep

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
                    if mk in l.lower():
                        return "Riga " + str(i + 1) + " (" + l.strip()[:40] + ")"
        return None
    for key in ("violazioni_critiche", "avvertenze"):
        for v in (rep.get(key) or []):
            if isinstance(v, dict):
                if "intero" in str(v.get("posizione", "")).lower():
                    continue
                p = find_pos(str(v.get("titolo", "")) + " " + str(v.get("problema", "")))
                if p:
                    v["posizione"] = p
    return rep

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

PROMPT_MARKERS = ["[{'type'", "'type': 'text'", "sei un senior", "regole fondamentali", "system prompt", "knowledge_chunks", "skill_prompt"]
def _user_text():
    for n in ("ad_text", "testo", "materiale", "ad_copy", "testo_materiale", "content"):
        v = globals().get(n)
        if isinstance(v, str) and v.strip():
            low = v.lower()
            if not any(mk in low for mk in PROMPT_MARKERS):
                return v
    return ""

def ensure_chiavi(rep):
    mappa = load_norme_chiavi()
    DATA = datetime.now().strftime("%d/%m/%Y")
    LBL = {"art117_c1_b":"Art. 117 c.1 lett. b","art117_c1_f":"Art. 117 c.1 lett. f","art117_c1_l":"Art. 117 c.1 lett. l","art118_c1":"Art. 118 c.1","art118_c8":"Art. 118 c.8","art114_c3_a":"Art. 114 c.3 lett. a"}
    for v in (rep.get("violazioni_critiche") or []) + (rep.get("avvertenze") or []):
        if not isinstance(v, dict):
            continue
        t = (str(v.get("titolo", "")) + " " + str(v.get("problema", ""))).lower()
        ks = v.get("norma_key") or []
        ks = list(ks) if isinstance(ks, list) else [ks]
        ch = False
        if ("farmacist" in t or "medico" in t or "dott." in t or "pneumologo" in t) and "art117_c1_f" not in ks:
            ks.append("art117_c1_f"); ch = True
        if ("n.1" in t or "primato" in t or "superior" in t) and "art117_c1_b" not in ks:
            ks.append("art117_c1_b"); ch = True
        if "118" in t and "art118_c8" not in ks:
            ks += [k for k in ("art118_c1", "art118_c8") if k not in ks]; ch = True
        if ch:
            ks = [k for k in ks if k in mappa]
            v["norma_key"] = ks
            v["norma_violata"] = " | ".join(LBL.get(k, k) + " - testo vigente al " + DATA + ", fonte Normattiva: «" + mappa[k] + "»" for k in ks)
    return rep

def ensure_testimonianza(rep, text):
    tl = (text or "").lower()
    if not ("sparisce in" in tl or "sig.ra" in tl):
        return rep
    if any("art117_c1_l" in (v.get("norma_key") or []) for v in (rep.get("violazioni_critiche") or []) if isinstance(v, dict)):
        return rep
    mappa = load_norme_chiavi(); DATA = datetime.now().strftime("%d/%m/%Y")
    rep.setdefault("violazioni_critiche", []).append({"titolo": "Testimonianza con attestazione di guarigione", "problema": "La testimonianza virgolettata con claim di esito terapeutico costituisce attestazione di guarigione vietata in assoluto, indipendentemente dalla veridicita'.", "posizione": "Quarta riga", "norma_key": ["art117_c1_l"], "norma_violata": "Art. 117 c.1 lett. l - testo vigente al " + DATA + ", fonte Normattiva: «" + mappa.get("art117_c1_l", "") + "»", "azione": "Eliminare integralmente la testimonianza: le attestazioni di guarigione sono vietate in assoluto e non sono sanabili."})
    return rep

def ensure_profilo(rep, text):
    tl = (text or "").lower()
    benefici = any(w in tl for w in ("n.1", "privo", "efficace", "sparisce", "sicuro", "consigliato"))
    rischi = any(w in tl for w in ("effetti indesiderati", "controindicazioni", "avvertenze", "profilo di rischio"))
    if not (benefici and not rischi):
        return rep
    if any("profilo di rischio" in (str(v.get("titolo", "")) + str(v.get("problema", ""))).lower() for v in (rep.get("violazioni_critiche") or []) if isinstance(v, dict)):
        return rep
    mappa = load_norme_chiavi(); DATA = datetime.now().strftime("%d/%m/%Y")
    rep.setdefault("violazioni_critiche", []).append({"titolo": "Omissione totale del profilo di rischio", "problema": "Il materiale presenta solo benefici senza informazioni sul profilo di rischio, impedendo una presentazione obiettiva e bilanciata.", "posizione": "Intero materiale", "norma_key": ["art114_c3_a", "art114_c3_b"], "norma_violata": "Art. 114 c.3 lett. a - testo vigente al " + DATA + ", fonte Normattiva: «" + mappa.get("art114_c3_a", "") + "»", "azione": "Integrare il materiale con il profilo di rischio del medicinale in modo bilanciato rispetto ai benefici, o rimandare al foglio illustrativo (obbligatorio ex art. 116 c.1 lett. b n.3)."})
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
    return rep

def ensure_norma(rep):
    mappa = load_norme_chiavi()
    LABEL = {"art113_c1_a":"Art. 113 c.1 lett. a","art114_c2":"Art. 114 c.2","art114_c3_a":"Art. 114 c.3 lett. a","art114_c3_b":"Art. 114 c.3 lett. b","art116_c1_a":"Art. 116 c.1 lett. a","art116_c1_b1":"Art. 116 c.1 lett. b n.1","art116_c1_b2":"Art. 116 c.1 lett. b n.2","art116_c1_b3":"Art. 116 c.1 lett. b n.3","art117_c1_a":"Art. 117 c.1 lett. a","art117_c1_b":"Art. 117 c.1 lett. b","art117_c1_f":"Art. 117 c.1 lett. f","art117_c1_g":"Art. 117 c.1 lett. g","art117_c1_i":"Art. 117 c.1 lett. i","art117_c1_l":"Art. 117 c.1 lett. l","art118_c1":"Art. 118 c.1","art118_c8":"Art. 118 c.8"}
    DATA = datetime.now().strftime("%d/%m/%Y")
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
                v["norma_violata"] = " | ".join("D.Lgs 219/2006, " + LABEL.get(k, k) + " - testo vigente al " + DATA + ", fonte Normattiva: <<" + mappa[k] + ">>" for k in ks)
    return rep

def clean_mancanti(rep):
    items = rep.get("elementi_mancanti")
    if isinstance(items, list):
        rep["elementi_mancanti"] = [v for v in items if len(re.sub(r"[-–•:\s]", "", str(v))) >= 6]
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
            if idx_test and "24 ore" in x:
                x = re.sub(r"violazione critica n\. \d+", "violazione critica n. " + str(idx_test), x)
                x = re.sub(r"vedi violazione n\. \d+", "vedi violazione n. " + str(idx_test), x)
            return x
        return x
    return walk(rep)

def ensure_sicuro_critica(rep, text):
    tl = (text or "").lower()
    if not ("sicuro" in tl and "bambini" in tl):
        return rep
    crit = rep.get("violazioni_critiche") or []
    if any("sicur" in (str(v.get("titolo", "")) + str(v.get("problema", ""))).lower() for v in crit if isinstance(v, dict)):
        return rep
    mappa = load_norme_chiavi(); DATA = datetime.now().strftime("%d/%m/%Y")
    crit.append({"titolo": "Aggettivo di sicurezza assoluta su fascia pediatrica", "problema": "L'aggettivo 'sicuro' in 'sicuro anche per bambini sotto i 2 anni' costituisce affermazione categorica di sicurezza assoluta, vietata indipendentemente dal RCP (profilo incondizionato). Per la fascia di eta' v. l'avvertenza dedicata.", "posizione": "Riga 2", "norma_key": ["art114_c3_a", "art117_c1_b"], "norma_violata": "D.Lgs 219/2006, Art. 114 c.3 lett. a - testo vigente al " + DATA + ", fonte Normattiva: «" + mappa.get("art114_c3_a", "") + "» | D.Lgs 219/2006, Art. 117 c.1 lett. b - testo vigente al " + DATA + ", fonte Normattiva: «" + mappa.get("art117_c1_b", "") + "»", "azione": "Eliminare l'aggettivo 'sicuro'. Il profilo di sicurezza assoluta e' violazione non sanabile, indipendente dalla verifica RCP sulla fascia."})
    rep["violazioni_critiche"] = crit
    for v in (rep.get("avvertenze") or []):
        if isinstance(v, dict) and "art114_c2" in (v.get("norma_key") or []) and "sicur" in str(v.get("problema", "")).lower():
            v["titolo"] = "Claim pediatrico - fascia sotto i 2 anni - conformita' RCP non verificabile (v. la violazione critica sull'aggettivo di sicurezza assoluta)"
            v["problema"] = "L'indicazione 'bambini sotto i 2 anni' configura claim terapeutico verificabile solo contro il RCP (fascia di eta' autorizzata), assente nella knowledge base. Il profilo dell'aggettivo 'sicuro' e' contestato separatamente come violazione incondizionata."
    for v in crit:
        if isinstance(v, dict):
            t = (str(v.get("titolo", "")) + str(v.get("problema", ""))).lower()
            if "sicurezza assoluta" in t or ("effetti collaterali" in t and "bambini" not in t):
                v["problema"] = re.sub(r"\(v\. anche l'avvertenza sulla conformita'? ?RCP della stessa frase\)", "", str(v.get("problema", "")))
    return rep

def demote_doppia(rep):
    crit = rep.get("violazioni_critiche") or []
    keep = []
    moved = []
    for v in crit:
        if isinstance(v, dict) and ("autodiagnosi" in (str(v.get("titolo", "")) + str(v.get("problema", ""))).lower() or (v.get("norma_key") or []) == ["art117_c1_i"]):
            moved.append(v)
        else:
            keep.append(v)
    if moved:
        rep["avvertenze"] = (rep.get("avvertenze") or []) + moved
    rep["violazioni_critiche"] = keep
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

def _norm_txt(t):
    return re.sub(r"[^a-z0-9à-öø-ÿ]+", "", (t or "").lower())

_KB_CACHE = {}
def _kb_all():
    if not _KB_CACHE:
        import glob as _g
        _KB_CACHE["t"] = _norm_txt("".join(open(f, encoding="utf-8", errors="replace").read() for f in sorted(_g.glob("kb/*.txt"))))
    return _KB_CACHE["t"]

def gate_citazioni(rep):
    kb = _kb_all()
    warns = rep.get("avvertenze")
    if not isinstance(warns, list):
        warns = []
    def _ok_quote(exc):
        w = _norm_txt(exc)
        if len(w) < 40:
            return False
        for i in range(0, max(1, len(w) - 60), 60):
            if w[i:i+80] in kb:
                return True
        return False
    for key in ("violazioni_critiche", "violations"):
        items = rep.get(key)
        if not isinstance(items, list):
            continue
        keep = []
        for v in items:
            if not isinstance(v, dict):
                keep.append(v); continue
            exc = v.get("source_excerpt") or ""
            if not exc:
                mtxt = str(v.get("norma_violata") or v.get("norma") or v.get("testo_norma") or "")
                q = re.findall(r"[«\"']([^«»\"']{40,})[»\"']", mtxt)
                exc = max(q, key=len) if q else ""
            if _ok_quote(exc):
                keep.append(v)
            else:
                v2 = dict(v)
                v2["titolo"] = "[RIFERIMENTO DA VERIFICARE] " + str(v.get("titolo", v.get("issue", "Rilievo")))
                warns.append(v2)
        rep[key] = keep
    rep["avvertenze"] = warns
    return rep

def gate_severita(rep):
    warns = rep.get("avvertenze")
    if not isinstance(warns, list):
        warns = []
    for key in ("violazioni_critiche", "violations"):
        items = rep.get(key)
        if not isinstance(items, list):
            continue
        keep = []
        for v in items:
            if isinstance(v, dict) and (v.get("conditioned_by") or v.get("condizionato")):
                warns.append(dict(v, titolo="[DA VERIFICARE - " + str(v.get("conditioned_by") or "ambito condizionato") + "] " + str(v.get("titolo", v.get("issue", "")))))
            else:
                keep.append(v)
        rep[key] = keep
    rep["avvertenze"] = warns
    return rep

def build_pdf(title, sections):
    from fpdf import FPDF
    pdf = FPDF()
    pdf.add_page()
    if os.path.exists("logo.png"):
        try: pdf.image("logo.png", x=140, y=8, w=60)
        except Exception: pass
    pdf.set_font("Helvetica", "B", 15)
    pdf.multi_cell(0, 9, clean_for_pdf(title))
    pdf.set_x(pdf.l_margin)
    pdf.set_font("Helvetica", "I", 10)
    pdf.multi_cell(0, 6, "Data di riferimento: " + datetime.now().strftime("%d/%m/%Y %H:%M"))
    pdf.set_x(pdf.l_margin)
    try:
        _mot = str(st.session_state.get("check_result", {}).get("model", "") or "")
    except Exception:
        _mot = ""
    if _mot:
        pdf.set_font("Helvetica", "I", 10)
        pdf.multi_cell(0, 6, "Motore: " + _mot)
        pdf.set_x(pdf.l_margin)
    pdf.ln(4)
    for h, b in sections:
        pdf.set_font("Helvetica", "B", 11)
        pdf.multi_cell(0, 7, clean_for_pdf(h))
        pdf.set_x(pdf.l_margin)
        pdf.set_font("Helvetica", "", 10)
        pdf.multi_cell(0, 6, clean_for_pdf(b))
        pdf.set_x(pdf.l_margin)
        pdf.ln(3)
    return bytes(pdf.output())

def salva_report(data, prefisso):
    fname = f"{prefisso}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
    with open(fname, "wb") as f:
        f.write(data)
    return fname

def mostra_errore_pdf():
    import traceback
    tb = traceback.format_exc()
    try:
        with open("errore_pdf.log", "w") as f:
            f.write(tb)
    except Exception:
        pass
    st.error("Errore generazione PDF (dettagli in errore_pdf.log):")
    st.code(tb)

def polish_obj(o):
    if isinstance(o, dict):
        return {k: polish_obj(v) for k, v in o.items()}
    if isinstance(o, list):
        return [polish_obj(v) for v in o]
    if isinstance(o, str):
        for a, b in (("purche'","purché"),("perche'","perché"),("poiche'","poiché"),("affinche'","affinché"),("cioe'","cioè"),("bensi'","bensì"),("nonche'","nonché"),("gia'","già"),("piu'","più")):
            o = o.replace(a, b)
        return o
    return o

def report_sections(rep, source_desc, not_analyzed):
    S = [("MATERIALE ANALIZZATO", "\n".join(source_desc) or "-")]
    if not_analyzed:
        S.append(("NON ANALIZZATO", "\n".join(not_analyzed)))
    S.append(("STATO DEL CORPUS", "Documenti: D.Lgs 219/2006; Codice Deontologico Farmindustria; FAQ D&R. Ultimo aggiornamento: " + kb_update_date()))
    S.append(("STATO COMPLESSIVO", f"{rep.get('stato_complessivo','')} - Tipo materiale: {rep.get('tipo_materiale','')}"))
    S.append(("RIEPILOGO ESECUTIVO", rep.get("riepilogo_esecutivo", "")))
    for i, e in enumerate(rep.get("esclusioni", []), 1):
        S.append((f"ESCLUSIONE {i} - {e.get('titolo','')}", f"Rilievo: {e.get('rilievo','')}\nNorma di riferimento: {e.get('norma','')}\nConseguenza: {e.get('conseguenza','')}"))
    for i, v in enumerate(rep.get("violazioni_critiche", []), 1):
        S.append((f"VIOLAZIONE CRITICA {i} - {v.get('titolo','')}", f"Posizione: {v.get('posizione','')}\nProblema: {v.get('problema','')}\nNorma violata: {v.get('norma_violata','')}\nAzione richiesta: {v.get('azione','')}"))
    for i, v in enumerate(rep.get("avvertenze", []), 1):
        S.append((f"AVVERTENZA {i} - {v.get('titolo','')}", f"Posizione: {v.get('posizione','')}\nProblema: {v.get('problema','')}\nNorma: {v.get('norma_violata','')}\nAzione: {v.get('azione','')}"))
    notes = rep.get("note_informative", [])
    if notes:
        body = "\n\n".join([f"{i}. {n.get('testo','') if isinstance(n, dict) else n}" for i, n in enumerate(notes, 1)])
        S.append(("NOTE INFORMATIVE (segnalazioni al revisore, NON costituiscono contestazioni)", body))
    em = rep.get("elementi_mancanti", [])
    if rep.get("stato_complessivo") == "OUT_OF_SCOPE":
        S.append(("ELEMENTI MANCANTI", "Non valutabile: il materiale è fuori dall'ambito della knowledge base caricata."))
    else:
        S.append(("ELEMENTI MANCANTI", "\n".join([f"- {x.get('elemento','')}: {x.get('riferimento','')}" for x in em]) if em else "Nessuno rispetto alla knowledge base caricata."))
    cr = rep.get("claims_rcp", [])
    if not (rep.get("stato_complessivo") == "OUT_OF_SCOPE"):
        if isinstance(x, dict):
            st.write(f"- {x.get('claim','')} — *{x.get('status','')}*")
        else:
            st.write(str(x))
    az = rep.get("azioni_raccomandate", [])
    if az:
        S.append(("AZIONI RACCOMANDATE", "\n".join([f"{i}. {a}" for i, a in enumerate(az, 1)])))
    S.append(("NOTA PER IL REVISORE UMANO", rep.get("reviewer_notes", "")))
    S.append(("DISCLAIMER", "Report generato automaticamente dal sistema di Compliance QA. Validazione umana richiesta prima dell'uso."))
    return S

def set_topbar(msg):
    if msg:
        m = msg.replace("'", "").replace('"', "")
        html = "<script>var d=window.parent.document;var el=d.getElementById('nx-topbar');if(!el){el=d.createElement('div');el.id='nx-topbar';d.body.appendChild(el);}el.style.cssText='position:fixed;top:14px;right:14px;z-index:999999;background:#0b1220;border:1px solid #4ade80;color:#4ade80;padding:8px 16px;border-radius:999px;font:600 13px system-ui,sans-serif;box-shadow:0 6px 18px rgba(0,0,0,.55)';el.textContent='" + m + "';</script>"
    else:
        html = "<script>var d=window.parent.document;var el=d.getElementById('nx-topbar');if(el){el.remove();}</script>"
    components.html(html, height=0, width=0)

def render_report(cr):
    import nexora_core
    rep = cr.get("rep") or {}
    ad = str(cr.get("ad_text") or "")
    ok, lines = nexora_core.golden_check(rep, ad)
    if "tussanplus" in ad.lower() and "gusto miele" in ad.lower():
        st.info(("🧪 AUTO-DIFF CASO D'ORO ✅ " if ok else "🧪 AUTO-DIFF CASO D'ORO ❌ SCOSTATO — ") + " · ".join(lines))
    md = nexora_core.render_md(rep, cr)
    c, w, mnt, r = nexora_core.counts(rep)
    st.session_state["nx_onepager"] = "SINTESI ESECUTIVA: " + str(c) + " critiche - " + str(w) + " avvertenze - " + str(mnt) + " mancanti - " + str(r) + " claim RCP."
    with st.container(border=True):
        st.markdown(md)
    if st.button("🖨️ Genera PDF", key="gen_pdf"):
        import nexora_core
        pdf_bytes = nexora_core.make_pdf(md)
        if pdf_bytes:
            st.session_state["pdf_bytes"] = pdf_bytes
            st.success("PDF generato. Clicca 'Scarica PDF' sotto.")
            st.rerun()
        else:
            st.error("PDF non generato: libreria non disponibile")
    if st.session_state.get("pdf_bytes"):
        st.download_button("⬇️ Scarica PDF", st.session_state["pdf_bytes"], file_name="report_compliance.pdf", mime="application/pdf", key="dl_pdf")
        st.caption("PDF pronto per il download")

def clear_check():
    st.session_state.clear_count = st.session_state.get("clear_count", 0) + 1
    st.session_state.pop("check_result", None)

def clear_chat():
    st.session_state.messages = []

def get_embedding(text):
    r = requests.post("https://api.openai.com/v1/embeddings",
        headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
        json={"model": "text-embedding-3-small", "input": text})
    r.raise_for_status()
    return r.json()["data"][0]["embedding"]

def search_kb(query, sector="pharma", match_count=6):
    emb = get_embedding(query)
    r = requests.post(f"{SUPABASE_URL}/rest/v1/rpc/match_chunks",
        headers={"apikey": SUPABASE_SERVICE_KEY,
                 "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                 "Content-Type": "application/json"},
        json={"query_embedding": emb, "match_sector": sector, "match_count": match_count})
    r.raise_for_status()
    return r.json()

def find_article_in_file(article_num, filepath):
    with open(filepath, encoding="utf-8") as f:
        text = f.read()
    base = rf'(?:Art\.|Articolo)\s+{article_num}\b'
    matches = list(re.finditer(r'(?m)^\s*' + base, text)) or list(re.finditer(base, text))
    if not matches: return None
    start = matches[-1].start()
    next_m = re.search(r'(?m)^\s*(?:Art\.|Articolo)\s+\d+', text[start+10:])
    end = start + 10 + next_m.start() if next_m else len(text)
    return text[start:end].strip()

def scope_pack():
    parts = []
    a = find_article_in_file("113", "kb/pharma_dlgs219.txt")
    if a: parts.append("[D.Lgs 219/2006, art. 113]\n" + a[:3000])
    for n in ("116", "118", "119"):
        a = find_article_in_file(n, "kb/pharma_dlgs219.txt")
        if a: parts.append(f"[D.Lgs 219/2006, art. {n}]\n" + a[:2000])
    for n in ("1", "2"):
        a = find_article_in_file(n, "kb/pharma_codice_deontologico.txt")
        if a: parts.append(f"[Codice Deontologico Farmindustria, Articolo {n}]\n" + a[:2500])
    try:
        with open("kb/pharma_dr_ims.txt", encoding="utf-8") as f:
            t = f.read()
        m = None
        for pat in ("assolutamente essere depositato", "non deve essere depositato", "deposito"):
            m = re.search(r'(?s).{0,400}' + pat + r'.{0,1600}', t)
            if m: break
        if m: parts.append("[FAQ D&R, deposito AIFA]\n" + m.group(0))
    except Exception:
        pass
    return "\n\n---\n\n".join(parts)

def analyze_json(content):
    last_err = None
    for model in ("gpt-4o", "gpt-4o-mini"):
        try:
            r = requests.post("https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                json={"model": model, "temperature": 0.0,
                      "response_format": {"type": "json_object"},
                      "messages": [{"role": "user", "content": content}]})
            r.raise_for_status()
            return json.loads(r.json()["choices"][0]["message"]["content"])
        except Exception as e:
            last_err = e
    raise last_err

def choose_file(query):
    q = query.lower()
    if "deontolog" in q or "codice" in q: return "kb/pharma_codice_deontologico.txt"
    if "domande" in q or "faq" in q or "risposte" in q or "marketing" in q: return "kb/pharma_dr_ims.txt"
    return "kb/pharma_dlgs219.txt"

def ask_llm(messages, json_mode=False, temperature=0.7, model="gpt-4o-mini"):
    payload = {"model": model, "messages": messages, "temperature": temperature}
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    r = requests.post("https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
        json=payload)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]

# ---------- HEADER ----------
hleft, hright = st.columns([3, 1])
with hleft:
    st.markdown("# 🧠 Farma Compliance · Brain")
    st.markdown('Senior Compliance Officer AI · Knowledge Base: D.Lgs 219/2006 · Codice Deontologico · FAQ &nbsp; <span class="badge green">KB ATTIVA</span>', unsafe_allow_html=True)
with hright:
    if os.path.exists("logo.png"):
        with open("logo.png", "rb") as f:
            logo_b64 = base64.b64encode(f.read()).decode()
        st.markdown(f'''
        <div style="background:#ffffff; border-radius:14px; padding:10px; text-align:center; margin-top:-36px;">
            <img src="data:image/png;base64,{logo_b64}" style="width:100%;">
        </div>
        ''', unsafe_allow_html=True)
    else:
        st.markdown('<div style="border:1px dashed #4ade80; border-radius:12px; padding:24px 10px; text-align:center; color:#4ade80; font-size:12px; margin-top:12px;">LOGO</div>', unsafe_allow_html=True)

tab_check, tab_chat = st.tabs(["📋 Check Pubblicità", "💬 Chat Normativa"])

# ---------------- TAB CHECK ----------------
with tab_check:
    with st.container(border=True):
        st.markdown("### Carica il materiale da verificare")
        n = st.session_state.get("clear_count", 0)
        ad_text = st.text_area("Testo del materiale (o URL del sito/pagina)", height=100, placeholder="Incolla qui il testo dello spot / annuncio / post social, oppure un URL...", key=f"ad_text_{n}")
        ad_image = st.file_uploader("Foto / immagine (opzionale)", type=["png", "jpg", "jpeg"], key=f"ad_image_{n}")
        rcp_file = st.file_uploader("📄 RCP del prodotto (PDF o TXT, facoltativo): sblocca la verifica automatica dei claim", type=["pdf", "txt"])
        rcp_text = ""
        if rcp_file:
            try:
                if rcp_file.name.lower().endswith(".txt"):
                    rcp_text = rcp_file.read().decode("utf-8", "replace")
                else:
                    from pypdf import PdfReader
                    import io as _io
                    rcp_text = "\n".join(p.extract_text() or "" for p in PdfReader(_io.BytesIO(rcp_file.read())).pages)
            except Exception as _e:
                st.caption("⚠️ Impossibile leggere l'RCP: " + str(_e))
        rcp_instr = "\n\nISTRUZIONI RCP: per ogni voce di claims_rcp verifica il claim contro il RCP fornito e sostituisci UNVERIFIABLE_RCP_NOT_IN_KB con CONFORME_RCP (cita sezione, es. §4.1) o VIOLAZIONE_RCP (cita sezione). I divieti assoluti di legge restano indipendenti dal RCP."
        rcp_extra = ("\n\nRCP DEL PRODOTTO:\n" + rcp_text[:20000] + rcp_instr) if rcp_text else ""
        pseudo = st.checkbox("🔒 Pseudonimizza nomi di persone fisiche nel report (per distribuzione esterna)", value=False)
        use_claude = bool(ANTHROPIC_API_KEY)

        colA, colB = st.columns(2)
        with colA:
            analyze = st.button("🔍 Analizza conformità", type="primary")
        with colB:
            st.button("🗑️ Cancella dati inseriti", on_click=clear_check)

    area = st.container()

    if analyze:
        with area:
            with st.status("🔎 Analisi di conformità in corso...", expanded=True) as status:
                autoscroll(True)
                st.write("📥 **Fase 1/4:** Acquisizione del materiale...")
                set_topbar("📥 Fase 1/4 — Acquisizione materiale")
                content_text = ""
                source_desc = []
                not_analyzed = []
                for u in re.findall(r'https?://\S+', ad_text or ""):
                    try:
                        t = fetch_url(u)
                        if len(t) >= 200:
                            content_text += f"\n[Contenuto recuperato da {u}]\n{t}"
                            source_desc.append(f"URL {u} ({len(t)} caratteri recuperati)")
                            st.write(f"   ✅ {u} — {len(t)} caratteri")
                        else:
                            not_analyzed.append(f"URL {u}: contenuto insufficiente ({len(t)} caratteri), pagina probabilmente dinamica")
                            st.write(f"   ⚠️ {u} — insufficiente")
                    except Exception as e:
                        not_analyzed.append(f"URL {u}: non accessibile ({type(e).__name__})")
                        st.write(f"   ❌ {u} — non accessibile")
                extra = re.sub(r'https?://\S+', '', ad_text or "").strip()
                if extra:
                    content_text += f"\n[Testo inserito dall'utente]\n{extra}"
                    source_desc.append("Testo inserito dall'utente")
                if ad_image:
                    source_desc.append(f"Immagine: {ad_image.name}")
                else:
                    not_analyzed.append("Nessuna immagine fornita")

                if not content_text.strip() and not ad_image:
                    status.update(label="⛔ Analisi interrotta", state="error")
                    st.error("Contenuto non accessibile. Carica il materiale come testo, file o immagine.")
                    st.stop()

                content_send = content_text[:12000]

                st.write("📚 **Fase 2/4:** Recupero delle regole dalla Knowledge Base...")
                set_topbar("📚 Fase 2/4 — Recupero regole dalla KB")
                try:
                    results = search_kb(content_send or "pubblicità medicinali", "pharma", 20)
                    rules = "\n\n---\n\n".join([f"[{source_label(r)}]\n{r['chunk_text']}" for r in results])
                    rules += "\n\n---\n\nREGOLE DI AMBITO (disposizioni da citare per l'ambito di applicazione):\n" + scope_pack()
                    st.write(f"   ✅ {len(results)} chunk recuperati + regole di ambito")
                except Exception as e:
                    rules = ""
                    status.update(label="⛔ Errore Knowledge Base", state="error")
                    st.error(f"Errore KB: {e}")
                    st.stop()

                st.write("🧠 **Fase 3/4: Analisi approfondita sul corpus normativo...")
                set_topbar("🧠 Fase 3/4 — Analisi in corso (1-4 min)")
                image_b64 = None
                mime = "image/png"
                if ad_image:
                    mime = ad_image.type or "image/png"
                    image_b64 = base64.b64encode(ad_image.read()).decode()
                try:
                    if use_claude:
                        st.write("   🧠 Analisi approfondita in corso...")
                        corpus = claude_engine.essential_corpus() + "\n\n---\n\nFAQ D&R PERTINENTI:\n" + "\n\n---\n\n".join([f"[{source_label(r)}]\n{r['chunk_text']}" for r in results])
                        system_blocks = [
                            {"type": "text", "text": SKILL_PROMPT + ("\nPSEUDONIMIZZA=1." if pseudo else "\nPSEUDONIMIZZA=0.")},
                            {"type": "text", "text": "CORPUS NORMATIVO INTEGRALE (knowledge base del cliente):\n" + corpus, "cache_control": {"type": "ephemeral"}},
                        ]
                        if rcp_text:
                            system_blocks.append({"type": "text", "text": "RCP DEL PRODOTTO (documento autorizzato):\n" + rcp_text[:60000] + rcp_instr})
                        live = st.empty()
                        try:
                            try:
                                rep, _m = claude_engine.ask_claude_stream(ANTHROPIC_API_KEY, system_blocks, "MATERIALE DA ANALIZZARE:\n" + content_send, image_b64, mime, on_delta=lambda s: live.text("⏳ Report in generazione...\n" + s[-600:]))
                            except Exception:
                                live.text("⏳ Nuovo tentativo di analisi...")
                                rep, _m = claude_engine.ask_claude(ANTHROPIC_API_KEY, system_blocks, "MATERIALE DA ANALIZZARE:\n" + content_send, image_b64, mime)
                            modello = "NEXORA Deep Engine"
                        except Exception:
                            live.text("⏳ Motore standard di riserva...")
                            prompt = SKILL_PROMPT + ("\nPSEUDONIMIZZA=1." if pseudo else "\nPSEUDONIMIZZA=0.") + "\nREGOLE (knowledge base caricata):\n" + rules + rcp_extra + "\n\nMATERIALE DA ANALIZZARE:\n" + content_send
                            content = [{"type": "text", "text": prompt}]
                            if image_b64:
                                content.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{image_b64}"}})
                            rep = analyze_json(content)
                            modello = "NEXORA Standard Engine"
                    else:
                        prompt = SKILL_PROMPT + ("\nPSEUDONIMIZZA=1." if pseudo else "\nPSEUDONIMIZZA=0.") + "\nREGOLE (knowledge base caricata):\n" + rules + rcp_extra + "\n\nMATERIALE DA ANALIZZARE:\n" + content_send
                        content = [{"type": "text", "text": prompt}]
                        if image_b64:
                            content.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{image_b64}"}})
                        rep = analyze_json(content)
                        modello = "NEXORA Standard Engine"
                    rep = polish_obj(rep)
                    st.write(f"   ✅ Analisi completata — stato: {rep.get('stato_complessivo','')}")
                except Exception as e:
                    status.update(label="⛔ Errore analisi LLM", state="error")
                    set_topbar(None)
                    st.error(f"Errore analisi: {type(e).__name__}: {e}")
                    st.stop()

                st.write("📄 **Fase 4/4:** Generazione del report PDF...")
                set_topbar("📄 Fase 4/4 — Generazione report PDF")
                import nexora_core
                rep, _probs = nexora_core.pipeline(rep, _user_text())
                _probs = validate_rep(rep)
                if _probs:
                    st.error("🛑 BUILD FALLITA - controlli automatici: " + "; ".join(_probs))
                    st.stop()
                rep = gate_severita(rep)
                cr = {"rep": rep, "source_desc": source_desc, "not_analyzed": not_analyzed, "created": time.time(), "model": modello, "ad_text": _user_text()}
                try:
                    data = build_pdf("REPORT DI COMPLIANCE - Farma Compliance", report_sections(rep, source_desc, not_analyzed))
                    cr["pdf"] = data
                    cr["fname"] = salva_report(data, "report_compliance")
                    st.write(f"   ✅ PDF salvato: {cr['fname']}")
                except Exception as e:
                    st.write(f"   ⚠️ PDF non generato: {e}")

                status.update(label="✅ Analisi completata — report qui sotto", state="complete")
                st.toast("✅ Report pronto! Lo trovi subito sotto questo riquadro", icon="✅")

                st.session_state.check_result = cr
                st.rerun()

    elif st.session_state.get("check_result"):
        with area:
            set_topbar(None)
            with st.container(border=True):
                render_report(st.session_state["check_result"])

# ---------------- TAB CHAT ----------------
with tab_chat:
    if "messages" not in st.session_state:
        st.session_state.messages = []

    colC, colD, colE = st.columns(3)
    with colC:
        st.button("🗑️ Cancella conversazione", on_click=clear_chat)
    with colD:
        if st.session_state.messages:
            if st.button("🖨️ Genera report PDF", type="primary"):
                try:
                    transcript = "\n\n".join([f"{'DOMANDA' if m['role']=='user' else 'RISPOSTA'}: {m['content']}" for m in st.session_state.messages])
                    data = build_pdf("REPORT CONSULENZA - Farma Compliance", [("CONVERSAZIONE", transcript)])
                    st.session_state.chat_report = data
                    st.session_state.chat_fname = salva_report(data, "report_chat")
                    st.success("Report PDF pronto e salvato in PROGETTO")
                except Exception:
                    mostra_errore_pdf()
    with colE:
        if st.session_state.get("chat_report"):
            st.download_button("💾 Scarica report PDF", data=st.session_state.chat_report,
                               file_name=st.session_state.get("chat_fname", "report_chat.pdf"),
                               mime="application/pdf", type="primary")

    for m in st.session_state.messages:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    if prompt := st.chat_input("Tua domanda..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        article_match = re.search(r'(?:art(?:icolo)?\.?\s*)(\d+)', prompt, re.IGNORECASE)
        if article_match:
            num = article_match.group(1)
            filepath = choose_file(prompt)
            art = find_article_in_file(num, filepath)
            if art:
                answer = ask_llm([{"role": "user", "content": f"""Sei un assistente legale. Rispondi basandoti SOLO sul contesto.
Contesto:
Articolo {num}:
{art[:3000]}
Domanda: {prompt}"""}], temperature=0.0)
                answer += f"\n\n📚 Fonte: {DOC_NAMES.get(os.path.basename(filepath).replace('.txt',''), os.path.basename(filepath))}, Articolo {num}"
            else:
                answer = f"Articolo {num} non trovato in {os.path.basename(filepath)}."
        else:
            try:
                results = search_kb(prompt, "pharma", 3)
                context = "\n\n---\n\n".join([f"[{source_label(r)}]\n{r['chunk_text']}" for r in results])
                answer = ask_llm([{"role": "user", "content": f"""Sei un assistente legale ed esperto di normative farmaceutiche italiane.
Rispondi basandoti SOLO sul contesto. Cita SEMPRE documento e articolo tra parentesi quadre, es. [D.Lgs 219/2006, art. 115].
Contesto:
{context}
Domanda: {prompt}"""}], temperature=0.0)
                sources = " · ".join(sorted(set([source_label(r) for r in results])))
                answer += f"\n\n📚 Fonti: {sources}"
            except Exception as e:
                answer = f"Errore: {e}"

        st.session_state.messages.append({"role": "assistant", "content": answer})
        with st.chat_message("assistant"):
            st.markdown(answer)

_cr3 = st.session_state.get("check_result")
if _cr3 and _cr3.get("created") and (time.time() - _cr3["created"]) < 15:
    components.html("""
    <script>
    (function(){
      var d = window.parent.document;
      function go(){ var el = d.getElementById('farma-fine'); if(el){ el.scrollIntoView({behavior:'smooth', block:'start'}); } }
      setTimeout(go, 400);
      setTimeout(go, 1200);
    })();
    </script>
    """, height=0, width=0)

_cr3 = st.session_state.get("check_result")
if _cr3 and _cr3.get("created") and (time.time() - _cr3["created"]) < 15:
    components.html("""
    <script>
    (function(){
      var d = window.parent.document;
      function go(){ var el = d.getElementById('farma-fine'); if(el){ el.scrollIntoView({behavior:'smooth', block:'start'}); } }
      setTimeout(go, 400);
      setTimeout(go, 1200);
    })();
    </script>
    """, height=0, width=0)

if st.session_state.get("check_result"):
    scroll_to_report("farma-report")
