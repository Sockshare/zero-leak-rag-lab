"""Core Enterprise RAG Engine:
- Pre-Retrieval Identity & BigQuery Row-Level Security (RLS) Trimming vs. Naive Confused-Deputy RAG
- Hybrid Search: Sparse BM25 + Dense Semantic Vector Similarity + Reciprocal Rank Fusion (RRF)
- Model Armor Input/Output Guardrail & Citation Grounding Verifier
- Dual-Route LLM Support: Local Onboard Ollama (Default) + Cloud APIs (Google Gemini, OpenAI, Anthropic)
- RAG vs. Long-Context (1M+) vs. Fine-Tuning Architecture Trade-Off Calculator
"""

from __future__ import annotations

import json
import math
import os
import re
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from raglab.corpus import DOCUMENT_CHUNKS, MCP_TICKETS, PERSONAS, WAREHOUSE_DEAL_ROWS

REPO_ROOT = Path(__file__).resolve().parent.parent

# Semantic concept clusters so our zero-dependency dense vector embedder captures synonyms
# (e.g., "acquisition" <-> "acquire"/"buyout"/"M&A", "quota" <-> "429"/"throttling") while still
# illustrating why pure dense embeddings miss exact alphanumeric IDs like SEC-401 without BM25!
_SEMANTIC_CONCEPTS: List[Tuple[str, Tuple[str, ...]]] = [
    ("concept_mna", ("acquisition", "acquire", "acquiring", "buyout", "merger", "m&a", "horizon", "term", "sheet", "mnpi", "deal", "target")),
    ("concept_finance", ("revenue", "arr", "margin", "forecast", "budget", "spend", "cost", "discount", "pricing", "financial", "quarter", "q4")),
    ("concept_security", ("security", "vpc", "vpc-sc", "perimeter", "cmek", "kms", "acl", "iam", "oauth", "oidc", "confused", "deputy", "leak", "ciso")),
    ("concept_quota", ("throttling", "rate", "limit", "quota", "burst", "provisioned", "throughput", "latency", "429", "peak", "outage")),
    ("concept_hr", ("medical", "leave", "fmla", "hipaa", "accommodation", "privacy", "hr", "employee", "restricted")),
    ("concept_policy", ("travel", "hotel", "meal", "reimbursement", "handbook", "policy", "expense", "per-diem")),
    ("concept_sales", ("west", "east", "emea", "customer", "account", "renewal", "pipeline", "mobilize", "ramp", "stage")),
]

_INJECTION_PATTERNS = (
    r"ignore\s+(?:all\s+)?(?:previous|prior|role|acl|security)",
    r"bypass\s+(?:acl|security|permissions|restrictions)",
    r"act\s+as\s+(?:ceo|admin|root|system)",
    r"dump\s+all\s+(?:rows|documents|secrets|deals)",
    r"system\s+prompt",
    r"override\s+(?:access|policy|clearance)",
)

_SESSION_KEYS: Dict[str, str] = {}

SEARCH_STRATEGIES = ("hybrid_rrf", "dense_vector_only", "bm25_keyword_only")
SECURITY_MODES = ("zero_leak", "naive_confused_deputy")
OLLAMA_TIMEOUT_S = 90.0

PRICING_NOTE = (
    "Illustrative order-of-magnitude estimates using placeholder unit prices ($0.15 / 1M input tokens, "
    "$0.60 / 1M output tokens, $18 / 1M indexed tokens, $180 per tuning run). They are not a current price "
    "list. Check the provider's pricing page before quoting any figure."
)


def _describe_llm_error(exc: Exception) -> str:
    """Short, key-free description of why an LLM call failed (shown in the UI)."""
    if isinstance(exc, urllib.error.HTTPError):
        msg = f"HTTP {exc.code} {exc.reason}"
    elif isinstance(exc, (TimeoutError, urllib.error.URLError)):
        msg = f"Could not reach the model endpoint or it timed out ({getattr(exc, 'reason', exc)})"
    else:
        msg = f"{type(exc).__name__}: {exc}"
    msg = re.sub(r"(key=)[^&\s]+", r"\1***", msg)
    return msg[:240]


