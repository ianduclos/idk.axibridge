"""Draft-only Mosca 2 operations; Keep uses the ordinary source/resolve path."""
import json
from pathlib import Path
from fastapi import APIRouter,HTTPException
from .mosca2.jobs import RunRequest,manager,status

router=APIRouter(prefix='/mosca2',tags=['mosca2'])

@router.get('/status')
def runtime_status():return status()

@router.get('/materials')
def materials():
    return json.loads((Path(__file__).parent/'mosca2/materials.json').read_text())

@router.post('/jobs')
def start(request:RunRequest):
    try:return manager.start(request)
    except (RuntimeError,OSError) as exc:raise HTTPException(409,str(exc)) from exc

@router.get('/jobs/{id}')
def get(id:str):
    try:return manager.get(id)
    except KeyError:raise HTTPException(404,'Unknown fly run') from None

@router.delete('/jobs/{id}')
def cancel(id:str):
    try:return manager.cancel(id)
    except KeyError:raise HTTPException(404,'Unknown fly run') from None
