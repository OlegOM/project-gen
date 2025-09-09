import asyncio
import time

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
    prd_path = pathlib.Path(prd)
    prd_text = prd_path.read_text()
    
    # Create cache file path based on PRD file
    cache_file = prd_path.parent / f"{prd_path.stem}_cached_spec.json"
    
    # Try to load cached spec first
    if cache_file.exists():
        print(f"🔄 Loading cached spec from {cache_file}")
        try:
            spec = json.loads(cache_file.read_text())
            print("✅ Cached spec loaded successfully - skipping PRD processing")
        except Exception as e:
            print(f"❌ Failed to load cached spec: {e}")
            print("🔄 Falling back to full PRD processing...")
            spec = prd_to_spec(prd_text)
            spec = enrich_spec(spec, prd_text)
            # Save the generated spec for next time
            cache_file.write_text(json.dumps(spec, indent=2))
            print(f"💾 Spec cached to {cache_file}")
    else:
        print("🔄 No cached spec found - processing PRD...")
        spec = prd_to_spec(prd_text)
        spec = enrich_spec(spec, prd_text)
        # Save the generated spec for next time
        cache_file.write_text(json.dumps(spec, indent=2))
        print(f"💾 Spec cached to {cache_file}")

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

def print_time(start_time):
    seconds = round(time.time() - start_time)
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    print("--- %s seconds ---" % seconds)
    print(f'{h:d}:{m:02d}:{s:02d}')


if __name__ == "__main__":
    start_time = time.time()

    app()

    print_time(start_time)