def _read_env_key(names: Tuple[str, ...]) -> str:
    for n in names:
        v = (os.environ.get(n) or "").strip()
        if v:
            return v
    dotenv_path = REPO_ROOT / ".env"
    if dotenv_path.is_file():
        try:
            for raw in dotenv_path.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, val = line.split("=", 1)
                    if k.strip() in names:
                        cleaned = val.strip().strip('"').strip("'")
                        if cleaned:
                            return cleaned
        except Exception:
            pass
    return ""


def get_llm_status(ollama_url: str = "http://127.0.0.1:11434") -> Dict[str, Any]:
    """Return available Local Onboard Ollama models (default) + optional Cloud API profiles."""
    base = ollama_url.rstrip("/")
    ollama_models: List[str] = []
    try:
        req = urllib.request.Request(f"{base}/api/tags", headers={"User-Agent": "ZeroLeak-RAG-Lab/1.0"})
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            ollama_models = [m.get("name", "") for m in data.get("models", []) if m.get("name")]
    except Exception:
        ollama_models = []

    ollama_models.sort(key=lambda m: (0 if "llama3.2" in m else (1 if "qwen" in m or "llama3" in m else 2), m))
    profiles: List[Dict[str, Any]] = []
    if ollama_models:
        for m in ollama_models:
            profiles.append({
                "id": f"ollama-{m}",
                "name": f"Local Ollama (Onboard) — {m}",
                "provider": "ollama",
                "model": m,
                "group": "local_onboard",
                "has_api_key": False,
            })
    else:
        profiles.append({
            "id": "ollama-default",
            "name": "Local Ollama (Onboard Default) — llama3.2:3b",
            "provider": "ollama",
            "model": "llama3.2:3b",
            "group": "local_onboard",
            "has_api_key": False,
        })

    profiles.extend([
        {
            "id": "cloud-gemini",
            "name": "Google Gemini API — gemini-2.5-flash (Cloud API)",
            "provider": "gemini",
            "model": "gemini-2.5-flash",
            "group": "cloud_api",
            "has_api_key": bool(_SESSION_KEYS.get("gemini") or _read_env_key(("GEMINI_API_KEY", "GOOGLE_API_KEY"))),
        },
        {
            "id": "cloud-openai",
            "name": "OpenAI API — gpt-4o-mini (Cloud API)",
            "provider": "openai",
            "model": "gpt-4o-mini",
            "group": "cloud_api",
            "has_api_key": bool(_SESSION_KEYS.get("openai") or _read_env_key(("OPENAI_API_KEY",))),
        },
        {
            "id": "cloud-anthropic",
            "name": "Anthropic Claude API — claude-3-7-sonnet-latest (Cloud API)",
            "provider": "anthropic",
            "model": "claude-3-7-sonnet-latest",
            "group": "cloud_api",
            "has_api_key": bool(_SESSION_KEYS.get("anthropic") or _read_env_key(("ANTHROPIC_API_KEY",))),
        },
    ])
    return {
        "ollama_connected": len(ollama_models) > 0,
        "ollama_models": ollama_models,
        "profiles": profiles,
    }


def build_unified_corpus() -> List[Dict[str, Any]]:
    """Normalize all 3 enterprise connectors (Drive Docs, BigQuery RLS Rows, MCP Tickets) into indexable records."""
    records: List[Dict[str, Any]] = []
    for doc in DOCUMENT_CHUNKS:
        records.append({
            "id": doc["id"],
            "connector": doc["connector"],
            "connector_type": "document_acl",
            "title": doc["title"],
            "uri": doc["uri"],
            "sensitivity": doc["sensitivity"],
            "allowed_groups": list(doc["allowed_groups"]),
            "rls_region": None,
            "content": doc["content"],
        })
    for row in WAREHOUSE_DEAL_ROWS:
        records.append({
            "id": row["row_id"],
            "connector": "BigQuery Warehouse (Row-Level Security)",
            "connector_type": "bigquery_rls",
            "title": f"BigQuery Deal Row {row['row_id']} — {row['account_name']} ({row['region']})",
            "uri": f"bq://enterprise_analytics.customer_deals/{row['row_id']}",
            "sensitivity": f"RLS_REGION_{row['region']}",
            "allowed_groups": ["sales-org", "finance-leadership", "exec-leadership"],
            "rls_region": row["region"],
            "content": (
                f"Account: {row['account_name']} | Region: {row['region']} | Committed ARR: ${row['arr_usd']:,} USD | "
                f"Delivery Stage: {row['stage']} | Renewal Risk: {row['renewal_risk']} | Notes: {row['notes']}"
            ),
        })
    for tkt in MCP_TICKETS:
        records.append({
            "id": tkt["id"],
            "connector": tkt["connector"],
            "connector_type": "mcp_rbac",
            "title": tkt["title"],
            "uri": tkt["uri"],
            "sensitivity": tkt["sensitivity"],
            "allowed_groups": list(tkt["allowed_groups"]),
            "rls_region": None,
            "content": tkt["content"],
        })
    return records


