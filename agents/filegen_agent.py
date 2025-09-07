from __future__ import annotations
import pathlib, json, re, os, traceback
from typing import Dict, Any, List, Tuple
from projectgen.executor.diff_healer import run_and_heal
from pydantic import BaseModel, field_validator, ValidationInfo

_TEXT_EXTS = {".py",".txt",".ini",".cfg",".env",".yml",".yaml",".md",".html",".tsx",".ts",".js",".json"}

def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", name.strip().lower())

def _rules_for_entity(spec, entity_name: str):
    rules = []
    for r in spec.get("business_rules", []):
        if _token_overlap(entity_name, r.get("target", "")) >= 0.3:
            rules.append(r)
    return rules

def _rules_for_workflow(spec, wf_name: str):
    rules = []
    for r in spec.get("business_rules", []):
        if _token_overlap(wf_name, r.get("target", "")) >= 0.3:
            rules.append(r)
    return rules


def _token_overlap(name: str, text: str) -> float:
    name_tokens = set(re.findall(r"\w+", name.lower()))
    if not name_tokens:
        return 0.0
    text_tokens = set(re.findall(r"\w+", text.lower()))
    return len(name_tokens & text_tokens) / len(name_tokens)

def _requirements_for_entity(spec: Dict[str, Any], entity_name: str) -> List[Dict[str, Any]]:
    out = []
    for r in spec.get("requirements", []):
        if _token_overlap(entity_name, r.get("text", "")) >= 0.3:
            out.append(r)
    return out


def _requirements_for_workflow(spec: Dict[str, Any], wf_name: str) -> List[Dict[str, Any]]:
    out = []
    for r in spec.get("requirements", []):
        if _token_overlap(wf_name, r.get("text", "")) >= 0.3:
            out.append(r)
    return out

def _missing_stack_todos(stacks: Dict[str, Any]) -> List[str]:
    todos: List[str] = []
    backend = stacks.get("backend", {})
    if backend.get("framework", "unspecified") == "unspecified":
        todos.append("# TODO: specify backend framework in spec")
    if backend.get("lang", "unspecified") == "unspecified":
        todos.append("# TODO: specify backend language in spec")
    return todos

def _strip_code_fences(code: str) -> str:
    code = code.strip()
    if code.startswith("```"):
        code = re.sub(r"^```[a-zA-Z0-9_]*\n", "", code)
    if code.endswith("```"):
        code = re.sub(r"\n```$", "", code)
    return code

def _llm_workflow_code(flow: Dict[str, Any], reqs, rules, stacks) -> str:
    import openai
    prompt = f"""You generate Python functions implementing application workflows.
Workflow: {json.dumps(flow, indent=2)}
Relevant requirements: {json.dumps(reqs, indent=2)}
Business rules: {json.dumps(rules, indent=2)}
Tech stacks: {json.dumps(stacks, indent=2)}
Use the stacks when writing code. If information is missing, add comments and TODO notes with recommendations.
Return only Python code without explanations."""
    r = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    return _strip_code_fences(r["choices"][0]["message"]["content"])

def _llm_route_code(ent: Dict[str, Any], reqs, rules, stacks) -> str:
    import openai
    prompt = f"""Implement a FastAPI router for the entity {ent['name']}.
Requirements: {json.dumps(reqs, indent=2)}
Business rules: {json.dumps(rules, indent=2)}
Tech stacks: {json.dumps(stacks, indent=2)}
Use comments and TODOs if stack information is insufficient.
Return only Python code."""
    r = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    return _strip_code_fences(r["choices"][0]["message"]["content"])

def _render_schema(ent, rules):
    # Build BaseModel with validators for simple 'field >= 0', 'field in [...]'
    name = ent["name"]
    fields = ent.get("fields", [])
    # naive types
    to_py = {"uuid":"str","string":"str","int":"int","integer":"int","bool":"bool","boolean":"bool"}
    lines = [ "from pydantic import BaseModel, field_validator, ValidationInfo", "", f"class Create{name}Request(BaseModel):" ]
    if not fields:
        lines.append("    id: str | None = None")
    else:
        for f in fields:
            t = to_py.get(str(f.get("type","string")).lower(), "str")
            opt = " | None = None" if not f.get("pk") else ""
            lines.append(f"    {f['name']}: {t}{opt}")

    # validators
    for r in rules:
        expr = r.get("expr","")
        msg  = (r.get("message") or "validation failed").replace('"', '\\"')
        m_ge0 = re.match(r"^([a-zA-Z_]\w*)\s*>=\s*0$", expr.replace(" ", ""))
        m_in  = re.match(r"^([a-zA-Z_]\w*)\s*in\s*\[(.+)\]$", expr)
        if m_ge0:
            field = m_ge0.group(1)
            lines += [
                "",
                f"    @field_validator('{field}')",
                f"    def validate_{field}_non_negative(cls, v, info: ValidationInfo):",
                f"        if v is not None and v < 0:",
                f"            raise ValueError(\"{msg}\")",
                f"        return v",
            ]
        elif m_in:
            field = m_in.group(1)
            options = m_in.group(2)
            lines += [
                "",
                f"    @field_validator('{field}')",
                f"    def validate_{field}_enum(cls, v, info: ValidationInfo):",
                f"        allowed = [{options}]",
                f"        if v is not None and v not in allowed:",
                f"            raise ValueError(\"{msg}\")",
                f"        return v",
            ]

    return "\n".join(lines) + "\n"

