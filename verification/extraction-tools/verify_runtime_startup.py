from pathlib import Path
import os, socket, json
D=Path.cwd()
os.environ['LANGSMITH_TRACING']='false';os.environ['LANGCHAIN_TRACING_V2']='false'
_original=socket.socket.connect
def offline(sock,address):
 if isinstance(address,tuple) and address[0] not in ('127.0.0.1','localhost','::1'):raise AssertionError('External network prohibited')
 return _original(sock,address)
socket.socket.connect=offline
from fastapi.testclient import TestClient
from backend.app.main import create_app
from backend.app.config import Settings, ROOT
assert ROOT==D
assert not (D/'.env').exists()
assert not (D/'data/app.sqlite3').exists(),'Runtime smoke requires a new empty standalone DB'
settings=Settings(_env_file=None,app_data_dir=D/'data',content_api_key='',pollinations_api_key='')
assert 'http://127.0.0.1:8001' in settings.app_allowed_origins
app=create_app(settings,start_worker=True)
with TestClient(app) as client:
 assert client.get('/api/v1/health').status_code==200
 assert client.get('/api/v1/research-reports').json()==[]
 assert client.get('/api/v1/content').json()['total']==0
 assert client.get('/api/v1/generation-jobs').json()['total']==0
 assert client.get('/api/v1/health',headers={'Origin':'http://127.0.0.1:8001'}).status_code==200
 assert client.get('/api/v1/health',headers={'Origin':'https://untrusted.example'}).status_code==403
 result={'root_is_standalone':True,'database_created':settings.database_path.is_file(),'normal_worker_startup_and_shutdown':True,'seeded_reports':0,'generation_jobs':0,'content_items':0,'own_port_origin_allowed':True,'untrusted_origin_rejected':True,'external_network_blocked':True}
(D/'verification/runtime-startup.json').write_text(json.dumps(result,indent=2))
p=D/'finish_extraction.py';text=p.read_text();text=text.replace('There is no default runtime `data/app.sqlite3` until startup; the verified databases are isolated test databases.','An empty independent `data/app.sqlite3` was initialized by a separate normal-worker startup/shutdown smoke check; it contains no reports, generation jobs or content. The test suite uses its own isolated databases. See `verification/runtime-startup.json`.');p.write_text(text,encoding='utf-8')
print(json.dumps(result,indent=2))
