
'use strict';
const $=s=>document.querySelector(s), $$=s=>Array.from(document.querySelectorAll(s));
const state={boot:null,room:'1208',current:null,photos:[],scenario:null,parentId:null,busy:false,view:'capture',role:'cleaner',settingsBusy:false,zone:'bedroom',task:null,routingBusy:false,lastRouting:null,protocol:'standard-capture-1.0'};
const esc=s=>String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const labels={pass:'可见项通过',fail:'发现问题',unknown:'无法判断'},symbols={pass:'✓',fail:'!',unknown:'?'};
const modeLabel=mode=>({offline:'对话 AI · 离线回放',demo:'预设流程',live:'实时 AI'}[mode]||mode);
const sourceDescription=mode=>state.current?.replayed_from&&state.current.mode===mode?'此前真实API结果回看；本页按新规则分流，未再次调用模型。':({offline:'加载已记录的看图结果，本次没有重新识别。',demo:'预设流程演示，未调用视觉模型。',live:'实时模型观察，仍需人工核实。'}[mode]);
const when=s=>new Date(s).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false});
let toastTimer;
function toast(message){$('#toast').textContent=message;$('#toast').classList.add('show');clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('#toast').classList.remove('show'),4500);}
async function api(url,body){const response=await fetch(url,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const data=await response.json();if(!response.ok){const error=new Error(data.error||'请求失败');error.status=response.status;throw error;}return data;}
function showDialog(id){const d=$('#'+id);if(!d.open)d.showModal();}
function closedAction(r=state.current){return r?.rework_started_at?'rework':r?.reviews.at(-1)?.action;}
function closed(){return ['release','rework'].includes(closedAction());}
function scrollTop(){window.scrollTo({top:0,behavior:'instant'});}
function setView(name){state.view=name;$$('.view').forEach(v=>v.hidden=v.id!==name+'-view');$$('.nav-item').forEach(b=>b.classList.toggle('active',b.dataset.view===name));updateAction();if(name==='queue'||name==='history')loadLists();scrollTop();}
function setRole(role){state.role=role;document.body.dataset.role=role;$('#role-label').textContent=role==='cleaner'?'保洁端':'主管端';$('#review-panel').hidden=!state.current||role!=='supervisor';updateAction();}
function setBusy(value){state.busy=value;document.body.classList.toggle('busy',value);$$('#edit-room,.scenario-card,#mode,#start-rework,#submit-review,#save-review,#request-rework,#release-room,#new-inspection,#reinspect,#auto-upload,#mixed-samples,#retry-routing,#sample-all,#clear-photos,#replace-photos,#capture-mode,[data-capture],[data-save-adjudication],[data-adjust],[data-use-example]').forEach(b=>b.disabled=value);updateAction();updatePhotoControls();}
function updateAction(){
 const r=state.current, visible=state.view==='capture'&&(state.role==='cleaner'||!r);
 $('#capture-action').hidden=!visible;document.body.classList.toggle('has-action',visible);
 const b=$('#primary-action');b.disabled=state.busy;
 if(state.busy){b.textContent=state.routingBusy?'正在识别取景并归位…':'正在检查，请稍候…';$('#action-note').textContent='可以切换页面查看其他记录';return;}
 if(!r){const count=state.protocol?new Set(state.photos.filter(p=>p.kind==='required').map(p=>p.task_id)).size:new Set(state.photos.map(p=>p.zone)).size;$('#action-label').textContent=modeLabel($('#mode').value);$('#action-note').textContent=state.protocol?count+' / 6 必拍任务已添加':'历史两区域案例';b.textContent=state.photos.length?'检查已有证据 ↗':'载入六项生成样例 ↗';return;}
 $('#action-label').textContent=r.room+' 房 · '+(r.replayed_from?'真实API留档':modeLabel(r.mode));
 $('#action-note').textContent=r.summary.label;
 if(r.analysis_status==='error'&&!r.reviews.length)b.textContent='重试分析 ↻';
 else if(closed())b.textContent=closedAction(r)==='rework'?'整改后重新拍照 ↗':'开始下一轮检查 ↗';
 else if(r.triage?.can_start_rework&&!r.submitted_at)b.textContent='直接整改并复查 ↗';
 else b.textContent=r.submitted_at?'打开主管复核 ↗':'提交主管复核 ↗';
}
const icons={
 bedroom:'<svg viewBox="0 0 32 32"><path d="M5 25V11m22 14V11M5 19h22M5 25h22M8 18v-5h16v5M8 13V8h16v5M5 26v2m22-2v2"/></svg>',
 bathroom:'<svg viewBox="0 0 32 32"><path d="M5 16h22l-3 8H8l-3-8Zm11 8v5M8 29h16M12 16V7c0-4 7-4 7 0v2m-3 0h6M19 11v2"/></svg>'
};
function renderLegacyCapture(){
 const zones=state.boot.zones;
 $('#capture-progress').textContent=new Set(state.photos.map(p=>p.zone)).size+' / 2 个区域';
 $('#room-label').textContent=state.room;$('#room-status').textContent=state.parentId?'● 整改复查 · 重新采集证据':'● 待拍照 · 房号由你确认';
 $('#capture-list').innerHTML=Object.entries(zones).map(([zone,name])=>{
  const photos=state.photos.map((p,index)=>({...p,index})).filter(p=>p.zone===zone);
  return '<article class="capture-card"><button class="capture-card-main" data-capture="'+zone+'"><span class="capture-icon">'+icons[zone]+'</span><span class="capture-copy"><strong>'+name+'</strong><small>'+(zone==='bedroom'?'拍全床铺、床边地面及桌面':'拍清台盆、马桶及浴巾牙具')+'</small></span><span class="capture-status '+(photos.length?'done':'')+'">'+(photos.length?'已拍 '+photos.length+' 张':'去拍照 ↗')+'</span></button>'+(photos.length?'<div class="capture-thumbs">'+photos.map(p=>'<div class="capture-thumb"><img src="'+esc(p.url)+'" alt="'+esc(name)+'"><button class="thumb-open" data-draft-photo="'+p.index+'" aria-label="查看'+esc(name)+'原图"></button><button class="thumb-remove" data-remove="'+p.index+'" aria-label="移除照片">×</button></div>').join('')+'</div>':'')+'</article>';
 }).join('');
 $$('[data-capture]').forEach(b=>b.onclick=()=>capture(b.dataset.capture));
 $$('[data-draft-photo]').forEach(b=>b.onclick=()=>openPhoto(Number(b.dataset.draftPhoto),true));
 $$('[data-remove]').forEach(b=>b.onclick=async()=>{if(state.busy)return;setBusy(true);try{await materializeScenario();state.photos.splice(Number(b.dataset.remove),1);renderCapture();}catch(e){toast(e.message);}finally{setBusy(false);}});
 $$('.scenario-card').forEach(b=>b.classList.toggle('selected',b.dataset.scenario===state.scenario));
 updateAction();
}

const routingDefault='按关键内容宽松匹配，角度和装修不同也可以。';
function updatePhotoControls(){
 $$('[data-capture],[data-use-example],[data-adjust],[data-remove]').forEach(b=>b.disabled=state.busy);
 const locked=state.busy||!!state.current;
 $('#clear-photos').disabled=locked||!state.photos.length;
 $('#replace-photos').disabled=locked;
 $('#draft-photo-count').textContent='本轮 '+state.photos.length+' 张';
}
function resetCapturePhotos(){
 state.photos=[];state.scenario=null;state.task=null;state.zone='bedroom';state.lastRouting=null;
 ['camera-input','gallery-input','auto-input','replace-input'].forEach(id=>$('#'+id).value='');
 $('#routing-status').textContent=routingDefault;
}
function clearCapturePhotos(){
 if(state.busy||state.current)return;
 resetCapturePhotos();renderCapture();toast('已清空本轮图片，房号及历史检查记录保留。');
}
function preferredAnalysisMode(){
 let saved;try{saved=localStorage.getItem('inspector-analysis-mode');}catch{}
 return ['offline','demo','live'].includes(saved)?saved:state.boot?.config?.configured&&state.boot.config.last_connection_test?.status==='success'?'live':'offline';
}
function selectAnalysisMode(mode,persist=true){
 if(!['offline','demo','live'].includes(mode))mode='offline';
 $('#mode').value=mode;
 if(persist){try{localStorage.setItem('inspector-analysis-mode',mode);}catch{}}
 updateSettings();
}

function renderCapture(){
 updatePhotoControls();
 if(!state.protocol){$('#supplement-list').innerHTML='';$('#supplement-count').textContent='历史两区域案例';renderLegacyCapture();updatePhotoControls();return;}
 const tasks=state.boot.capture_tasks;
 const count=new Set(state.photos.filter(p=>p.kind==='required').map(p=>p.task_id)).size;
 $('#capture-progress').textContent=count+' / '+tasks.length+' 个必拍任务';
 $('#room-label').textContent=state.room;
 $('#room-status').textContent=state.parentId?'● 整改复查 · 重新添加生成证据':'● 合成素材演示 · 非真实房态';
 $('#capture-list').innerHTML=tasks.map((t,n)=>{
  const index=state.photos.findIndex(p=>p.task_id===t.id&&p.kind==='required'),photo=state.photos[index];
  return '<article class="capture-card task-card" data-task-card="'+t.id+'"><div class="task-heading"><span class="task-number">'+(n+1)+'</span><strong>'+esc(t.name)+'</strong><span class="task-badge '+(photo?'done':'')+'">'+(photo?'已添加 · 待检查':'必拍')+'</span></div><p class="task-hint">'+esc(t.hint)+'</p>'+(photo?'<div class="task-photo"><button data-draft-photo="'+index+'" aria-label="查看'+esc(t.name)+'"><img src="'+esc(photo.url)+'" alt="'+esc(t.name)+'生成图"></button><button class="thumb-remove" data-remove="'+index+'" aria-label="移除'+esc(t.name)+'">×</button></div>':'')+'<div class="task-actions"><button data-guide="'+t.id+'">取景示例</button><button data-use-example="'+t.id+'">'+(photo?'恢复正常样例':'添加生成样例')+'</button><button data-capture="'+t.zone+'" data-task="'+t.id+'">'+(photo?'替换这张图':'选择生成图')+'</button>'+(photo?'<button data-adjust="'+index+'">调整归位</button>':'')+'</div></article>';
 }).join('');
 const extras=state.photos.map((p,index)=>({...p,index})).filter(p=>p.kind==='supplement');
 $('#supplement-list').innerHTML=extras.map(p=>'<div class="supplement-row"><img src="'+esc(p.url)+'" alt="补充生成图"><div><strong>补充证据</strong><small>'+esc(state.boot.zones[p.zone])+' · 不计入必拍任务</small><small>'+esc(p.assignment?.manual_reason||p.assignment?.reason||'可手动调整归位')+'</small></div><button data-draft-photo="'+p.index+'">查看</button><button data-adjust="'+p.index+'">调整</button><button data-remove="'+p.index+'" aria-label="移除补充照片">×</button></div>').join('');
 $('#supplement-count').textContent='补充 '+extras.length+' 张';
 $$('[data-capture]').forEach(b=>b.onclick=()=>capture(b.dataset.task));
 $$('[data-guide]').forEach(b=>b.onclick=()=>openGuide(b.dataset.guide));
 $$('[data-use-example]').forEach(b=>b.onclick=()=>useTaskExample(b.dataset.useExample));
 bindDraftPhotos();updateAction();
}
function bindDraftPhotos(){
 updatePhotoControls();
 $$('[data-adjust]').forEach(b=>b.onclick=()=>openAdjustment(Number(b.dataset.adjust)));
 $$('[data-draft-photo]').forEach(b=>b.onclick=()=>openPhoto(Number(b.dataset.draftPhoto),true));
 $$('[data-remove]').forEach(b=>b.onclick=async()=>{if(state.busy)return;setBusy(true);try{await materializeScenario();state.photos.splice(Number(b.dataset.remove),1);renderCapture();}catch(e){toast(e.message);}finally{setBusy(false);}});
}
function openGuide(id){
 const task=state.boot.capture_tasks.find(t=>t.id===id);
 $('#guide-title').textContent=task.name+' · 取景示例';
 $('#guide-content').innerHTML='<img class="guide-image" src="/assets/'+task.example+'" alt="AI生成取景示例"><p>'+esc(task.hint)+'</p><p class="muted-note">AI生成示例，仅说明取景范围；本图正常不代表任意上传图合格。画面无法证明清洁过程或真实房间身份。</p>';
 showDialog('guide-dialog');
}
async function useTaskExample(id){
 if(state.busy||state.current)return;setBusy(true);
 try{
  const t=state.boot.capture_tasks.find(t=>t.id===id);
  await materializeScenario();
  const blob=await (await fetch('/assets/'+t.example)).blob(),url=await fileData(blob);
  state.photos=state.photos.filter(p=>!(p.task_id===id&&p.kind==='required'));
  if(state.photos.length>=10)throw new Error('每轮最多10张生成图。');
  state.photos.push({url,data:url.split(',')[1],mime:'image/png',name:t.name+' · AI生成',zone:t.zone,task_id:id,kind:'required'});
  renderCapture();
 }catch(e){toast(e.message);}finally{setBusy(false);}
}

function newDraft(parentId=null){
 if(state.busy)return;state.current=null;state.parentId=parentId;state.protocol=state.boot?.capture_protocol||'standard-capture-1.0';resetCapturePhotos();
 selectAnalysisMode(preferredAnalysisMode(),false);
 const url=new URL(location.href);url.searchParams.delete('inspection');history.replaceState(null,'',url);
 sessionStorage.removeItem('inspector-current');$('#capture-stage').hidden=false;$('#result-stage').hidden=true;
 $('#reviewer').value='';$('#added-issues').value='';$('#review-note').value='';$('#confirm-full').checked=false;
 setRole('cleaner');setView('capture');renderCapture();
}
function chooseScenario(id){
 if(state.busy)return;const parent=state.parentId;newDraft(parent);state.scenario=id;
 const scenario=state.boot.scenarios.find(s=>s.id===id);state.protocol=scenario.capture_protocol||null;
 state.photos=scenario.photos.map(({file,zone,name,task_id,kind})=>({url:'/assets/'+file,name:name||state.boot.zones[zone],zone,task_id,kind,mime:'image/png'}));
 if(!['clean','defects','incomplete'].includes(id)&&$('#mode').value==='demo')$('#mode').value='offline';
 $('#demo-picker').open=false;updateSettings();renderCapture();toast('已载入AI生成素材 · '+modeLabel($('#mode').value));
}
function capture(taskId){if(state.busy)return;const task=state.boot.capture_tasks.find(t=>t.id===taskId);state.task=task?.id||null;state.zone=task?.zone||(taskId==='bathroom'?'bathroom':'bedroom');$('#camera-input').click();}

function fileData(file){return new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(new Error('读取照片失败，请重试。'));reader.readAsDataURL(file);});}
async function preparePhoto(file,zone){
 if(!file.type.startsWith('image/'))throw new Error('请选择照片文件。');
 let blob=file, mime=file.type;
 if(file.size>5000000||!['image/jpeg','image/png','image/webp'].includes(mime)){
  const url=URL.createObjectURL(file),image=new Image();
  try{image.src=url;await image.decode();const scale=Math.min(1,2048/Math.max(image.naturalWidth,image.naturalHeight));const canvas=document.createElement('canvas');canvas.width=Math.round(image.naturalWidth*scale);canvas.height=Math.round(image.naturalHeight*scale);canvas.getContext('2d').drawImage(image,0,0,canvas.width,canvas.height);blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/jpeg',0.9));mime='image/jpeg';}
  catch{throw new Error('浏览器无法读取此照片，请使用 JPG、PNG 或 WebP。');}
  finally{URL.revokeObjectURL(url);}
 }
 if(!blob||blob.size>5000000)throw new Error('照片过大，请降低相机分辨率后重拍。');
 const url=await fileData(blob);
 return {url,data:url.split(',')[1],mime,name:file.name||'生成照片',zone,task_id:state.task,kind:state.task?'required':'supplement'};
}
async function materializeScenario(){
 if(!state.scenario)return;
 const photos=await Promise.all(state.photos.map(async p=>({...p,data:(await fileData(await (await fetch(p.url)).blob())).split(',')[1]})));
 state.photos=photos;state.scenario=null;
}
async function addLegacyFiles(files,zone,replace){
 if(state.busy||!files.length)return;setBusy(true);
 try{
  if(state.current){throw new Error('请先开始新一轮检查或整改复查，再拍摄照片。');}
  const ready=await Promise.all(Array.from(files).map(file=>preparePhoto(file,zone)));
  await materializeScenario();
  const kept=replace?(state.protocol?state.photos.filter(p=>!(p.task_id===state.task&&p.kind==='required')):state.photos.filter(p=>p.zone!==zone)):state.photos;
  if(kept.length+ready.length>10)throw new Error('每轮最多10张生成图，请先移除多余照片。');
  state.photos=kept.concat(ready);renderCapture();toast('生成图已添加；任务标签不等于照片内容已合格。');
 }catch(e){toast(e.message);}finally{$('#camera-input').value='';$('#gallery-input').value='';setBusy(false);}
}

const draftId=()=>('p'+Date.now().toString(36)+Math.random().toString(36).slice(2,11));
async function routeIncoming(ready,{replaceAll=false,replaceTask=null,deduplicate=true}={}){
 if(state.current)throw new Error('请先新建一轮，再添加照片。');
 await materializeScenario();
 const previous=state.photos.slice(),replacing=replaceAll||!!replaceTask;
 if(!replacing&&deduplicate){
  const unique=ready.filter(p=>!previous.some(old=>p.data&&old.data===p.data));
  if(!unique.length){$('#routing-status').textContent='这些照片已在本轮，无需重复添加。更换整组请点“全部替换图片”，补充图可重新归位。';toast('同样照片已添加，本次未重复调用归位。');return;}
  ready=unique;
 }
 const kept=replaceAll?[]:previous.filter(p=>!(replaceTask&&p.kind==='required'&&p.task_id===replaceTask));
 if(kept.length+ready.length>10)throw new Error('每轮最多10张生成图，可用“全部替换图片”更换整组。');
 const occupied=kept.filter(p=>p.kind==='required').map(p=>p.task_id);
 for(const p of ready){p._previous_assignment=p.assignment;p._draft_id=draftId();p.task_id=null;p.kind='supplement';p.assignment={method:'unclassified',reason:'尚未完成自动归位；不会计入必拍任务。'};}
 if(!replacing){state.photos=previous.concat(ready);renderCapture();}
 try{
  const result=await api('/api/photos/route',{mode:$('#mode').value,occupied_tasks:occupied,photos:ready.map(p=>({id:p._draft_id,data:p.data,zone:p.zone}))});
  for(const row of result.assignments){const p=ready.find(p=>p._draft_id===row.photo_id);if(!p)continue;Object.assign(p,{task_id:row.task_id,kind:row.kind,zone:row.zone,assignment:{method:'auto',routing_id:result.routing_id,photo_id:row.photo_id,source:result.source.kind,...row}});}
  const replacedTarget=replaceTask&&ready.some(p=>p.task_id===replaceTask);
  const retained=replaceAll?[]:replacedTarget?kept:previous;
  if(retained.length+ready.length>10)throw new Error('新图未匹配要替换的任务且本轮已满，原图保留；请先清空或全部替换。');
  state.photos=retained.concat(ready);state.lastRouting=result;
  const fitted=result.assignments.filter(a=>a.task_id).length;
  const occupiedCount=result.assignments.filter(a=>a.framing==='occupied').length;
  let note=occupiedCount?' '+occupiedCount+'张对应任务已有图，可单项替换或全部替换。':'';
  if(!fitted&&!result.source.realtime&&!occupiedCount)note+=' 离线仅匹配原始文件，新图或转存图请选实时AI后重新归位。';
  if(replaceTask&&!replacedTarget)note+=' 新图不属于原任务，原任务照片已保留。';
  $('#routing-status').textContent=(result.source.realtime?'真实AI归位':'离线取景记录匹配')+'：'+fitted+' 张填入必拍项，'+(ready.length-fitted)+' 张归补充证据。归位不代表卫生合格。'+note;
  toast(replaceAll?'整组图片已替换并重新归位。':replacedTarget?'该任务图片已替换，其他图片保留。':'归位完成，接下来单独检查清洁情况。');
 }catch(e){
  if(replacing){state.photos=previous;$('#routing-status').textContent='替换未完成，原图片全部保留。'+e.message;}
  else{
   for(const p of ready)p.assignment=p._previous_assignment?.routing_id?p._previous_assignment:{method:'unclassified',reason:'自动归位失败：'+e.message+'；照片保留，可重试或手动调整。'};
   $('#routing-status').textContent='归位未完成，照片全部保留在补充证据；没有套用预设答案。';
  }
  throw e;
 }finally{renderCapture();}
}
async function addFiles(files,zone,replace=false,replaceAll=false){
 if(!state.protocol&&!replaceAll)return addLegacyFiles(files,zone,replace);
 if(state.busy||!files.length)return;state.routingBusy=true;setBusy(true);
 const replaceTask=replace?state.task:null,previousProtocol=state.protocol;
 try{
  const ready=await Promise.all(Array.from(files).map(file=>preparePhoto(file,zone)));
  if(replaceAll)state.protocol=state.boot.capture_protocol;
  await routeIncoming(ready,{replaceAll,replaceTask});
 }catch(e){if(replaceAll){state.protocol=previousProtocol;renderCapture();}toast(e.message);}finally{state.routingBusy=false;state.task=null;['camera-input','gallery-input','auto-input','replace-input'].forEach(id=>$('#'+id).value='');setBusy(false);}
}
async function mixedSamples(){
 if(state.busy)return;
 if(state.current||state.photos.length){toast('请先开始空白新一轮，再体验乱序归位。');return;}
 state.routingBusy=true;setBusy(true);
 try{
  const names=['standard-floor.png','bed-low-light.png','standard-supplies.png','bed-hair-detail.png','standard-basin.png','bed-clean.png','standard-bed-detail.png','standard-toilet.png'];
  const ready=await Promise.all(names.map(async(file,index)=>{const blob=await (await fetch('/assets/'+file)).blob();const url=await fileData(blob);return {url,data:url.split(',')[1],mime:'image/png',name:'生成图 '+(index+1),zone:'bedroom',task_id:null,kind:'supplement'};}));
  await routeIncoming(ready);
 }catch(e){toast(e.message);}finally{state.routingBusy=false;setBusy(false);}
}
async function retryRouting(){
 if(state.busy||state.current)return;
 const retry=state.photos.filter(p=>p.kind==='supplement');
 if(!retry.length){toast('没有待重新归位的补充图。');return;}
 state.routingBusy=true;setBusy(true);
 try{await materializeScenario();const pending=state.photos.filter(p=>p.kind==='supplement');state.photos=state.photos.filter(p=>p.kind!=='supplement');await routeIncoming(pending,{deduplicate:false});}
 catch(e){toast(e.message);}finally{state.routingBusy=false;setBusy(false);renderCapture();}
}
function openAdjustment(index){
 if(state.busy||state.current)return;
 const p=state.photos[index];if(!p)return;
 $('#adjust-index').value=index;$('#adjust-preview').src=p.url;
 $('#adjust-task').innerHTML='<option value="">补充证据（不计必拍）</option>'+state.boot.capture_tasks.map(t=>'<option value="'+t.id+'">'+esc(t.name)+'</option>').join('');
 $('#adjust-task').value=p.task_id||'';$('#adjust-zone').value=p.zone;$('#adjust-reason').value='';
 $('#adjust-original').textContent=p.assignment?.reason||'当前为示例指定位置，尚无AI归位结论。';
 showDialog('adjust-dialog');
}
async function applyAdjustment(e){
 e.preventDefault();if(state.busy)return;
 const index=Number($('#adjust-index').value),id=$('#adjust-task').value,reason=$('#adjust-reason').value.trim();
 if(!reason){toast('请填写实际取景依据，保留调整记录。');return;}
 setBusy(true);
 try{
  await materializeScenario();const photo=state.photos[index];
  if(id){const old=state.photos.find(p=>p!==photo&&p.task_id===id&&p.kind==='required');if(old){old.assignment={...(old.assignment?.routing_id?old.assignment:{}),method:'manual_displaced',previous_task_id:old.task_id,manual_reason:'手动交换到补充证据：'+reason};old.kind='supplement';old.task_id=null;}}
  photo.assignment={...(photo.assignment?.routing_id?photo.assignment:{}),method:'manual',previous_task_id:photo.task_id,manual_reason:reason};
  photo.task_id=id||null;photo.kind=id?'required':'supplement';photo.zone=id?state.boot.capture_tasks.find(t=>t.id===id).zone:$('#adjust-zone').value;
  $('#adjust-dialog').close();renderCapture();toast('已手动调整，原始归位依据和调整理由会随检查保存。');
 }catch(err){toast(err.message);}finally{setBusy(false);}
}

function issueFindings(item){if(Array.isArray(item.findings))return item.findings;return ['fail','unknown'].includes(item.status)&&item.image_id?[item]:[];}
function issueLocations(item){const rows=issueFindings(item);return (rows.length?rows:[item]).map((f,index)=>{const nav=feedbackNavigation(item,f,index);return '<div class="issue-locations"><div>'+(rows.length?'<strong>'+(f.status==='unknown'?'待确认':'问题')+' '+(index+1)+'</strong><p>'+esc(f.evidence)+'</p>':'')+(nav.primary_image_id?'<button class="check-location" data-locate="'+esc(nav.primary_image_id)+'">查看该项原图'+(nav.bbox?'与位置':'（无可靠框）')+' ↗</button>':'')+'</div></div>';}).join('');}
function boxes(photo){
 if(!state.current)return '';const result=[];
 state.current.items.forEach(item=>issueFindings(item).forEach((f,index)=>{const nav=feedbackNavigation(item,f,index);if(nav.primary_image_id!==photo.id||!['fail','unknown'].includes(f.status)||!nav.bbox)return;const [x,y,x2,y2]=nav.bbox;result.push('<div class="issue-box '+(f.status==='unknown'?'uncertain':'')+'" style="left:'+x*100+'%;top:'+y*100+'%;width:'+(x2-x)*100+'%;height:'+(y2-y)*100+'%"><b>'+(f.status==='unknown'?'待确认：':'')+esc(item.name)+(issueFindings(item).length>1?' · '+(index+1):'')+'</b></div>');}));return result.join('');
}
function renderIndependentReview(r){
 const policy=r.independent_review,panel=$('#independent-review-panel');panel.hidden=!policy?.enabled;
 if(!policy?.enabled){panel.innerHTML='';return;}
 panel.innerHTML='<h4>高风险区域独立复查</h4><p class="muted-note">即使AI判通过，也要逐张查看这些原图并记录依据。发现问题请在上方修改结论或补充遗漏；勾选复查本身不代表该项通过。</p>'+policy.rows.map(row=>'<article class="independent-review-row"><strong>'+esc(row.name)+' · AI：'+labels[row.ai_status]+'</strong><p>'+esc(row.focus)+'</p><div>'+row.photo_ids.map((id,index)=>'<button type="button" class="text-button" data-risk-photo="'+esc(id)+'">查看原图 '+(index+1)+' ↗</button>').join('')+'</div>'+(!row.photo_ids.length?'<p class="muted-note">缺少可用原图，请补拍。</p>':'')+'<label class="manual-item"><input type="checkbox" data-risk-review="'+row.id+'" '+(row.confirmation?.reviewed?'checked':'')+'><span>我已独立复查上述原图，发现的问题已另外记录</span></label><textarea rows="2" maxlength="1000" data-risk-reason="'+row.id+'" aria-label="'+esc(row.name)+'依据" placeholder="记录实际看到什么、仍有什么疑点；不能只写已看">'+esc(row.confirmation?.reason||'')+'</textarea></article>').join('')+'<p class="muted-note">缺少复查记录会阻止放房；此记录不能证明现实中已执行现场检查。</p>';
 $$('[data-risk-photo]').forEach(b=>b.onclick=()=>openPhoto(r.photos.findIndex(p=>p.id===b.dataset.riskPhoto)));
}
function openPhoto(index,draft=false){const p=(draft?state.photos:state.current.photos)[index];if(!p){toast('没有找到对应照片，请刷新记录。');return;}const task=state.boot.capture_tasks.find(t=>t.id===p.task_id);$('#lightbox-title').textContent=(task?.name||p.name||state.boot.zones[p.zone])+' · 完整原图';$('#lightbox-body').innerHTML='<div class="lightbox-image"><img width="1448" height="1086" src="'+esc(p.url)+'" alt="'+esc(task?.name||p.name)+'"><div class="photo-overlay">'+(draft?'':boxes(p))+'</div></div>';showDialog('photo-dialog');}
function renderCoverage(r){
 const c=r.capture_coverage;
 $('#coverage-result').innerHTML=c?'<strong>必拍证据 '+c.ready+' / '+c.total+' 项可用</strong><p>'+(c.complete?'任务齐全仅表示指定证据可用，仍需逐项复核。':'待补拍／替换：'+esc(c.missing.join('、')))+'。</p><small>全部图片为AI生成；现场核实与放房仅演示，不代表真实房间达标。</small>':'<strong>历史两区域案例</strong><p>本案例不执行六项标准任务，保留用于对比旧流程。现场核实为模拟。</p>';
}
function renderTriage(r){
 const t=r.triage,panel=$('#triage-panel');panel.hidden=!t;if(!t)return;
 const copy={direct_rework:['明确问题','有可见依据，可直接整改'],manual_review:['人工裁决','判断有歧义或规格需核实'],retake:['需要补图','没有拍到，或照片不可用']};
 const renderRow=(i,key)=>{const id=key==='manual_review'?(i.review_evidence?.primary_image_id||i.image_id):i.image_id;return '<div class="triage-row"><strong>'+esc(i.name)+'</strong><p>'+esc(i.manual_override?.reason||i.evidence)+'</p>'+(id?'<button class="text-button" data-locate="'+esc(id)+'">查看'+(key==='manual_review'?'疑点':'证据')+'位置 ↗</button>':'')+'</div>';};
 const section=key=>t.groups[key].length?'<section class="triage-group '+key+'"><h4>'+copy[key][0]+'</h4>'+t.groups[key].map(i=>renderRow(i,key)).join('')+'</section>':'';
 const remaining=t.groups.manual_review.filter(i=>!(t.feedback_targets||[]).some(target=>target.check_id===(i.check_id||i.id)&&target.finding_id===(i.finding_id||i.id)));
 panel.innerHTML='<div class="section-heading"><h3>下一步怎么处理</h3><span>按证据分流</span></div><div class="triage-counts">'+Object.entries(copy).map(([key,[title,detail]])=>'<div class="triage-count '+key+'"><strong>'+t.counts[key]+'</strong><span>'+title+'</span><small>'+detail+'</small></div>').join('')+'</div>'+section('direct_rework')+renderAdjudicationTargets(r)+(remaining.length?'<section class="triage-group manual_review"><h4>其他待核实项</h4>'+remaining.map(i=>renderRow(i,'manual_review')).join('')+'</section>':'')+section('retake')+'<p class="muted-note">直接整改后另开关联复查。照片通过后，最终放房仍需人工确认；现场核实在本Demo中为模拟。</p>';
 bindAdjudicationControls(r);$('#start-rework').hidden=!t.can_start_rework||closed();$('#submit-review').hidden=closed()||Boolean(r.submitted_at);
}
async function startRework(){
 if(state.busy)return;setBusy(true);let parent=null;
 try{state.current=await api('/api/inspections/'+state.current.id+'/start-rework',{actor:'演示保洁'});parent=state.current.id;loadLists();}
 catch(e){toast(e.message);}finally{setBusy(false);}
 if(parent){newDraft(parent);toast('已记录直接整改，当前新批次关联原问题；需重新添加证据。');}
}

function renderResult(){
 const r=state.current,last=r.reviews.at(-1),sum=r.summary,done=closed();
 $('#capture-stage').hidden=true;$('#result-stage').hidden=false;$('#result-room').textContent=r.room+' 房';
 const title=r.rework_started_at?'已开始整改 · 待关联复查':last?.action==='release'?(last.manual_mode==='simulated'?'演示放房 · 现场核实为模拟':'历史人工放房记录'):last?.action==='rework'?'已要求整改 / 补拍':sum.label;
 $('#verdict').innerHTML='<div class="verdict '+sum.decision+'"><span class="verdict-icon">'+(sum.decision==='rework'?'!':sum.decision==='photo_pass'?'✓':'?')+'</span><div><strong>'+esc(title)+'</strong><p>'+sourceDescription(r.mode)+'</p></div></div>';
 renderCoverage(r);renderTriage(r);renderIndependentReview(r);
 const independent=r.independent_review;$('#independent-review-notice').hidden=!independent?.enabled;$('#independent-review-notice').textContent=independent?.enabled&&independent.complete?'床品与台盆独立复查记录已齐全；不代表真实现场检查已完成。':independent?.historical_closed_record?'本轮已结束，按当时记录回看；未完成的独立复查不得视为通过。':independent?.enabled?'高风险独立复查：'+independent.pending+'项待记录。AI通过仍需人工查看床品与台盆原图；这不会改写AI结果。':'';
$('#evidence-count').textContent=r.photos.length+' 张 · '+(r.finding_counts?.fail??r.items.filter(i=>i.status==='fail').length)+' 处可见问题 · 点开看原图';
 $('#metrics').innerHTML=['pass','fail','unknown'].map(s=>'<div class="metric"><strong>'+sum.counts[s]+'</strong><span>'+(s==='fail'?'问题检查项':labels[s])+'</span></div>').join('');
 $('#evidence-photos').innerHTML=r.photos.map((p,n)=>'<div class="evidence-photo"><div class="photo-image" data-photo="'+n+'" role="button" tabindex="0" aria-label="查看'+esc(p.name)+'原图"><img width="1448" height="1086" src="'+esc(p.url)+'" alt="'+esc(p.name)+'"><div class="photo-overlay">'+boxes(p)+'</div></div><div class="evidence-caption"><span>'+esc(p.name||state.boot.zones[p.zone])+'</span><small>'+'AI生成素材'+'</small></div></div>').join('');
 $$('[data-photo]').forEach(b=>{b.onclick=()=>openPhoto(Number(b.dataset.photo));b.onkeydown=e=>{if(e.key==='Enter')b.click();};});
 $('#result-mode').textContent=modeLabel(r.mode)+(r.replayed_from?' · 留档回看':'');
 $('#checklist').innerHTML=r.items.map(i=>{const o=r.effective_review?.overrides?.[i.id];return '<div class="check-row"><div class="check-main"><span class="status-symbol '+i.status+'">'+symbols[i.status]+'</span><div class="check-text"><strong class="check-title">'+esc(i.name)+'</strong><p class="check-evidence">'+esc(i.evidence)+'</p>'+issueLocations(i)+renderFeedbackBadge(i,r)+'</div><span class="check-status '+i.status+'">'+labels[i.status]+'</span></div><div class="override-line"><select data-override="'+i.id+'" aria-label="复核'+esc(i.name)+'" '+(done?'disabled':'')+'><option value="">保留原始观察</option>'+['pass','fail','unknown'].map(s=>'<option value="'+s+'" '+(o?.status===s?'selected':'')+'>人工：'+labels[s]+'</option>').join('')+'</select><input data-reason="'+i.id+'" aria-label="'+esc(i.name)+'核实依据" placeholder="填写现场核实依据" value="'+esc(o?.reason||'')+'" '+(o?'':'hidden')+' '+(done?'disabled':'')+'></div></div>';}).join('');
 $$('[data-override]').forEach(s=>s.onchange=()=>{const input=$('[data-reason="'+s.dataset.override+'"]');input.hidden=!s.value;if(s.value)input.focus();});
 $$('[data-locate]').forEach(b=>b.onclick=()=>openPhoto(r.photos.findIndex(p=>p.id===b.dataset.locate)));
 $('#analysis-error').hidden=!r.analysis_error;$('#analysis-error').textContent=r.analysis_error||'';
 $('#result-footnote').textContent=(r.mode==='offline'?'已加载 '+(r.observation_source?.matched_photos||0)+'/'+r.photos.length+' 张匹配观察；非实时识别，非盲测。疑似框为估计位置。':r.mode==='demo'?'观察与框选均为预设。':'模型：'+(r.model||'未成功返回')+'。')+' '+r.standard_version+' · '+(r.replayed_from?'原始API调用':r.mode==='offline'?'记录加载':'处理')+'耗时 '+(r.elapsed_seconds??'—')+' 秒';
 $('#cleaner-next').textContent=done?'本轮已结束，可在记录中回看。':r.submitted_at?'已提交主管复核，房间尚未确认可入住。':sum.decision==='rework'?'已标出的明确问题可直接整改；其余疑点与补图任务仍需处理。':sum.decision==='needs_review'?'有项目缺少证据，请补拍或提交主管现场核实。':'照片可见项未发现异常，仍需主管复核与现场检查。';
 $('#reviewer').value=last?.reviewer||state.feedbackReviewer||'';$('#added-issues').value=(last?.added_issues||[]).join('\n');$('#review-note').value=last?.note||'';$('#confirm-full').checked=last?.confirm_full_review||false;
 $$('#manual-checks input').forEach(c=>c.checked=last?.manual?.[c.dataset.manual]||false);
 $$('#review-panel input,#review-panel textarea').forEach(c=>c.disabled=done);
 $('.review-actions').hidden=done;$('#closed-actions').hidden=!done;
 $('#review-status').textContent=last?last.reviewer+' · '+when(last.at)+' 北京时间 · '+({save:'已保存复核',rework:'要求整改 / 补拍',release:'演示放房（现场核实为模拟）'}[last.action]):'';
 $('#audit').innerHTML=(r.parent_id?'<div class="audit-entry">关联上一轮：<button id="open-parent" class="text-button">'+esc(r.parent_id.slice(0,8))+' ↗</button></div>':'')+r.events.map(e=>'<div class="audit-entry"><time>'+esc(when(e.at))+' 北京时间</time>'+esc(e.message)+'</div>').join('');
 if($('#open-parent'))$('#open-parent').onclick=()=>loadRecord(r.parent_id);
 $('#raw-output').textContent=JSON.stringify({mode:r.mode,model:r.model,usage:r.usage,observations:r.raw_response,adjudications:r.adjudications||[],feedback_state:r.feedback_state,independent_review:r.independent_review,timing:r.timing,triage:r.triage,replayed_from:r.replayed_from,policy_adjustments:r.items.filter(i=>i.policy_adjustment).map(i=>({id:i.id,adjustment:i.policy_adjustment})),observation_source:r.observation_source,photo_assignments:r.photos.filter(p=>p.assignment).map(p=>({image_id:p.id,assignment:p.assignment}))},null,2);
 setRole(state.role);updateAction();
}
async function analyze(){
 if(state.busy)return;
 if($('#mode').value==='live'&&!state.boot.config.configured){toast('请先在电脑端连接视觉模型。');setView('settings');return;}
 setBusy(true);
 try{
  if(!state.current){state.current=await api('/api/inspections',{room:state.room,mode:$('#mode').value,scenario:state.scenario,parent_id:state.parentId,capture_protocol:state.protocol,photos:state.scenario?undefined:state.photos.map(({data,name,mime,zone,task_id,kind,assignment})=>({data,name,mime,zone,task_id,kind,assignment:assignment?.routing_id||["manual","manual_displaced"].includes(assignment?.method)?assignment:undefined}))});sessionStorage.setItem('inspector-current',state.current.id);}
  state.current=await api('/api/inspections/'+state.current.id+'/analyze',{});
  renderResult();if(state.view==='capture')scrollTop();toast(state.current.analysis_status==='error'?'处理失败，各项保持无法判断。':state.current.mode==='offline'?'已加载对话AI观察；本次未进行实时识别。':'检查完成，请查看结果。');
 }catch(e){toast(e.message);}finally{setBusy(false);}
}
async function submit(){if(state.busy)return;setBusy(true);try{state.current=await api('/api/inspections/'+state.current.id+'/submit',{});renderResult();toast('已提交主管复核，房间保持待确认。');loadLists();}catch(e){toast(e.message);}finally{setBusy(false);}}
async function primary(){
 if(state.busy)return;const r=state.current;
 if(!r){if(state.photos.length)return analyze();chooseScenario('standard_clean');return;}
 if(r.analysis_status==='error'&&!r.reviews.length)return analyze();
 if(closed())return newDraft(closedAction(r)==='rework'?r.id:null);
 if(r.triage?.can_start_rework&&!r.submitted_at)return startRework();
 if(r.submitted_at){setRole('supervisor');setView('capture');$('#review-panel').scrollIntoView({behavior:'smooth',block:'start'});return;}
 return submit();
}
function reviewPayload(action){const overrides={},manual={},risk_reviews={};$$("[data-risk-review]").forEach(c=>{risk_reviews[c.dataset.riskReview]={reviewed:c.checked,reason:$('[data-risk-reason="'+c.dataset.riskReview+'"]').value,photo_ids:state.current.independent_review.rows.find(r=>r.id===c.dataset.riskReview).photo_ids};});$$('[data-override]').forEach(s=>{if(s.value)overrides[s.dataset.override]={status:s.value,reason:$('[data-reason="'+s.dataset.override+'"]').value};});$$('[data-manual]').forEach(c=>manual[c.dataset.manual]=c.checked);return {risk_reviews,manual_mode:'simulated',simulation_ack:$('#confirm-full').checked,action,reviewer:$('#reviewer').value,overrides,manual,added_issues:$('#added-issues').value.split('\n').map(s=>s.trim()).filter(Boolean),note:$('#review-note').value,confirm_full_review:$('#confirm-full').checked};}
async function review(action){if(state.busy)return;const payload=reviewPayload(action);setBusy(true);try{state.current=await api('/api/inspections/'+state.current.id+'/review',payload);renderResult();loadLists();toast({save:'复核已保存。',rework:'已要求整改，可重新拍照复查。',release:'已记录演示放房；现场项目为模拟。'}[action]);}catch(e){toast(e.message);}finally{setBusy(false);}}
function recordCard(r){const action=closedAction(r),title=action==='release'?(r.reviews.at(-1)?.manual_mode==='simulated'?'演示放房':'历史放房记录'):action==='rework'?'待整改 / 补拍':r.submitted_at?'待主管复核':'尚未提交复核';return '<button class="record-card" data-record="'+r.id+'"><div class="record-top"><strong>'+esc(r.room)+'<small>标准间</small></strong><span class="'+r.summary.decision+'">'+title+'</span></div><p>'+esc(r.summary.label)+'</p><footer><span>'+esc(when(r.created_at))+'</span><span>'+(r.parent_id?'整改复查 · ':'')+modeLabel(r.mode)+' ↗</span></footer></button>';}
async function loadLists(){try{const records=await api('/api/history');const queue=records.filter(r=>r.submitted_at&&!['release','rework'].includes(closedAction(r)));$('#queue-badge').hidden=!queue.length;$('#queue-count').textContent='待复核 · '+queue.length+' 间';$('#queue-list').innerHTML=queue.length?queue.map(recordCard).join(''):'<div class="record-empty"><strong>暂时没有待复核房间</strong>保洁完成检查并提交后，会出现在这里。</div>';$('#history-list').innerHTML=records.length?records.map(recordCard).join(''):'<div class="record-empty"><strong>每次检查，都会留下记录</strong>先完成一轮拍照检查。</div>';$$('[data-record]').forEach(b=>b.onclick=()=>loadRecord(b.dataset.record));}catch(e){if(state.view==='queue'||state.view==='history')toast(e.message);}}
async function loadRecord(id){if(state.busy)return;try{const r=await api('/api/inspections/'+id);state.current=r;state.photos=r.photos;state.parentId=r.parent_id;state.scenario=r.scenario;state.protocol=r.capture_protocol||null;state.room=r.room;$('#room').value=r.room;$('#mode').value=r.mode;updateSettings();sessionStorage.setItem('inspector-current',id);setView('capture');if(['complete','error'].includes(r.analysis_status))renderResult();else{toast('本轮尚未完成分析，请稍后刷新记录。');state.current=null;renderCapture();}}catch(e){toast(e.message);}}
function updateSettings(){$('#capture-mode').value=$('#mode').value;$('#capture-mode-note').textContent=$('#mode').value==='live'?'实时AI会识别上传内容；归位不代表清洁合格。':$('#mode').value==='offline'?'离线只按原始文件匹配已有记录；新图或转存图请选实时AI。':'预设流程不识别新图；取景使用已有素材记录。';$('#connection-status').textContent=connectionStatusText(state.boot.config);$('#mode-help').textContent=sourceDescription($('#mode').value);$('#analysis-source-notice').textContent=state.current?.replayed_from?'真实API留档回看 · 本页未再次调用模型':$('#mode').value==='offline'?'对话 AI 观察 · 离线回放，仅匹配已记录的图片':$('#mode').value==='demo'?'预设流程演示 · 判定固定，未调用模型':'实时 AI · 将调用配置的模型服务';updateAction();}
function connectionStatusText(c){
 if(!c.configured)return '尚未连接';
 const verified=c.last_connection_test?.status==='success';
 return (verified?'图像请求已验证':'已配置 · 尚未验证')+(c.remembered?' · 本机已记住':c.credential_source==='environment'?' · 环境变量':' · 临时连接');
}
function renderConnectionSettings(){
 const c=state.boot.config,local=state.boot.access?.is_local!==false;
 $('#remember-option').hidden=!c.remember_supported;
 $('#credential-help').textContent=c.remember_supported?'勾选后保存在Windows凭据管理器，同一电脑、同一Windows账户更新或重启后自动恢复；不随项目打包。未勾选仅在后台运行期间保留。':'当前环境使用临时连接；后台重启后需重新填写，也可由环境变量提供。';
 const last=c.last_connection_test;
 $('#connection-test-status').textContent=c.storage_error||(!c.configured?'填写配置后可用一张内置生成图验证图像请求。':last?('最近验证：'+(last.status==='success'?'图像请求成功':'未通过')+' · '+when(last.at)+(last.message?'；'+last.message:'')):'配置已填写，尚未验证密钥、权限和图像请求。');
 $('#test-config').disabled=state.settingsBusy||!local;
 $('#clear-config').disabled=state.settingsBusy||!local;
 $('#settings-save').disabled=state.settingsBusy||!local;
 $('#open-connection-test').hidden=!last?.inspection_id;
}
function openSettings(){
 const local=state.boot.access?.is_local!==false;
 $('#model-fields').hidden=!local;$('#remote-model-note').hidden=local;
 $('#config-base').value=state.boot.config.base_url;$('#config-model').value=state.boot.config.model;$('#config-key').value='';
 $('#config-remember').checked=Boolean(state.boot.config.remembered);
 renderConnectionSettings();showDialog('settings-dialog');
}
async function saveConfig(e,verify=false){
 e.preventDefault();if(state.settingsBusy||!$('#settings-form').reportValidity())return;
 const body={base_url:$('#config-base').value.trim(),model:$('#config-model').value.trim(),remember:state.boot.config.remember_supported&&$('#config-remember').checked};
 if($('#config-key').value.trim())body.api_key=$('#config-key').value.trim();
 state.settingsBusy=true;renderConnectionSettings();
 try{
  state.boot.config=await api('/api/config',body);$('#config-key').value='';selectAnalysisMode('live');
  if(!verify){$('#settings-dialog').close();toast(state.boot.config.remembered?'已记住本机配置，更新或重启后可自动恢复。':'配置已保存为临时连接；后台关闭后需重新填写。');}
  else{
   $('#connection-test-status').textContent='正在发送一张内置生成图验证连接，请稍候…';
   const result=await api('/api/config/test',{});state.boot.config=result.config;updateSettings();renderConnectionSettings();
   toast(result.configuration_changed?'验证期间配置已变更，当前配置仍需重新验证。':result.success?'图像请求成功返回；这只验证连接，不代表房间达标。':'验证未通过，已保留错误记录，未切换离线答案。');
  }
 }catch(err){$('#connection-test-status').textContent=err.message;toast(err.message);}
 finally{state.settingsBusy=false;$('#test-config').disabled=false;$('#clear-config').disabled=false;$('#settings-save').disabled=false;}
}

async function openAccess(){try{const info=await api('/api/access');$('#access-content').innerHTML=!info.is_local?'<p class="muted-note">手机已连接本地工作台。电脑服务需保持运行；模型密钥由电脑端配置。</p>':!info.lan_enabled?'<p class="muted-note">当前仅本机访问。请运行项目中的“手机访问.cmd”，再查看本页。</p>':'<p class="muted-note">1. 手机与电脑连接同一 Wi-Fi。<br>2. 在手机浏览器输入电脑的 Wi-Fi 地址：</p>'+info.urls.map(u=>'<a class="access-url" href="'+esc(u)+'">'+esc(u)+'</a>').join('')+'<p class="muted-note">3. 输入本次连接码：</p><div class="pair-digits">'+esc(info.pair_code)+'</div><p class="muted-note">连接码随服务重启更换。电脑可以留在办公室。若无法访问，请检查 Wi-Fi 隔离、VPN 或系统防火墙。</p>';showDialog('access-dialog');}catch(e){toast(e.message);}}
function exportRecord(){const blob=new Blob([JSON.stringify(state.current,null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='inspection-'+state.current.id.slice(0,8)+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
function bind(){
 $$('.nav-item').forEach(b=>b.onclick=()=>{if(b.dataset.view==='queue')setRole('supervisor');setView(b.dataset.view);});
 const toggle=()=>{setRole(state.role==='cleaner'?'supervisor':'cleaner');toast(state.role==='cleaner'?'已切换保洁演示端。':'已切换主管演示端。');};
 $('#role-toggle').onclick=toggle;$('#role-settings').onclick=toggle;$('#primary-action').onclick=primary;
 $('#edit-room').onclick=()=>{if(!state.busy){$('#room').value=state.room;showDialog('room-dialog');}};
 $('#room-form').onsubmit=e=>{
  e.preventDefault();if(state.busy)return;const room=$('#room').value.trim();if(!room)return;
  const changed=room!==state.room;state.room=room;$('#room-dialog').close();
  if(changed){newDraft();toast('已切换到 '+room+' 房，本轮图片已清空；历史记录保留。');}else renderCapture();
 };
 $('#room-dialog').addEventListener('close',()=>$('#room').value=state.room);
 $('#clear-photos').onclick=clearCapturePhotos;
 $('#replace-photos').onclick=()=>{if(!state.busy&&!state.current){state.task=null;$('#replace-input').click();}};
 $('#replace-input').onchange=e=>addFiles(e.target.files,'bedroom',false,true);
 $('#capture-mode').onchange=e=>selectAnalysisMode(e.target.value);
 $('#auto-upload').onclick=()=>{if(!state.busy&&!state.current){state.task=null;$('#auto-input').click();}};
 $('#auto-input').onchange=e=>addFiles(e.target.files,'bedroom',false);
 $('#mixed-samples').onclick=mixedSamples;$('#retry-routing').onclick=retryRouting;$('#adjust-form').onsubmit=applyAdjustment;
 $('#camera-input').onchange=e=>addFiles(e.target.files,state.zone,true);
 $('#gallery-open').onclick=()=>{if(!state.busy&&!state.current)showDialog('supplement-dialog');};
 $('#supplement-upload').onclick=()=>{state.task=null;state.zone=$('#supplement-zone').value;$('#supplement-dialog').close();$('#gallery-input').click();};
 $('#sample-all').onclick=()=>chooseScenario('standard_clean');
 $('#gallery-input').onchange=e=>addFiles(e.target.files,state.zone,false);
 $$('[data-close]').forEach(b=>b.onclick=()=>$('#'+b.dataset.close).close());
 $('#new-inspection').onclick=()=>newDraft();$('#reinspect').onclick=()=>newDraft(state.current.id);
 $('#start-rework').onclick=startRework;$('#submit-review').onclick=submit;
 $('#save-review').onclick=()=>review('save');$('#request-rework').onclick=()=>review('rework');$('#release-room').onclick=()=>review('release');
 $('#refresh-history').onclick=loadLists;$('#refresh-queue').onclick=loadLists;
 $('#settings-open').onclick=openSettings;$('#settings-form').onsubmit=e=>saveConfig(e,false);$('#test-config').onclick=e=>saveConfig(e,true);$('#open-connection-test').onclick=()=>{const id=state.boot.config.last_connection_test?.inspection_id;if(id){$('#settings-dialog').close();loadRecord(id);}};
 $('#settings-dialog').addEventListener('close',()=>$('#config-key').value='');
 $('#clear-config').onclick=async()=>{try{state.boot.config=await api('/api/config',{clear:true});updateSettings();$('#config-remember').checked=false;$('#config-key').value='';renderConnectionSettings();toast('已清除本机保存与当前连接。');}catch(e){toast(e.message);}};
 $('#access-open').onclick=openAccess;$('#desktop-connect').onclick=openAccess;
 $('#standard-open').onclick=()=>showDialog('standard-dialog');
 $('#export-record').onclick=exportRecord;$('#export-adjudications').onclick=exportAdjudicationData;
 $('#mode').onchange=()=>{selectAnalysisMode($('#mode').value);if(state.current)toast('分析方式用于下一轮，当前结果不会改变。');};
 $('#pair-form').onsubmit=async e=>{e.preventDefault();try{await api('/api/pair',{code:$('#pair-code').value});$('#pair-dialog').close();$('#pair-code').value='';await boot();}catch(err){$('#pair-error').textContent=err.message;}};
 $('#pair-dialog').addEventListener('cancel',e=>e.preventDefault());
}
async function boot(){
 try{
  state.boot=await api('/api/bootstrap');selectAnalysisMode(preferredAnalysisMode(),false);$('#export-adjudications').hidden=state.boot.access?.is_local===false;
  $('#scenario-grid').innerHTML=[...state.boot.scenarios].sort((a,b)=>Number(!!b.capture_protocol)-Number(!!a.capture_protocol)).map((s,n)=>'<button class="scenario-card" data-scenario="'+s.id+'"><span>'+['✓','!','?','⌕','!','☾'][n%6]+'</span>'+esc(s.title)+'<small>查看样例 ↗</small></button>').join('');
  $$('[data-scenario]').forEach(b=>b.onclick=()=>chooseScenario(b.dataset.scenario));
  $('#manual-checks').innerHTML=state.boot.manual_checks.map(c=>'<label class="manual-item"><input type="checkbox" data-manual="'+c.id+'"><span>【模拟】'+esc(c.name)+'</span></label>').join('');
  $('#standard-list').innerHTML=state.boot.checks.map(c=>'<div class="standard-row"><strong>'+esc(c.name)+'</strong><span>'+esc(c.rule)+'</span></div>').join('');
  $('#auto-routing-panel').hidden=!state.boot.routing_enabled;
  $('#routing-references').innerHTML=state.boot.capture_tasks.map(t=>'<button data-reference="'+t.id+'"><img src="/assets/'+t.example+'" alt="'+esc(t.name)+'参考图"><span>'+esc(t.name)+'</span></button>').join('');
  $$('[data-reference]').forEach(b=>b.onclick=()=>openGuide(b.dataset.reference));
  updateSettings();renderCapture();loadLists();
  const requested=new URLSearchParams(location.search).get("inspection");if(requested&&/^[a-f0-9]{32}$/.test(requested))await loadRecord(requested);
 }catch(e){if(e.status===403)showDialog('pair-dialog');else toast('服务未就绪：'+e.message);}
}
bind();boot();
