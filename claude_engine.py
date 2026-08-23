import json
import re
import requests

CLAUDE_MODELS = ["claude-sonnet-4-5", "claude-sonnet-4-20250514", "claude-3-7-sonnet-latest", "claude-3-5-sonnet-latest"]

_CORPUS = None
_ESSENTIAL = None

def load_corpus():
    global _CORPUS
    if _CORPUS is None:
        parts = []
        for f in ("kb/pharma_dlgs219.txt", "kb/pharma_codice_deontologico.txt", "kb/pharma_dr_ims.txt"):
            try:
                with open(f, encoding="utf-8") as fh:
                    parts.append(fh.read())
            except Exception:
                pass
        _CORPUS = "\n\n========\n\n".join(parts)
    return _CORPUS

def _find_article(article_num, filepath):
    with open(filepath, encoding="utf-8") as f:
        text = f.read()
    base = r'(?:Art\.|Articolo)\s+' + str(article_num) + r'\b'
    matches = list(re.finditer(r'(?m)^\s*' + base, text)) or list(re.finditer(base, text))
    if not matches:
        return None
    start = matches[-1].start()
    next_m = re.search(r'(?m)^\s*(?:Art\.|Articolo)\s+\d+', text[start+10:])
    end = start + 10 + next_m.start() if next_m else len(text)
    return text[start:end].strip()

def essential_corpus():
    global _ESSENTIAL
    if _ESSENTIAL is None:
        parts = []
        for n in range(111, 128):
            a = _find_article(n, "kb/pharma_dlgs219.txt")
            if a:
                parts.append("[D.Lgs 219/2006, art. %d]\n%s" % (n, a[:4000]))
        for n in range(1, 9):
            a = _find_article(n, "kb/pharma_codice_deontologico.txt")
            if a:
                parts.append("[Codice Deontologico Farmindustria, Articolo %d]\n%s" % (n, a[:4000]))
        _ESSENTIAL = "\n\n---\n\n".join(parts)
    return _ESSENTIAL

def parse_json_loose(text):
    try:
        return json.loads(text)
    except Exception:
        a = text.find("{")
        b = text.rfind("}")
        if a != -1 and b != -1 and b > a:
            try:
                return json.loads(text[a:b+1])
            except Exception:
                pass
        raise ValueError("JSON non valido o troncato. Inizio risposta: " + text[:200])

def _build_content(user_text, image_b64, mime):
    content = []
    if image_b64:
        mt = mime if mime in ("image/png", "image/jpeg", "image/gif", "image/webp") else "image/png"
        content.append({"type": "image", "source": {"type": "base64", "media_type": mt, "data": image_b64}})
    content.append({"type": "text", "text": user_text})
    return content

def _check_error(r):
    t = r.text.lower()
    if r.status_code in (400, 404) and ("model" in t or "not found" in t):
        return "model"
    if r.status_code == 400 and "prompt is too long" in t:
        return "long"
    return None

def ask_claude(api_key, system_blocks, user_text, image_b64=None, mime="image/png", max_tokens=32000):
    content = _build_content(user_text, image_b64, mime)
    last = None
    for model in CLAUDE_MODELS:
        try:
            r = requests.post("https://api.anthropic.com/v1/messages",
                headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
                json={"model": model, "max_tokens": max_tokens, "system": system_blocks,
                      "messages": [{"role": "user", "content": content}]},
                timeout=600)
            err = _check_error(r)
            if err == "model":
                last = Exception("modello non disponibile: " + model)
                continue
            if err == "long":
                raise Exception("Prompt troppo lungo per la finestra di Claude (corpus eccessivo)")
            r.raise_for_status()
            return parse_json_loose(r.json()["content"][0]["text"]), model
        except Exception as e:
            last = e
    raise last

def ask_claude_stream(api_key, system_blocks, user_text, image_b64=None, mime="image/png", max_tokens=32000, on_delta=None):
    content = _build_content(user_text, image_b64, mime)
    last = None
    for model in CLAUDE_MODELS:
        try:
            r = requests.post("https://api.anthropic.com/v1/messages",
                headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
                json={"model": model, "max_tokens": max_tokens, "system": system_blocks,
                      "messages": [{"role": "user", "content": content}], "stream": True},
                timeout=(10, 90), stream=True)
            if r.status_code != 200:
                err = _check_error(r)
                if err == "model":
                    last = Exception("modello non disponibile: " + model)
                    continue
                if err == "long":
                    raise Exception("Prompt troppo lungo per la finestra di Claude (corpus eccessivo)")
                r.raise_for_status()
            acc = ""
            for line in r.iter_lines():
                if not line:
                    continue
                s = line.decode("utf-8", "replace")
                if not s.startswith("data:"):
                    continue
                d = s[5:].strip()
                if d == "[DONE]":
                    break
                try:
                    j = json.loads(d)
                except Exception:
                    continue
                if j.get("type") == "content_block_delta":
                    txt = j.get("delta", {}).get("text", "")
                    if txt:
                        acc += txt
                        if on_delta:
                            on_delta(acc)
            if not acc:
                raise Exception("Risposta vuota da " + model)
            return parse_json_loose(acc), model
        except Exception as e:
            last = e
    raise last
