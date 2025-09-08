from __future__ import annotations
import pathlib, json, re, os, traceback
from typing import Dict, Any, List, Tuple
from projectgen.executor.diff_healer import run_and_heal
from pydantic import BaseModel, field_validator, ValidationInfo
import re
from nltk.stem import LancasterStemmer

stemmer = LancasterStemmer()

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
        if _token_overlap(wf_name, f'{r.get("target", "")} {r.get("message", "")}') >= 0.3:
            rules.append(r)
    return rules


def _token_overlap_old(name: str, text: str) -> float:
    name_tokens = set(re.findall(r"\w+", name.lower()))
    if not name_tokens:
        return 0.0
    text_tokens = set(re.findall(r"\w+", text.lower()))
    intersect = name_tokens & text_tokens
    return len(intersect) / len(name_tokens)

def _token_overlap(name: str, text: str) -> float:
    name_tokens = re.findall(r"\w+", name.lower())
    if not name_tokens:
        return 0.0
    text_tokens = re.findall(r"\w+", text.lower())

    # normalize each token to its root form
    name_roots = {stemmer.stem(tok) for tok in name_tokens}
    text_roots = {stemmer.stem(tok) for tok in text_tokens}

    intersect = name_roots & text_roots
    return len(intersect) / len(name_roots)

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

def _llm_generate_enhanced_workflow_prompt(flow: Dict[str, Any], reqs, rules, stacks, entities: List[Dict[str, Any]], prd_text: str | None = None) -> str:
    """Step 1: Generate sophisticated prompt with enhanced workflows, requirements and business rules"""
    import openai

    step1_prompt = f"""
You are an expert software architect and business analyst. Your task is to analyze and enhance the given workflow, requirements, and business rules to create comprehensive specifications for Python code generation.

Given Input:
- Workflow: {json.dumps(flow, indent=2)}
- Requirements: {json.dumps(reqs, indent=2)}
- Business Rules: {json.dumps(rules, indent=2)}
- Tech Stack: {json.dumps(stacks, indent=2)}
- Entities: {json.dumps(entities, indent=2)}
"""
    
    if prd_text:
        step1_prompt += f"\nOriginal PRD Document:\n{prd_text}\n"
    
    step1_prompt += """
Your task is to:

1. ENHANCE THE WORKFLOW:
   - Expand the workflow with detailed steps, error handling, and edge cases
   - Add specific implementation details based on the tech stack and entities
   - Include entity CRUD operations, relationships, and state management
   - Define entity validation, security considerations, and performance optimizations
   - Define clear input/output specifications with entity schemas
   - Add entity-specific logging, monitoring, and observability requirements
   - Include database transactions, entity lifecycle management, and data consistency

2. ENHANCE THE REQUIREMENTS:
   - Break down high-level requirements into entity-specific technical requirements
   - Add acceptance criteria with entity CRUD test scenarios
   - Include entity-specific non-functional requirements (performance, security, scalability)
   - Define entity API contracts, data schemas, and relationship mappings
   - Add entity validation, error handling, and edge case requirements
   - Include entity migration, backup, and recovery requirements

3. ENHANCE THE BUSINESS RULES:
   - Expand business rules with entity-specific validation logic
   - Add entity constraint definitions and field validation rules
   - Include entity-based business logic for different user roles and permissions
   - Define entity state transitions and lifecycle workflow rules
   - Add entity audit trails, versioning, and compliance requirements
   - Include entity relationship constraints and referential integrity rules

4. CREATE DETAILED IMPLEMENTATION INSTRUCTIONS:
   - Specify exact Python modules, classes, and functions for entity management
   - Define entity database models, repositories, and service layers
   - Include entity-specific API endpoints and business logic services
   - Add entity dependency injection, configuration, and environment setup
   - Include entity migration scripts and database schema management
   - Add comprehensive entity error handling and logging strategies
   - Specify entity-specific testing approaches and test cases

Return a JSON object with the following structure:
{
  "enhanced_workflow": {
    "name": "string",
    "description": "detailed description",
    "steps": ["step1", "step2", ...],
    "error_handling": ["error scenario 1", ...],
    "inputs": {"param1": "type and description"},
    "outputs": {"result1": "type and description"},
    "dependencies": ["service1", "service2"],
    "entities_involved": ["Entity1", "Entity2"],
    "entity_operations": ["create", "read", "update", "delete"],
    "entity_relationships": ["Entity1 -> Entity2"],
    "performance_requirements": "string",
    "security_considerations": ["consideration1", ...]
  },
  "enhanced_requirements": [
    {
      "id": "REQ-001",
      "description": "detailed requirement",
      "acceptance_criteria": ["criteria1", "criteria2"],
      "technical_details": "implementation specifics",
      "test_scenarios": ["scenario1", "scenario2"]
    }
  ],
  "enhanced_business_rules": [
    {
      "id": "BR-001",
      "rule": "business rule description",
      "validation_logic": "specific validation code",
      "error_messages": ["error1", "error2"],
      "affected_entities": ["entity1", "entity2"]
    }
  ],
  "implementation_instructions": {
    "modules_to_create": ["module1.py", "module2.py"],
    "classes_and_functions": {
      "ClassName": ["method1", "method2"]
    },
    "database_models": ["Model1", "Model2"],
    "api_endpoints": [
      {"method": "POST", "path": "/api/endpoint", "description": "purpose"}
    ],
    "dependencies": ["fastapi", "sqlalchemy"],
    "configuration_needed": ["config1", "config2"],
    "testing_strategy": "testing approach description"
  }
}

Focus on creating production-ready, comprehensive specifications that will result in high-quality, maintainable Python code.
"""
    
    r = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": step1_prompt}],
        temperature=0,
        response_format={"type": "json_object"},
    )
    return r["choices"][0]["message"]["content"]

