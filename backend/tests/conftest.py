"""Prevent any unmocked internet access or inherited credentials in tests."""
import os
from pathlib import Path
import socket
import pytest
ROOT=Path(__file__).resolve().parents[2]
for name in list(os.environ):
    if name.endswith(('_API_KEY','_API_SECRET','_TOKEN')) or name.startswith(('CONTENT_','POLLINATIONS_','LANGSMITH_','LANGCHAIN_','RESEARCH_','SEARCH_','APP_DATA_DIR')):
        os.environ.pop(name,None)
os.environ['LANGSMITH_TRACING']='false'
os.environ['LANGCHAIN_TRACING_V2']='false'
os.environ['PLAYWRIGHT_BROWSERS_PATH']=str(ROOT/'.cache/ms-playwright')
@pytest.fixture(autouse=True)
def offline_sockets(monkeypatch):
    original=socket.socket.connect
    def checked(sock,address):
        if isinstance(address,tuple) and address[0] not in ('127.0.0.1','localhost','::1'):
            raise AssertionError('Unmocked external network access prohibited during extraction tests')
        return original(sock,address)
    monkeypatch.setattr(socket.socket,'connect',checked)