def _render_workflow(flow: Dict[str, Any], spec: Dict[str, Any]) -> str:
    name = _slug(flow.get("name", "workflow"))
    use_llm = os.getenv("USE_LLM", "false").lower() == "true"
    reqs = _requirements_for_workflow(spec, flow.get("name", ""))
    rules = _rules_for_workflow(spec, flow.get("name", ""))
    stacks = spec.get("stacks", {})
    todos = _missing_stack_todos(stacks)
    if use_llm:
        try:
            code = _llm_workflow_code(flow, reqs, rules, stacks)
            if todos:
                code = "\n".join(todos) + "\n" + code
            return code if code.endswith("\n") else code+"\n"
        except Exception:
            traceback.print_exc()
    trigger = flow.get("trigger", "")
    actions = flow.get("actions", [])
    lines = todos + [f"def {name}(context: dict) -> None:", f"    \"\"\"Trigger: {trigger}\"\"\""]
    if actions:
        lines.append("    # Actions:")
        for act in actions:
            lines.append(f"    # - {act}")
    lines.append("    pass")
    return "\n".join(lines) + "\n"

def _write(p: pathlib.Path, content: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.suffix in _TEXT_EXTS:
        content = content.replace("\r\n", "\n").replace("\\r\\n", "\n").replace("\\n", "\n")
    p.write_text(content)

def _req_header(ids: List[str]) -> str:
    return ("# REQ: " + ", ".join(sorted(set(ids))) + "\n") if ids else ""

def _match_req_ids(spec: Dict[str, Any], hint: str) -> List[str]:
    ids = []
    hint_l = hint.lower()
    for r in spec.get("requirements", []):
        txt = (r.get("text") or "").lower()
        if any(w and w in txt for w in re.split(r"[^a-z0-9]+", hint_l) if len(w) > 2):
            ids.append(r["id"])
    return ids[:5]

def _fastapi_main(name: str) -> str:
    return f"""from fastapi import FastAPI
from .routes import *
app = FastAPI(title="{name} API")

@app.get('/health')
def health():
    return {{"status":"ok"}}
"""

def _pytest_cfg() -> str:
    return "[pytest]\naddopts = -q\n"

def _pytest_test() -> str:
    return """from fastapi.testclient import TestClient
from backend.app.main import app

def test_health():
    c = TestClient(app)
    r = c.get('/health')
    assert r.status_code == 200
    assert r.json().get('status') == 'ok'
"""

def _py_requirements() -> str:
    return "fastapi==0.111.0\nuvicorn[standard]==0.30.1\npydantic==2.7.4\nsqlalchemy==2.0.31\n"

_SQLA_TYPES = {"uuid":"String","string":"String","int":"Integer","integer":"Integer","bool":"Boolean","boolean":"Boolean"}

def _render_model(ent: Dict[str, Any]) -> str:
    name = ent["name"]
    fields = ent.get("fields", [])
    cols = []
    for f in fields:
        col_type = _SQLA_TYPES.get(str(f.get("type","string")).lower(), "String")
        flags = []
        if f.get("pk"): flags.append("primary_key=True")
        if f.get("unique"): flags.append("unique=True")
        flags_str = (", " + ", ".join(flags)) if flags else ""
        cols.append(f"    {f['name']} = Column({col_type}{flags_str})")
    body = "\n".join(cols) if cols else "    id = Column(String, primary_key=True)"
    return f"""from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, String, Integer, Boolean

Base = declarative_base()

class {name}(Base):
    __tablename__ = "{name.lower()}s"
{body}
"""

def _render_route(ent: Dict[str, Any], spec: Dict[str, Any]) -> str:
    use_llm = os.getenv("USE_LLM", "false").lower() == "true"
    reqs = _requirements_for_entity(spec, ent["name"])
    rules = _rules_for_entity(spec, ent["name"])
    stacks = spec.get("stacks", {})
    todos = _missing_stack_todos(stacks)
    if use_llm:
        try:
            code = _llm_route_code(ent, reqs, rules, stacks)
            if todos:
                code = "\n".join(todos) + "\n" + code
            return code if code.endswith("\n") else code+"\n"
        except Exception:
            traceback.print_exc()
    ename = ent["name"]
    lname = ename.lower()
    lines = todos + [
        "from fastapi import APIRouter",
        "from typing import List, Dict",
        f"from .schemas import Create{ename}Request",
        "",
        f"router = APIRouter(prefix='/{lname}s', tags=['{ename}'])",
        "_DB: List[Dict] = []",
        "",
        f"@router.get('', response_model=List[Dict])",
        f"def list_{lname}s():",
        "    return _DB",
        "",
        f"@router.post('', response_model=Dict)",
        f"def create_{lname}(item: Create{ename}Request):",
        "    d = item.model_dump()",
        "    _DB.append(d)",
        "    return d",
    ]
    return "\n".join(lines) + "\n"

def _frontend_index_html() -> str:
    return """<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>App</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
"""

def _frontend_main_tsx(app_name: str) -> str:
    return f"""import React from 'react'
import ReactDOM from 'react-dom/client'

function App() {{
  return (<main style={{ fontFamily: 'sans-serif' }}><h1>Welcome to {app_name} 🚀</h1></main>);
}}

ReactDOM.createRoot(document.getElementById('root')!).render(<App />)
"""

def _frontend_tsconfig() -> str:
    return json.dumps({"compilerOptions":{"target":"ES2020","jsx":"react-jsx","module":"ESNext","moduleResolution":"bundler","strict":True,"esModuleInterop":True,"skipLibCheck":True},"include":["src"]}, indent=2)

def _frontend_vite_config() -> str:
    return "import { defineConfig } from 'vite'\nimport react from '@vitejs/plugin-react'\nexport default defineConfig({ plugins: [react()], server: { host: true } })"

def _frontend_package_json() -> str:
    return json.dumps({"name":"frontend","private":True,"type":"module","scripts":{"dev":"vite","build":"vite build","preview":"vite preview --host"},"dependencies":{"react":"^18.2.0","react-dom":"^18.2.0"},"devDependencies":{"@vitejs/plugin-react":"^4.2.0","typescript":"^5.5.4","vite":"^5.3.0"}}, indent=2)

def _compose(name: str) -> str:
    return f"""version: "3.9"
services:
  api:
    image: python:3.11-slim
    working_dir: /app
    volumes: ["./:/app"]
    command: sh -lc "pip install -r backend/requirements.txt && uvicorn backend.app.main:app --host 0.0.0.0 --port 8000"
    ports: ["8000:8000"]
  db:
    image: postgres:15
    environment:
      - POSTGRES_DB={name}_db
      - POSTGRES_USER=admin
      - POSTGRES_PASSWORD=secret
    ports: ["5432:5432"]
  frontend:
    image: node:20
    working_dir: /app/frontend
    volumes: ["./:/app"]
    command: sh -lc "npm ci && npm run dev -- --host"
    ports: ["5173:5173"]
"""

_HTTP_RE = re.compile(r"(?i)\b(GET|POST|PUT|DELETE|PATCH)\s+(/[\w\-/{}:]+)")

def _acceptance_to_tests(req: Dict[str, Any]):
    out = []
    rid = req.get("id","R-0000").lower().replace("-","_")
    for i, acc in enumerate(req.get("acceptance",[]) or [], start=1):
        m = _HTTP_RE.search(acc or "")
        if not m: continue
        method, path = m.group(1).upper(), m.group(2)
        if method != "GET": continue
        code = f"""# REQ: {req.get('id','R-0000')}
from fastapi.testclient import TestClient
from backend.app.main import app

def test_{rid}_{i}():
    c = TestClient(app)
    r = c.get("{path}")
    assert r.status_code == 200
"""
        out.append((f"tests/requirements/test_{rid}_{i}.py", code))
    return out

def _doc_workflows(flows: List[Dict[str, Any]]) -> str:
    lines = ["# Workflows"]
    for f in flows or []:
        lines.append(f"## {f.get('name','')}")
        if f.get("trigger"):
            lines.append(f"*Trigger:* {f['trigger']}")
        for act in f.get("actions", []) or []:
            lines.append(f"- {act}")
    return "\n".join(lines) + "\n"

def _doc_requirements(reqs: List[Dict[str, Any]]) -> str:
    lines = ["# Requirements"]
    for r in reqs or []:
        lines.append(f"## {r.get('id','')}")
        lines.append(r.get("text", ""))
        if r.get("acceptance"):
            lines.append("### Acceptance Criteria")
            for a in r["acceptance"]:
                lines.append(f"- {a}")
    return "\n".join(lines) + "\n"

def _doc_rules(rules: List[Dict[str, Any]]) -> str:
    lines = ["# Business Rules"]
    for r in rules or []:
        lines.append(f"- {r.get('id','')}: {r.get('target','')} {r.get('expr','')}")
    return "\n".join(lines) + "\n"

def generate_files(spec: Dict[str, Any], plan: Dict[str, Any], out_dir: str, prd_text: str | None = None) -> Dict[str, str]:
    name = spec["meta"]["name"]
    out = pathlib.Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    files: Dict[str, str] = {}
    schema_blocks: List[str] = []

    _write(out / "backend" / "app" / "__init__.py", "")
    _write(out / "backend" / "app" / "routes" / "__init__.py", "from . import *\n")
    _write(out / "backend" / "app" / "models" / "__init__.py", "")
    _write(out / "backend" / "app" / "workflows" / "__init__.py", "")

    for item in plan["files"]:
        path = out / item["path"]; code = "// TODO"

        if item["path"].endswith("backend/app/main.py"):
            code = _req_header(_match_req_ids(spec, "health")) + _fastapi_main(name)
        elif item["path"].endswith("backend/requirements.txt"):
            code = _py_requirements()
        elif item["path"].endswith("pytest.ini"):
            code = _pytest_cfg()
        elif item["path"].endswith("tests/test_health.py"):
            code = _pytest_test()

        m_ent = re.match(r"backend/app/models/([a-z0-9_]+)\.py$", item["path"])
        if m_ent:
            en = next((e for e in spec.get("entities", []) if e["name"].lower() == m_ent.group(1)), None)
            if en:
                hdr = _req_header(_match_req_ids(spec, en["name"]))
                code = hdr + _render_model(en)

        m_route = re.match(r"backend/app/routes/([a-z0-9_]+)\.py$", item["path"])
        if m_route:
            base = m_route.group(1).rstrip("s")
            en = next((e for e in spec.get("entities", []) if e["name"].lower() == base), None)
            if en:
                hdr = _req_header(_match_req_ids(spec, en["name"]))
                code = hdr + _render_route(en, spec)

                rules = _rules_for_entity(spec, en["name"])
                schema_blocks.append(hdr + _render_schema(en, rules))

        m_wf = re.match(r"backend/app/workflows/([a-z0-9_]+)\.py$", item["path"])
        if m_wf:
            wf = next((w for w in spec.get("workflows", []) if _slug(w.get("name", "")) == m_wf.group(1)), None)
            if wf:
                hdr = _req_header(_match_req_ids(spec, wf.get("name", "")))
                code = hdr + _render_workflow(wf, spec)


        if item["path"].endswith("frontend/index.html"): code = _frontend_index_html()
        elif item["path"].endswith("frontend/src/main.tsx"): code = _frontend_main_tsx(name)
        elif item["path"].endswith("frontend/tsconfig.json"): code = _frontend_tsconfig()
        elif item["path"].endswith("frontend/vite.config.ts"): code = _frontend_vite_config()
        elif item["path"].endswith("frontend/package.json"): code = _frontend_package_json()

        if item["path"].endswith("infra/docker-compose.yml"): code = _compose(name)

        _write(path, code); files[item["path"]] = code

    if schema_blocks:
        schema_path = out / "backend" / "app" / "routes" / "schemas.py"
        schema_code = "\n".join(schema_blocks)
        _write(schema_path, schema_code)
        files[str(schema_path.relative_to(out))] = schema_code

    (out / "docs").mkdir(parents=True, exist_ok=True)
    if prd_text:
        _write(out / "docs" / "PRD.md", prd_text)
    _write(out / "docs" / "spec.json", json.dumps(spec, indent=2))
    _write(out / "docs" / "workflows.md", _doc_workflows(spec.get("workflows", [])))
    _write(out / "docs" / "requirements.md", _doc_requirements(spec.get("requirements", [])))
    _write(out / "docs" / "business_rules.md", _doc_rules(spec.get("business_rules", [])))

    for req in spec.get("requirements", []):
        for path, code in _acceptance_to_tests(req):
            _write(out / path, code)
            files[path] = code
    run_and_heal(str(out))
    return files