def _llm_workflow_code(flow: Dict[str, Any], reqs, rules, stacks, prd_text: str | None = None, entities: List[Dict[str, Any]] = None) -> str:
    """Step 2: Generate Python code using enhanced specifications"""
    import openai
    
    try:
        # Step 1: Generate enhanced prompt
        entities = entities or []
        enhanced_specs_json = _llm_generate_enhanced_workflow_prompt(flow, reqs, rules, stacks, entities, prd_text)
        enhanced_specs = json.loads(enhanced_specs_json)
        
        # Step 2: Generate Python code using enhanced specifications
        step2_prompt = f"""
You are an expert Python developer. Generate production-ready Python code based on the following enhanced specifications:

ENHANCED SPECIFICATIONS:
{json.dumps(enhanced_specs, indent=2)}

TECH STACK:
{json.dumps(stacks, indent=2)}
"""
        
        if prd_text:
            step2_prompt += f"\nORIGINAL PRD (for context):\n{prd_text[:10000]}...\n"
        
        step2_prompt += """
Generate complete, production-ready Python code that implements the enhanced workflow specifications. Include:

1. Complete function implementations with proper error handling
2. Type hints and comprehensive docstrings
3. Input validation and sanitization
4. Proper logging and monitoring
5. Database operations using the specified ORM
6. API endpoint implementations if applicable
7. Unit tests for key functionality
8. Configuration and dependency management
9. Security best practices
10. Performance optimizations

The code should be:
- Production-ready and maintainable
- Well-documented with clear comments
- Following Python best practices and PEP 8
- Include proper exception handling
- Have comprehensive error messages
- Be testable and modular

Return ONLY the Python code without markdown formatting or explanations.
"""
        
        r = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": step2_prompt}],
            temperature=0,
        )
        return _strip_code_fences(r["choices"][0]["message"]["content"])
        
    except Exception as e:
        traceback.print_exc()
        # Fallback to original simple approach
        prompt = (
            "You generate Python functions implementing application workflows.\n"
            f"Workflow: {json.dumps(flow, indent=2)}\n"
            f"Relevant requirements: {json.dumps(reqs, indent=2)}\n"
            f"Business rules: {json.dumps(rules, indent=2)}\n"
            f"Tech stacks: {json.dumps(stacks, indent=2)}\n"
        )
        if prd_text:
            prompt += f"Original PRD:\n{prd_text}\n"
        prompt += (
            "Use the stacks when writing code. If information is missing, add comments and TODO notes with recommendations.\n"
            "Return only Python code without explanations."
        )
        r = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        return _strip_code_fences(r["choices"][0]["message"]["content"])

def _llm_generate_enhanced_route_prompt(ent: Dict[str, Any], reqs, rules, stacks, all_entities: List[Dict[str, Any]], prd_text: str | None = None) -> str:
    """Step 1: Generate sophisticated prompt with enhanced entity specifications"""
    import openai
    
    step1_prompt = f"""
You are an expert API architect and backend developer. Your task is to analyze and enhance the given entity, requirements, and business rules to create comprehensive specifications for FastAPI route generation.

Given Input:
- Entity: {json.dumps(ent, indent=2)}
- All Entities: {json.dumps(all_entities, indent=2)}
- Requirements: {json.dumps(reqs, indent=2)}
- Business Rules: {json.dumps(rules, indent=2)}
- Tech Stack: {json.dumps(stacks, indent=2)}
"""
    
    if prd_text:
        step1_prompt += f"\nOriginal PRD Document:\n{prd_text}\n"
    
    step1_prompt += f"""
Your task is to:

1. ENHANCE THE ENTITY SPECIFICATION:
   - Expand entity fields with proper types, constraints, and relationships
   - Add validation rules, indexes, and database constraints
   - Define entity lifecycle states and transitions
   - Include audit fields (created_at, updated_at, created_by, etc.)
   - Add soft delete and versioning if applicable
   - Define entity permissions and access control

2. ENHANCE THE API REQUIREMENTS:
   - Create comprehensive CRUD operations with proper HTTP methods
   - Add filtering, sorting, pagination, and search capabilities
   - Define request/response schemas with validation
   - Include bulk operations and batch processing
   - Add file upload/download endpoints if needed
   - Define API versioning and deprecation strategy

3. ENHANCE THE BUSINESS RULES:
   - Convert business rules into specific validation logic
   - Add authorization rules for different user roles
   - Define data consistency and integrity constraints
   - Include business workflow validations
   - Add rate limiting and security rules
   - Define audit and compliance requirements

4. CREATE DETAILED API SPECIFICATIONS:
   - Define all REST endpoints with proper HTTP methods
   - Specify request/response schemas and status codes
   - Add comprehensive error handling and error codes
   - Include authentication and authorization requirements
   - Define caching strategies and performance optimizations
   - Add monitoring, logging, and observability requirements

Return a JSON object with the following structure:
{{
  "enhanced_entity": {{
    "name": "{ent.get('name', 'Entity')}",
    "description": "detailed entity description",
    "fields": [
      {{
        "name": "field_name",
        "type": "field_type",
        "constraints": ["constraint1", "constraint2"],
        "validation_rules": ["rule1", "rule2"],
        "description": "field purpose"
      }}
    ],
    "relationships": [
      {{
        "type": "one_to_many",
        "target_entity": "RelatedEntity",
        "description": "relationship purpose"
      }}
    ],
    "lifecycle_states": ["draft", "active", "archived"],
    "permissions": {{
      "create": ["admin", "user"],
      "read": ["admin", "user", "guest"],
      "update": ["admin", "owner"],
      "delete": ["admin"]
    }}
  }},
  "enhanced_requirements": [
    {{
      "id": "API-001",
      "description": "detailed API requirement",
      "endpoints": [
        {{
          "method": "GET",
          "path": "/api/v1/entities",
          "description": "List entities with pagination",
          "parameters": ["page", "limit", "filter"],
          "response_schema": "EntityListResponse"
        }}
      ],
      "acceptance_criteria": ["criteria1", "criteria2"]
    }}
  ],
  "enhanced_business_rules": [
    {{
      "id": "BR-001",
      "rule": "business rule description",
      "validation_logic": "specific validation implementation",
      "error_codes": ["ERR_001", "ERR_002"],
      "affected_endpoints": ["/api/v1/entities"],
      "user_roles": ["admin", "user"]
    }}
  ],
  "api_specifications": {{
    "base_path": "/api/v1/{ent.get('name', 'entities').lower()}",
    "endpoints": [
      {{
        "method": "GET",
        "path": "/",
        "description": "List entities",
        "parameters": ["page", "limit", "sort", "filter"],
        "response_codes": [200, 400, 401, 403, 500],
        "caching": "5 minutes",
        "rate_limit": "100 requests/minute"
      }}
    ],
    "schemas": [
      {{
        "name": "CreateEntityRequest",
        "fields": ["field1", "field2"],
        "validation_rules": ["rule1", "rule2"]
      }}
    ],
    "error_handling": [
      {{
        "code": "ERR_001",
        "message": "Validation failed",
        "http_status": 400
      }}
    ],
    "security": {{
      "authentication": "JWT Bearer",
      "authorization": "Role-based",
      "input_validation": "Pydantic models",
      "rate_limiting": "Redis-based"
    }},
    "monitoring": {{
      "logging": "Structured JSON logs",
      "metrics": "Prometheus metrics",
      "tracing": "OpenTelemetry"
    }}
  }}
}}

Focus on creating production-ready, comprehensive API specifications that will result in high-quality, maintainable FastAPI routes.
"""
    
    r = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": step1_prompt}],
        temperature=0,
        response_format={"type": "json_object"},
    )
    return r["choices"][0]["message"]["content"]

