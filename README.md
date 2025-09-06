# ProjectGen v8 — PRD → Spec (defaults) → Enrich (entities/workflows/requirements) → Plan → Files → Traceability

## Quick start
```bash
cd projectgen_v8/projectgen
pip install -r projectgen/requirements.txt

# Example PRD
cat > prd.txt << 'EOF'
Name: Demo CRM
Entity: Customer (id, email, name)
Req: Users can list customers
On signup: create customer; send welcome email
EOF

# Run pipeline
python -m projectgen.cli pipeline --prd prd.txt --out ./generated

# Coverage report
python -m projectgen.cli coverage -P ./generated/demo-crm
```