def check_principal_access(record: Dict[str, Any], persona: Dict[str, Any]) -> Tuple[bool, str]:
    """Evaluate Pre-Retrieval IAM Group ACL + BigQuery Row-Level Access Policy (`SESSION_USER()`)."""
    user_groups = set(persona.get("groups", []))
    allowed_groups = set(record.get("allowed_groups", []))
    matched_groups = sorted(user_groups & allowed_groups)

    if not matched_groups:
        return (
            False,
            f"Blocked by Document/MCP IAM ACL: requires {sorted(allowed_groups)}, caller has {sorted(user_groups)}",
        )

    if record.get("connector_type") == "bigquery_rls":
        row_region = record.get("rls_region")
        user_regions = set(persona.get("allowed_regions", []))
        if row_region not in user_regions:
            return (
                False,
                f"Blocked by BigQuery Row-Level Access Policy: row region='{row_region}' not in caller's allowed_regions={sorted(user_regions)}",
            )
        return (
            True,
            f"Authorized via group `{matched_groups[0]}` + BigQuery RLS `region='{row_region}'`",
        )

    return True, f"Authorized via principal group `{matched_groups[0]}`"


def _tokenize_bm25(text: str) -> List[str]:
    # Keep alphanumeric identifiers like SEC-401, OPS-209, BQ-ROW-103 intact AND split subparts
    raw_tokens = re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", text.lower())
    expanded: List[str] = []
    for tok in raw_tokens:
        expanded.append(tok)
        if "-" in tok:
            expanded.extend(p for p in tok.split("-") if len(p) > 1)
    return expanded


def _compute_dense_vector(text: str) -> Dict[str, float]:
    """Compute a smooth semantic concept + word-stem vector (intentionally stripping exact alphanumeric IDs
    so users can observe why pure dense embeddings struggle on exact ticket codes like `SEC-401` vs Hybrid RRF).
    """
    cleaned = re.sub(r"\b[a-z]{2,5}-\d+\b", " ", text.lower())
    words = re.findall(r"[a-z]{3,}", cleaned)
    vec: Dict[str, float] = {}
    for cname, keywords in _SEMANTIC_CONCEPTS:
        hits = sum(1 for w in words if w in keywords)
        if hits:
            vec[cname] = hits * 2.4
    for w in words:
        if w in {"the", "and", "for", "with", "that", "this", "from", "are", "what", "all", "tell", "show"}:
            continue
        stem = w[:5]
        vec[f"stem_{stem}"] = vec.get(f"stem_{stem}", 0.0) + 0.8
    norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
    return {k: v / norm for k, v in vec.items()}


def _cosine_sim(v1: Dict[str, float], v2: Dict[str, float]) -> float:
    if not v1 or not v2:
        return 0.0
    return sum(val * v2.get(k, 0.0) for k, val in v1.items())


