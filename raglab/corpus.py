"""Simulated Enterprise Identity Provider (IdP), Multi-Connector Knowledge Corpus
(Document Store, Warehouse Row-Level Security Table, and Issue Tracker MCP), and
Code-Level Troubleshooting Scenarios for Interview Preparation.
"""

from __future__ import annotations

from typing import Any, Dict, List

PERSONAS: List[Dict[str, Any]] = [
    {
        "id": "jordan_sales_west",
        "name": "Jordan Alvarez",
        "title": "Account Executive — US-West",
        "email": "jordan.alvarez@acme-enterprise.example",
        "idp_provider": "Okta OIDC -> GCP Workload Identity Federation",
        "groups": ["all-employees", "sales-org", "region-us-west"],
        "allowed_regions": ["US-WEST"],
        "badge": "Sales (US-West Only)",
        "summary": "Can view Public Handbook, Sales Playbook, and ONLY US-WEST rows in the Revenue Warehouse. Blocked from M&A, HR Confidential, SRE Secrets, and US-EAST/EMEA deals.",
    },
    {
        "id": "marcus_sre",
        "name": "Marcus Chen",
        "title": "Staff Platform & Reliability Engineer",
        "email": "marcus.chen@acme-enterprise.example",
        "idp_provider": "Entra ID SAML -> GCP Workforce Identity Pool",
        "groups": ["all-employees", "eng-platform", "sre-oncall"],
        "allowed_regions": [],
        "badge": "Engineering / SRE",
        "summary": "Can view SRE Incident Postmortems, VPC-SC & MCP Connector Runbooks, and Engineering Tickets. Blocked from M&A Deal Room, Sales ARR Deals, and HR Compensation.",
    },
    {
        "id": "priya_finance",
        "name": "Priya Nair",
        "title": "VP of Finance & Revenue Operations",
        "email": "priya.nair@acme-enterprise.example",
        "idp_provider": "Okta OIDC -> GCP Workload Identity Federation",
        "groups": ["all-employees", "finance-leadership"],
        "allowed_regions": ["US-WEST", "US-EAST", "EMEA", "APAC"],
        "badge": "Finance Leadership (All Regions)",
        "summary": "Can view all regional rows in the Revenue Warehouse and Q4 Financial Forecasts. Blocked from unannounced Board M&A Term Sheets and HR Medical/PIP records.",
    },
    {
        "id": "elena_ceo",
        "name": "Elena Vance",
        "title": "Chief Executive Officer",
        "email": "elena.vance@acme-enterprise.example",
        "idp_provider": "Okta OIDC + Hardware Security Key MFA",
        "groups": ["all-employees", "exec-leadership", "finance-leadership", "board-mna-committee"],
        "allowed_regions": ["US-WEST", "US-EAST", "EMEA", "APAC"],
        "badge": "CEO & M&A Committee",
        "summary": "Authorized for Board M&A Deal Room ('Project Horizon') and global financials, but STILL blocked from `hr-medical-restricted` records (Least Privilege > Org Chart!).",
    },
]

