/* CP16F: durable local QA save; browser download is optional, not a success criterion. */
'use strict';
(function(){
  async function save(canvas,kind){
    if(!['VIEWPORT','ALPHA_AB'].includes(kind))throw Error('QA_KIND_INVALID');
    if(location.protocol!=='http:' || location.hostname!=='127.0.0.1')throw Error('LOCAL_PYTHON_HOST_REQUIRED');
    if(!canvas || canvas.width<1 || canvas.height<1 || canvas.width*canvas.height>8000000)throw Error('QA_CANVAS_SIZE_INVALID');
    const blob=await new Promise((resolve,reject)=>canvas.toBlob(b=>b?resolve(b):reject(Error('HOLD_PNG_ENCODING')),'image/png'));
    if(blob.size<45 || blob.size>8*1024*1024)throw Error('QA_PNG_BYTES_OUT_OF_BOUNDS');
    const response=await fetch('api/qa-png', {
      method:'POST', headers:{'Content-Type':'image/png','X-MMD-QA-Kind':kind},
      body:blob, cache:'no-store', credentials:'same-origin'
    });
    const payload=await response.json();
    if(!response.ok || !payload.ok || payload.result?.result!=='PNG_SAVED_TO_EVIDENCE')throw Error(payload.error||'HOLD_QA_SAVE_NOT_CONFIRMED');
    return payload.result;
  }
  function showLink(id,result){
    const link=document.getElementById(id);
    if(!link)return;
    link.href=result.download_url;
    link.textContent='Download saved PNG copy';
    link.hidden=false;
  }
  window.StudioQaExport=Object.freeze({save,showLink});
})();
