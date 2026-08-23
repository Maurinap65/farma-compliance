#!/usr/bin/env python3
"""
Runner di regressione.
  python3 check_build.py golden/*.json
Esce con codice 1 se un caso d'oro non e' rispettato: usalo come pre-commit
o come step di build. Sostituisce la lettura a occhio dei PDF.

Formato di un caso d'oro (JSON):
{
  "nome": "tussanplus",
  "testo": "<materiale in input>",
  "rep_grezzo": { ...output del modello... },
  "atteso": {
     "critiche":  [["art117_c1_b","art117_c1_f"], ["art114_c3_a","art117_c1_b"], ...],
     "avvertenze":[["art114_c2"], ["art117_c1_g"], ["art117_c1_i"]],
     "mancanti":  [["art116_c1_b1"], ["art116_c1_b2"], ["art116_c1_b3"], ["art118_c1"]],
     "claims_rcp": 3
  }
}
`rep_grezzo` va congelato UNA VOLTA: cosi' il runner misura la pipeline, non il modello.
Per misurare anche il modello, usa --live e passa un callable di estrazione.
"""

import sys
import json
import glob

import nexora_core as nx


def composizione(rep, severita):
    out = []
    for v in nx.ordina(rep)[severita]:
        out.append(sorted(v["norma_key"]))
    return sorted(out)


def confronta(nome, atteso, ottenuto, etichetta, problemi):
    if atteso is None:
        return
    a = sorted([sorted(x) for x in atteso])
    o = sorted([sorted(x) for x in ottenuto])
    if a == o:
        return
    mancano = [x for x in a if x not in o]
    inattesi = [x for x in o if x not in a]
    for x in mancano:
        problemi.append("%s | %s: atteso e non prodotto -> %s" % (nome, etichetta, "+".join(x)))
    for x in inattesi:
        problemi.append("%s | %s: prodotto e non atteso -> %s" % (nome, etichetta, "+".join(x)))


def esegui(path, strict_gate=False):
    caso = json.load(open(path, encoding="utf-8"))
    nome = caso.get("nome", path)
    corpus = nx.Corpus.load()
    problemi = []

    try:
        rep, gate, corpus = nx.pipeline(caso["rep_grezzo"], caso["testo"],
                                        corpus=corpus, strict=strict_gate)
    except nx.ReportNonValido as e:
        for p in e.problemi:
            problemi.append("%s | GATE: %s" % (nome, p))
        return problemi, None

    for p in gate:
        problemi.append("%s | GATE: %s" % (nome, p))

    att = caso.get("atteso") or {}
    confronta(nome, att.get("critiche"), composizione(rep, nx.CRITICA), "critiche", problemi)
    confronta(nome, att.get("avvertenze"), composizione(rep, nx.AVVERTENZA), "avvertenze", problemi)
    confronta(nome, att.get("mancanti"), composizione(rep, nx.MANCANTE), "mancanti", problemi)

    if "claims_rcp" in att:
        n = len(rep.get("claims_rcp") or [])
        if n != att["claims_rcp"]:
            problemi.append("%s | claims_rcp: atteso %d, ottenuto %d" % (nome, att["claims_rcp"], n))

    # invarianti che valgono su qualunque caso, non solo su questo
    for v in rep["rilievi"]:
        if v.get("_pos_non_ancorata") and v["severita"] != nx.MANCANTE:
            problemi.append("%s | posizione non ancorata al testo: %s" % (nome, v["titolo"][:70]))

    return problemi, rep


def main(argv):
    strict = "--strict" not in argv
    paths = [a for a in argv[1:] if not a.startswith("--")] or sorted(glob.glob("golden/*.json"))
    if not paths:
        print("nessun caso d'oro trovato in golden/*.json")
        return 2

    tutti = []
    for p in paths:
        prob, rep = esegui(p, strict_gate=False)
        nome = json.load(open(p, encoding="utf-8")).get("nome", p)
        if prob:
            print("FAIL  %s" % nome)
            for x in prob:
                print("      %s" % x)
        else:
            c, w, m, r = nx.conta(rep)
            print("OK    %s  (%d critiche / %d avvertenze / %d mancanti / %d claim)"
                  % (nome, c, w, m, r))
        tutti += prob

    print("-" * 60)
    if tutti:
        print("BUILD RESPINTA: %d scostamenti" % len(tutti))
        return 1
    print("BUILD ACCETTATA")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