def _llm_generate_enhanced_service_prompt(ent: Dict[str, Any], reqs, rules, stacks, all_entities: List[Dict[str, Any]], prd_text: str | None = None) -> str:
    """Step 1: Generate enhanced service specifications"""
    import openai
    
    step1_prompt = f"""
You are an expert software architect. Generate comprehensive service layer specifications for the entity "{ent['name']}" based on the following information:

ENTITY DETAILS:
{json.dumps(ent, indent=2)}

REQUIREMENTS:
{json.dumps(reqs, indent=2)}

BUSINESS RULES:
{json.dumps(rules, indent=2)}

TECH STACK:
{json.dumps(stacks, indent=2)}

ALL ENTITIES (for relationships):
{json.dumps(all_entities, indent=2)}
"""
    
    if prd_text:
        step1_prompt += f"\nORIGINAL PRD (for context):\n{prd_text[:10000]}...\n"
    
    step1_prompt += """
Generate detailed service layer specifications in JSON format that include:

{{
  "service_name": "EntityService",
  "business_logic": [
    {{
      "method": "create_entity",
      "description": "Create new entity with validation",
      "validation_rules": ["rule1", "rule2"],
      "business_constraints": ["constraint1", "constraint2"],
      "side_effects": ["effect1", "effect2"]
    }}
  ],
  "data_operations": [
    {{
      "operation": "create",
      "repository_method": "create",
      "pre_processing": ["validation", "transformation"],
      "post_processing": ["logging", "notifications"]
    }}
  ],
  "validation_logic": [
    {{
      "field": "field_name",
      "rules": ["required", "min_length:3"],
      "custom_validation": "business rule description"
    }}
  ],
  "error_handling": [
    {{
      "error_type": "ValidationError",
      "http_status": 400,
      "message": "Validation failed",
      "recovery_action": "return detailed error"
    }}
  ],
  "integrations": [
    {{
      "service": "external_service",
      "purpose": "data enrichment",
      "error_handling": "graceful degradation"
    }}
  ],
  "caching_strategy": {{
    "cache_reads": true,
    "cache_duration": "300s",
    "invalidation_triggers": ["create", "update", "delete"]
  }},
  "monitoring": {{
    "metrics": ["operation_count", "error_rate", "response_time"],
    "logging": ["info", "error", "debug"],
    "alerts": ["high_error_rate", "slow_response"]
  }},
  "security": {{
    "authorization": "role-based",
    "input_sanitization": true,
    "audit_logging": true
  }}
}}

Focus on creating comprehensive service specifications that will result in high-quality, maintainable business logic layer.
"""
    
    r = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": step1_prompt}],
        temperature=0,
        response_format={"type": "json_object"},
    )
    return r["choices"][0]["message"]["content"]

def _llm_service_code(ent: Dict[str, Any], reqs, rules, stacks, prd_text: str | None = None, all_entities: List[Dict[str, Any]] = None) -> str:
    """Step 2: Generate service code using enhanced specifications"""
    import openai
    
    try:
        # Step 1: Generate enhanced specifications
        all_entities = all_entities or []
        enhanced_specs_json = _llm_generate_enhanced_service_prompt(ent, reqs, rules, stacks, all_entities, prd_text)
        enhanced_specs = json.loads(enhanced_specs_json)
        
        # Step 2: Generate service code using enhanced specifications
        step2_prompt = f"""
You are an expert Python developer. Generate production-ready service layer code based on the following enhanced specifications:

ENHANCED SPECIFICATIONS:
{json.dumps(enhanced_specs, indent=2)}

ENTITY DETAILS:
{json.dumps(ent, indent=2)}

TECH STACK:
{json.dumps(stacks, indent=2)}
"""
        
        if prd_text:
            step2_prompt += f"\nORIGINAL PRD (for context):\n{prd_text[:10000]}...\n"
        
        step2_prompt += """
Generate complete, production-ready Python service class code that implements the enhanced service specifications. Include:

1. Complete service class with all business logic methods
2. Comprehensive input validation and sanitization
3. Business rule enforcement and constraint checking
4. Error handling with proper HTTP exceptions
5. Logging and monitoring integration
6. Caching implementation where specified
7. Integration with external services
8. Security measures and authorization checks
9. Transaction management and rollback handling
10. Performance optimizations
11. Audit logging and compliance features
12. Unit test helpers and mock interfaces

The code should include:
- Type hints and comprehensive docstrings
- Custom exception classes for business logic errors
- Dependency injection for repositories and external services
- Configuration management for business rules
- Event publishing for domain events
- Metrics collection and performance monitoring
- Input/output data transformation
- Async/await patterns for I/O operations
- Circuit breaker patterns for external integrations
- Rate limiting and throttling mechanisms

Structure the code as follows:
1. Import statements
2. Custom exception classes
3. Service class definition
4. Business logic methods
5. Validation helper methods
6. Integration helper methods
7. Monitoring and logging utilities

Return ONLY the Python code without markdown formatting or explanations.
"""
        
        r = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": step2_prompt}],
            temperature=0,
        )
        return _strip_code_fences(r["choices"][0]["message"]["content"])
        
    except Exception as e:
        traceback.print_exc()
        # Fallback to original simple approach
        name = ent["name"]
        return f"""from typing import List, Optional, Dict, Any
from ..repositories.{name.lower()}_repository import {name}Repository
from ..models.{name.lower()} import {name}
from fastapi import Depends, HTTPException
import logging

logger = logging.getLogger(__name__)

class {name}Service:
    def __init__(self, repository: {name}Repository = Depends()):
        self.repository = repository
    
    async def create_{name.lower()}(self, data: Dict[str, Any]) -> {name}:
        try:
            # Add business logic validation here
            self._validate_{name.lower()}_data(data)
            
            {name.lower()} = self.repository.create(**data)
            logger.info(f"Created {name.lower()} with id: {{{name.lower()}.id}}")
            return {name.lower()}
        except Exception as e:
            logger.error(f"Error creating {name.lower()}: {{e}}")
            raise HTTPException(status_code=400, detail=str(e))
    
    async def get_{name.lower()}(self, id: str) -> {name}:
        {name.lower()} = self.repository.get_by_id(id)
        if not {name.lower()}:
            raise HTTPException(status_code=404, detail="{name} not found")
        return {name.lower()}
    
    async def get_all_{name.lower()}s(self, skip: int = 0, limit: int = 100) -> List[{name}]:
        return self.repository.get_all(skip=skip, limit=limit)
    
    async def update_{name.lower()}(self, id: str, data: Dict[str, Any]) -> {name}:
        try:
            self._validate_{name.lower()}_data(data, is_update=True)
            
            {name.lower()} = self.repository.update(id, **data)
            if not {name.lower()}:
                raise HTTPException(status_code=404, detail="{name} not found")
            
            logger.info(f"Updated {name.lower()} with id: {{id}}")
            return {name.lower()}
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error updating {name.lower()}: {{e}}")
            raise HTTPException(status_code=400, detail=str(e))
    
    async def delete_{name.lower()}(self, id: str) -> bool:
        success = self.repository.delete(id)
        if not success:
            raise HTTPException(status_code=404, detail="{name} not found")
        
        logger.info(f"Deleted {name.lower()} with id: {{id}}")
        return success
    
    def _validate_{name.lower()}_data(self, data: Dict[str, Any], is_update: bool = False):
        # Add entity-specific validation logic here
        # This method should implement business rules validation
        pass
"""

