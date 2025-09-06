from __future__ import annotations
import os, re, json, yaml
from typing import Dict, Any, List
from projectgen.agents.requirements_agent import extract_requirements
from projectgen.agents.rules_agent import extract_rules

_CTRL_CHARS = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F]")
_ZERO_WIDTH = re.compile(r"[\u200B-\u200F\u2028\u2029\u2060\uFEFF]")
SMART_QUOTES = { "\u2018": "'", "\u2019": "'", "\u201A": "'", "\u201B": "'", "\u201C": '"', "\u201D": '"', "\u201E": '"', "\u201F": '"' }

def _sanitize_text(s: str) -> str:
    if not s:
        return s
    for k, v in SMART_QUOTES.items():
        s = s.replace(k, v)
    s = _ZERO_WIDTH.sub("", s)
    s = _CTRL_CHARS.sub("", s)
    s = s.replace("\t", "  ")
    return s.strip()

_FENCE_RE = re.compile(r"```(?:\s*(yaml|yml|json))?\s*?\n(.*?)```", re.IGNORECASE | re.DOTALL)

def _extract_structured_block(text: str) -> str:
    text = (text or "").strip()
    blocks = [(m.group(1) or "", m.group(2)) for m in _FENCE_RE.finditer(text)]
    if not blocks:
        return text
    for lang, body in blocks:
        if lang.lower() in ("yaml", "yml"):
            return body
    for lang, body in blocks:
        if lang.lower() == "json":
            return body
    return max(blocks, key=lambda b: len(b[1]))[1]

def _load_structured(text: str) -> Dict[str, Any]:
    s = _sanitize_text(text)
    if s.lstrip().startswith("{") or s.lstrip().startswith("["):
        try:
            return json.loads(s)
        except Exception:
            pass
    return yaml.safe_load(s)

def _uniq(seq: List[Any]) -> List[Any]:
    seen = set(); out: List[Any] = []
    for x in seq:
        try: k = json.dumps(x, sort_keys=True)
        except Exception: k = str(x)
        if k not in seen: seen.add(k); out.append(x)
    return out

def _heuristic_entities(prd_text: str) -> List[Dict[str, Any]]:
    entities: List[Dict[str, Any]] = []
    for m in re.finditer(r"(?i)\bentity:\s*([A-Za-z][A-Za-z0-9_]*)\s*\(([^)]+)\)", prd_text):
        name = m.group(1).strip()
        fields = [f.strip() for f in m.group(2).split(",") if f.strip()]
        ent = {"name": name, "fields": [{"name": f, "type": "string"} for f in fields]}
        entities.append(ent)
    blocks = re.split(r"\n(?=#+\s)", prd_text)
    for b in blocks:
        h = re.match(r"#+\s*([A-Za-z][A-Za-z0-9_]*)", b)
        if not h: continue
        name = h.group(1)
        bullet_fields = re.findall(r"^\s*[-*]\s*([A-Za-z][A-Za-z0-9_]*)\s*$", b, flags=re.M)
        if bullet_fields:
            ent = {"name": name, "fields": [{"name": f, "type": "string"} for f in bullet_fields]}
            entities.append(ent)
    if not entities:
        entities = [{
            "name":"Customer",
            "fields":[{"name":"id","type":"uuid","pk":True},{"name":"email","type":"string","unique":True},{"name":"name","type":"string"}]
        }]
    return _uniq(entities)

def _heuristic_workflows(prd_text: str) -> List[Dict[str, Any]]:
    flows: List[Dict[str, Any]] = []
    for m in re.finditer(r"(?i)(?:when|on)\s+(.+?):\s*(.+)", prd_text):
        trigger = m.group(1).strip()
        actions = [a.strip() for a in re.split(r"[;,]", m.group(2)) if a.strip()]
        flows.append({"name": trigger[:40], "trigger": trigger, "actions": actions})
    return _uniq(flows)