def score_candidates_hybrid(
    query: str,
    candidates: List[Dict[str, Any]],
    strategy: str = "hybrid_rrf",
    top_k: int = 4,
) -> List[Dict[str, Any]]:
    """Score candidate chunks using Dense Vector, Sparse BM25, or Hybrid Reciprocal Rank Fusion (RRF)."""
    if not candidates:
        return []

    q_tokens = _tokenize_bm25(query)
    q_vec = _compute_dense_vector(query)

    # BM25 statistics across candidate pool
    doc_tokens_list = [_tokenize_bm25(f"{c['id']} {c['title']} {c['content']}") for c in candidates]
    n_docs = len(candidates)
    avgdl = (sum(len(dt) for dt in doc_tokens_list) / n_docs) if n_docs else 1.0
    df: Counter[str] = Counter()
    for dt in doc_tokens_list:
        for ut in set(dt):
            df[ut] += 1

    scored: List[Dict[str, Any]] = []
    for idx, cand in enumerate(candidates):
        dt = doc_tokens_list[idx]
        tf = Counter(dt)
        dl = len(dt) or 1
        bm25 = 0.0
        for qt in q_tokens:
            if tf[qt] > 0:
                idf = math.log(1.0 + (n_docs - df[qt] + 0.5) / (df[qt] + 0.5))
                num = tf[qt] * (1.5 + 1.0)
                den = tf[qt] + 1.5 * (1.0 - 0.75 + 0.75 * (dl / avgdl))
                bm25 += idf * (num / den)

        c_vec = _compute_dense_vector(f"{cand['title']} {cand['content']}")
        dense = _cosine_sim(q_vec, c_vec)

        item = dict(cand)
        item["bm25_score"] = round(bm25, 4)
        item["dense_score"] = round(dense, 4)
        scored.append(item)

    # Compute ranks for RRF
    by_dense = sorted(scored, key=lambda x: (-x["dense_score"], x["id"]))
    by_bm25 = sorted(scored, key=lambda x: (-x["bm25_score"], x["id"]))
    dense_rank = {x["id"]: r for r, x in enumerate(by_dense, start=1)}
    bm25_rank = {x["id"]: r for r, x in enumerate(by_bm25, start=1)}

    for item in scored:
        cid = item["id"]
        # A ranker only contributes when it has a real (non-zero) signal. Otherwise the arbitrary
        # tie-break rank among all-zero scores would earn RRF credit and outrank true matches.
        rrf = 0.0
        if item["dense_score"] > 0:
            rrf += 1.0 / (20.0 + dense_rank[cid])
        if item["bm25_score"] > 0:
            rrf += 1.0 / (20.0 + bm25_rank[cid])
        item["rrf_score"] = round(rrf, 5)
        item["dense_rank"] = dense_rank[cid]
        item["bm25_rank"] = bm25_rank[cid]

    if strategy == "dense_vector_only":
        scored.sort(key=lambda x: (-x["dense_score"], x["id"]))
    elif strategy == "bm25_keyword_only":
        scored.sort(key=lambda x: (-x["bm25_score"], x["id"]))
    else:
        scored.sort(key=lambda x: (-x["rrf_score"], -x["bm25_score"], -x["dense_score"], x["id"]))

    return scored[:top_k]


def check_model_armor_input(query: str) -> Dict[str, Any]:
    """Simulate Google Cloud Model Armor prompt-injection & jailbreak inspection."""
    triggered = [pat for pat in _INJECTION_PATTERNS if re.search(pat, query, re.IGNORECASE)]
    return {
        "inspected": True,
        "injection_detected": len(triggered) > 0,
        "matched_rules": len(triggered),
        "verdict": "FLAGGED_PROMPT_INJECTION" if triggered else "CLEAN",
        "architect_note": (
            "Model Armor flagged adversarial prompt-injection phrasing! Notice why Defense-in-Depth matters: "
            "in Naive RAG, this prompt steals restricted chunks already sitting in context; in Zero-Leak RAG, "
            "even if a novel jailbreak evades Model Armor, unauthorized chunks NEVER entered the prompt (`Δ = ∅`)."
            if triggered
            else "Input passed Model Armor prompt-injection & PII screen."
        ),
    }


