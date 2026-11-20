#!/usr/bin/env python3
"""Zero-Leak Enterprise RAG & Connector Lab — Zero-Dependency HTTP Server (Port 8111)."""

from __future__ import annotations

import argparse
import json
import mimetypes
from concurrent.futures import ThreadPoolExecutor
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict
from urllib.parse import urlparse

from raglab import __version__
from raglab.corpus import CODE_BUG_CHALLENGES, PERSONAS
from raglab.engine import (
    build_unified_corpus,
    evaluate_architecture_tradeoff,
    get_llm_status,
    run_rag_query,
)

ROOT_DIR = Path(__file__).resolve().parent


class ZeroLeakRagHandler(BaseHTTPRequestHandler):
    server_version = f"ZeroLeakRAGLab/{__version__}"

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        return

    def _send_json(self, payload: Any, status: int = HTTPStatus.OK) -> None:
        raw = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(raw)

    def _read_json(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        data = json.loads(raw) if raw.strip() else {}
        if not isinstance(data, dict):
            raise ValueError("Request body must be a JSON object.")
        return data

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        route = urlparse(self.path).path

        if route == "/api/health":
            llm = get_llm_status()
            self._send_json({
                "status": "ok",
                "service": "zero-leak-rag-lab",
                "version": __version__,
                "personas_count": len(PERSONAS),
                "corpus_records_count": len(build_unified_corpus()),
                "ollama_connected": llm["ollama_connected"],
                "ollama_models": llm["ollama_models"],
            })
            return

        if route == "/api/bootstrap":
            self._send_json({
                "personas": PERSONAS,
                "corpus": build_unified_corpus(),
                "bug_challenges": CODE_BUG_CHALLENGES,
                "llm": get_llm_status(),
            })
            return

        if route in ("/", "/index.html"):
            target = ROOT_DIR / "index.html"
        elif route.startswith("/static/"):
            target = (ROOT_DIR / route.lstrip("/")).resolve()
            if not str(target).startswith(str((ROOT_DIR / "static").resolve())):
                self._send_json({"error": "Forbidden"}, status=HTTPStatus.FORBIDDEN)
                return
        else:
            self._send_json({"error": f"Not found: {route}"}, status=HTTPStatus.NOT_FOUND)
            return

        if not target.is_file():
            self._send_json({"error": "Asset not found"}, status=HTTPStatus.NOT_FOUND)
            return

        data = target.read_bytes()
        mime, _ = mimetypes.guess_type(str(target))
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mime or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self) -> None:  # noqa: N802
        route = urlparse(self.path).path
        try:
            body = self._read_json()
        except Exception as exc:  # noqa: BLE001
            self._send_json({"error": f"Invalid JSON: {exc}"}, status=HTTPStatus.BAD_REQUEST)
            return

        try:
            if route == "/api/rag/query":
                self._send_json(self._handle_rag_query(body))
            elif route == "/api/architect/tradeoff":
                self._send_json(evaluate_architecture_tradeoff(body))
            else:
                self._send_json({"error": f"Unknown endpoint: {route}"}, status=HTTPStatus.NOT_FOUND)
        except (ValueError, TypeError) as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
        except Exception as exc:  # noqa: BLE001
            self._send_json(
                {"error": f"Internal error: {type(exc).__name__}: {exc}"},
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    @staticmethod
    def _handle_rag_query(body: Dict[str, Any]) -> Dict[str, Any]:
        query = str(body.get("query") or "").strip()
        if not query:
            raise ValueError("Query must not be empty.")
        persona_id = str(body.get("persona_id") or "jordan_sales_west")
        strategy = str(body.get("search_strategy") or "hybrid_rrf")
        llm_config = body.get("llm_config") or {"provider": "ollama", "model": "llama3.2:3b"}
        if not isinstance(llm_config, dict):
            raise ValueError("llm_config must be a JSON object like {\"provider\": \"ollama\", \"model\": \"llama3.2:3b\"}.")
        compare_both = bool(body.get("compare_both", True))

        def run(mode: str) -> Dict[str, Any]:
            return run_rag_query(
                query=query,
                persona_id=persona_id,
                security_mode=mode,
                search_strategy=strategy,
                llm_config=llm_config,
            )

        if not compare_both:
            return run(str(body.get("security_mode") or "zero_leak"))

        # Validate inputs once up front (raises ValueError -> HTTP 400), then run both pipelines
        # concurrently so the side-by-side view costs one LLM round-trip of wall time, not two.
        with ThreadPoolExecutor(max_workers=2) as pool:
            zero_leak_future = pool.submit(run, "zero_leak")
            naive_future = pool.submit(run, "naive_confused_deputy")
            zero_leak = zero_leak_future.result()
            naive = naive_future.result()
        return {
            "ok": True,
            "compare_both": True,
            "query": query,
            "naive_confused_deputy": naive,
            "zero_leak_acl_enforced": zero_leak,
        }


def create_server(host: str = "127.0.0.1", port: int = 8111) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), ZeroLeakRagHandler)


def main() -> int:
    parser = argparse.ArgumentParser(description="Zero-Leak Enterprise RAG & Connector Lab (Port 8111)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8111)
    args = parser.parse_args()
    srv = create_server(args.host, args.port)
    print(f"Zero-Leak Enterprise RAG Lab listening on http://{args.host}:{args.port}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
