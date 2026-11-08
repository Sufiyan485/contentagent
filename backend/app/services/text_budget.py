"""Compact evidence and schema projections; originals remain unchanged in storage."""
from copy import deepcopy
import json


def compact_report(report):
    data=report.model_dump(mode='json')
    passages=[]; claims=[]
    for claim in data['claims']:
        evidence=[]
        for entry in claim['evidence']:
            passage={k:v for k,v in entry.items() if v is not None}
            if passage not in passages: passages.append(passage)
            evidence.append(passages.index(passage))
        claims.append({k:claim[k] for k in ('id','text','verification_status','limitations')} | {'evidence_refs':evidence})
    return {k:data[k] for k in ('origin','topic','summary','warnings','limitations')} | {
        'sources':[{k:s[k] for k in ('id','url','title','published_at')} for s in data['sources']],
        'claims':claims,'evidence_passages':passages,
    }


def compact_schema(schema):
    schema=deepcopy(schema)
    defs=schema.get('$defs',{})
    if 'GeneratedConcept' in defs:
        defs['GeneratedConcept']['properties'].pop('platform_variants',None)
        defs.pop('PlatformCreative',None)
    def strip(node):
        if isinstance(node,dict):
            return {k:strip(v) for k,v in node.items() if k not in ('title','description','default')}
        if isinstance(node,list): return [strip(v) for v in node]
        return node
    result=strip(schema)
    result['title']=schema.get('title','Output')
    return result


def completion_budget(prompt):
    """Bound output by requested work; unknown/revision schemas retain a larger cap."""
    try:
        payload=json.JSONDecoder().raw_decode(prompt.split('\n',1)[1])[0]
        request=payload.get('request')
        if request:
            captions=len(request.get('platforms',['instagram']))
            words={'concise':70,'balanced':160,'detailed':240}.get(request.get('caption_length'),160)
            return min(6000,1000+request.get('concept_count',1)*(request.get('slide_count',1)*350+captions*(words*2+150)))
    except (ValueError,IndexError,TypeError): pass
    return 6000
