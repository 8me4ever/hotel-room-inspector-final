"""Append-only human judgments and evidence navigation, without changing AI observations."""
from __future__ import annotations
import copy,hashlib,json,re
from datetime import datetime,timezone
from capture import TASKS,PROTOCOL
from findings import item_findings

VERSION='human-adjudication-1.0'
CHECK_TASK={c:t['id'] for t in TASKS for c in t['checks']}
OUTCOMES={'issue':'fail','no_issue':'pass','inconclusive':'unknown'}

def closed(record):
    return bool(record.get('rework_started_at') or (record.get('reviews') and record['reviews'][-1].get('action') in ('release','rework')))

def evidence_for(record,check_id,candidate):
    photos=record.get('photos',[]);quality=record.get('quality',{});original=candidate.get('image_id')
    usable={p['id']:p for p in photos if quality.get(p['id'],{}).get('usable') is True}
    required=[p['id'] for p in photos if p.get('task_id')==CHECK_TASK.get(check_id) and p['id'] in usable]
    specification=candidate.get('uncertainty_type')=='specification'
    if specification and record.get('capture_protocol')==PROTOCOL:
        ids=required
    else:ids=([original] if original in usable else []) or required
    return {'photo_ids':ids,'primary_image_id':ids[0] if ids else None,'original_image_id':original,'adjusted':bool(ids and ids[0]!=original),'bbox':candidate.get('bbox') if ids and ids[0]==original else None}

def target_key(check_id,candidate,index=0):return check_id+':'+str(candidate.get('id') or ('location-'+str(index+1)))

def targets(record):
    latest={a['target_id']:a for a in record.get('adjudications',[])}
    result=[]
    for item in record.get('items',[]):
        for index,candidate in enumerate(item_findings(item) or [item]):
            kind=candidate.get('uncertainty_type',item.get('uncertainty_type'))
            if candidate.get('status')!='unknown' or kind not in ('ambiguous','specification'):continue
            ident=target_key(item['id'],candidate,index)
            result.append({'target_id':ident,'check_id':item['id'],'finding_id':candidate.get('id'),'name':item['name'],'uncertainty_type':kind,'original_status':item['status'],'original_observation':copy.deepcopy(candidate),'evidence':candidate.get('evidence',item.get('evidence','')),'review_evidence':evidence_for(record,item['id'],candidate),'latest_feedback':latest.get(ident)})
    return result

def effective_view(record,review=None):
    explicit=review is not None
    selected=copy.deepcopy(review if explicit else (record.get('reviews') or [{}])[-1])
    latest={a['target_id']:a for a in record.get('adjudications',[])}
    items=copy.deepcopy(record.get('items',[]))
    for item in items:
        original_status=item['status'];rows=item_findings(item)
        candidates=rows or [item];applied=[]
        for index,candidate in enumerate(candidates):
            feedback=latest.get(target_key(item['id'],candidate,index))
            if not feedback:continue
            applied.append(feedback)
            description=(feedback['issue_description']+'；依据：' if feedback['outcome']=='issue' else '')+feedback['reason']
            candidate.update(status=OUTCOMES[feedback['outcome']],evidence=description,uncertainty_type='ambiguous' if feedback['outcome']=='inconclusive' else 'none',latest_feedback=feedback)
            evidence=feedback['review_evidence'];candidate['image_id']=evidence['primary_image_id'];candidate['bbox']=evidence['bbox']
        if applied:
            if rows:
                item['findings']=candidates
                first=next((c for c in candidates if c['status']=='fail'),None) or next((c for c in candidates if c['status']=='unknown'),None) or candidates[0]
                item.update({k:first.get(k) for k in ('status','evidence','image_id','bbox','uncertainty_type')})
            item['original_status']=original_status;item['human_feedback']=applied
            if not explicit and any(len(record.get('reviews',[]))<=a['review_count_at_save'] for a in applied):
                selected.get('overrides',{}).pop(item['id'],None)
    return items,selected

