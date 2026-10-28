'use strict';
let studioBridge=null, appMode='preview', currentModel=null, currentMesh=null;
const $=id=>document.getElementById(id);
const asText=x=>(x===null||x===undefined||x==='')?'—':String(x);
function setText(id,value){const el=$(id);if(el)el.textContent=asText(value)}
function showPage(name){if(name==='viewport' && window.StudioViewport)window.StudioViewport.requestFrame();document.querySelectorAll('.tabpage').forEach(el=>el.classList.toggle('hidden',el.id!==name)); document.querySelectorAll('.nav[data-tab]').forEach(el=>el.classList.toggle('active',el.dataset.tab===name));}
function status(message){setText('globalStatus',message)}
for(const element of document.querySelectorAll('.nav[data-tab]'))element.addEventListener('click',()=>showPage(element.dataset.tab));
const cap=(array,max=160)=>Array.isArray(array)?array.slice(0,max):[];
function records(id,rows,getName,filter=''){
 const out=$(id); out.replaceChildren(); const q=filter.toLocaleLowerCase();
 const matching=Array.isArray(rows)?rows.filter(x=>JSON.stringify(x).toLocaleLowerCase().includes(q)):[];
 if(!matching.length){out.textContent='No matching records (or not available).';return;}
 for(const item of matching.slice(0,200)){
  const row=document.createElement('div');row.className='record';
  const label=document.createElement('span');label.className='record-label';label.textContent=asText(getName(item));
  const idx=document.createElement('span');idx.className='record-idx';idx.textContent='#'+asText(item.index??item.material_index??item.bone_index??'—');
  row.append(label,idx);out.append(row);
 }
 if(matching.length>200){const p=document.createElement('p');p.className='muted';p.textContent=`Showing first 200 of ${matching.length} matches`;out.append(p);}
}
function resetModel(){currentModel=null;currentMesh=null;if(window.StudioViewport)window.StudioViewport.clear();for(const n of ['statVertices','statMaterials','statBones','statMorphs','fieldPath','fieldFormat','fieldEncoding'])setText(n,'—')}
function showModel(data){
 const p=data||{}; currentModel=p; currentMesh=null; if(window.StudioViewport)window.StudioViewport.clear();
 const h=p.header||{},s=p.scan||{},b=p.bones||{}, counts=s.section_summary||{};
 setText('modelTitle',h.model_name||h.local_name||s.model_info?.local_name||'Unnamed Model');
 setText('modelSubtitle',p.message||'Source is read-only.');
 status(h.status==='error'?'HOLD: header inspection failed':'Model read-only inspection finished');
 setText('statVertices',counts.vertex_count??s.vertex_count);
 setText('statMaterials',counts.material_count??s.material_count);
 setText('statBones',counts.bone_count??s.bone_count);
 setText('statMorphs',counts.morph_count??s.morph_count);
 setText('fieldPath',p.path);
 setText('fieldFormat',(h.detected_format||'?').toUpperCase()+' '+asText(h.version));
 setText('fieldEncoding',h.encoding);
 setText('fieldInspect',h.status?.toUpperCase()||'NOT RUN');
 setText('fieldScan',s.status?.toUpperCase()||'NOT RUN');
 setText('structureOutput',p.scan?JSON.stringify({summary:counts,scan_complete:s.scan_complete,texture_paths:cap(s.texture_paths,50),number_of_materials:s.material_count,number_of_morphs:s.morph_count},null,2):'Structural scan not available.');
 setText('diagnosticsOutput',JSON.stringify({header_status:h.status,header_errors:h.errors||[],header_warnings:h.warnings||[],scan_status:s.status,scan_complete:s.scan_complete??null,scan_errors:s.errors||[],scan_warnings:s.warnings||[],note:p.message},null,2));
 const boneRows=b.bones||s.bones||[];
 const windows=s.row_windows||{};
 const materials=s.materials||[];
 const morphs=s.morphs||[];
 records('boneRows',boneRows,x=>x.display_name??x.name??x.local_name??'[unnamed]',$('boneFilter').value);
 records('materialRows',materials,x=>x.local_name??x.universal_name??x.name??'[unnamed]',$('materialFilter').value);
 records('morphRows',morphs,x=>x.local_name??x.universal_name??x.name??'[unnamed]',$('morphFilter').value);
 setText('boneCountLabel',windows.bones?`Showing ${windows.bones.returned} of ${windows.bones.total} · first-page preview; search limited to loaded rows`:`${boneRows.length} records available`);
 setText('materialCountLabel',windows.materials?`Showing ${windows.materials.returned} of ${windows.materials.total} · first-page preview; search limited to loaded rows`:`${materials.length} records available`);
 setText('morphCountLabel',windows.morphs?`Showing ${windows.morphs.returned} of ${windows.morphs.total} · first-page preview; search limited to loaded rows`:`${morphs.length} records available`);
 showPage('overview');
}
function showMotion(data){
 const d=data||{};setText('motionTitle',d.model_name||'VMD motion');
 setText('motionMeta',`VMD2 · ${d.status||'unknown'} · ${d.path||''}`);
 setText('vmdOutput',JSON.stringify({counts:d.counts,frame_ranges:d.frame_ranges,warnings:d.warnings,sha256:d.sha256,scope:d.scope},null,2));
 const r=d.frame_ranges||{};const labels=['bone','morph','camera'];const root=$('vmdTracks');root.replaceChildren();
 for(const key of labels){const item=r[key]||{};const track=document.createElement('div');track.className='track';
  const title=document.createElement('strong');title.textContent=`${key.toUpperCase()} · ${d.counts?.[key]??0} keys`;
  const subtitle=document.createElement('span');subtitle.textContent=(item.first_frame===null||item.first_frame===undefined)?'No keyframes':`Frames ${item.first_frame}–${item.last_frame}`;
  track.append(title,subtitle);root.append(track);}
 status(`Read-only VMD inspection: ${d.status||'unknown'}`);showPage('motion');
}
function showTemplate(data){
 setText('creatorOutput',JSON.stringify(data||{},null,2));status(`Creator P0: ${data?.status||'HOLD'}`);showPage('creator');
}
function showResult(response){
 let p;try{p=typeof response==='string'?JSON.parse(response):response;}catch(e){status('HOLD: invalid JSON response');return;}
 if(!p||typeof p!=='object'||!['model','motion','template','preview'].includes(p.kind)){status('HOLD: unknown response kind');return;}
 if(p.kind==='model')showModel(p.data);
 if(p.kind==='preview'){currentMesh=p.data;try{window.StudioViewport.load(p.data);showPage('viewport');status('Static mesh rendered · READ ONLY');}catch(e){status('VIEWPORT HOLD: '+e.message);setText('viewportStatus','HOLD: '+e.message);}}
 if(p.kind==='motion')showMotion(p.data);
 if(p.kind==='template')showTemplate(p.data);
}
async function inspect(kind,path){
 if(!path){if(studioBridge){studioBridge.openFile(kind);return;}status('Enter a local file path first.');return;}
 if(studioBridge){studioBridge.inspectPath(kind,path);return;}
 if(appMode==='browser'){
  status(`Inspecting ${kind} (read-only)…`);
  try{const r=await fetch('api/inspect',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({kind,path})});const x=await r.json();if(!r.ok||!x.ok){status('HOLD: '+asText(x.error));return;}showResult(x.result);}
  catch(e){status('HOLD: browser bridge unavailable');}
 }else status('Static preview: start desktop host or browser launcher.');
}
function setupOp(id,kind){$(id).addEventListener('click',()=>inspect(kind,$('pathInput').value.trim()));}
setupOp('openModelButton','model'); setupOp('openMotionButton','motion');setupOp('openTemplateButton','template');
$('pathInput').addEventListener('keydown',e=>{if(e.key==='Enter')inspect('model',$('pathInput').value.trim());});
$('boneFilter').addEventListener('input',e=>{const p=currentModel||{};records('boneRows',p.bones?.bones||p.scan?.bones||[],x=>x.display_name??x.name??x.local_name,e.target.value);});
$('materialFilter').addEventListener('input',e=>{records('materialRows',currentModel?.scan?.materials||[],x=>x.local_name??x.universal_name??x.name,e.target.value);});
$('morphFilter').addEventListener('input',e=>{records('morphRows',currentModel?.scan?.morphs||[],x=>x.local_name??x.universal_name??x.name,e.target.value);});
if(typeof qt!=='undefined' && typeof QWebChannel!=='undefined'){
 new QWebChannel(qt.webChannelTransport,function(channel){studioBridge=channel.objects.studio;studioBridge.resultReady.connect(showResult);studioBridge.statusReady.connect(status);appMode='qt';status('Qt desktop connected · read-only');});
}else if(location.protocol==='http:'&&location.hostname==='127.0.0.1'){
 appMode='browser';status('Local Python browser host connected · read-only');
}else{status('Static preview only · no core connected');}

$('loadMeshButton').addEventListener('click',()=>{if(!currentModel || !currentModel.path){status('Open a PMX model before loading 3D mesh.');return;} inspect('preview',currentModel.path);});
$('resetCameraButton').addEventListener('click',()=>{if(window.StudioViewport)window.StudioViewport.resetCamera();});
