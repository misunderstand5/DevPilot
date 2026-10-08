import asyncio,json,time,statistics,os
from pathlib import Path
import httpx
API_URL=os.getenv('DEVPILOT_API_URL','http://127.0.0.1:8001').rstrip('/')
async def main():
    password=os.getenv('DEVPILOT_PASSWORD')
    if not password: raise RuntimeError('DEVPILOT_PASSWORD is required')
    cases=[json.loads(x) for x in Path('data/eval/agent_cases.jsonl').read_text(encoding='utf-8').splitlines() if x.strip()]
    rows=[]
    async with httpx.AsyncClient(timeout=180, trust_env=False) as c:
        login=await c.post(f'{API_URL}/api/v1/auth/login',json={
            'tenant':os.getenv('DEVPILOT_TENANT','devpilot'),
            'username':os.getenv('DEVPILOT_USERNAME','engineer'),
            'password':password})
        login.raise_for_status(); c.headers['Authorization']='Bearer '+login.json()['access_token']
        for x in cases:
            t=time.perf_counter(); r=await c.post(f'{API_URL}/api/v1/chat',json={'query':x['question'],'bypass_cache':True}); r.raise_for_status(); d=r.json(); ms=(time.perf_counter()-t)*1000
            row={'id':x['id'],'latency_ms':round(ms,1),'intent_ok':d.get('intent')==x['expected_intent'],'tool_ok':x['expected_tool'] in d.get('tools_used',[]),'answer_ok':all(k.lower() in d.get('answer','').lower() for k in x.get('answer_keywords',[]))}
            rows.append(row); print(row)
    l=sorted(z['latency_ms'] for z in rows); s={'intent_accuracy':sum(z['intent_ok'] for z in rows)/len(rows),'tool_success_rate':sum(z['tool_ok'] for z in rows)/len(rows),'answer_keyword_accuracy':sum(z['answer_ok'] for z in rows)/len(rows),'p50_ms':statistics.median(l),'p95_ms':l[max(0,int(len(l)*.95)-1)]}
    Path('reports').mkdir(exist_ok=True); Path('reports/agent_eval.json').write_text(json.dumps({'summary':s,'rows':rows},ensure_ascii=False,indent=2),encoding='utf-8'); print(s)
if __name__=='__main__': asyncio.run(main())