# Connector 1: Unstructured Enterprise Document Store (SharePoint / Drive Connector)
DOCUMENT_CHUNKS: List[Dict[str, Any]] = [
    {
        "id": "DOC-PUB-001",
        "connector": "Enterprise Drive / SharePoint Connector",
        "title": "Global Employee AI Usage & Travel Policy (2026)",
        "uri": "drive://policies/global-employee-handbook-2026.md",
        "sensitivity": "INTERNAL_PUBLIC",
        "allowed_groups": ["all-employees"],
        "content": (
            "All employees may use approved enterprise AI assistants grounded on internal data stores. "
            "Customer PII and credentials must never be pasted into unapproved consumer AI tools. "
            "Standard domestic travel meal reimbursement is $85/day and hotel cap is $325/night."
        ),
    },
    {
        "id": "DOC-SALES-002",
        "connector": "Enterprise Drive / SharePoint Connector",
        "title": "Enterprise AI Field Sales & Discounting Playbook",
        "uri": "drive://sales/fy26-discount-governance.md",
        "sensitivity": "CONFIDENTIAL_SALES",
        "allowed_groups": ["sales-org", "finance-leadership", "exec-leadership"],
        "content": (
            "Account Executives may offer up to a 12% standard volume discount on annual committed AI platform contracts. "
            "Discounts between 13% and 25% require VP of Finance approval (Priya Nair). Multi-year commits above $1M ARR "
            "qualify for Forward Deployed Engineering onboarding support during Mobilize (S4.1) and Ramp (S4.2)."
        ),
    },
    {
        "id": "DOC-SRE-003",
        "connector": "Enterprise Drive / SharePoint Connector",
        "title": "VPC Service Controls & Custom MCP Connector Architecture Runbook",
        "uri": "drive://engineering/vpc-sc-mcp-architecture.md",
        "sensitivity": "CONFIDENTIAL_ENG",
        "allowed_groups": ["eng-platform", "sre-oncall"],
        "content": (
            "Production AI agents run inside a VPC Service Controls (VPC-SC) perimeter using Private Service Connect (PSC) "
            "endpoints with zero public internet egress. All custom MCP tool servers authenticate upstream via OAuth 2.0 "
            "token exchange and Cloud KMS Customer-Managed Encryption Keys (CMEK rotation: 90 days)."
        ),
    },
    {
        "id": "DOC-MNA-004",
        "connector": "Enterprise Drive / SharePoint Connector",
        "title": "STRICTLY CONFIDENTIAL — Project Horizon M&A Term Sheet",
        "uri": "drive://board-vault/project-horizon-term-sheet.pdf",
        "sensitivity": "RESTRICTED_BOARD_MNA",
        "allowed_groups": ["board-mna-committee"],
        "content": (
            "Project Horizon: Acme Corp has signed a non-binding letter of intent to acquire VectorShield AI "
            "for $420 Million USD ($310M cash, $110M equity) closing December 18, 2026. Material Non-Public Information "
            "(MNPI) — strictly restricted to the Board M&A Committee prior to public SEC 8-K filing."
        ),
    },
    {
        "id": "DOC-FIN-005",
        "connector": "Enterprise Drive / SharePoint Connector",
        "title": "Q4 FY26 Consolidated Margin & Cloud Token Spend Forecast",
        "uri": "drive://finance/q4-fy26-margin-forecast.xlsx",
        "sensitivity": "CONFIDENTIAL_FINANCE",
        "allowed_groups": ["finance-leadership", "exec-leadership"],
        "content": (
            "Q4 FY26 consolidated gross margin is projected at 74.2% on $148.5M quarterly revenue. "
            "Implementing model routing (routing 78% of tier-1 classification queries to Flash-Lite and 22% to Pro) "
            "reduced monthly Vertex AI inference spend from $94,000/mo to $26,400/mo (-71.9%) with zero accuracy drop."
        ),
    },
    {
        "id": "DOC-HR-006",
        "connector": "Enterprise Drive / SharePoint Connector",
        "title": "HR Restricted — Protected Leave & Medical Accommodation Roster",
        "uri": "drive://hr-vault/protected-medical-leave-q4.docx",
        "sensitivity": "RESTRICTED_HR_HIPAA",
        "allowed_groups": ["hr-confidential"],
        "content": (
            "HIPAA / Employment Privacy Restricted: Employee ID E-88412 is on approved FMLA medical accommodation "
            "through February 2027. Access is strictly isolated to `hr-confidential` legal custodians; even C-Suite "
            "executives including the CEO are excluded under Least-Privilege privacy controls."
        ),
    },
]

# Connector 2: Structured Analytical Warehouse with Row-Level Access Policies (BigQuery RLS Simulator)
WAREHOUSE_DEAL_ROWS: List[Dict[str, Any]] = [
    {
        "row_id": "BQ-ROW-101",
        "region": "US-WEST",
        "account_name": "Pacific Biotech Corp",
        "arr_usd": 640000,
        "stage": "S4.2 Ramping",
        "renewal_risk": "LOW",
        "notes": "Deploying identity-aware RAG over 180k clinical SOP PDFs in US-WEST region.",
    },
    {
        "row_id": "BQ-ROW-102",
        "region": "US-WEST",
        "account_name": "GoldenGate Logistics",
        "arr_usd": 410000,
        "stage": "S4.1 Mobilize",
        "renewal_risk": "MEDIUM",
        "notes": "Waiting on Okta OIDC to Workload Identity Federation group claim mapping.",
    },
    {
        "row_id": "BQ-ROW-103",
        "region": "US-EAST",
        "account_name": "WallStreet Clearing House",
        "arr_usd": 1850000,
        "stage": "S4.2 Ramping",
        "renewal_risk": "HIGH",
        "notes": "CISO requires VPC Service Controls + CMEK + Private Service Connect verification before production cutover.",
    },
    {
        "row_id": "BQ-ROW-104",
        "region": "EMEA",
        "account_name": "Nordic Sovereign Bank",
        "arr_usd": 1220000,
        "stage": "S4.3 Go-Live",
        "renewal_risk": "LOW",
        "notes": "Pinned EU-only data residency (`europe-west4`) with Provisioned Throughput for sub-1.2s p95 latency.",
    },
]

