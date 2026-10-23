"""Provider/model selection and sample scoring for Wiki reranking."""
import asyncio
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.ai import custom_models as cm
from app.ai.llm_catalog import LLM_CATALOG
from app.database import get_db
from app.services.audit_service import log_audit
from app.services.auth_service import require_permission
from app.services.config_service import ConfigService
from app.services.wiki_reranker import ACTIVE_KEY, LEGACY_ID, build_scorer, close_scorer, validate_scores

router = APIRouter()
PERMISSION = 'org:settings:manage'


class SwitchBody(BaseModel):
    model_spec_id: str = Field(min_length=1, max_length=200)


class TestBody(SwitchBody):
    query: str = Field(default='Thủ tục đăng ký xe', min_length=1, max_length=500)
    documents: list[str] = Field(default_factory=lambda:[
        'Hồ sơ, thủ tục đăng ký xe máy và cấp biển số xe.',
        'Thủ tục cấp phiếu lý lịch tư pháp.', 'Quy định về phòng cháy, chữa cháy.'], min_length=1, max_length=10)


@router.get('/settings/rerank/catalog')
async def catalog(db=Depends(get_db), _user=require_permission(PERMISSION)):
    svc, specs = ConfigService(db), []
    for spec in LLM_CATALOG.values():
        specs.append({'id':spec.id, 'provider':spec.provider, 'group':spec.provider,
                      'model_id':spec.model_id, 'label':spec.label, 'custom':False,
                      'api_key_configured':bool(await svc.get(cm.provider_key_config_key('rerank', spec.provider))),
                      'notes':'LLM chấm điểm 0–1; chỉ trả điểm, không sinh câu trả lời.'})
    specs.append({'id':LEGACY_ID, 'provider':'custom', 'group':'custom', 'custom':False,
                  'model_id':await svc.get('reranker_model') or '', 'label':'Reranker HTTP hiện có',
                  'base_url':await svc.get('reranker_base_url'), 'protocol':'rerank',
                  'api_key_configured':bool(await svc.get('reranker_base_url')),
                  'notes':'Giữ cấu hình /rerank hiện có. Thêm model Custom để dùng endpoint mới.'})
    for model in await cm.list_custom(db, 'rerank'):
        specs.append({'id':model.id, 'provider':model.provider, 'group':model.provider,
                      'model_id':model.model_id, 'label':model.label, 'custom':True,
                      'base_url':model.base_url, 'protocol':model.protocol,
                      'api_key_configured':bool(await cm.resolve_api_key(db, model)),
                      'notes':'/rerank chuyên dụng' if model.protocol == 'rerank' else 'LLM chấm điểm 0–1'})
    return {'active_spec_id':await svc.get(ACTIVE_KEY) or LEGACY_ID, 'specs':specs}


@router.post('/settings/rerank/switch')
async def switch(body: SwitchBody, db=Depends(get_db), user=require_permission(PERMISSION)):
    try:
        scorer = await build_scorer(db, body.model_spec_id)
    except ValueError as exc:
        raise HTTPException(400, 'Model chưa có cấu hình hoặc API key hợp lệ.') from exc
    svc = ConfigService(db)
    await svc.set(ACTIVE_KEY, body.model_spec_id)
    from app.services.wiki_reranker import HTTPReranker
    if isinstance(scorer, HTTPReranker):
        await svc.set('reranker_base_url', scorer.base_url)
        await svc.set('reranker_model', scorer.model)
        if scorer.api_key:
            await svc.set('reranker_api_key', scorer.api_key)
    await log_audit(db, user, 'switch_rerank_model', 'app_config', ACTIVE_KEY, reason=f'model={body.model_spec_id}')
    await db.commit()
    return {'active_spec_id':body.model_spec_id}


@router.post('/settings/rerank/test')
async def test(body: TestBody, db=Depends(get_db), _user=require_permission(PERMISSION)):
    if any(len(d) > 2400 for d in body.documents):
        raise HTTPException(422, 'Mỗi đoạn thử tối đa 2400 ký tự.')
    start = time.monotonic()
    scorer = None
    try:
        scorer = await build_scorer(db, body.model_spec_id)
        scores = await asyncio.wait_for(scorer.score(body.query, [{'text':d} for d in body.documents]), timeout=30.)
        scores = validate_scores([{'index':i, 'score':s} for i,s in enumerate(scores)], len(body.documents))
        return {'success':True, 'latency_ms':round((time.monotonic()-start)*1000),
                'results':[{'index':i, 'score':score, 'text':body.documents[i]} for i,score in enumerate(scores)]}
    except Exception as exc:
        return {'success':False, 'latency_ms':round((time.monotonic()-start)*1000),
                'message':f'Không chấm điểm được ({type(exc).__name__}). Kiểm tra model, giao thức, endpoint và API key.'}
    finally:
        await close_scorer(scorer)
