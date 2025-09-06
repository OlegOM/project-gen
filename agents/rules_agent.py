# projectgen/agents/rules_agent.py
from __future__ import annotations
import os, re, json
from typing import List, Dict, Any

def _mk_id(n:int)->str: return f"BR-{n:04d}"

_PAT_NEG = re.compile(r"(?i)\b(must|cannot|can't|should not|must not)\b.*\b(negative|less than\s*0)\b")
_PAT_ENUM = re.compile(r"(?i)\b(status|state)\b.*\b(can be|allowed|one of)\b[: ]+([A-Za-z,\s|]+)")
_PAT_EQ   = re.compile(r"(?i)^([A-Za-z_][\w\.]*)\s*=\s*(.+)$")

def _heuristic_rules(prd: str) -> List[Dict[str,Any]]:
    out: List[Dict[str,Any]] = []; n = 1
    for line in prd.splitlines():
        l = line.strip()
        if not l: continue

        m = _PAT_NEG.search(l)
        if m:
            # naive target guess: first token like "amount" / "total"
            m2 = re.search(r"\b([A-Za-z_][A-Za-z0-9_]*)\b", l)
            tgt = (m2.group(1) if m2 else "amount").capitalize() + ".amount"
            out.append({"id": _mk_id(n), "target": tgt, "kind":"constraint", "expr":"amount >= 0",
                        "message":"amount must not be negative"}); n += 1
            continue

        m = _PAT_ENUM.search(l)
        if m:
            field = m.group(1).strip()
            options = [w.strip().lower() for w in re.split(r"[,\|]", m.group(3)) if w.strip()]
            out.append({"id": _mk_id(n), "target": f"{field.capitalize()}.{field.lower()}",
                        "kind":"constraint", "expr": f"{field.lower()} in {options}",
                        "message": f"{field} must be one of {options}"}); n += 1
            continue

        m = _PAT_EQ.match(l)
        if m:
            target, rhs = m.group(1), m.group(2)
            out.append({"id": _mk_id(n), "target": target, "kind":"derivation", "expr": f"{target} == {rhs}",
                        "message": f"{target} must equal {rhs}"}); n += 1

    return out

def _llm_rules(prd: str) -> List[Dict[str,Any]]:
    import openai, json as _json
    prompt = f"""Extract atomic business rules as JSON:
[{{"id":"BR-0001","target":"Invoice.total","kind":"constraint|derivation|transition","expr":"python-like expression","message":"..." }}, ...]
Rules must be testable and refer to concrete entity fields.
PRD:
{prd}"""
    r = openai.ChatCompletion.create(model="gpt-4o-mini", messages=[{"role":"user","content":prompt}], temperature=0)
    try:
        arr = _json.loads(r["choices"][0]["message"]["content"])
        # backfill ids if missing
        out=[]; c=1
        for it in arr if isinstance(arr, list) else []:
            if not isinstance(it, dict) or not it.get("expr"): continue
            it.setdefault("id", _mk_id(c)); c+=1
            it.setdefault("kind", "constraint")
            it.setdefault("message", "")
            out.append(it)
        return out or _heuristic_rules(prd)
    except Exception:
        return _heuristic_rules(prd)

def extract_rules(prd: str) -> List[Dict[str,Any]]:
    use_llm = os.getenv("USE_LLM","false").lower()=="true"
    return _llm_rules(prd) if use_llm else _heuristic_rules(prd)
