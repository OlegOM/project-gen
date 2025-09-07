# projectgen/agents/rules_agent.py
from __future__ import annotations
import os, re, json, traceback
from typing import List, Dict, Any

def _mk_id(n:int)->str: return f"BR-{n:04d}"

_PAT_NEG = re.compile(r"(?i)\b(must|cannot|can't|should not|must not)\b.*\b(negative|less than\s*0)\b")
_PAT_ENUM = re.compile(r"(?i)\b(status|state)\b.*\b(can be|allowed|one of)\b[: ]+([A-Za-z,\s|]+)")
_PAT_EQ   = re.compile(r"(?i)^([A-Za-z_][\w\.]*)\s*=\s*(.+)$")
_PAT_CMP  = re.compile(
    r"(?i)\b([A-Za-z_][A-Za-z0-9_]*)\b[^\n]*?"  # field
    r"(?:must|should|has to|needs to|cannot|can't|must not|should not)?[^\n]*?"
    r"(at least|no less than|greater than or equal to|>=|more than|greater than|>|"
    r"less than or equal to|<=|at most|no more than|not exceed|cannot exceed|"
    r"must not exceed|should not exceed|less than|<)\s*(\d+(?:\.\d+)?)"
)
_PAT_UNIQUE = re.compile(
    r"(?i)\b([A-Za-z_][A-Za-z0-9_]*)\b[^\n]*?"  # field
    r"(?:must|should|has to|needs to)?[^\n]*?\bunique\b"
)
_PAT_NOT_EMPTY = re.compile(
    r"(?i)\b([A-Za-z_][A-Za-z0-9_]*)\b[^\n]*?"  # field
    r"(must|should|has to|needs to|cannot|can't|must not|should not)?[^\n]*?"
    r"(not be empty|not be blank|be required|is required|required)"
)

_CMP_MAP = {
    "at least": ">=",
    "no less than": ">=",
    "greater than or equal to": ">=",
    ">=": ">=",
    "more than": ">",
    "greater than": ">",
    ">": ">",
    "less than": "<",
    "<": "<",
    "less than or equal to": "<=",
    "<=": "<=",
    "at most": "<=",
    "no more than": "<=",
    "not exceed": "<=",
    "cannot exceed": "<=",
    "must not exceed": "<=",
    "should not exceed": "<=",
}

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

        m = _PAT_CMP.search(l)
        if m:
            field, comp, val = m.group(1), m.group(2), m.group(3)
            op = _CMP_MAP.get(comp.lower(), ">=")
            target = f"{field.capitalize()}.{field.lower()}"
            msg = (
                f"{field} {comp.lower()} {val}"
                if comp.lower().startswith(("cannot", "must not", "should not", "not"))
                else f"{field} must be {comp.lower()} {val}"
            )
            out.append({
                "id": _mk_id(n),
                "target": target,
                "kind": "constraint",
                "expr": f"{field.lower()} {op} {val}",
                "message": msg,
            }); n += 1
            continue

        m = _PAT_UNIQUE.search(l)
        if m:
            field = m.group(1)
            target = f"{field.capitalize()}.{field.lower()}"
            out.append({
                "id": _mk_id(n),
                "target": target,
                "kind": "constraint",
                "expr": f"unique({field.lower()})",
                "message": f"{field} must be unique",
            }); n += 1
            continue

        m = _PAT_NOT_EMPTY.search(l)
        if m:
            field = m.group(1)
            target = f"{field.capitalize()}.{field.lower()}"
            out.append({
                "id": _mk_id(n),
                "target": target,
                "kind": "constraint",
                "expr": f"{field.lower()} not in (None, '')",
                "message": f"{field} must not be empty",
            }); n += 1
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
Return ONLY a JSON array, no markdown.
PRD:
{prd}"""
    r = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        response_format={"type": "json_object"},
    )
    raw = r["choices"][0]["message"]["content"]
    raw = raw.strip().strip("`")
    if raw.lower().startswith("json"):
        raw = raw[4:].strip()
    try:
        arr = _json.loads(raw)
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
        traceback.print_exc()
        return _heuristic_rules(prd)

def extract_rules(prd: str) -> List[Dict[str,Any]]:
    use_llm = os.getenv("USE_LLM","false").lower()=="true"
    return _llm_rules(prd) if use_llm else _heuristic_rules(prd)
