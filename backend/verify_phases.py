#!/usr/bin/env python3
"""Comprehensive verification of Phase 0-3 implementation.

Usage:
    python verify_phases.py              # Static checks only
    python verify_phases.py --runtime    # Static + runtime (requires server running)
    python verify_phases.py --eval       # Static + RAGAS evaluation comparison
"""

import ast
import os
import sys
from pathlib import Path

APP_DIR = Path(__file__).parent / "app"
ROOT = Path(__file__).parent

errors = []
warnings = []


def check_file(relpath, required_symbols, phase=""):
    """Verify a file parses and contains required symbols."""
    path = ROOT / relpath
    if not path.exists():
        errors.append(f"[{phase}] {relpath}: FILE NOT FOUND")
        return False
    try:
        src = path.read_text()
        # Detect corruption
        if '\x00' in src:
            errors.append(f"[{phase}] {relpath}: CORRUPTED (null bytes)")
            return False
        ast.parse(src)
        for sym in required_symbols:
            if sym not in src:
                errors.append(f"[{phase}] {relpath}: MISSING '{sym}'")
        return True
    except SyntaxError as e:
        errors.append(f"[{phase}] {relpath}: SYNTAX ERROR {e}")
        return False


def check_no_symbol(relpath, forbidden, phase=""):
    """Verify a symbol has been removed."""
    path = ROOT / relpath
    if not path.exists():
        return
    src = path.read_text()
    for sym in forbidden:
        if sym in src:
            errors.append(f"[{phase}] {relpath}: STALE '{sym}' should be removed")


# ================================================================
# PHASE 0: Baseline + Migrations
# ================================================================
print("=" * 60)
print("PHASE 0: Baseline + Agent Migration + Cache Warmup")
print("=" * 60)

check_file("app/rag/retriever.py", [
    "def retrieve_evidence(",
    "def retrieve_evidence_with_retry(",
    "def warmup_query_cache(",
    "def retrieve_documents(",
    "def _multi_route_search(",
], "P0")

check_no_symbol("app/rag/retriever.py", [
    "from app.rag.context import (\n    kg_context_supplement as _kg_context_supplement,",
    "kg_context_supplement as _kg_context_supplement",
], "P0")

check_file("app/agents/knowledge_agent.py", ["retrieve_evidence"], "P0")
check_file("app/agents/grading_agent.py", ["retrieve_evidence"], "P0")
check_file("app/agents/path_agent.py", ["retrieve_evidence"], "P0")
check_file("app/rag/ingest.py", ["warmup_query_cache"], "P0")

# Baseline evaluation
baseline = ROOT / "data" / "evaluation" / "baseline_20260519.json"
if baseline.exists():
    print(f"  [OK] P0: Baseline exists: {baseline}")
else:
    warnings.append("[P0] Baseline file not found. Run: python -m app.evaluation.cli --dataset baseline.jsonl")

print(f"  Phase 0: {'PASSED' if not errors else 'ISSUES FOUND'}")

# ================================================================
# PHASE 1: Evidence Pipeline
# ================================================================
print("\n" + "=" * 60)
print("PHASE 1: EvidenceVerifier + Retry + QueryClassifier + Token Budget")
print("=" * 60)

check_file("app/rag/verifier.py", [
    "class Verdict",
    "class VerificationResult",
    "def verify_evidence(",
    "def is_retrieval_sufficient(",
    "_run_rule_checks",
    "retry_hints",
], "P1")

check_file("app/rag/retriever.py", [
    "retrieve_evidence_with_retry",
    "VerificationResult",
    "max_retries",
], "P1")

check_file("app/rag/query_classifier.py", [
    "with_structured_output",
    "QueryClassifyResult",
], "P1")

check_no_symbol("app/rag/query_classifier.py", [
    "StrOutputParser",
    ".split(',')",
], "P1")

check_file("app/config.py", [
    "CONTEXT_TOKEN_BUDGET",
    "MAX_STUDENT_PROFILE_TOKENS",
], "P1")

check_file("app/rag/fusion.py", [
    "settings.CONTEXT_TOKEN_BUDGET",
    "settings.MAX_STUDENT_PROFILE_TOKENS",
], "P1")

print(f"  Phase 1: {'PASSED' if not errors else 'ISSUES FOUND'}")

# ================================================================
# PHASE 2: Agentic RAG
# ================================================================
print("\n" + "=" * 60)
print("PHASE 2: Adaptive Depth + Reflection + KG Evidence + Tool Layering")
print("=" * 60)

