import typer, pathlib, json
import re
from pathlib import Path

from projectgen.agents.spec_agent import prd_to_spec
from projectgen.agents.spec_enricher import enrich_spec
from projectgen.agents.fileplan_agent import spec_to_fileplan
from projectgen.agents.filegen_agent import generate_files
from projectgen.trace.coverage import coverage as cov

app = typer.Typer(help="ProjectGen CLI v8 (requirements-aware)", no_args_is_help=True)

@app.command()
def pipeline(
    prd: str = typer.Option(..., "--prd", "-p", exists=True, file_okay=True, dir_okay=False, readable=True),
    out: str = typer.Option("./generated", "--out", "-o")
):
    """End-to-end: PRD -> Spec -> (Enrich) -> Plan -> Files (+ heal)"""
    prd_text = pathlib.Path(prd).read_text()

    spec = prd_to_spec(prd_text)
    spec = enrich_spec(spec, prd_text)

    plan = spec_to_fileplan(spec)

    safe_name = re.sub(r'[:/\\]', '_', spec["meta"]["name"])  # → 'Eva AI Agent_PulseCheck'
    proj_dir = Path(out) / safe_name
    proj_dir.mkdir(parents=True, exist_ok=True)

    (proj_dir / "docs").mkdir(parents=True, exist_ok=True)
    (proj_dir / "docs" / "PRD.md").write_text(prd_text)

    generate_files(spec, plan, str(proj_dir), prd_text=prd_text)
    typer.echo(f"✅ Pipeline complete. Project at {proj_dir}")

# @app.command()
# def dump_spec(prd: str = typer.Option(..., "--prd", "-p")):
#     """Print the enriched spec for inspection"""
#     prd_text = pathlib.Path(prd).read_text()
#     spec = enrich_spec(prd_to_spec(prd_text), prd_text)
#     typer.echo(json.dumps(spec, indent=2))
#
# @app.command()
# def coverage(project: str = typer.Option("./generated/my-app", "--project", "-P")):
#     """Compute requirement coverage for a generated project."""
#     rep = cov(project)
#     typer.echo(json.dumps(rep, indent=2))

if __name__ == "__main__":
    app()