def _llm_route_code(ent: Dict[str, Any], reqs, rules, stacks, prd_text: str | None = None, all_entities: List[Dict[str, Any]] = None) -> str:
    """Step 2: Generate FastAPI route code using enhanced specifications"""
    import openai
    
    try:
        # Step 1: Generate enhanced specifications
        all_entities = all_entities or []
        enhanced_specs_json = _llm_generate_enhanced_route_prompt(ent, reqs, rules, stacks, all_entities, prd_text)
        enhanced_specs = json.loads(enhanced_specs_json)
        
        # Step 2: Generate FastAPI route code using enhanced specifications
        step2_prompt = f"""
You are an expert FastAPI developer. Generate production-ready FastAPI router code based on the following enhanced specifications:

ENHANCED SPECIFICATIONS:
{json.dumps(enhanced_specs, indent=2)}

TECH STACK:
{json.dumps(stacks, indent=2)}
"""
        
        if prd_text:
            step2_prompt += f"\nORIGINAL PRD (for context):\n{prd_text[:10000]}...\n"
        
        step2_prompt += """
Generate complete, production-ready FastAPI router code that implements the enhanced API specifications. Include:

1. Complete APIRouter with all CRUD endpoints
2. Pydantic models for request/response validation
3. Comprehensive error handling with proper HTTP status codes
4. Input validation and sanitization
5. Authentication and authorization decorators
6. Database operations using the specified ORM
7. Proper logging and monitoring
8. Rate limiting and security measures
9. Pagination, filtering, and sorting
10. API documentation with OpenAPI descriptions
11. Unit tests for all endpoints
12. Performance optimizations and caching

The code should include:
- Type hints and comprehensive docstrings
- Proper exception handling with custom error classes
- Database transaction management
- Input validation with detailed error messages
- Security best practices (SQL injection prevention, XSS protection)
- Monitoring and observability (metrics, tracing, logging)
- Configuration management
- Dependency injection for services and repositories

Structure the code as follows:
1. Import statements
2. Pydantic models (request/response schemas)
3. Custom exception classes
4. Router definition
5. Endpoint implementations
6. Helper functions
7. Unit tests

Return ONLY the Python code without markdown formatting or explanations.
"""
        
        r = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": step2_prompt}],
            temperature=0,
        )
        return _strip_code_fences(r["choices"][0]["message"]["content"])
        
    except Exception as e:
        traceback.print_exc()
        # Fallback to original simple approach
        prompt = (
            f"Implement a FastAPI router for the entity {ent['name']}.\n"
            f"Requirements: {json.dumps(reqs, indent=2)}\n"
            f"Business rules: {json.dumps(rules, indent=2)}\n"
            f"Tech stacks: {json.dumps(stacks, indent=2)}\n"
        )
        if prd_text:
            prompt += f"Original PRD:\n{prd_text}\n"
        prompt += "Use comments and TODOs if stack information is insufficient.\nReturn only Python code."
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
    return "\n".join(lines)

def generate_files(spec: Dict[str, Any], plan: Dict[str, Any], out_dir: str, prd_text: str | None = None) -> Dict[str, str]:
    """Generate project files from spec and plan"""
    out = pathlib.Path(out_dir)
    files = {}
    schema_blocks = []
    name = spec.get("meta", {}).get("name", "project")
    hdr = "# Auto-generated file\n"

    for item in plan["files"][:20]:
        print (f'Generating file: {item["path"]}')
        path = out / item["path"]
        code = "// TODO"
        
        # Create parent directories
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # Handle different file types
        if item["path"].endswith("backend/requirements.txt"):
            code = _py_requirements()
        elif item["path"].endswith("pytest.ini"):
            code = _pytest_cfg()
        elif item["path"].endswith("tests/test_health.py"):
            code = _pytest_test()
        elif item["path"].endswith("frontend/tsconfig.json"):
            code = _frontend_tsconfig()
        elif item["path"].endswith("frontend/vite.config.ts"):
            code = _frontend_vite_config()
        elif item["path"].endswith("frontend/package.json"):
            code = _frontend_package_json()
        elif item["path"].endswith("infra/docker-compose.yml"):
            code = _compose(name)
        
        # Handle __init__.py files for new folders
        elif path.name == "__init__.py":
            parent_name = path.parent.name
            if parent_name in ["database", "repositories", "services"]:
                code = f"# {parent_name.capitalize()} module\n"
        
        # Database files
        elif path.name == "connection.py" and "database" in str(path):
            code = hdr + _database_connection()
        elif path.name == "base.py" and "database" in str(path):
            code = hdr + _database_base()
        elif path.name == "migrations.py" and "database" in str(path):
            code = hdr + _database_migrations()
        
        # Repository files
        elif "_repository.py" in str(path):
            m_repo = re.match(r".*repositories/([^/]+)_repository\.py$", str(path))
            if m_repo:
                entity_name = m_repo.group(1)
                en = _find_entity_by_name(spec.get("entities", []), entity_name)
                if en:
                    code = hdr + _render_repository(en, spec)
        
        # Service files
        elif "_service.py" in str(path):
            m_service = re.match(r".*services/([^/]+)_service\.py$", str(path))
            if m_service:
                entity_name = m_service.group(1)
                en = _find_entity_by_name(spec.get("entities", []), entity_name)
                if en:
                    all_entities = spec.get("entities", [])
                    code = hdr + _render_service(en, spec, all_entities, prd_text)
                else:
                    print (f'!!! Service not found for base: {base}')

        # Model files
        elif "/models/" in str(path) and path.suffix == ".py" and path.name != "__init__.py":
            base = path.stem
            en = _find_entity_by_name(spec.get("entities", []), base)
            if en:
                code = hdr + _render_model(en)
            else:
                print(f'!!! Model not found for base: {base}')

        # Route files
        elif "/routes/" in str(path) and path.suffix == ".py" and path.name != "__init__.py":
            base = path.stem.rstrip("s")  # Remove trailing 's' from plural routes
            en = _find_entity_by_name(spec.get("entities", []), base)
            if en:
                all_entities = spec.get("entities", [])
                code = hdr + _render_route(en, spec, prd_text, all_entities)
            else:
                print (f'!!! Route not found for base: {base}')

        # Workflow files
        elif "/workflows/" in str(path) and path.suffix == ".py" and path.name != "__init__.py":
            base = path.stem
            # wf = next((w for w in spec.get("workflows", []) if _slug(w.get("name", "")) == base), None)
            wf = _find_workflow_by_name(spec.get("workflows", []), base)
            if wf:
                entities = spec.get("entities", [])
                code = hdr + _render_workflow(wf, spec, prd_text, entities)
            else:
                print (f'!!! Workflow not found for base: {base}')
        
        # Schema generation for routes
        if "/routes/" in str(path) and path.suffix == ".py" and path.name != "__init__.py":
            base = path.stem.rstrip("s")
            en = _find_entity_by_name(spec.get("entities", []), base)
            if en:
                rules = _rules_for_entity(spec, en["name"])
                schema_code = _render_schema(en, rules)
                schema_blocks.append(schema_code)
            else:
                print (f'!!! Route not found for base: {base}')

        _write(path, code)
        files[item["path"]] = code

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
        test_files = _acceptance_to_tests(req)
        for path, code in test_files:
            _write(out / path, code)
            files[path] = code
    run_and_heal(str(out))
    return files

