import asyncio, json
from pathlib import Path
from statistics import mean
import _bootstrap  # noqa: F401
from app.config import get_settings
from app.db import engine
from app.services.rag import get_rag_service
from app.security import AuthUser
from app.services.acl import accessible_document_ids


EVAL_USER = AuthUser(
    id="00000000-0000-0000-0000-000000000012",
    tenant_id="00000000-0000-0000-0000-000000000001",
    tenant_slug="devpilot", username="engineer", role="MEMBER",
)


async def filtered_dense(rag, query, allowed):
    items = await rag.dense_search(query, top_k=60)
    return [item for item in items if int(item.get("document_id", -1)) in allowed][:5]


def load_cases():
    return [json.loads(x) for x in Path('data/eval/retrieval_cases.jsonl').read_text(encoding='utf-8').splitlines() if x.strip()]


def metrics(ranks):
    out={}
    for k in (1,3,5):
        out[f'Recall@{k}']=sum(r is not None and r<=k for r in ranks)/len(ranks)
    out['MRR']=mean((1.0/r if r else 0.0) for r in ranks)
    return out


async def run_variant(name, search_fn):
    ranks=[]
    for case in load_cases():
        items=await search_fn(case['question'])
        titles=[x.get('title') for x in items]
        expected=set(case.get('expected_docs') or [case['expected_doc']])
        rank=next((i+1 for i,t in enumerate(titles) if t in expected),None)
        ranks.append(rank)
        print(name, case['id'], 'rank=', rank, 'titles=', titles[:5])
    result=metrics(ranks)
    print(name, json.dumps(result,ensure_ascii=False,indent=2))
    return result


async def main():
    rag=get_rag_service()
    report={}
    print('\n=== DENSE ONLY ===')
    allowed=await accessible_document_ids(EVAL_USER)
    report['dense']=await run_variant('dense',lambda q: filtered_dense(rag,q,allowed))
    print('\n=== HYBRID RRF ===')
    report['hybrid']=await run_variant('hybrid',lambda q: rag.hybrid_search(q,final_top_k=5,use_rerank=False,allowed_document_ids=allowed))
    if get_settings().rerank_enabled:
        print('\n=== HYBRID + RERANK ===')
        report['hybrid_rerank']=await run_variant('hybrid+rerank',lambda q: rag.hybrid_search(q,final_top_k=5,use_rerank=True,allowed_document_ids=allowed))
    else:
        print('\n[RERANK SKIPPED] .env 中 RERANK_ENABLED=false。')
    Path('reports').mkdir(exist_ok=True)
    Path('reports/retrieval_eval.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('WROTE reports/retrieval_eval.json')
    await engine.dispose()

if __name__=='__main__':
    asyncio.run(main())