def validate_feedback(record,payload):
    if closed(record):raise ValueError('本轮已结束，请在新批次核查；历史记录仅回看。')
    if record.get('analysis_status')!='complete':raise ValueError('请先完成AI检查。')
    if not isinstance(payload,dict):raise ValueError('裁决格式无效。')
    current=next((t for t in targets(record) if t['target_id']==payload.get('target_id')),None)
    if current is None:raise ValueError('该项不是可裁决的原始疑点，缺图和质量不足应补拍。')
    def field(name,limit=1000,required=True):
        value=payload.get(name,'')
        if not isinstance(value,str) or len(value)>limit or (required and not value.strip()):raise ValueError('请完整填写核查人、结论和判断依据；发现问题时说明具体问题。')
        return value.strip()
    ident=field('submission_id',32)
    if not re.fullmatch(r'[a-f0-9]{32}',ident):raise ValueError('提交编号无效，请重新保存。')
    outcome=payload.get('outcome');basis=payload.get('basis')
    if outcome not in OUTCOMES or basis not in ('photo_review','configuration_record','simulation'):raise ValueError('请选择裁决结论和核查方式。')
    reason=field('reason');reviewer=field('reviewer',100)
    issue_type=field('issue_type',100,False);description=field('issue_description',1000,False);reference=field('basis_reference',1000,False)
    if outcome=='issue' and (not issue_type or not description):raise ValueError('确认是问题时，请填写问题类型和具体问题。')
    if basis=='configuration_record' and not reference:raise ValueError('请填写核对的配置记录或其他可追溯依据。')
    if current['uncertainty_type']=='specification' and outcome!='inconclusive' and basis=='photo_review':raise ValueError('照片不能证明浴巾规格；请核对配置记录，或明确选择仅演示假设。')
    ids=payload.get('photo_ids')
    expected=current['review_evidence']['photo_ids']
    if not isinstance(ids,list) or any(not isinstance(i,str) for i in ids) or len(ids)!=len(set(ids)) or set(ids)!=set(expected):raise ValueError('核查照片与本项不一致，请刷新后查看对应原图。')
    if outcome!='inconclusive' and not ids:raise ValueError('缺少本项可用照片，请先补拍，不能直接确认。')
    raw=record.get('raw_response')
    return {'id':ident,'version':VERSION,'at':datetime.now(timezone.utc).isoformat(timespec='microseconds'),'target_id':current['target_id'],'check_id':current['check_id'],'finding_id':current['finding_id'],'reviewer':reviewer,'outcome':outcome,'reason':reason,'issue_type':issue_type if outcome=='issue' else None,'issue_description':description if outcome=='issue' else None,'basis':basis,'basis_reference':reference or None,'photo_ids':ids,'review_evidence':current['review_evidence'],'original_observation':current['original_observation'],'original_check_status':current['original_status'],'review_count_at_save':len(record.get('reviews',[])),'supersedes':(current.get('latest_feedback') or {}).get('id'),'raw_response_sha256':hashlib.sha256(json.dumps(raw,ensure_ascii=False,sort_keys=True).encode('utf-8')).hexdigest(),'simulation_assumption':basis=='simulation','ready_for_training':False}

def training_rows(record):
    photos={p['id']:p for p in record.get('photos',[])}
    for a in record.get('adjudications',[]):
        yield {'schema_version':VERSION,'inspection_id':record['id'],'room':record.get('room'),'analysis_mode':record.get('mode'),'model':record.get('model'),'standard_version':record.get('standard_version'),'observation_source':record.get('observation_source'),'all_hotel_images_generated':record.get('simulation_only') is True,'feedback':copy.deepcopy(a),'photos':[{k:photos[ident].get(k) for k in ('id','path','sha256','task_id','kind')} for ident in a['photo_ids'] if ident in photos],'ready_for_training':False,'label_state':'exclude_simulation' if a['basis']=='simulation' else 'unresolved' if a['outcome']=='inconclusive' else 'needs_independent_quality_review','requires_dataset_split':True}
