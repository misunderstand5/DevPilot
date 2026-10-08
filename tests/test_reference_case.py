import json
from pathlib import Path

from app.services.evidence_quality import assess_evidence
from scripts.prepare_reference_case import CASE_DIR, MANIFEST, validate_manifest


def test_reference_case_is_pinned_and_complete():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert validate_manifest(manifest) == []
    assert manifest["source_tag"] == "v0.10.7"
    assert len(manifest["service_mapping"]) == 6
    assert all((CASE_DIR / name).exists() for name in manifest["knowledge_files"])


def test_reference_eval_dataset_is_valid_jsonl():
    path = Path("data/eval/online_boutique_cases.jsonl")
    cases = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert len(cases) == 8
    assert len({case["id"] for case in cases}) == len(cases)


def test_evidence_quality_passes_grounded_mixed_answer():
    report = assess_evidence({
        "intent": "mixed", "final_answer": "基于文档和发布记录的结论",
        "citations": [{"title": "runbook"}],
        "tools_used": ["recent_deployments", "mcp.github.get_commit"],
        "needs_github_evidence": True,
        "external_evidence": [{"status": "success"}],
    })
    assert report["status"] == "passed"
    assert report["score"] == 1.0


def test_evidence_quality_rejects_unsupported_mixed_answer():
    report = assess_evidence({
        "intent": "mixed", "final_answer": "猜测", "needs_github_evidence": True,
        "citations": [], "tools_used": [], "external_evidence": [],
    })
    assert report["status"] == "insufficient"
    assert report["score"] < 0.5