def _call_llm_for_rag(
    llm_config: Dict[str, Any],
    system_prompt: str,
    user_prompt: str,
) -> Tuple[str, str]:
    provider = (llm_config.get("provider") or "ollama").lower()
    model = llm_config.get("model") or ("gemini-2.5-flash" if provider == "gemini" else "llama3.2:3b")
    explicit_key = (llm_config.get("api_key") or "").strip()
    if explicit_key and provider in ("gemini", "openai", "anthropic"):
        _SESSION_KEYS[provider] = explicit_key

    if provider in ("ollama", "ollama_local"):
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "keep_alive": "30m",
            "options": {"temperature": 0.0, "seed": 42, "num_predict": 180, "num_ctx": 2048},
        }
        req = urllib.request.Request(
            "http://127.0.0.1:11434/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT_S) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return ((body.get("message") or {}).get("content") or "").strip(), model

    if provider == "gemini":
        api_key = explicit_key or _SESSION_KEYS.get("gemini") or _read_env_key(("GEMINI_API_KEY", "GOOGLE_API_KEY"))
        if not api_key:
            raise ValueError("Gemini API key required (set GEMINI_API_KEY in .env or paste in UI).")
        # Try the requested model first, then fall back. (gemini-2.5-flash-lite was retired for new
        # API users, so the lite fallback is gemini-3.5-flash-lite.)
        chain = list(dict.fromkeys([model, "gemini-2.5-flash", "gemini-3.5-flash-lite", "gemini-flash-latest"]))
        failures: List[str] = []
        for gem_model in chain:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{gem_model}:generateContent"
            gen_cfg: Dict[str, Any] = {"temperature": 0.0, "maxOutputTokens": 600}
            if "2.5-flash" in gem_model:
                gen_cfg["thinkingConfig"] = {"thinkingBudget": 0}
            payload = {
                "systemInstruction": {"parts": [{"text": system_prompt}]},
                "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
                "generationConfig": gen_cfg,
            }
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=20.0) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                    parts = (((body.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [{}])
                    txt = "".join(str(p.get("text") or "") for p in parts if not p.get("thought")).strip()
                    if txt:
                        return txt, gem_model
                    failures.append(f"{gem_model}: empty response")
            except urllib.error.HTTPError as e:
                if e.code in (401, 403):
                    raise ValueError(f"Gemini rejected the API key (HTTP {e.code}).") from None
                detail = ""
                if e.code == 429:
                    try:
                        err_body = e.read().decode("utf-8", "replace")
                    except Exception:  # noqa: BLE001
                        err_body = ""
                    detail = " daily free-tier quota used up" if "PerDay" in err_body else " rate limit or quota"
                elif e.code == 404:
                    detail = " model not available for this key"
                failures.append(f"{gem_model}: HTTP {e.code}{detail}")
            except (TimeoutError, urllib.error.URLError):
                failures.append(f"{gem_model}: timed out or unreachable")
        raise RuntimeError("No Gemini model answered. " + "; ".join(failures))

    if provider == "openai":
        api_key = explicit_key or _SESSION_KEYS.get("openai") or _read_env_key(("OPENAI_API_KEY",))
        if not api_key:
            raise ValueError("OpenAI API key required.")
        payload = {
            "model": model or "gpt-4o-mini",
            "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            "temperature": 0.0,
            "max_tokens": 280,
        }
        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20.0) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return (body["choices"][0]["message"]["content"] or "").strip(), payload["model"]

    if provider == "anthropic":
        api_key = explicit_key or _SESSION_KEYS.get("anthropic") or _read_env_key(("ANTHROPIC_API_KEY",))
        if not api_key:
            raise ValueError("Anthropic API key required.")
        payload = {
            "model": model or "claude-3-7-sonnet-latest",
            "max_tokens": 280,
            "temperature": 0.0,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        }
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "x-api-key": api_key, "anthropic-version": "2023-06-01"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20.0) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return (body["content"][0]["text"] or "").strip(), payload["model"]

    raise ValueError(f"Unsupported provider: {provider}")


