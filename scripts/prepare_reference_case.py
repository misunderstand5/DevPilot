"""Validate and optionally ingest the pinned Online Boutique reference case."""
import argparse
import asyncio
import json
from pathlib import Path
from urllib.parse import urlparse

import httpx

import _bootstrap  # noqa: F401


ROOT = Path(__file__).resolve().parents[1]
CASE_DIR = ROOT / "data" / "reference_cases" / "online-boutique"
MANIFEST = CASE_DIR / "manifest.json"
TENANT_ID = "00000000-0000-0000-0000-000000000001"
ADMIN_ID = "00000000-0000-0000-0000-000000000011"


def validate_manifest(manifest: dict) -> list[str]:
    errors: list[str] = []
    if manifest.get("source_repository") != "GoogleCloudPlatform/microservices-demo":
        errors.append("unexpected_source_repository")
    tag = str(manifest.get("source_tag", ""))
    if not tag.startswith("v") or tag in {"v0", "main", "latest"}:
        errors.append("source_must_be_pinned_to_a_release_tag")
    for name in manifest.get("knowledge_files", []):
        if not (CASE_DIR / name).is_file():
            errors.append(f"missing_knowledge_file:{name}")
    for url in manifest.get("sources", []):
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.netloc not in {
            "raw.githubusercontent.com", "github.com"
        }:
            errors.append(f"untrusted_source_url:{url}")
        if f"/{tag}/" not in parsed.path:
            errors.append(f"source_not_pinned:{url}")
    if len(manifest.get("service_mapping", {})) < 4:
        errors.append("service_mapping_too_small")
    return errors


async def verify_live_sources(manifest: dict) -> list[dict]:
    rows = []
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        for url in manifest["sources"]:
            try:
                response = await client.get(url, headers={"Range": "bytes=0-4095"})
                rows.append({"url": url, "ok": response.status_code in {200, 206},
                             "status_code": response.status_code})
            except httpx.HTTPError as exc:
                rows.append({"url": url, "ok": False, "error": exc.__class__.__name__})
    return rows


async def ingest(manifest: dict) -> list[dict]:
    from app.db import engine
    from app.services.rag import get_rag_service

    rag = get_rag_service()
    rows = []
    for name in manifest["knowledge_files"]:
        path = CASE_DIR / name
        result = await rag.ingest_file(
            path,
            title=f"online-boutique-v0.10.7_{path.stem}",
            source_uri=f"reference://online-boutique/v0.10.7/{name}",
            tenant_id=TENANT_ID,
            owner_user_id=ADMIN_ID,
            visibility="TENANT",
        )
        rows.append({"file": name, **result})
    await engine.dispose()
    return rows


async def seed_reference_ops() -> dict:
    from sqlalchemy import text
    from app.db import engine, session_scope

    repo = "https://github.com/GoogleCloudPlatform/microservices-demo"
    mapped = ("shipping-service", "notification-service", "inventory-service", "pricing-service")
    async with session_scope() as db:
        for service in mapped:
            await db.execute(text("""
                INSERT INTO service(name,owner_team,repo_url,environment,status,description)
                VALUES(:name,'reference-commerce',:repo,'reference','UNKNOWN',:description)
                ON DUPLICATE KEY UPDATE repo_url=VALUES(repo_url)
            """), {"name": service, "repo": repo,
                    "description": f"Online Boutique v0.10.7 公开参考映射：{service}"})
        await db.execute(text("""
            UPDATE service SET repo_url=:repo
            WHERE name IN ('order-service','payment-service','shipping-service',
                           'notification-service','inventory-service','pricing-service')
        """), {"repo": repo})
        await db.execute(text("""
            INSERT INTO deployment(service_id,version,environment,status,started_at,finished_at,
                                   operator_name,commit_sha,notes)
            SELECT s.id,'v0.10.7','reference','SUCCESS','2026-09-18 00:00:00',
                   '2026-09-18 00:00:00','upstream-release','5b608cb',
                   '公开参考版本；不是 DevPilot 生产发布记录'
            FROM service s WHERE s.name='order-service'
              AND NOT EXISTS (
                SELECT 1 FROM deployment d WHERE d.service_id=s.id
                AND d.version='v0.10.7' AND d.environment='reference'
              )
        """))
    await engine.dispose()
    return {"services_mapped": 6, "release": "v0.10.7", "environment": "reference"}


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="verify pinned upstream URLs")
    parser.add_argument("--ingest", action="store_true", help="index case documents into DevPilot")
    parser.add_argument("--seed-ops", action="store_true", help="add isolated reference release data")
    args = parser.parse_args()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    errors = validate_manifest(manifest)
    report = {"case_id": manifest.get("case_id"), "manifest_valid": not errors, "errors": errors}
    if args.live:
        report["sources"] = await verify_live_sources(manifest)
        if not all(row["ok"] for row in report["sources"]):
            errors.append("one_or_more_live_sources_unavailable")
    if args.ingest and not errors:
        report["ingestion"] = await ingest(manifest)
    if args.seed_ops and not errors:
        report["ops_seed"] = await seed_reference_ops()
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
