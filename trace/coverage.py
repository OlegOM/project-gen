from __future__ import annotations
import json, pathlib, re
from typing import Dict, Any

TEXT_EXTS={".py",".ts",".tsx",".js",".jsx",".html",".md",".yml",".yaml",".ini",".txt",".json"}

def _scan(root: pathlib.Path):
    hits={}
    for p in root.rglob("*"):
        if not p.is_file() or p.suffix not in TEXT_EXTS: continue
        s=p.read_text(errors="ignore")
        for m in re.finditer(r"REQ:\s*([A-Z]-\d{4}(?:\s*,\s*[A-Z]-\d{4})*)", s):
            for rid in [i.strip() for i in m.group(1).split(",")]:
                hits.setdefault(rid,set()).add(str(p.relative_to(root)))
    return {k:sorted(v) for k,v in hits.items()}

def coverage(project_root: str) -> Dict[str, Any]:
    root=pathlib.Path(project_root)
    spec_path = root / "docs" / "spec.json"
    spec = json.loads(spec_path.read_text()) if spec_path.exists() else {}
    requirements = spec.get("requirements", [])
    tags = _scan(root)
    report=[]
    for r in requirements:
        rid=r.get("id")
        files=tags.get(rid,[])
        report.append({"id":rid,"text":r.get("text",""),"priority":r.get("priority","P2"),"component":r.get("component","any"),"files":files,"covered":bool(files)})
    covered=sum(1 for e in report if e["covered"])
    return {"summary":{"total":len(report),"covered":covered,"coverage_pct":(100.0*covered/max(1,len(report)))},"requirements":report}