# Connector 3: Live Issue Tracker MCP Server (Jira / ServiceNow RBAC Tickets)
MCP_TICKETS: List[Dict[str, Any]] = [
    {
        "id": "SEC-401",
        "connector": "Issue Tracker MCP Connector",
        "title": "SEC-401: Fix Confused-Deputy Service Account on SharePoint Search Indexer",
        "uri": "mcp://tickets/SEC-401",
        "sensitivity": "CONFIDENTIAL_ENG",
        "allowed_groups": ["eng-platform", "sre-oncall", "exec-leadership"],
        "content": (
            "Ticket SEC-401 (P1 Open): Legacy staging search connector used a shared admin token instead of "
            "per-user principal ACL propagation. Remediation: enable Data Store ACL enforcement and require "
            "OAuth identity assertion at query time before vector + BM25 retrieval."
        ),
    },
    {
        "id": "OPS-209",
        "connector": "Issue Tracker MCP Connector",
        "title": "OPS-209: Vertex AI HTTP 429 Burst Throttling During Monday 9AM Peak",
        "uri": "mcp://tickets/OPS-209",
        "sensitivity": "CONFIDENTIAL_ENG",
        "allowed_groups": ["eng-platform", "sre-oncall"],
        "content": (
            "Ticket OPS-209 (Resolved): Pay-as-you-go shared quota hit HTTP 429 at 9:05 AM EST when 4,200 employees "
            "launched morning summary agents simultaneously. Fixed by sizing Provisioned Throughput (GSUs) for baseline "
            "traffic with automatic spillover to pay-as-you-go + exponential backoff."
        ),
    },
]

