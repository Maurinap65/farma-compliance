import nexora_core as nx

fails = []
def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)

rep = {"violazioni_critiche": [{"titolo": "T", "problema": "P", "norma_key": ["art117_c1_f"], "azione": "A"}], "avvertenze": [], "elementi_mancanti": [], "claims_rcp": []}
rep, probs = nx.pipeline(rep, "")
check("campo vuoto bloccato", any("vuoto" in p for p in nx.validate_rep({"violazioni_critiche": [{"titolo": "T", "problema": "", "norma_violata": "x", "azione": "a"}]})))

rep2 = {"violazioni_critiche": [{"titolo": "X per analogia art 119", "problema": "p", "norma_violata": "n", "azione": "a"}], "avvertenze": [], "elementi_mancanti": [], "claims_rcp": []}
rep2, _ = nx.pipeline(rep2, "")
check("analogia degradata a nota", len(rep2["violazioni_critiche"]) == 0 and len(rep2["note_informative"]) >= 1)

rep3 = {"violazioni_critiche": [], "avvertenze": [], "elementi_mancanti": ["Denominazione comune: art116_c1_b1"], "claims_rcp": []}
md = nx.render_md(rep3, {})
check("chiavi interne non in output", "art116_c1_b1" not in md and "Art. 116 c.1 lett. b n.1" in md)

rep4 = {"violazioni_critiche": [{"titolo": "[{'type': 'text'", "problema": "p", "norma_violata": "n", "azione": "a"}], "avvertenze": [], "elementi_mancanti": [], "claims_rcp": []}
check("marcatore prompt bloccato", len(nx.validate_rep(rep4)) >= 1)

rep5 = {"riepilogo_esecutivo": "Il materiale presenta 9 violazioni critiche e 1 avvertenze.", "violazioni_critiche": [1, 2, 3], "avvertenze": [1, 2]}
nx.fix_counts(rep5)
check("conteggi ricalcolati", "3 violazioni critiche" in rep5["riepilogo_esecutivo"] and "2 avvertenze" in rep5["riepilogo_esecutivo"])

print("----")
print("ESITO:", "TUTTI I TEST PASS" if not fails else "FALLITI: " + ", ".join(fails))
