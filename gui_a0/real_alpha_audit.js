/* CP16: user-click-only real-PMX GPU transparency observation. R13 renderer unchanged. */
'use strict';
(function(){
 const btn=document.getElementById('realAlphaAudit'),save=document.getElementById('realAlphaSave');
 const out=document.getElementById('realAlphaReport'),canvas=document.getElementById('viewportCanvas');
 const toggle=document.getElementById('viewportUseTransparency');
 const status=document.getElementById('viewportStatus'),stats=document.getElementById('viewportStats');
 if(!btn||!save||!out||!canvas||!toggle||!status||!stats)return;
 let latest=null;
 const pixelBound=6000000;
 function capture(gl,on){
   toggle.checked=on;
   // Existing R13 change listener draws synchronously; do not access or replace its shader.
   toggle.dispatchEvent(new Event('change',{bubbles:true}));
   const w=canvas.width,h=canvas.height;
   if(w<1||h<1||w*h>pixelBound)throw Error('FRAMEBUFFER_OUT_OF_BOUNDS');
   const data=new Uint8Array(w*h*4);
   gl.finish();gl.readPixels(0,0,w,h,gl.RGBA,gl.UNSIGNED_BYTE,data);
   if(gl.getError()!==gl.NO_ERROR)throw Error('GPU_READBACK_ERROR');
   return {w,h,data};
 }
 function compare(a,b){
   if(a.w!==b.w||a.h!==b.h)throw Error('FRAMEBUFFER_DIMENSIONS_CHANGED');
   let different=0,sum=0,max=0;
   for(let i=0;i<a.data.length;i+=4){
     const d=Math.max(Math.abs(a.data[i]-b.data[i]),Math.abs(a.data[i+1]-b.data[i+1]),Math.abs(a.data[i+2]-b.data[i+2]));
     if(d>3){different++;sum+=d;max=Math.max(max,d);}
   }
   return {changed_pixels:different,max_difference:max,mean_changed_delta:different?Number((sum/different).toFixed(2)):0};
 }
 function run(){
   latest=null;save.disabled=true;
   const state=window.StudioViewport?.cameraState?.();
   if(!state||!state.ready)throw Error('HOLD_LOAD_REAL_PMX_FIRST');
   if(!window.StudioAlphaPolicy?.classify)throw Error('HOLD_ALPHA_POLICY_SCRIPT_NOT_LOADED');
   if(!status.textContent.includes('TEXTURED MESH READY'))throw Error('HOLD_WAIT_UNTIL_TEXTURES_COMPLETE');
   const gl=canvas.getContext('webgl2');if(!gl)throw Error('HOLD_WEBGL2_UNAVAILABLE');
   const initial=toggle.checked;
   let off,on;
   try{off=capture(gl,false);on=capture(gl,true);}
   finally{toggle.checked=initial;toggle.dispatchEvent(new Event('change',{bubbles:true}));}
   const delta=compare(off,on);
   // A/B has finished with the same loaded model; keep a ready sentinel for repeated audits.
   status.textContent='TEXTURED MESH READY — CP16 A/B captured';
   const label=delta.changed_pixels>0?'GPU_ALPHA_EFFECT_OBSERVED':'NO_RENDER_DIFFERENCE_FOR_THIS_MODEL';
   latest={checkpoint:'CP16',result:'PASS_REAL_PMX_GPU_AB_CAPTURED',alpha_effect:label,
     observed_pixel_difference:delta,framebuffer:{width:off.w,height:off.h},
     texture_classifier:{script_loaded:true,alpha_bearing:state.sampledAlphaTextures,significant_blend:state.significantBlendTextures},
     model_summary:(stats.textContent||'').slice(0,200),
     camera:{yaw:state.yaw,pitch:state.pitch,distance:state.distance},
     controls:{correct_pmx_v:state.correctDiffuseUV,toon:state.useToon,sphere:state.useSphere,lighting:state.legacyLighting?'R8_LEGACY':'R9_EXPERIMENTAL',mode:state.colorMode},
     mmd_parity:'NOT_VERIFIED',pmx_source_modified:false,time_utc:new Date().toISOString()};
   latest.pixels={off,on};
   const display={...latest,pixels:'Retained only in browser memory for optional QA PNG export'};
   out.textContent=JSON.stringify(display,null,2);
   save.disabled=false;
 }
 btn.addEventListener('click',()=>{
   out.textContent='CP16 RUNNING';save.disabled=true;
   try{run();}catch(e){out.textContent='HOLD_CP16_REAL_PMX_GPU_AUDIT: '+String(e.message||e)+'\nNo transparency parity claim.';}
 });
 function drawSnapshot(ctx,snap,x,y,w,h){
   const tmp=document.createElement('canvas');tmp.width=snap.w;tmp.height=snap.h;
   const t=tmp.getContext('2d');if(!t)throw Error('QA_2D_CONTEXT_UNAVAILABLE');
   const im=t.createImageData(snap.w,snap.h),stride=snap.w*4;
   for(let row=0;row<snap.h;row++)im.data.set(snap.data.subarray((snap.h-1-row)*stride,(snap.h-row)*stride),row*stride);
   t.putImageData(im,0,0);ctx.drawImage(tmp,x,y,w,h);
 }
 save.addEventListener('click',()=>{
   if(!latest)return;
   try{
     const img=document.createElement('canvas');img.width=1040;img.height=510;
     const c=img.getContext('2d');if(!c)throw Error('QA_2D_CONTEXT_UNAVAILABLE');
     c.fillStyle='#0e1626';c.fillRect(0,0,img.width,img.height);
     drawSnapshot(c,latest.pixels.off,10,10,505,330);
     drawSnapshot(c,latest.pixels.on,525,10,505,330);
     c.fillStyle='#fff';c.font='17px monospace';c.fillText('Real PMX alpha OFF',18,365);c.fillText('Real PMX alpha ON',530,365);
     c.font='13px monospace';
     const rows=['CP16 '+latest.result+' | '+latest.alpha_effect,
       'Changed pixels: '+latest.observed_pixel_difference.changed_pixels+' / '+(latest.framebuffer.width*latest.framebuffer.height),
       'Alpha bearing: '+latest.texture_classifier.alpha_bearing+' | significant-blend textures: '+latest.texture_classifier.significant_blend,
       'MMD PARITY NOT VERIFIED | model '+latest.model_summary.slice(0,102)];
     rows.forEach((line,i)=>c.fillText(line,12,395+23*i));
     if(!window.StudioQaExport?.save)throw Error('LOCAL_QA_EXPORT_UNAVAILABLE');
     out.textContent+='\nQA_AB_PNG_SAVING_TO_EVIDENCE';
     window.StudioQaExport.save(img,'ALPHA_AB').then(result=>{
       window.StudioQaExport.showLink('realAlphaDownloadLink',result);
       out.textContent+='\nPNG_SAVED_TO_EVIDENCE='+result.evidence_png+'\nSHA256='+result.sha256;
     }).catch(error=>{out.textContent+='\nHOLD_CP16_PNG_SAVE: '+String(error.message||error);});
   }catch(e){out.textContent+='\nHOLD_CP16_PNG: '+String(e.message||e);}
 });
})();
