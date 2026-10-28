/* CP14: Synthetic transparent-layer QA. No model/network/PMX writes. */
'use strict';
(function(){
 const canvas=document.getElementById('corpusCanvas'),start=document.getElementById('corpusRun');
 const save=document.getElementById('corpusSave'),status=document.getElementById('corpusStatus'),out=document.getElementById('corpusReport');
 if(!canvas||!start||!save||!status||!out)return;
 let last=null;
 function vec(x){return Array.from(x).map(v=>Number(v));}
 function proximity(actual,expected,tol=11){return actual.slice(0,3).every((v,i)=>Math.abs(v-expected[i])<=tol);}
 function samplePolicy(){
  const policy=window.StudioAlphaPolicy;
  if(!policy||typeof policy.classify!=='function')throw Error('R13 alpha policy unavailable');
  const count=96*96;
  function make(frac,value){const a=new Uint8ClampedArray(count*4);a.fill(255);const n=Math.round(frac*count);for(let i=0;i<n;i++)a[i*4+3]=value;return a;}
  const samples={opaque:policy.classify(make(0,255)),sparse:policy.classify(make(.01,128)),significant:policy.classify(make(.12,128)),cutout:policy.classify(make(.2,0)),unknown:policy.classify(new Uint8ClampedArray(3))};
  const pass=!samples.opaque.needsBlend&&!samples.opaque.unknown&&samples.sparse.hasAlpha&&!samples.sparse.needsBlend&&samples.significant.needsBlend&&!samples.cutout.needsBlend&&samples.unknown.unknown;
  return {pass,samples};
 }
 function shader(gl,type,src){const s=gl.createShader(type);gl.shaderSource(s,src);gl.compileShader(s);if(!gl.getShaderParameter(s,gl.COMPILE_STATUS)){const log=gl.getShaderInfoLog(s);gl.deleteShader(s);throw Error('GLSL '+log);}return s;}
 function runGpu(){
  const gl=canvas.getContext('webgl2',{alpha:false,depth:true,antialias:false,preserveDrawingBuffer:true});
  if(!gl)throw Error('WEBGL2_UNAVAILABLE');
  const vs=shader(gl,gl.VERTEX_SHADER,`#version 300 es
   layout(location=0) in vec2 a_position;
   uniform float u_depth;
   void main(){gl_Position=vec4(a_position,u_depth*2.0-1.0,1.0);}`);
  const fs=shader(gl,gl.FRAGMENT_SHADER,`#version 300 es
   precision highp float;
   uniform vec4 u_rgba;
   out vec4 fragColor;
   void main(){fragColor=u_rgba;}`);
  const pg=gl.createProgram();gl.attachShader(pg,vs);gl.attachShader(pg,fs);gl.linkProgram(pg);
  if(!gl.getProgramParameter(pg,gl.LINK_STATUS))throw Error('GLSL_LINK '+gl.getProgramInfoLog(pg));
  gl.deleteShader(vs);gl.deleteShader(fs);gl.useProgram(pg);
  const pos=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,pos);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array([-1,-1,1,-1,-1,1,1,1]),gl.STATIC_DRAW);
  gl.enableVertexAttribArray(0);gl.vertexAttribPointer(0,2,gl.FLOAT,false,0,0);
  const ud=gl.getUniformLocation(pg,'u_depth'),uc=gl.getUniformLocation(pg,'u_rgba');
  gl.enable(gl.SCISSOR_TEST);gl.enable(gl.DEPTH_TEST);gl.depthFunc(gl.LESS);gl.disable(gl.CULL_FACE);
  gl.enable(gl.BLEND);gl.blendFunc(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA);
  const draw=(z,rgba)=>{gl.uniform1f(ud,z);gl.uniform4fv(uc,new Float32Array(rgba));gl.drawArrays(gl.TRIANGLE_STRIP,0,4);};
  function scenario(x,sorted){
   gl.viewport(x,0,240,240);gl.scissor(x,0,240,240);
   gl.depthMask(true);gl.clearColor(0,0,0,1);gl.clearDepth(1);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);
   draw(.9,[0,0,1,1]);
   if(sorted){gl.depthMask(false);draw(.6,[0,1,0,.5]);draw(.2,[1,0,0,.5]);}
   else{gl.depthMask(true);draw(.2,[1,0,0,.5]);draw(.6,[0,1,0,.5]);}
   gl.depthMask(true);const px=new Uint8Array(4);gl.readPixels(x+120,120,1,1,gl.RGBA,gl.UNSIGNED_BYTE,px);
   if(gl.getError()!==gl.NO_ERROR)throw Error('GL_READBACK_ERROR');
   return vec(px);
  }
  const legacy=scenario(0,false),sorted=scenario(240,true);
  gl.disable(gl.SCISSOR_TEST);gl.flush();
  const a=proximity(legacy,[128,0,128]),b=proximity(sorted,[128,64,64]);
  return {pass:a&&b&&Math.abs(sorted[1]-legacy[1])>35,legacy,sorted,reference:{legacy:[128,0,128],sorted:[128,64,64]},tolerance:11};
 }
 start.addEventListener('click',()=>{
  status.textContent='RUNNING GPU CORPUS';save.disabled=true;last=null;
  try{
   const policy=samplePolicy();const gpu=runGpu();const pass=policy.pass&&gpu.pass;
   last={checkpoint:'CP14',result:pass?'PASS_GPU_CORPUS':'HOLD_GPU_CORPUS',policy,gpu,model_source_used:false,reference_mmd_parity:'NOT_VERIFIED',captured_at_utc:new Date().toISOString()};
   status.textContent=last.result;out.textContent=JSON.stringify(last,null,2);save.disabled=false;
  }catch(err){status.textContent='HOLD_GPU_CORPUS';out.textContent=JSON.stringify({result:'HOLD_GPU_CORPUS',error:String(err.message||err),mmd_parity:'NOT_VERIFIED'},null,2);}
 });
 save.addEventListener('click',()=>{
  if(!last)return;const c=document.createElement('canvas');c.width=480;c.height=330;const ctx=c.getContext('2d');
  if(!ctx)return;ctx.fillStyle='#0e1626';ctx.fillRect(0,0,c.width,c.height);ctx.drawImage(canvas,0,0);
  ctx.fillStyle='#e5edf8';ctx.font='14px monospace';ctx.fillText('CP14 synthetic GPU corpus - '+last.result,12,265);
  ctx.fillText('Legacy RGB '+last.gpu.legacy.slice(0,3)+' | Sorted '+last.gpu.sorted.slice(0,3),12,288);
  ctx.fillText('R13 alpha policy '+(last.policy.pass?'PASS':'HOLD')+' | NOT MMD PARITY',12,313);
  const a=document.createElement('a');a.href=c.toDataURL('image/png');a.download='MMD_CP14_GPU_CORPUS_'+(last.result.startsWith('PASS')?'PASS':'HOLD')+'.png';document.body.append(a);a.click();a.remove();
 });
})();
