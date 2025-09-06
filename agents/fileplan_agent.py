from __future__ import annotations
from typing import Dict, Any, List

def spec_to_fileplan(spec: Dict[str, Any]) -> Dict[str, Any]:
    files: List[Dict[str, Any]] = []
    libs = spec.get("constraints", {}).get("allowed_libs", {})
    be = spec["stacks"]["backend"]; be_fw = (be.get("framework") or "").lower(); be_lang = (be.get("lang") or "").lower()
    fe = spec["stacks"]["frontend"]; fe_fw = (fe.get("framework") or "").lower(); fe_lang = (fe.get("lang") or "").lower()

    # Backend (FastAPI default)
    if be_fw in {"fastapi","django"} or be_lang == "python":
        files += [
            {"path":"backend/app/main.py","role":"entrypoint","depends_on":[],"contracts":["GET /health returns 200 {status:'ok'}"]},
            {"path":"backend/app/models/__init__.py","role":"pkg","depends_on":[],"contracts":[]},
            {"path":"backend/app/routes/__init__.py","role":"pkg","depends_on":[],"contracts":[]},
            {"path":"tests/test_health.py","role":"test","depends_on":["backend/app/main.py"],"contracts":["GET /health == 200"]},
            {"path":"backend/requirements.txt","role":"deps","depends_on":[],"contracts":[]},
            {"path":"pytest.ini","role":"test_config","depends_on":[],"contracts":[]},
        ]
        for ent in (spec.get("entities") or []):
            ename = ent["name"]
            files += [
                {"path":f"backend/app/models/{ename.lower()}.py","role":"model","depends_on":[],"contracts":[f"Model for {ename}"]},
                {"path":f"backend/app/routes/{ename.lower()}s.py","role":"api","depends_on":[f"backend/app/models/{ename.lower()}.py"],"contracts":[f"CRUD for {ename}"]},
            ]

    # Frontend React TS default
    if fe_fw=="react" and fe_lang=="ts":
        files += [
            {"path":"frontend/index.html","role":"page","depends_on":[],"contracts":["Mounts #root"]},
            {"path":"frontend/src/main.tsx","role":"entry","depends_on":[],"contracts":["Renders app title"]},
            {"path":"frontend/tsconfig.json","role":"tsconfig","depends_on":[],"contracts":[]},
            {"path":"frontend/package.json","role":"deps","depends_on":[],"contracts":[]},
            {"path":"frontend/vite.config.ts","role":"vite","depends_on":[],"contracts":[]},
        ]
    else:
        files.append({"path":"frontend/index.html","role":"page","depends_on":[],"contracts":["Shows app title"]})

    # Infra
    files.append({"path":"infra/docker-compose.yml","role":"compose","depends_on":[],"contracts":["api, frontend, db services"]})
    return {"files": files, "libraries": libs}