def _write(path, content):
    """Write content to file"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)

def _find_entity_by_name(entities: List[Dict[str, Any]], name: str) -> Dict[str, Any] | None:
    """Find entity by name, handling singular/plural variations"""
    name_lower = name.lower()
    
    # Direct match first
    for entity in entities:
        entity_name = entity["name"].lower()
        if entity_name == name_lower:
            return entity
    
    # Try singular/plural variations
    for entity in entities:
        entity_name = entity["name"].lower()
        
        # Check if entity name matches with 's' added/removed
        if entity_name.endswith('s') and entity_name[:-1] == name_lower:
            return entity
        if name_lower.endswith('s') and name_lower[:-1] == entity_name:
            return entity
            
        # Handle common irregular plurals
        irregular_plurals = {
            'person': 'people', 'child': 'children', 'foot': 'feet', 
            'tooth': 'teeth', 'mouse': 'mice', 'man': 'men', 'woman': 'women'
        }
        
        # Check irregular plurals both ways
        if entity_name in irregular_plurals and irregular_plurals[entity_name] == name_lower:
            return entity
        if name_lower in irregular_plurals and irregular_plurals[name_lower] == entity_name:
            return entity
        
        # Reverse lookup for irregular plurals
        for singular, plural in irregular_plurals.items():
            if entity_name == plural and name_lower == singular:
                return entity
            if entity_name == singular and name_lower == plural:
                return entity
    
    return None

def _requirements_for_service(spec: Dict[str, Any], entity_name: str) -> List[Dict[str, Any]]:
    """Get requirements relevant to service layer for specific entity"""
    all_reqs = spec.get("requirements", [])
    service_reqs = []
    
    entity_lower = entity_name.lower()
    
    for req in all_reqs:
        req_text = str(req.get("description", "")).lower()
        req_title = str(req.get("title", "")).lower()
        
        # Include if requirement mentions the entity or service-related keywords
        service_keywords = [
            "business logic", "validation", "processing", "workflow", 
            "calculation", "transformation", "integration", "service",
            "rule", "constraint", "policy", "authorization", "audit"
        ]
        
        if (entity_lower in req_text or entity_lower in req_title or
            any(keyword in req_text or keyword in req_title for keyword in service_keywords)):
            service_reqs.append(req)
    
    return service_reqs

def _rules_for_service(spec: Dict[str, Any], entity_name: str) -> List[Dict[str, Any]]:
    """Get business rules relevant to service layer for specific entity"""
    all_rules = spec.get("business_rules", [])
    service_rules = []
    
    entity_lower = entity_name.lower()
    
    for rule in all_rules:
        rule_text = str(rule.get("description", "")).lower()
        rule_expr = str(rule.get("expr", "")).lower()
        
        # Include if rule mentions the entity or contains service-level logic
        service_rule_keywords = [
            "validate", "check", "ensure", "must", "should", "cannot",
            "required", "optional", "minimum", "maximum", "between",
            "before", "after", "during", "when", "if", "unless"
        ]
        
        if (entity_lower in rule_text or entity_lower in rule_expr or
            any(keyword in rule_text or keyword in rule_expr for keyword in service_rule_keywords)):
            service_rules.append(rule)
    
    return service_rules

def _stacks_for_service(spec: Dict[str, Any], entity_name: str) -> Dict[str, Any]:
    """Get tech stacks relevant to service layer"""
    all_stacks = spec.get("stacks", {})
    service_stacks = {}
    
    # Service layer typically needs these stack components
    service_relevant_keys = [
        "backend", "database", "cache", "queue", "messaging", 
        "monitoring", "logging", "security", "validation",
        "business_logic", "integration", "api", "auth"
    ]
    
    for key, value in all_stacks.items():
        if any(relevant in key.lower() for relevant in service_relevant_keys):
            service_stacks[key] = value
    
    # Always include core backend stacks
    if "backend" in all_stacks:
        service_stacks["backend"] = all_stacks["backend"]
    if "database" in all_stacks:
        service_stacks["database"] = all_stacks["database"]
        
    return service_stacks

def _entities_for_service(spec: Dict[str, Any], entity_name: str) -> List[Dict[str, Any]]:
    """Get entities relevant to service layer for specific entity"""
    all_entities = spec.get("entities", [])
    service_entities = []
    
    target_entity = None
    related_entities = []
    
    # Find the target entity
    for entity in all_entities:
        if entity["name"].lower() == entity_name.lower():
            target_entity = entity
            service_entities.append(entity)
            break
    
    if not target_entity:
        return service_entities
    
    # Find related entities through foreign keys
    target_fields = target_entity.get("fields", [])
    for field in target_fields:
        if field.get("fk"):  # Foreign key relationship
            fk_entity_name = field.get("fk")
            for entity in all_entities:
                if entity["name"].lower() == fk_entity_name.lower():
                    if entity not in service_entities:
                        service_entities.append(entity)
    
    # Find entities that reference this entity
    for entity in all_entities:
        if entity == target_entity:
            continue
        entity_fields = entity.get("fields", [])
        for field in entity_fields:
            if field.get("fk") and field.get("fk").lower() == entity_name.lower():
                if entity not in service_entities:
                    service_entities.append(entity)
    
    return service_entities

def _find_workflow_by_name(workflows: List[Dict[str, Any]], name: str) -> Dict[str, Any] | None:
    """Find workflow by name, handling slug variations"""
    name_lower = name.lower().replace('_', '-').replace(' ', '-')
    
    # Direct match first
    for workflow in workflows:
        wf_name = workflow.get("name", "")
        if _slug(wf_name) == name_lower:
            return workflow
    
    # Try variations without special characters
    name_clean = re.sub(r'[^a-z0-9]', '', name_lower)
    for workflow in workflows:
        wf_name = workflow.get("name", "")
        wf_clean = re.sub(r'[^a-z0-9]', '', _slug(wf_name))
        if wf_clean == name_clean:
            return workflow
    
    # Try partial matches (workflow name contains the file name or vice versa)
    for workflow in workflows:
        wf_name = workflow.get("name", "")
        wf_slug = _slug(wf_name)
        if name_lower in wf_slug or wf_slug in name_lower:
            return workflow
    
    return None

def _py_requirements() -> str:
    return """fastapi==0.111.0