def run_rag_query(
    query: str,
    persona_id: str = "jordan_sales_west",
    security_mode: str = "zero_leak",
    search_strategy: str = "hybrid_rrf",
    llm_config: Optional[Dict[str, Any]] = None,
    top_k: int = 3,
) -> Dict[str, Any]:
    """Execute a full Enterprise RAG query under either:
      - `zero_leak` (Pre-Retrieval Identity Propagation + BigQuery RLS + Hybrid RRF + Grounded Citations)
      - `naive_confused_deputy` (Shared Admin Service Account + System-Prompt-Only 'Guardrail')
    """
    t0 = time.time()
    if not (query or "").strip():
        raise ValueError("Query must not be empty.")
    persona = next((p for p in PERSONAS if p["id"] == persona_id), None)
    if persona is None:
        raise ValueError(f"Unknown persona_id: {persona_id!r}")
    if search_strategy not in SEARCH_STRATEGIES:
        raise ValueError(f"Unknown search_strategy: {search_strategy!r} (expected one of {SEARCH_STRATEGIES})")
    if security_mode not in SECURITY_MODES:
        raise ValueError(f"Unknown security_mode: {security_mode!r} (expected one of {SECURITY_MODES})")
    corpus = build_unified_corpus()
    armor = check_model_armor_input(query)

    authorized_pool: List[Dict[str, Any]] = []
    blocked_records: List[Dict[str, Any]] = []

    for rec in corpus:
        allowed, reason = check_principal_access(rec, persona)
        rec_with_acl = dict(rec)
        rec_with_acl["caller_authorized"] = allowed
        rec_with_acl["acl_decision_reason"] = reason
        if allowed:
            authorized_pool.append(rec_with_acl)
        else:
            blocked_records.append(rec_with_acl)

    if security_mode == "naive_confused_deputy":
        # Over-privileged service account indexes and retrieves across ALL records regardless of caller ACLs!
        retrieved = score_candidates_hybrid(query, authorized_pool + blocked_records, strategy=search_strategy, top_k=top_k)
    else:
        # Zero-Leak: Pre-filter BEFORE scoring so unauthorized records never enter memory or context!
        retrieved = score_candidates_hybrid(query, authorized_pool, strategy=search_strategy, top_k=top_k)

    leaked_chunks = [c for c in retrieved if not c.get("caller_authorized", True)]
    context_block = "\n\n".join(
        f"[{c['id']}] ({c['connector']} | Sensitivity: {c['sensitivity']})\nTitle: {c['title']}\nContent: {c['content']}"
        for c in retrieved
    )

    if security_mode == "naive_confused_deputy":
        sys_prompt = (
            f"You are an internal assistant answering {persona['name']} ({persona['title']}). "
            "Use the retrieved context chunks below to answer the user's question concisely with [ID] citations."
        )
    else:
        sys_prompt = (
            f"You are an identity-aware enterprise AI assistant answering {persona['name']} ({persona['title']}). "
            "Every chunk below has already been pre-filtered for this user's IAM groups and "
            "BigQuery Row-Level Access Policies. Answer ONLY from the provided chunks, include [ID] citations "
            "(e.g. [DOC-SALES-002] or [BQ-ROW-101]), and if the answer is not in the authorized context, state clearly "
            "that no authorized records matched."
        )

    usr_prompt = f"Retrieved Context Chunks:\n{context_block or '(No authorized chunks matched)'}\n\nUser Question: {query}"

    cfg = llm_config or {"provider": "ollama", "model": "llama3.2:3b"}
    used_model = cfg.get("model") or "llama3.2:3b"
    answer = ""
    llm_error: Optional[str] = None
    try:
        answer, used_model = _call_llm_for_rag(cfg, sys_prompt, usr_prompt)
        if not answer:
            llm_error = "The model returned an empty response."
    except Exception as exc:  # noqa: BLE001
        llm_error = _describe_llm_error(exc)

    llm_fallback_used = not answer
    if llm_fallback_used:
        # No LLM answer: show the top retrieved chunk verbatim, and say so (never pass it off as model output).
        if not retrieved:
            answer = "No authorized documents or warehouse rows matched your query under your current IAM scope."
        else:
            top = retrieved[0]
            answer = f"Based on [{top['id']}] ({top['title']}): {top['content']}"

    cited_ids = list(dict.fromkeys(re.findall(r"\[([A-Z]+-[A-Z0-9\-]+)\]", answer)))
    retrieved_ids = {c["id"] for c in retrieved}
    valid_citations = [cid for cid in cited_ids if cid in retrieved_ids]
    invalid_citations = [cid for cid in cited_ids if cid not in retrieved_ids]
    # Share of cited IDs that really are in the retrieved context; None when the answer cites nothing.
    grounding_score = round(100 * len(valid_citations) / len(cited_ids)) if cited_ids else None

    latency_ms = round((time.time() - t0) * 1000.0, 1)
    return {
        "ok": True,
        "security_mode": security_mode,
        "search_strategy": search_strategy,
        "persona": persona,
        "model_armor": armor,
        "total_corpus_records": len(corpus),
        "authorized_pool_count": len(authorized_pool),
        "blocked_by_acl_count": len(blocked_records),
        "blocked_summary": [
            {"id": b["id"], "title": b["title"], "reason": b["acl_decision_reason"]}
            for b in blocked_records
        ],
        "retrieved_chunks": retrieved,
        "data_leak_occurred": len(leaked_chunks) > 0,
        "leaked_chunk_ids": [c["id"] for c in leaked_chunks],
        "llm_provider": (cfg.get("provider") or "ollama").lower(),
        "llm_model": used_model,
        "llm_fallback_used": llm_fallback_used,
        "llm_error": llm_error,
        "answer": answer,
        "cited_ids": cited_ids,
        "valid_citations": valid_citations,
        "invalid_citations": invalid_citations,
        "grounding_score_pct": grounding_score,
        "latency_ms": latency_ms,
    }


