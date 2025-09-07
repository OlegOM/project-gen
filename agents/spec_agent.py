from __future__ import annotations
import os, re, json, yaml, traceback
from typing import Any, Dict
from pathlib import Path
from jsonschema import validate, ValidationError

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "specs" / "SPEC_SCHEMA.json"

def _load_schema() -> Dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text())

# ---------- SANITIZERS & EXTRACTORS ----------
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
            traceback.print_exc()
            pass
    return yaml.safe_load(s)

# ---------- NORMALIZATION & DEFAULTS ----------
def _normalize(s: str | None) -> str:
    if not s: return "unspecified"
    t = s.strip().lower()
    mapping = { "node.js":"node","nodejs":"node","node js":"node","javascript":"js","typescript":"ts","postgresql":"postgres","postgre":"postgres","kubernetes":"k8s","next.js":"nextjs","material ui":"material-ui","mui":"material-ui" }
    return mapping.get(t, t)

def _apply_defaults(spec: Dict[str, Any], prd_text: str) -> Dict[str, Any]:
    be = spec["stacks"]["backend"]; fe = spec["stacks"]["frontend"]
    if be.get("framework") in (None, "", "unspecified"):
        be["framework"] = "fastapi"
    if be.get("lang") in (None, "", "unspecified"):
        be["lang"] = "python"
    if fe.get("framework") in (None, "", "unspecified"):
        fe["framework"] = "react"
    if fe.get("lang") in (None, "", "unspecified"):
        fe["lang"] = "ts"
    t = prd_text.lower()
    if fe.get("ui") in (None, "", "unspecified"):
        if "material-ui" in t or "material ui" in t or "mui" in t:
            fe["ui"] = "material-ui"
    return spec

def _name_from_prd(prd_text: str) -> str:
    m = re.findall(r"(?:name|project|product)[:\-]\s*([A-Za-z0-9_\- ]+)", prd_text, re.I)
    n = (m[0] if m else "my-app").strip()
    return re.sub(r"\s+", "-", n.lower())

def _coerce_to_schema(data: Dict[str, Any] | None, prd_text: str) -> Dict[str, Any]:
    data = dict(data or {})
    meta = dict(data.get("meta") or {})
    if "name" not in meta or not isinstance(meta.get("name"), str) or not meta["name"].strip():
        meta["name"] = _name_from_prd(prd_text)
    meta.setdefault("domain", "App")
    meta.setdefault("version", "0.1.0")
    data["meta"] = meta

    stacks = dict(data.get("stacks") or {})
    be = dict(stacks.get("backend") or {})
    fe = dict(stacks.get("frontend") or {})
    db = dict(stacks.get("database") or {})
    infra = dict(stacks.get("infra") or {})
    be.setdefault("framework", "unspecified"); be.setdefault("lang", "unspecified"); be.setdefault("orm", "unspecified"); be.setdefault("runtime", "unspecified")
    fe.setdefault("framework", "unspecified"); fe.setdefault("lang", "unspecified"); fe.setdefault("ui", "unspecified")
    db.setdefault("type", "unspecified"); db.setdefault("version", "unspecified")
    infra.setdefault("orchestrator", "unspecified"); infra.setdefault("cloud", "unspecified")
    stacks["backend"]=be; stacks["frontend"]=fe; stacks["database"]=db; stacks["infra"]=infra
    data["stacks"]=stacks

    data.setdefault("entities", data.get("entities") or [])
    data.setdefault("workflows", data.get("workflows") or [])
    data.setdefault("requirements", data.get("requirements") or [])
    data.setdefault("integrations", data.get("integrations") or {})
    data.setdefault("non_functional", data.get("non_functional") or {})
    data.setdefault("ci_cd", data.get("ci_cd") or {})
    data.setdefault("constraints", data.get("constraints") or {})
    return data

