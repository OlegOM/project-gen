from __future__ import annotations
import os, re, json, traceback
from typing import List, Dict, Any

def _mk_id(n:int)->str: return f"R-{n:04d}"

TRIGGERS = [r"(?i)\s*(req|requirement|must)[:\-]\s*(.+)"]

def _heuristic_requirements(prd: str)->List[Dict[str,Any]]:
    reqs=[]; n=1
    for line in prd.splitlines():
        for pat in TRIGGERS:
            m=re.match(pat, line.strip())
            if m:
                reqs.append({"id":_mk_id(n),"text":m.group(2).strip(),"component":"any","priority":"P2","acceptance":[]}); n+=1
                break
    # default health
    reqs.append({"id":_mk_id(n),"text":"API exposes GET /health returning 200 with {status:'ok'}",
                 "component":"backend","priority":"P0","acceptance":["GET /health == 200 && body.status == 'ok'"]})
    return reqs

def _llm_extract(prd_text: str) -> List[Dict[str, Any]]:
    import openai, json as _json
    prompt=f"""Return ONLY a JSON array of requirements with fields id|text|component|priority|acceptance.
Keep each requirement atomic and testable. If any field is unknown, omit it (caller fills defaults).
No markdown or code fences.
PRD:
{prd_text}"""
    r=openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[{"role":"user","content":prompt}],
        temperature=0,
        response_format={"type":"json_object"},
    )
    raw = r["choices"][0]["message"]["content"]
    raw = raw.strip().strip("`")
    if raw.lower().startswith("json"):
        raw = raw[4:].strip()
    data=_json.loads(raw)
    out=[]; c=1
    if isinstance(data, list):
        for d in data:
            if not isinstance(d, dict) or not d.get("text"): continue
            out.append({
                "id": d.get("id", _mk_id(c)),
                "text": d["text"].strip(),
                "component": d.get("component","any"),
                "priority": d.get("priority","P2"),
                "acceptance": d.get("acceptance",[]) if isinstance(d.get("acceptance"), list) else []
            }); c+=1
    return out

def extract_requirements(prd_text: str) -> List[Dict[str,Any]]:
    use_llm=os.getenv("USE_LLM","false").lower()=="true"
    if use_llm:
        try:
            reqs = _llm_extract(prd_text)
            if not reqs: reqs=_heuristic_requirements(prd_text)
        except Exception:
            traceback.print_exc()
            reqs=_heuristic_requirements(prd_text)
    else:
        reqs=_heuristic_requirements(prd_text)

    # Deduplicate and clean
    seen=set(); out=[]
    for r in reqs:
        k=r["text"].lower()
        if k in seen: continue
        seen.add(k); out.append(r)
    for i,r in enumerate(out, start=1):
        if not re.match(r"^R-\d{4}$", r.get("id","")):
            r["id"]=_mk_id(i)
        r.setdefault("component","any")
        r.setdefault("priority","P2")
        r.setdefault("acceptance",[])
    return out