def evaluate_architecture_tradeoff(params: Dict[str, Any]) -> Dict[str, Any]:
    """Interactive Architect Calculator comparing:
      1. Enterprise Hybrid RAG (Vertex AI Search / Grounding)
      2. Long-Context Window Stuffing + Context Caching (Gemini 1M–2M Context)
      3. Supervised Fine-Tuning (SFT / LoRA Adapter)
    """
    corpus_tokens = int(params.get("corpus_tokens", 2_500_000))
    update_freq = str(params.get("update_freq", "hourly")).lower()       # realtime | hourly | monthly | static
    queries_per_day = int(params.get("queries_per_day", 5000))
    needs_acls = bool(params.get("needs_acls", True))
    needs_citations = bool(params.get("needs_citations", True))
    goal = str(params.get("goal", "factual_qa")).lower()                # factual_qa | style_format | deep_single_doc

    monthly_queries = queries_per_day * 30

    # Cost & latency estimates (illustrative enterprise order-of-magnitude math)
    # 1. Hybrid RAG: ~2,500 retrieved prompt tokens + 300 output tokens per query + index hosting
    rag_input_cost = (monthly_queries * 2500 / 1_000_000) * 0.15
    rag_output_cost = (monthly_queries * 300 / 1_000_000) * 0.60
    rag_index_cost = max(60.0, (corpus_tokens / 1_000_000) * 18.0)
    rag_monthly_usd = round(rag_input_cost + rag_output_cost + rag_index_cost, 2)
    rag_p95_ms = 1150

    # 2. Long-Context (1M-2M): only feasible if corpus_tokens <= 1,800,000 AND no per-doc row ACL split
    lc_feasible = corpus_tokens <= 1_800_000 and not needs_acls
    effective_lc_tokens = min(corpus_tokens, 2_000_000)
    # Context caching cuts input token price ~75% when static/monthly, NOT when changing realtime per-user
    cache_discount = 0.28 if (update_freq in ("monthly", "static") and not needs_acls) else 1.0
    lc_monthly_usd = round(
        (monthly_queries * effective_lc_tokens / 1_000_000) * 0.15 * cache_discount
        + (monthly_queries * 300 / 1_000_000) * 0.60,
        2,
    )
    lc_p95_ms = int(900 + (effective_lc_tokens / 100_000) * 260)

    # 3. Fine-Tuning (SFT): low per-query token cost, CANNOT enforce per-user ACLs or real-time facts/citations
    sft_retrain_runs = {"realtime": 30, "hourly": 30, "monthly": 1, "static": 1}.get(update_freq, 4)
    sft_train_cost = sft_retrain_runs * 180.0
    sft_infer_cost = (monthly_queries * 800 / 1_000_000) * 0.20
    sft_monthly_usd = round(sft_train_cost + sft_infer_cost, 2)
    sft_p95_ms = 680

    lc_small_static = lc_feasible and corpus_tokens <= 450_000 and update_freq in ("static", "monthly")
    # Long-context only wins when re-sending the corpus on every query stays within ~3x the RAG bill.
    lc_cost_ok = lc_monthly_usd <= 3 * rag_monthly_usd

    if goal == "style_format" and not needs_citations and not needs_acls:
        recommended = "Supervised Fine-Tuning (SFT) — or SFT + RAG Hybrid"
        rationale = (
            "Fine-tuning excels at teaching consistent output schemas, domain jargon, or classification tone—NOT "
            "memorizing changing enterprise facts or enforcing document ACLs. If factual freshness or citations are "
            "also needed, pair a lightweight SFT model with Hybrid RAG."
        )
        script = (
            "\"For this workload I would recommend supervised fine-tuning. The goal is a consistent tone or output "
            "schema, not fresh facts, and there is no per-user ACL or citation requirement, so changing model "
            f"behavior is the right lever (roughly ${sft_monthly_usd:,.0f}/mo in this estimate). Fine-tuning does not "
            "teach live knowledge or permissions, so if they later need current facts or citations I would add "
            "Hybrid RAG next to the tuned model rather than retrain more often.\""
        )
    elif lc_small_static and lc_cost_ok:
        recommended = "Long-Context Window (1M+) + Vertex AI Context Caching"
        rationale = (
            f"Because the entire corpus ({corpus_tokens:,} tokens) fits comfortably inside Gemini's context window, "
            "rarely changes, and has uniform permissions (no per-user ACL split), Context Caching avoids chunk-boundary "
            "loss and enables cross-document reasoning without building a retrieval pipeline. In this estimate it costs "
            f"~${lc_monthly_usd:,.0f}/mo vs. ~${rag_monthly_usd:,.0f}/mo for Hybrid RAG at this query volume."
        )
        script = (
            f"\"For this workload I would recommend long-context with context caching. The whole corpus is about "
            f"{corpus_tokens:,} tokens, it fits in the context window, it rarely changes, and everyone has the same "
            "permissions, so I would skip the retrieval pipeline and let the model reason across the full documents. "
            f"The trade-off is cost and latency per query (roughly ${lc_monthly_usd:,.0f}/mo vs. "
            f"${rag_monthly_usd:,.0f}/mo for RAG in this estimate), so I would move to Hybrid RAG if the corpus grows, "
            "query volume climbs, or per-user ACLs appear.\""
        )
    else:
        recommended = "Identity-Propagated Hybrid RAG (Vertex AI Search / Grounding)"
        reasons = []
        if needs_acls:
            reasons.append("per-user IAM & row-level ACL pre-filtering cannot be safely enforced via model weights or a shared cached prompt")
        if corpus_tokens > 1_800_000:
            reasons.append(f"the corpus ({corpus_tokens:,} tokens) exceeds single-prompt context limits and would explode latency/cost")
        if update_freq in ("realtime", "hourly"):
            reasons.append(f"{update_freq} data updates require instant index/SQL reflection without retraining or busting context caches")
        if needs_citations:
            reasons.append("auditable chunk-level grounding citations are mandatory")
        if lc_feasible and lc_monthly_usd > rag_monthly_usd:
            reasons.append(
                f"re-sending {effective_lc_tokens:,} tokens on every query is estimated at ~${lc_monthly_usd:,.0f}/mo "
                f"vs. ~${rag_monthly_usd:,.0f}/mo for retrieval at {queries_per_day:,} queries/day"
            )
        if not reasons:
            reasons.append("retrieval keeps each prompt small, so cost and latency stay flat as the corpus and query volume grow")
        rationale = "Recommended because " + "; and ".join(reasons) + "."
        script = (
            f"\"For this workload, I would recommend {recommended}. Fine-tuning changes model behavior and format—not "
            f"live knowledge or user permissions—and stuffing {effective_lc_tokens:,} tokens into every prompt "
            f"{'breaks per-user ACL caching and ' if needs_acls else ''}costs ~${lc_monthly_usd:,.0f}/mo vs. "
            f"~${rag_monthly_usd:,.0f}/mo for Hybrid RAG at ~{rag_p95_ms} ms p95 latency.\""
        )

    return {
        "recommended_pattern": recommended,
        "architect_rationale": rationale,
        "interview_30s_script": script,
        "pricing_note": PRICING_NOTE,
        "options": [
            {
                "name": "Identity-Propagated Hybrid RAG",
                "est_monthly_cost_usd": rag_monthly_usd,
                "est_p95_latency_ms": rag_p95_ms,
                "supports_per_user_acls": True,
                "supports_realtime_updates": True,
                "supports_citations": True,
                "verdict": "BEST FIT" if "RAG" in recommended and "SFT" not in recommended else "STRONG COMPLEMENT",
            },
            {
                "name": "Long-Context (1M+) + Context Caching",
                "est_monthly_cost_usd": lc_monthly_usd,
                "est_p95_latency_ms": lc_p95_ms,
                "supports_per_user_acls": False,
                "supports_realtime_updates": update_freq not in ("realtime",),
                "supports_citations": True,
                "verdict": "BEST FIT" if "Long-Context" in recommended else ("INFEASIBLE (>Context / ACLs)" if not lc_feasible else "HIGHER COST AT SCALE"),
            },
            {
                "name": "Supervised Fine-Tuning (SFT / LoRA)",
                "est_monthly_cost_usd": sft_monthly_usd,
                "est_p95_latency_ms": sft_p95_ms,
                "supports_per_user_acls": False,
                "supports_realtime_updates": False,
                "supports_citations": False,
                "verdict": "BEST FIT" if recommended.startswith("Supervised") else "WRONG TOOL FOR FACTS/ACLS",
            },
        ],
    }