check_file("app/rag/query_classifier.py", [
    "class RetrievalDepth",
    "def resolve_retrieval_depth(",
    "SHALLOW_DEPTH",
    "STANDARD_DEPTH",
    "DEEP_DEPTH",
    "CODE_DEPTH",
    "TEXT_ONLY_DEPTH",
    "skip_rerank",
], "P2")

check_file("app/agents/reflection_agent.py", [
    "class ReflectionResult",
    "def reflect(",
    "def apply_reflection_to_answer(",
    "_rule_signals",
    "_llm_reflection",
], "P2")

check_file("app/agents/supervisor.py", [
    "from app.agents.reflection_agent import reflect, apply_reflection_to_answer",
], "P2")

check_file("app/rag/evidence.py", [
    "def kg_evidence_from_query(",
    "kg.get_prerequisites",
    "kg.get_next_topics",
    "kg.get_learning_path",
    "nodes=nodes,",
    "edges=edges,",
    "paths=path_list,",
], "P2")

check_file("app/rag/fusion.py", [
    "kg_evidences: list[KGEvidence] | None = None",
    "if kg_evidences is not None:",
], "P2")

check_file("app/agents/knowledge_agent.py", [
    '@tool("text_search")',
    '@tool("knowledge_search")',
    "atext_search",
    "aknowledge_search",
    "TEXT_ONLY_DEPTH",
], "P2")

check_file("app/agents/kg_tools.py", [
    '@tool("kg_search")',
    "akg_search",
    "kg_evidence_from_query",
], "P2")

print(f"  Phase 2: {'PASSED' if not errors else 'ISSUES FOUND'}")

# ================================================================
# PHASE 3: Multi-Agent RAG
# ================================================================
print("\n" + "=" * 60)
print("PHASE 3: Planner + Synthesis + LangGraph Fan-out")
print("=" * 60)

check_file("app/agents/planner_agent.py", [
    "class SubTask",
    "class ExecutionPlan",
    "def create_plan(",
    "def should_use_planner(",
    "_parse_plan",
], "P3")

check_file("app/agents/synthesis_agent.py", [
    "class AgentOutput",
    "class SynthesisResult",
    "def synthesize(",
    "_deduplicate_outputs",
], "P3")

check_file("app/agents/supervisor.py", [
    "from langgraph.types import Command, Send",
    "Annotated[list[dict], operator.add]",
    "async def planner_node",
    "async def synthesis_node",
    "def continue_to_agents",
    'builder.add_node("planner_node"',
    'builder.add_node("synthesis_node"',
    'builder.add_node("text_retrieval"',
    'builder.add_node("kg_retrieval"',
    'builder.add_node("parallel_knowledge"',
    'builder.add_conditional_edges("planner_node", continue_to_agents)',
    'builder.add_edge("knowledge_agent", END)',
], "P3")

check_file("app/agents/knowledge_agent.py", [
    "create_text_retrieval_agent",
    "TEXT_RETRIEVAL_PROMPT",
], "P3")

check_file("app/agents/kg_tools.py", [
    "create_kg_retrieval_agent",
    "KG_RETRIEVAL_PROMPT",
], "P3")

print(f"  Phase 3: {'PASSED' if not errors else 'ISSUES FOUND'}")