def _coerce_entities(entities: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not isinstance(entities, list): return out
    for e in entities:
        if not isinstance(e, dict): continue
        name = e.get("name")
        if not isinstance(name, str) or not name.strip(): continue
        fields = e.get("fields") or []
        if not isinstance(fields, list): fields = []
        cleaned_fields = []
        seen = set()
        for f in fields:
            if not isinstance(f, dict): continue
            fname = f.get("name")
            if not isinstance(fname, str) or not fname.strip(): continue
            if fname in seen: continue
            seen.add(fname)
            ftype = f.get("type","string")
            item = {"name": fname, "type": str(ftype)}
            if "pk" in f: item["pk"] = bool(f.get("pk"))
            if "unique" in f: item["unique"] = bool(f.get("unique"))
            if f.get("fk") is not None: item["fk"] = str(f.get("fk"))
            cleaned_fields.append(item)
        out.append({"name": name, "fields": cleaned_fields})
    return _uniq(out)

def _coerce_workflows(workflows: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not isinstance(workflows, list): return out
    for w in workflows:
        if not isinstance(w, dict): continue
        name = w.get("name") or w.get("trigger") or "Workflow"
        trigger = w.get("trigger") or ""
        actions = w.get("actions") or []
        if isinstance(actions, str): actions = [actions]
        actions = [str(a).strip() for a in actions if str(a).strip()]
        out.append({"name": str(name)[:80], "trigger": str(trigger), "actions": actions})
    return _uniq(out)

def _ensure_health(flows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    s = json.dumps(flows).lower()
    if "health" not in s and "/health" not in s:
        flows.append({"name":"Health","trigger":"http","actions":["GET /health returns 200 {status:ok}"]})
    return flows

def _llm_extract(prd_text: str) -> Dict[str, Any]:
    import openai
    system = (
        "Output ONLY one structured block (prefer JSON) describing entities and workflows. "
        "No prose, no Markdown, no fences. Keys:\n"
        "entities: [ { name: str, fields: [ { name: str, type: str, pk?: bool, unique?: bool, fk?: str } ] } ]\n"
        "workflows: [ { name: str, trigger: str, actions: [str,...] } ]"
    )
    user = f"PRD:\n{prd_text}\n\nReturn a single JSON object (preferred) or YAML with keys: entities, workflows."
    msgs = [{"role":"system","content":system},{"role":"user","content":user}]
    for _ in range(3):
        resp = openai.ChatCompletion.create(model="gpt-4o-mini", messages=msgs, temperature=0)
        raw = resp["choices"][0]["message"]["content"]
        body = _extract_structured_block(raw)
        try:
            data = _load_structured(body) or {}
            ents = _coerce_entities(data.get("entities"))
            flows = _coerce_workflows(data.get("workflows"))
            return {"entities": ents, "workflows": flows}
        except Exception as e:
            msgs.append({"role":"assistant","content":raw[:1200]})
            msgs.append({"role":"user","content":f"Failed to parse: {e}. Return ONLY a JSON object with 'entities' and 'workflows'."})
    return {"entities": [], "workflows": []}

def enrich_spec(spec: Dict[str, Any], prd_text: str) -> Dict[str, Any]:
    use_llm = os.getenv("USE_LLM","false").lower()=="true"
    ents: List[Dict[str, Any]] = []
    flows: List[Dict[str, Any]] = []
    if use_llm:
        try:
            data = _llm_extract(prd_text)
            ents = data.get("entities", []) or []
            flows = data.get("workflows", []) or []
        except Exception:
            ents, flows = [], []
    if not ents: ents = _heuristic_entities(prd_text)
    if not flows: flows = _heuristic_workflows(prd_text)
    flows = _ensure_health(flows)

    new_spec = dict(spec)
    new_spec["entities"] = ents
    new_spec["workflows"] = flows
    new_spec["requirements"] = extract_requirements(prd_text)
    new_spec["business_rules"] = extract_rules(prd_text)
    return new_spec