# ---------- LLM & HEURISTICS ----------
def _llm_prd_to_spec_data(prd_text: str) -> Dict[str, Any]:
    import openai
    schema = _load_schema()
    template = {
        "meta": {"name": "<string>", "domain": "<string>", "version": "<string>"},
        "stacks": {
            "backend": {"framework": "<string>", "lang": "<string>", "orm": "<string>", "runtime": "<string>"},
            "frontend": {"framework": "<string>", "lang": "<string>", "ui": "<string>"},
            "database": {"type": "<string>", "version": "<string>"},
            "infra": {"orchestrator": "<string>", "cloud": "<string>"}
        },
        "entities": [], "workflows": [], "requirements": [], "integrations": {}, "non_functional": {}, "ci_cd": {}, "constraints": {}
    }
    system = ("Return ONLY a single JSON object (no markdown). "
              "It MUST contain keys: meta, stacks, entities, workflows, requirements, integrations, non_functional, ci_cd, constraints. "
              "If a value is not explicitly stated in the PRD, use the string 'unspecified'.")
    user = ("JSON Schema:\n" + json.dumps(schema) + "\n\nTemplate (shape only):\n" + json.dumps(template, indent=2) +
            "\n\nPRD:\n" + prd_text + "\n\nOutput: ONE JSON object only.")

    msgs = [{"role":"system","content":system},{"role":"user","content":user}]
    for _ in range(3):
        resp = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=msgs,
            temperature=0,
            response_format={"type": "json_object"},
        )
        raw = resp["choices"][0]["message"]["content"]
        try:
            parsed = json.loads(raw)
        except Exception:
            traceback.print_exc()
            body = _extract_structured_block(raw)
            try:
                parsed = json.loads(body)
            except Exception as e:
                traceback.print_exc()
                msgs.append({"role":"assistant","content":raw[:1200]})
                msgs.append({"role":"user","content":f"Not valid JSON: {e}. Return ONE JSON object matching the template keys."})
                continue

        coerced = _coerce_to_schema(parsed, prd_text)
        try:
            validate(instance=coerced, schema=schema)
            return coerced
        except ValidationError as e:
            traceback.print_exc()
            msgs.append({"role":"assistant","content":json.dumps(coerced)[:1200]})
            msgs.append({"role":"user","content":f"Validation failed: {e.message} at path {list(e.path)}. Return ONE JSON object with ALL required fields."})
            continue
    raise RuntimeError("LLM could not produce a valid spec after retries.")

def _heuristic_prd_to_spec(prd_text: str) -> Dict[str, Any]:
    t = prd_text.lower()
    def pick(regexes, value):
        return value if any(re.search(r, t) for r in regexes) else "unspecified"
    backend_fw = pick([r"\bfastapi\b", r"\bdjango\b", r"\bexpress\b", r"\bnest\b", r"\bspring\b"], "unspecified")
    backend_lang = pick([r"\bpython\b", r"\btypescript\b", r"\bjavascript\b", r"\bts\b", r"\bjs\b"], "unspecified")
    frontend_fw = pick([r"\bnext\.?js\b", r"\breact\b", r"\bvue\b", r"\bnuxt\b"], "unspecified")
    frontend_lang = pick([r"\btypescript\b", r"\bjavascript\b", r"\bts\b", r"\bjs\b"], "unspecified")
    db_type = pick([r"\bpostgres(?:ql)?\b", r"\bmysql\b", r"\bsqlite\b", r"\bmssql\b"], "unspecified")
    infra_orch = pick([r"\bdocker(?:-compose)?\b", r"\bkubernetes\b", r"\bk8s\b"], "unspecified")
    cloud = pick([r"\baws\b", r"\bgcp\b", r"\bazure\b"], "unspecified")

    name_match = re.findall(r"(?:name|project|product)[:\-]\s*([A-Za-z0-9_\- ]+)", prd_text, re.I)
    proj_name = (name_match[0] if name_match else "my-app").strip().lower().replace(" ", "-")

    data: Dict[str, Any] = {
        "meta": {"name": proj_name, "domain": "App", "version": "0.1.0"},
        "stacks": {
            "backend": {"framework": _normalize(backend_fw), "lang": _normalize(backend_lang), "orm": "unspecified", "runtime": "unspecified"},
            "frontend": {"framework": _normalize(frontend_fw), "lang": _normalize(frontend_lang), "ui": "unspecified"},
            "database": {"type": _normalize(db_type), "version": "unspecified"},
            "infra": {"orchestrator": _normalize(infra_orch), "cloud": _normalize(cloud)},
        },
        "entities": [], "workflows": [], "requirements": [], "integrations": {}, "non_functional": {}, "ci_cd": {}, "constraints": {},
    }
    validate(instance=data, schema=_load_schema())
    return _apply_defaults(data, prd_text)

def prd_to_spec(prd_text: str) -> Dict[str, Any]:
    use_llm = os.getenv("USE_LLM","false").lower() == "true"
    if use_llm:
        try:
            data = _llm_prd_to_spec_data(prd_text)
        except Exception as e:
            traceback.print_exc()
            print(f"[spec_agent] LLM failed, fallback to heuristics: {e}")
            data = _heuristic_prd_to_spec(prd_text)
    else:
        data = _heuristic_prd_to_spec(prd_text)

    be = data["stacks"]["backend"]; fe = data["stacks"]["frontend"]
    be["framework"] = _normalize(be.get("framework")); be["lang"] = _normalize(be.get("lang"))
    fe["framework"] = _normalize(fe.get("framework")); fe["lang"] = _normalize(fe.get("lang"))
    data = _apply_defaults(data, prd_text)

    validate(instance=data, schema=_load_schema())
    return data