# ================================================================
# RUNTIME CHECKS (--runtime flag)
# ================================================================
if "--runtime" in sys.argv:
    print("\n" + "=" * 60)
    print("RUNTIME CHECKS")
    print("=" * 60)
    try:
        # Graph compilation test
        from app.agents.supervisor import build_multi_agent_graph
        graph = build_multi_agent_graph()
        print("  [OK] LangGraph builds successfully")
        print(f"  Nodes: {list(graph.nodes.keys())}")

        # Verify critical nodes exist
        required_nodes = {"supervisor", "knowledge_agent", "question_agent",
                         "grading_agent", "path_agent", "planner_node",
                         "text_retrieval", "kg_retrieval", "parallel_knowledge",
                         "synthesis_node"}
        missing = required_nodes - set(graph.nodes.keys())
        if missing:
            errors.append(f"Missing graph nodes: {missing}")
        else:
            print("  [OK] All required nodes present")

    except Exception as e:
        errors.append(f"Graph compilation failed: {e}")

    try:
        # Planner unit test
        from app.agents.planner_agent import _parse_plan
        sample = '{"sub_tasks":[{"id":"t1","query":"What is virtual memory?","recommended_agent":"text_retrieval","reasoning":"test"}],"synthesis_strategy":"merge","complexity":"standard"}'
        plan = _parse_plan(sample)
        assert plan is not None, "parse failed"
        assert len(plan.sub_tasks) == 1, "wrong subtask count"
        assert plan.sub_tasks[0].query == "What is virtual memory?"
        print("  [OK] Planner _parse_plan: sample parses correctly")
    except Exception as e:
        errors.append(f"Planner unit test failed: {e}")

    try:
        # Synthesis unit test
        from app.agents.synthesis_agent import AgentOutput, _deduplicate_outputs
        outputs = [
            AgentOutput(agent_name="a", subtask_id="t1", content="Hello world", confidence=0.8),
            AgentOutput(agent_name="b", subtask_id="t2", content="Hello world", confidence=0.5),
        ]
        deduped = _deduplicate_outputs(outputs)
        assert len(deduped) == 1, f"expected 1 after dedup, got {len(deduped)}"
        assert deduped[0].agent_name == "a", "should keep higher confidence"
        print("  [OK] Synthesis _deduplicate_outputs: works correctly")
    except Exception as e:
        errors.append(f"Synthesis unit test failed: {e}")

    try:
        # Complexity detection test
        from app.agents.planner_agent import should_use_planner
        assert should_use_planner("simple", []) is False
        assert should_use_planner("standard", ["comparison"]) is True
        assert should_use_planner("complex", []) is True
        print("  [OK] should_use_planner: gates correctly")
    except Exception as e:
        errors.append(f"Complexity gate test failed: {e}")

    try:
        # Tool availability test
        from app.agents.knowledge_agent import atext_search, aknowledge_search
        from app.agents.kg_tools import akg_search
        print("  [OK] All 3 tools importable: text_search, knowledge_search, kg_search")
    except Exception as e:
        errors.append(f"Tool import test failed: {e}")

    print(f"  Runtime: {'PASSED' if not errors else 'ISSUES FOUND'}")


# ================================================================
# EVALUATION COMPARISON (--eval flag)
# ================================================================
if "--eval" in sys.argv:
    print("\n" + "=" * 60)
    print("EVALUATION: RAGAS Comparison")
    print("=" * 60)
    print("  Run the following command:")
    print("    python -m app.evaluation.cli --dataset baseline.jsonl --output-tag phase3_check")
    print()
    print("  Then compare against baseline:")
    print("    python -m app.evaluation.cli --compare baseline_20260519.json phase3_check.json")
    print()
    print("  Target improvements:")
    print("    - context_precision: currently 0.15 (target > 0.30 with KG evidence boost)")
    print("    - context_recall:     currently 0.53 (target > 0.60 with Adaptive Depth)")
    print("    - faithfulness:       currently 0.94 (maintain or improve)")
    print("    - answer_relevancy:   currently 0.71 (target > 0.75)")


# ================================================================
# SUMMARY
# ================================================================
print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)

if errors:
    print(f"\nFAILED: {len(errors)} error(s)")
    for e in errors:
        print(f"  [!] {e}")
    sys.exit(1)
else:
    print("\nALL STATIC CHECKS PASSED")
    print()

# Verification checklist
print("Manual verification checklist:")
print("-" * 40)
checks = [
    ("P0", "Server starts without import errors", "curl http://localhost:8000/agent-graph"),
    ("P0", "Cache warmup logged after ingest", "Check logs for 'Cache warmup done'"),
    ("P1", "EvidenceVerifier logs verdict on each query", "Check logs for 'evidence_verdict'"),
    ("P1", "Query classifier uses structured output", "No StrOutputParser in query_classifier.py"),
    ("P2", "Shallow queries (simple concepts) < 1.5s latency", "Check metrics for latency_p50"),
    ("P2", "Reflection warnings on insufficient evidence", "Ask a niche question, check for reminder suffix"),
    ("P2", "KG evidence has nodes/edges/paths populated", "Check logs: 'KG evidence structured: nodes=X edges=Y'"),
    ("P2", "Agent chooses different tools for different queries", "Check logs for tool selection (text_search vs kg_search)"),
    ("P3", "Comparison queries route through planner", "Ask 'Compare virtual memory and cache', check for planner_node in logs"),
    ("P3", "Planner produces >=2 subtasks for cross-discipline", "Check logs: 'Planner: 2+ subtasks'"),
    ("P3", "Synthesis merges parallel outputs", "Check logs: 'Synthesis complete: N inputs'"),
    ("P3", "Simple queries still use fast path", "Ask 'What is a stack?', check supervisor routes to knowledge_agent directly"),
]
for phase, check, how in checks:
    print(f"  [{phase}] {check}")
    print(f"       How: {how}")
    print()

if warnings:
    print("Warnings:")
    for w in warnings:
        print(f"  [!] {w}")
