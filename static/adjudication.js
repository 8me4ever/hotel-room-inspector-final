'use strict';
const adjudicationLabels={issue:'确认是问题',no_issue:'确认不是问题',inconclusive:'仍无法判断'};
function feedbackNavigation(item,candidate,index=0){
 const key=item.id+':'+(candidate.id||('location-'+(index+1)));
 const target=state.current?.triage?.feedback_targets?.find(t=>t.target_id===key);
 return target?.review_evidence||{primary_image_id:candidate.image_id,bbox:candidate.bbox,adjusted:false};
}
function feedbackSubmissionId(){const b=new Uint8Array(16);if(globalThis.crypto?.getRandomValues)crypto.getRandomValues(b);else b.forEach((_,i)=>b[i]=Math.floor(Math.random()*256));return Array.from(b,x=>x.toString(16).padStart(2,'0')).join('');}
function feedbackDraft(target,record){
 state.feedbackDrafts??={};const key=record.id+'|'+target.target_id;
 if(!state.feedbackDrafts[key]){const old=target.latest_feedback||{};state.feedbackDrafts[key]={submission_id:feedbackSubmissionId(),outcome:old.outcome||'',basis:old.basis||'photo_review',issue_type:old.issue_type||'',issue_description:old.issue_description||'',reason:old.reason||'',basis_reference:old.basis_reference||''};}
 return state.feedbackDrafts[key];
}
function renderAdjudicationTargets(record){
 const targets=record.triage?.feedback_targets||[];if(!targets.length)return '';
 const latest=record.adjudications?.at(-1);const name=state.feedbackReviewer||latest?.reviewer||record.reviews.at(-1)?.reviewer||'';
 return '<section class="triage-group manual_review"><h4>人工裁决与记录</h4><label class="feedback-reviewer">核查人<input id="adjudication-reviewer" maxlength="100" autocomplete="name" placeholder="填写姓名或工号" value="'+esc(name)+'" '+(closed()?'disabled':'')+'></label>'+targets.map(target=>{
  const d=feedbackDraft(target,record),old=target.latest_feedback,ev=target.review_evidence;
  const options=(rows,value)=>rows.map(([v,label])=>'<option value="'+v+'" '+(v===value?'selected':'')+'>'+label+'</option>').join('');
  return '<article class="triage-row adjudication-target" data-target-id="'+esc(target.target_id)+'"><strong>'+esc(target.name)+'</strong><p>'+(ev.adjusted?'原观察引用其他照片：':'')+esc(target.evidence)+'</p>'+(ev.primary_image_id?'<button class="text-button" data-locate="'+esc(ev.primary_image_id)+'">查看疑点位置 ↗</button>':'<p>缺少该项可用原图，请先补拍。</p>')+(ev.adjusted?'<p class="evidence-correction">已关联该项任务原图，请以此重新核查；旧观察不作为这张图的判定，原始记录仍保留。</p>':'')+(old?'<div class="feedback-saved"><strong>'+adjudicationLabels[old.outcome]+'</strong><p>'+esc(old.reason)+'</p><small>'+esc(old.reviewer)+' · '+esc(when(old.at))+' · '+(old.basis==='simulation'?'仅演示假设，不作为训练真值':'标注待二次审核')+'</small></div>':'')+'<details class="feedback-editor" '+(!old&&!closed()?'open':'')+'><summary>'+(old?'查看或修订裁决':'填写核查结论和依据')+'</summary><fieldset data-feedback-form="'+esc(target.target_id)+'" '+(closed()?'disabled':'')+'><label>核查结论<select data-fb-field="outcome">'+options([['','请选择'],['issue','确认是问题'],['no_issue','确认不是问题'],['inconclusive','仍无法判断，需要补证据']],d.outcome)+'</select></label><div data-issue-fields><label>问题类型<select data-fb-field="issue_type">'+options([['','请选择问题类型'],['stain','污渍或残留'],['hair','毛发或异物'],['litter','垃圾或遗留物'],['quantity','数量不足'],['specification','规格不符合'],['other','其他问题']],d.issue_type)+'</select></label><label>具体是什么问题<textarea data-fb-field="issue_description" rows="2" maxlength="1000" placeholder="说明问题内容、位置及影响">'+esc(d.issue_description)+'</textarea></label></div><label>判断依据<textarea data-fb-field="reason" rows="3" maxlength="1000" placeholder="为什么是问题／为什么不是问题；仍不确定时说明缺什么证据">'+esc(d.reason)+'</textarea></label><label>核查方式<select data-fb-field="basis">'+options([['photo_review','查看照片'],['configuration_record','核对配置记录'],['simulation','仅演示假设']],d.basis)+'</select></label><label data-basis-reference>核对了什么记录<input data-fb-field="basis_reference" maxlength="1000" placeholder="记录编号、标准版本或其他可追溯依据" value="'+esc(d.basis_reference)+'"></label>'+(target.uncertainty_type==='specification'?'<p class="muted-note">照片不能证明浴巾规格；确认是否符合时需核对配置记录，或明确选择仅演示假设。</p>':'')+'<button type="button" class="button secondary full" data-save-adjudication>保存裁决记录</button><p class="muted-note">保存后形成独立记录，不改写原始AI观察，也不直接放房。</p></fieldset></details></article>';
 }).join('')+'</section>';
}
function bindAdjudicationControls(record){
 const reviewer=$('#adjudication-reviewer');if(reviewer)reviewer.oninput=()=>state.feedbackReviewer=reviewer.value;
 $$('[data-feedback-form]').forEach(form=>{
  const target=record.triage.feedback_targets.find(t=>t.target_id===form.dataset.feedbackForm),draft=feedbackDraft(target,record);
  const update=()=>{form.querySelectorAll('[data-fb-field]').forEach(input=>draft[input.dataset.fbField]=input.value);form.querySelector('[data-issue-fields]').hidden=draft.outcome!=='issue';form.querySelector('[data-basis-reference]').hidden=draft.basis!=='configuration_record';};
  form.querySelectorAll('[data-fb-field]').forEach(input=>{input.oninput=update;input.onchange=update;});update();
  form.querySelector('[data-save-adjudication]').onclick=async()=>{
   if(state.busy)return;update();state.feedbackReviewer=reviewer?.value||'';
   const payload={...draft,reviewer:state.feedbackReviewer,target_id:target.target_id,photo_ids:target.review_evidence.photo_ids};
   setBusy(true);
   try{state.current=await api('/api/inspections/'+record.id+'/adjudications',payload);delete state.feedbackDrafts[record.id+'|'+target.target_id];renderResult();loadLists();toast('人工裁决已保存，原始AI观察保留。');}
   catch(e){toast(e.message);}finally{setBusy(false);}
  };
 });
}
async function exportAdjudicationData(){
 try{const response=await fetch('/api/feedback/export');if(!response.ok){const result=await response.json();throw new Error(result.error||'导出失败');}const blob=await response.blob(),url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download='human-adjudications.jsonl';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);toast('已导出人工裁决；模拟与未决记录不作为训练真值。');}catch(e){toast(e.message);}
}

function renderFeedbackBadge(item,record){const rows=record.feedback_state?.[item.id]?.feedback||[];return rows.map(a=>'<div class="human-conclusion"><strong>人工裁决：'+adjudicationLabels[a.outcome]+'</strong><p>'+esc(a.reason)+'</p></div>').join('');}