uvicorn[standard]==0.30.1
pydantic==2.7.4
sqlalchemy==2.0.31
alembic==1.13.1
psycopg2-binary==2.9.7
python-multipart==0.0.6
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
pytest==7.4.0
pytest-asyncio==0.21.1
httpx==0.24.1
"""

def _pytest_cfg() -> str:
    return """[tool:pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = -v --tb=short
"""

def _pytest_test() -> str:
    return """import pytest
from fastapi.testclient import TestClient
from backend.app.main import app

def test_health():
    c = TestClient(app)
    r = c.get('/health')
    assert r.status_code == 200
    assert r.json().get('status') == 'ok'
"""

def _frontend_tsconfig() -> str:
    return json.dumps({"compilerOptions":{"target":"ES2020","jsx":"react-jsx","module":"ESNext","moduleResolution":"bundler","strict":True,"esModuleInterop":True,"skipLibCheck":True},"include":["src"]}, indent=2)

def _frontend_vite_config() -> str:
    return "import { defineConfig } from 'vite'\nimport react from '@vitejs/plugin-react'\nexport default defineConfig({ plugins: [react()], server: { host: true } })"

def _frontend_package_json() -> str:
    return json.dumps({"name":"frontend","private":True,"type":"module","scripts":{"dev":"vite","build":"vite build","preview":"vite preview --host"},"dependencies":{"react":"^18.2.0","react-dom":"^18.2.0"},"devDependencies":{"@vitejs/plugin-react":"^4.2.0","typescript":"^5.5.4","vite":"^5.3.0"}}, indent=2)

def _database_connection() -> str:
    return """from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.ext.declarative import declarative_base
from typing import Generator
import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@localhost/dbname")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
"""

def _database_base() -> str:
    return """from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, DateTime, String
from datetime import datetime
import uuid

Base = declarative_base()

class BaseModel(Base):
    __abstract__ = True
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
"""

def _database_migrations() -> str:
    return """from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
import os

def run_migrations():
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")

def create_migration(message: str):
    alembic_cfg = Config("alembic.ini")
    command.revision(alembic_cfg, autogenerate=True, message=message)
"""

def _render_repository(ent: Dict[str, Any], spec: Dict[str, Any]) -> str:
    name = ent["name"]
    return f"""from sqlalchemy.orm import Session
from typing import List, Optional
from ..models.{name.lower()} import {name}
from ..database.connection import get_db
from fastapi import Depends

class {name}Repository:
    def __init__(self, db: Session = Depends(get_db)):
        self.db = db
    
    def create(self, **kwargs) -> {name}:
        db_obj = {name}(**kwargs)
        self.db.add(db_obj)
        self.db.commit()
        self.db.refresh(db_obj)
        return db_obj
    
    def get_by_id(self, id: str) -> Optional[{name}]:
        return self.db.query({name}).filter({name}.id == id).first()
    
    def get_all(self, skip: int = 0, limit: int = 100) -> List[{name}]:
        return self.db.query({name}).offset(skip).limit(limit).all()
    
    def update(self, id: str, **kwargs) -> Optional[{name}]:
        db_obj = self.get_by_id(id)
        if db_obj:
            for key, value in kwargs.items():
                setattr(db_obj, key, value)
            self.db.commit()
            self.db.refresh(db_obj)
        return db_obj
    
    def delete(self, id: str) -> bool:
        db_obj = self.get_by_id(id)
        if db_obj:
            self.db.delete(db_obj)
            self.db.commit()
            return True
        return False
"""

def _render_service(ent: Dict[str, Any], spec: Dict[str, Any], all_entities: List[Dict[str, Any]], prd_text: str | None = None) -> str:
    print (f'🔄Generating service: {ent["name"]}')
    use_llm = os.getenv("USE_LLM", "false").lower() == "true"
    reqs = _requirements_for_service(spec, ent["name"])
    rules = _rules_for_service(spec, ent["name"])
    stacks = _stacks_for_service(spec, ent["name"])
    service_entities = _entities_for_service(spec, ent["name"])
    if use_llm:
        try:
            return _llm_service_code(ent, reqs, rules, stacks, prd_text, service_entities)
        except Exception as e:
            traceback.print_exc()
    
    # Fallback to simple template
    name = ent["name"]
    return f"""from typing import List, Optional, Dict, Any
from ..repositories.{name.lower()}_repository import {name}Repository
from ..models.{name.lower()} import {name}
from fastapi import Depends, HTTPException
import logging

logger = logging.getLogger(__name__)

class {name}Service:
    def __init__(self, repository: {name}Repository = Depends()):
        self.repository = repository
    
    async def create_{name.lower()}(self, data: Dict[str, Any]) -> {name}:
        try:
            # Add business logic validation here
            self._validate_{name.lower()}_data(data)
            
            {name.lower()} = self.repository.create(**data)
            logger.info(f"Created {name.lower()} with id: {{{name.lower()}.id}}")
            return {name.lower()}
        except Exception as e:
            logger.error(f"Error creating {name.lower()}: {{e}}")
            raise HTTPException(status_code=400, detail=str(e))
    
    async def get_{name.lower()}(self, id: str) -> {name}:
        {name.lower()} = self.repository.get_by_id(id)
        if not {name.lower()}:
            raise HTTPException(status_code=404, detail="{name} not found")
        return {name.lower()}
    
    async def get_all_{name.lower()}s(self, skip: int = 0, limit: int = 100) -> List[{name}]:
        return self.repository.get_all(skip=skip, limit=limit)
    
    async def update_{name.lower()}(self, id: str, data: Dict[str, Any]) -> {name}:
        try:
            self._validate_{name.lower()}_data(data, is_update=True)
            
            {name.lower()} = self.repository.update(id, **data)
            if not {name.lower()}:
                raise HTTPException(status_code=404, detail="{name} not found")
            
            logger.info(f"Updated {name.lower()} with id: {{id}}")
            return {name.lower()}
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error updating {name.lower()}: {{e}}")
            raise HTTPException(status_code=400, detail=str(e))
    
    async def delete_{name.lower()}(self, id: str) -> bool:
        success = self.repository.delete(id)
        if not success:
            raise HTTPException(status_code=404, detail="{name} not found")
        
        logger.info(f"Deleted {name.lower()} with id: {{id}}")
        return success
    
    def _validate_{name.lower()}_data(self, data: Dict[str, Any], is_update: bool = False):
        # Add entity-specific validation logic here
        # This method should implement business rules validation
        pass
"""

def _compose(name: str) -> str:
    return f"""version: "3.9"
services:
  api:
    image: python:3.11-slim
    working_dir: /app
    volumes: ["./:/app"]
    command: sh -lc "pip install -r backend/requirements.txt && alembic upgrade head && uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload"
    ports: ["8000:8000"]
    environment:
      - DATABASE_URL=postgresql://admin:secret@db:5432/{name}_db
    depends_on:
      - db
  db:
    image: postgres:15
    environment:
      - POSTGRES_DB={name}_db
      - POSTGRES_USER=admin
      - POSTGRES_PASSWORD=secret
    ports: ["5432:5432"]
    volumes:
      - postgres_data:/var/lib/postgresql/data
  frontend:
    image: node:20
    working_dir: /app/frontend
    volumes: ["./:/app"]
    command: sh -lc "npm ci && npm run dev -- --host"
    ports: ["5173:5173"]
    depends_on:
      - api
  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
    volumes:
      - redis_data:/data

volumes:
  postgres_data:
  redis_data:
"""

_SQLA_TYPES = {"uuid":"String","string":"String","int":"Integer","integer":"Integer","bool":"Boolean","boolean":"Boolean","text":"Text","datetime":"DateTime"}

def _render_model(ent: Dict[str, Any]) -> str:
    name = ent["name"]
    fields = ent.get("fields", [])
    cols = []
    imports = ["from sqlalchemy import Column, String, Integer, Boolean, DateTime, Text, ForeignKey"]
    imports.append("from sqlalchemy.orm import relationship")
    imports.append("from ..database.base import BaseModel")
    
    for f in fields:
        col_type = _SQLA_TYPES.get(str(f.get("type","string")).lower(), "String")
        flags = []
        if f.get("pk"): flags.append("primary_key=True")
        if f.get("unique"): flags.append("unique=True")
        if f.get("fk"): 
            flags.append(f"ForeignKey('{f.get('fk')}.id')")
            col_type = "String"
        flags_str = (", " + ", ".join(flags)) if flags else ""
        cols.append(f"    {f['name']} = Column({col_type}{flags_str})")
    
    # Add relationships if any foreign keys exist
    relationships = []
    for f in fields:
        if f.get("fk"):
            rel_name = f.get("fk").capitalize()
            relationships.append(f"    {f['name'].replace('_id', '')} = relationship('{rel_name}', back_populates='{name.lower()}s')")
    
    body = "\n".join(cols) if cols else "    pass"
    if relationships:
        body += "\n\n    # Relationships\n" + "\n".join(relationships)
    
    return "\n".join(imports) + f"\n\nclass {name}(BaseModel):\n    __tablename__ = \"{name.lower()}s\"\n\n{body}\n"

def _render_route(ent: Dict[str, Any], spec: Dict[str, Any], prd_text: str | None = None, all_entities: List[Dict[str, Any]] = None) -> str:
    print (f'🔄 Generating route: {ent["name"]}')
    use_llm = os.getenv("USE_LLM", "false").lower() == "true"
    reqs = _requirements_for_entity(spec, ent["name"])
    rules = _rules_for_entity(spec, ent["name"])
    stacks = spec.get("stacks", {})
    todos = _missing_stack_todos(stacks)
    if use_llm:
        try:
            all_entities = all_entities or []
            return _llm_route_code(ent, reqs, rules, stacks, prd_text, all_entities)
        except Exception as e:
            traceback.print_exc()
    
    name = ent["name"]
    return f"""from fastapi import APIRouter, Depends, HTTPException
from typing import List
from ..services.{name.lower()}_service import {name}Service
from ..models.{name.lower()} import {name}

router = APIRouter(prefix="/{name.lower()}s", tags=["{name.lower()}s"])

@router.post("/", response_model={name})
async def create_{name.lower()}(data: dict, service: {name}Service = Depends()):
    return await service.create_{name.lower()}(data)

@router.get("/{{id}}", response_model={name})
async def get_{name.lower()}(id: str, service: {name}Service = Depends()):
    return await service.get_{name.lower()}(id)

@router.get("/", response_model=List[{name}])
async def get_all_{name.lower()}s(skip: int = 0, limit: int = 100, service: {name}Service = Depends()):
    return await service.get_all_{name.lower()}s(skip=skip, limit=limit)

@router.put("/{{id}}", response_model={name})
async def update_{name.lower()}(id: str, data: dict, service: {name}Service = Depends()):
    return await service.update_{name.lower()}(id, data)

@router.delete("/{{id}}")
async def delete_{name.lower()}(id: str, service: {name}Service = Depends()):
    return await service.delete_{name.lower()}(id)
"""

def _render_workflow(wf: Dict[str, Any], spec: Dict[str, Any], prd_text: str | None = None, entities: List[Dict[str, Any]] = None) -> str:
    print (f'🔄 Generating workflow: {wf["name"]}')
    use_llm = os.getenv("USE_LLM", "false").lower() == "true"
    reqs = spec.get("requirements", [])
    rules = spec.get("business_rules", [])
    stacks = spec.get("stacks", {})
    if use_llm:
        try:
            entities = entities or []
            return _llm_workflow_code(wf, reqs, rules, stacks, prd_text, entities)
        except Exception as e:
            traceback.print_exc()
    
    name = wf.get("name", "Workflow")
    actions = wf.get("actions", [])
    
    workflow_code = f"""from typing import Dict, Any, List
import logging

logger = logging.getLogger(__name__)

class {name.replace(' ', '')}Workflow:
    def __init__(self):
        self.name = "{name}"
    
    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        \"\"\"Execute the {name} workflow\"\"\"
        logger.info(f"Starting workflow: {{self.name}}")
        
        try:
"""
    
    for i, action in enumerate(actions):
        step_name = f"step_{i+1}"
        action_desc = str(action).replace('"', '\\"')
        workflow_code += f"""            # Step {i+1}: {action_desc}
            context = await self.{step_name}(context)
            
"""
    
    workflow_code += """            logger.info(f"Completed workflow: {self.name}")
            return context
            
        except Exception as e:
            logger.error(f"Error in workflow {self.name}: {e}")
            raise
"""
    
    # Add step methods
    for i, action in enumerate(actions):
        step_name = f"step_{i+1}"
        action_desc = str(action).replace('"', '\\"')
        workflow_code += f"""
    async def {step_name}(self, context: Dict[str, Any]) -> Dict[str, Any]:
        \"\"\"Execute step {i+1}: {action_desc}\"\"\"
        # TODO: Implement {action_desc}
        logger.info("Executing step {i+1}: {action_desc}")
        return context
"""
    
    return workflow_code

def _doc_workflows(workflows: List[Dict[str, Any]]) -> str:
    """Generate markdown documentation for workflows"""
    if not workflows:
        return "# Workflows\n\nNo workflows defined.\n"
    
    doc = "# Workflows\n\n"
    for i, wf in enumerate(workflows, 1):
        name = wf.get("name", f"Workflow {i}")
        description = wf.get("description", "No description provided")
        actions = wf.get("actions", [])
        
        doc += f"## {name}\n\n"
        doc += f"**Description:** {description}\n\n"
        
        if actions:
            doc += "**Actions:**\n"
            for j, action in enumerate(actions, 1):
                doc += f"{j}. {action}\n"
        else:
            doc += "**Actions:** None defined\n"
        
        doc += "\n"
    
    return doc

def _doc_requirements(requirements: List[Dict[str, Any]]) -> str:
    """Generate markdown documentation for requirements"""
    if not requirements:
        return "# Requirements\n\nNo requirements defined.\n"
    
    doc = "# Requirements\n\n"
    for req in requirements:
        req_id = req.get("id", "REQ-UNKNOWN")
        title = req.get("title", "Untitled Requirement")
        description = req.get("description", "No description provided")
        priority = req.get("priority", "Medium")
        acceptance = req.get("acceptance", [])
        
        doc += f"## {req_id}: {title}\n\n"
        doc += f"**Priority:** {priority}\n\n"
        doc += f"**Description:** {description}\n\n"
        
        if acceptance:
            doc += "**Acceptance Criteria:**\n"
            for criterion in acceptance:
                doc += f"- {criterion}\n"
        else:
            doc += "**Acceptance Criteria:** None defined\n"
        
        doc += "\n"
    
    return doc

def _doc_rules(rules: List[Dict[str, Any]]) -> str:
    """Generate markdown documentation for business rules"""
    if not rules:
        return "# Business Rules\n\nNo business rules defined.\n"
    
    content = "# Business Rules\n\n"
    for i, rule in enumerate(rules, 1):
        content += f"## Rule {i}: {rule.get('name', 'Unnamed Rule')}\n\n"
        content += f"**Description:** {rule.get('description', 'No description provided')}\n\n"
        if rule.get('conditions'):
            content += f"**Conditions:** {rule['conditions']}\n\n"
        if rule.get('actions'):
            content += f"**Actions:** {rule['actions']}\n\n"
        content += "---\n\n"
    
    return content

def _acceptance_to_tests(req: Dict[str, Any]) -> List[Tuple[str, str]]:
    """Convert a requirement to acceptance test files"""
    req_name = req.get("name", "unnamed_requirement")
    req_text = req.get("text", "")
    acceptance_criteria = req.get("acceptance_criteria", [])
    
    # Generate a safe filename
    safe_name = re.sub(r'[^a-zA-Z0-9_]', '_', req_name.lower())
    test_filename = f"tests/test_{safe_name}.py"
    
    # Generate test content
    test_content = f'''"""
Acceptance tests for requirement: {req_name}

Requirement Description:
{req_text}
"""

import pytest
from unittest.mock import Mock, patch


class Test{req_name.replace(" ", "").replace("-", "").replace("_", "")}:
    """Test class for {req_name}"""
    
    def setup_method(self):
        """Setup test fixtures before each test method."""
        pass
    
    def teardown_method(self):
        """Teardown test fixtures after each test method."""
        pass
'''
    
    # Add test methods for each acceptance criterion
    if acceptance_criteria:
        for i, criterion in enumerate(acceptance_criteria, 1):
            criterion_text = criterion if isinstance(criterion, str) else criterion.get("text", "")
            safe_criterion_name = re.sub(r'[^a-zA-Z0-9_]', '_', criterion_text[:50].lower())
            
            test_content += f'''
    def test_acceptance_criterion_{i}_{safe_criterion_name}(self):
        """
        Test acceptance criterion: {criterion_text}
        """
        # TODO: Implement test for: {criterion_text}
        pytest.skip("Test implementation needed")
'''
    else:
        # Add a default test if no acceptance criteria
        test_content += f'''
    def test_{safe_name}_basic_functionality(self):
        """
        Basic functionality test for {req_name}
        """
        # TODO: Implement basic functionality test
        pytest.skip("Test implementation needed")
'''
    
    test_content += '''

    @pytest.mark.integration
    def test_integration_scenario(self):
        """Integration test scenario"""
        # TODO: Implement integration test
        pytest.skip("Integration test implementation needed")
    
    @pytest.mark.performance
    def test_performance_requirements(self):
        """Performance requirements test"""
        # TODO: Implement performance test
        pytest.skip("Performance test implementation needed")
'''
    
    return [(test_filename, test_content)]