# Tab 3: Code-Level Troubleshooting Exercises (Interview Reading-Code Practice)
CODE_BUG_CHALLENGES: List[Dict[str, Any]] = [
    {
        "id": "bug-post-filter-starvation",
        "title": "Bug #1: Post-Retrieval ACL Filtering ('Zero-Results Starvation')",
        "symptom": "Sales reps in `region-us-west` complain that searching for 'discount policy' returns 0 results even though `DOC-SALES-002` is shared with `sales-org`!",
        "broken_code": (
            "def search_enterprise_docs(query: str, user_groups: set[str]) -> list[dict]:\n"
            "    # Step 1: Fetch top_k=2 globally highest-scoring chunks from vector DB\n"
            "    raw_hits = vector_index.similarity_search(query, top_k=2)\n"
            "    # Step 2: Filter out chunks the user isn't allowed to see\n"
            "    return [doc for doc in raw_hits if set(doc['allowed_groups']) & user_groups]"
        ),
        "question": "Read the 5 lines of Python above. Why does an authorized Sales rep get an empty list `[]` when executive/finance docs happen to score slightly higher on the same keyword?",
        "root_cause": (
            "ACL filtering is happening AFTER `top_k=2` retrieval (Post-Filtering) instead of INSIDE the index query "
            "(Pre-Filtering)! When 2 restricted Executive/M&A docs take both `top_k=2` slots and then get stripped out "
            "in Step 2, the authorized Sales doc at rank #3 is never fetched—starving the user with `0` results."
        ),
        "fix_code": (
            "def search_enterprise_docs(query: str, user_groups: set[str]) -> list[dict]:\n"
            "    # Push the principal ACL filter INTO the vector/hybrid index query (Pre-Filtering)\n"
            "    return vector_index.similarity_search(\n"
            "        query,\n"
            "        top_k=5,\n"
            "        filter={'allowed_groups': {'$in': sorted(user_groups)}},\n"
            "    )"
        ),
        "interview_soundbite": (
            "\"Never filter ACLs in application code after Top-K vector search—push principal ACL metadata filters "
            "directly into the search index pre-filter (which Vertex AI Search & Gemini Enterprise data stores do natively) "
            "so you avoid both Top-K starvation and accidental memory exposure.\""
        ),
    },
    {
        "id": "bug-pure-vector-id-miss",
        "title": "Bug #2: Pure Dense Vector Search Missing Exact Ticket / SKU IDs (`SEC-401`)",
        "symptom": "An engineer asks the AI agent: 'What is the status of SEC-401?' and dense embedding search retrieves generic security policy docs instead of ticket `SEC-401`!",
        "broken_code": (
            "def retrieve_context(user_query: str, user_groups: list[str]):\n"
            "    q_vec = embed_model.encode(user_query)  # Dense semantic embedding only\n"
            "    return index.vector_query(embedding=q_vec, acl_groups=user_groups, top_k=3)"
        ),
        "question": "Why do dense embedding models struggle with queries like `SEC-401`, `BQ-ROW-103`, or part SKUs, and what retrieval architecture fixes it?",
        "root_cause": (
            "Dense vector embeddings compress text into smooth semantic concepts ('security', 'authentication'), losing "
            "exact lexical token precision on rare alphanumeric identifiers like `SEC-401`, error codes, or contract IDs."
        ),
        "fix_code": (
            "def retrieve_context(user_query: str, user_groups: list[str]):\n"
            "    # Hybrid Search: Combine Dense Vector similarity + Sparse BM25 exact keyword match via RRF\n"
            "    dense_hits = index.vector_query(user_query, acl_groups=user_groups, top_k=10)\n"
            "    sparse_hits = index.bm25_query(user_query, acl_groups=user_groups, top_k=10)\n"
            "    return reciprocal_rank_fusion(dense_hits, sparse_hits, k=60)[:5]"
        ),
        "interview_soundbite": (
            "\"In enterprise environments, users constantly query exact ticket IDs, SKU codes, and clause numbers. "
            "Always pair dense semantic embeddings with sparse lexical BM25 using Reciprocal Rank Fusion (Hybrid Search).\""
        ),
    },
    {
        "id": "bug-shared-cache-bleed",
        "title": "Bug #3: Semantic Response Cache Key Missing User Identity (Cross-Tenant Leak)",
        "symptom": "Elena (CEO) asks 'What major acquisitions are planned for Q4?' and gets Project Horizon. Two minutes later, Jordan (Sales) asks the exact same question and gets the CEO's cached M&A answer!",
        "broken_code": (
            " def answer_with_cache(user_query: str, user_token: dict) -> str:\n"
            "     cache_key = sha256(normalize_query(user_query))\n"
            "     if redis_cache.exists(cache_key):\n"
            "         return redis_cache.get(cache_key)\n"
            "     ans = run_acl_safe_rag(user_query, user_token)\n"
            "     redis_cache.set(cache_key, ans, ttl=3600)\n"
            "     return ans"
        ),
        "question": "Even though `run_acl_safe_rag()` properly enforces ACLs, why did Project Horizon leak to Jordan?",
        "root_cause": (
            "`cache_key` hashes ONLY `user_query` without binding the caller's normalized `allowed_groups` / security "
            "scope! Caching above an ACL-enforced RAG pipeline turns a secure retrieval layer into a cross-user data leak."
        ),
        "fix_code": (
            "def answer_with_cache(user_query: str, user_token: dict) -> str:\n"
            "    scope_fingerprint = ','.join(sorted(user_token['groups'])) + '|' + ','.join(sorted(user_token['regions']))\n"
            "    cache_key = sha256(f'{scope_fingerprint}::{normalize_query(user_query)}')\n"
            "    ..."
        ),
        "interview_soundbite": (
            "\"Any semantic or exact-match cache in front of an enterprise RAG agent MUST partition cache keys by the "
            "caller's normalized IAM group/entitlement hash—otherwise User B gets User A's cached grounded answer.\""
        ),
    },
    {
        "id": "bug-mcp-confused-deputy",
        "title": "Bug #4: Custom MCP Connector Using Static Service Account Key Instead of OAuth On-Behalf-Of",
        "symptom": "A customer built a custom MCP server for BigQuery using a static JSON service-account key with `roles/bigquery.dataViewer` on the whole dataset. Every employee sees all global regions!",
        "broken_code": (
            "# mcp_bigquery_server.py\n"
            "bq_client = bigquery.Client.from_service_account_json('/secrets/mcp-admin-sa.json')\n\n"
            "@mcp.tool()\n"
            "def query_deals(region_hint: str) -> list:\n"
            "    return list(bq_client.query(f\"SELECT * FROM crm.deals WHERE region = '{region_hint}'\"))"
        ),
        "question": "Spot the TWO severe security flaws in those 6 lines of Python.",
        "root_cause": (
            "1) Confused Deputy + Static Key Risk: Using a static `service_account.json` bypasses BigQuery Row-Level "
            "Access Policies (`SESSION_USER()`) because every query runs as `mcp-admin-sa`—plus static keys violate "
            "keyless Workload Identity best practices. 2) SQL Injection: String-interpolating `region_hint` lets a "
            "prompt-injected LLM pass `\"US-WEST' OR '1'='1\"` to dump all global rows!"
        ),
        "fix_code": (
            "# 1. Propagate end-user OAuth credentials (or IAM principal) + 2. Parameterized BigQuery query\n"
            "job_config = bigquery.QueryJobConfig(\n"
            "    query_parameters=[bigquery.ScalarQueryParameter('region', 'STRING', region_hint)]\n"
            ")\n"
            "user_bq_client = bigquery.Client(credentials=exchange_user_oauth_token(request.bearer_token))\n"
            "return list(user_bq_client.query('SELECT * FROM crm.deals WHERE region = @region', job_config=job_config))"
        ),
        "interview_soundbite": (
            "\"Custom MCP connectors should never hold static admin service account keys or interpolate LLM-supplied SQL. "
            "Use OAuth token exchange / Workforce Identity Federation so BigQuery Row-Level Security enforces `SESSION_USER()` "
            "natively, paired with parameterized queries.\""
        ),
    },
]
