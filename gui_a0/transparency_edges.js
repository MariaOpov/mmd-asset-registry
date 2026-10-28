/* CP15: GPU-only alpha/depth edge cases. No model parser or external requests. */
'use strict';
(function(){
 const canvas=document.getElementById('edgeCanvas'),run=document.getElementById('edgeRun');
 const save=document.getElementById('edgeSave'),status=document.getElementById('edgeStatus'),out=document.getElementById('edgeReport');
 if(!canvas||!run||!save||!status||!out)return;
 const expectations=[
  {name:'LEGACY_DEPTH_WRITES',rgb:[128,0,128]},
  {name:'SORTED_ALPHA',rgb:[128,64,64]},
  {name:'ZERO_ALPHA_OCCLUSION_BUG',rgb:[0,0,255]},
  {name:'ZERO_ALPHA_DISCARD_FIX',rgb:[0,128,128]},
  {name:'OPAQUE_FOREGROUND_OCCLUSION',rgb:[255,255,255]}
 ];
 const tolerance=11;
 let latest=null;
 function shader(gl,type,source){const sh=gl.createShader(type);gl.shaderSource(sh,source);gl.compileShader(sh);
  if(!gl.getShaderParameter(sh,gl.COMPILE_STATUS))throw Error('GLSL_COMPILE '+gl.getShaderInfoLog(sh));return sh;}
 function gpu(){
  const gl=canvas.getContext('webgl2',{alpha:false,depth:true,antialias:false,preserveDrawingBuffer:true});
  if(!gl)throw Error('WEBGL2_UNAVAILABLE');
  const vs=shader(gl,gl.VERTEX_SHADER,`#version 300 es
   layout(location=0) in vec2 a_xy; uniform float u_depth;
   void main(){gl_Position=vec4(a_xy,u_depth*2.0-1.0,1.0);}`);
  const fs=shader(gl,gl.FRAGMENT_SHADER,`#version 300 es
   precision highp float;uniform vec4 u_color;uniform bool u_discard_zero;
   out vec4 color;
   void main(){if(u_discard_zero && u_color.a < 0.001)discard;color=u_color;}`);
  const prog=gl.createProgram();gl.attachShader(prog,vs);gl.attachShader(prog,fs);gl.linkProgram(prog);
  if(!gl.getProgramParameter(prog,gl.LINK_STATUS))throw Error('GLSL_LINK '+gl.getProgramInfoLog(prog));
  gl.useProgram(prog);gl.deleteShader(vs);gl.deleteShader(fs);
  const buffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,buffer);
  gl.bufferData(gl.ARRAY_BUFFER,new Float32Array([-1,-1,1,-1,-1,1,1,1]),gl.STATIC_DRAW);
  gl.enableVertexAttribArray(0);gl.vertexAttribPointer(0,2,gl.FLOAT,false,0,0);
  const locDepth=gl.getUniformLocation(prog,'u_depth'),locColor=gl.getUniformLocation(prog,'u_color'),locDiscard=gl.getUniformLocation(prog,'u_discard_zero');
  gl.enable(gl.DEPTH_TEST);gl.depthFunc(gl.LESS);gl.disable(gl.CULL_FACE);
  gl.enable(gl.BLEND);gl.blendFunc(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA);gl.enable(gl.SCISSOR_TEST);
  function draw(z,rgba,discardZero=false){gl.uniform1f(locDepth,z);gl.uniform4fv(locColor,new Float32Array(rgba));gl.uniform1i(locDiscard,discardZero?1:0);gl.drawArrays(gl.TRIANGLE_STRIP,0,4);}
  function blue(){gl.depthMask(true);draw(.9,[0,0,1,1]);}
  function scenario(n){
   const x=n*200;gl.viewport(x,0,200,200);gl.scissor(x,0,200,200);
   gl.depthMask(true);gl.clearColor(0,0,0,1);gl.clearDepth(1);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);
   blue();
   if(n===0){gl.depthMask(true);draw(.2,[1,0,0,.5]);draw(.6,[0,1,0,.5]);}
   if(n===1){gl.depthMask(false);draw(.6,[0,1,0,.5]);draw(.2,[1,0,0,.5]);}
   if(n===2){gl.depthMask(true);draw(.2,[1,0,0,0],false);gl.depthMask(false);draw(.6,[0,1,0,.5]);}
   if(n===3){gl.depthMask(true);draw(.2,[1,0,0,0],true);gl.depthMask(false);draw(.6,[0,1,0,.5]);}
   if(n===4){gl.depthMask(true);draw(.2,[1,1,1,1]);gl.depthMask(false);draw(.6,[0,1,0,.5]);}
   gl.depthMask(true);
   const px=new Uint8Array(4);gl.readPixels(x+100,100,1,1,gl.RGBA,gl.UNSIGNED_BYTE,px);
   if(gl.getError()!==gl.NO_ERROR)throw Error('GPU_READBACK_ERROR');
   const rgb=Array.from(px.slice(0,3)),expected=expectations[n].rgb;
   const pass=rgb.every((v,i)=>Math.abs(v-expected[i])<=tolerance);
   return {test:expectations[n].name,rgb,expected,pass};
  }
  const results=expectations.map((_,i)=>scenario(i));gl.disable(gl.SCISSOR_TEST);gl.flush();
  // The alpha=0 depth bug should differ strongly from the explicit fragment discard correction.
  const witnessedFix=results[3].rgb[1]-results[2].rgb[1]>=100;
  return {pass:results.every(r=>r.pass)&&witnessedFix,results,witnessed_fix:witnessedFix,tolerance,webgl_version:'WebGL2'};
 }
 run.addEventListener('click',()=>{
  status.textContent='RUNNING_EDGE_GPU_TESTS';out.textContent='';save.disabled=true;latest=null;
  try{const g=gpu();latest={checkpoint:'CP15',result:g.pass?'PASS_GPU_EDGE_CORPUS':'HOLD_GPU_EDGE_CORPUS',gpu:g,uses_real_pmx:false,mmd_parity:'NOT_VERIFIED',time_utc:new Date().toISOString()};
   status.textContent=latest.result;out.textContent=JSON.stringify(latest,null,2);save.disabled=false;
  }catch(err){status.textContent='HOLD_GPU_EDGE_CORPUS';out.textContent=JSON.stringify({checkpoint:'CP15',result:'HOLD_GPU_EDGE_CORPUS',error:String(err.message||err),mmd_parity:'NOT_VERIFIED'},null,2);}
 });
 save.addEventListener('click',()=>{
  if(!latest)return;const c=document.createElement('canvas');c.width=1000;c.height=345;const ctx=c.getContext('2d');
  if(!ctx){status.textContent='HOLD_QA_CANVAS';return;}
  ctx.fillStyle='#0e1626';ctx.fillRect(0,0,1000,345);ctx.drawImage(canvas,0,0);
  ctx.fillStyle='#e5edf8';ctx.font='15px monospace';ctx.fillText('CP15 - '+latest.result+' - NOT MMD PARITY',12,226);
  latest.gpu.results.forEach((r,i)=>{ctx.fillText((i+1)+': '+r.test+' RGB '+r.rgb.join(',')+' '+(r.pass?'PASS':'HOLD'),12,250+i*18);});
  const a=document.createElement('a');a.href=c.toDataURL('image/png');a.download='MMD_CP15_EDGE_'+(latest.gpu.pass?'PASS':'HOLD')+'.png';document.body.appendChild(a);a.click();a.remove();
 });
})();
