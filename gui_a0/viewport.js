/* GUI-A2-P8 R13: conservative alpha classification protecting mostly-opaque face/hair. */
'use strict';
(function(){
 const canvas=document.getElementById('viewportCanvas');
 const indicator=document.getElementById('viewportStatus');
 const stats=document.getElementById('viewportStats');
 const colorModeControl=document.getElementById('viewportColorMode');
 const colorModeNote=document.getElementById('viewportColorModeNote');
 const toonControl=document.getElementById('viewportUseToon');
 const sphereControl=document.getElementById('viewportUseSphere');
 const legacyControl=document.getElementById('viewportLegacyLight');
 const correctedUvControl=document.getElementById('viewportCorrectUV');
 const compareButton=document.getElementById('viewportCompareEffects');
 const saveQaButton=document.getElementById('viewportSaveQaPng');
 const transparencyControl=document.getElementById('viewportUseTransparency');
 const compareOutput=document.getElementById('viewportCompareOutput');
 let useToon=true,useSphere=true,legacyLighting=false,correctDiffuseUV=true,alphaPass=false; // R11 legacy default; R13 coverage-gated alpha opt-in
 let colorMode=2; // 0 albedo; 1 albedo*diffuse; 2 toon/sphere MMD-style approximation
 let gl=null,program=null,ibo=null,posbo=null,normbo=null,uvbo=null,segments=[],indexCount=0;
 let textures=[],textureAlphaFlags=[],textureBlendFlags=[],textureAlphaUnknown=[],pendingTextures=0,loadedTextures=0,failedTextures=0,loadVersion=0;
 function finishTexture(version){if(version!==loadVersion)return;const done=loadedTextures+failedTextures;message(done===pendingTextures?`TEXTURED MESH READY — ${loadedTextures} texture(s), ${failedTextures} unavailable · alpha-bearing ${textureAlphaFlags.filter(Boolean).length}, significant-blend ${textureBlendFlags.filter(Boolean).length} · R13 ${alphaPass?"ON":"OFF"}`:`LOADING LOCAL TEXTURES — ${done}/${pendingTextures}`);draw();}
 let modelDigest='NOT_LOADED',modelName='NO_MODEL';
 let center=[0,0,0],radius=10,bounds=null,yaw=0.3,pitch=0.18,distance=20,ready=false,drag=null;
 let uniforms={},attribs={};
 function clamp(v,lo,hi){return Math.max(lo,Math.min(hi,v));}
 function message(t){if(indicator)indicator.textContent=t;}
 function shader(kind,src){const sh=gl.createShader(kind);gl.shaderSource(sh,src);gl.compileShader(sh);if(!gl.getShaderParameter(sh,gl.COMPILE_STATUS)){const m=gl.getShaderInfoLog(sh);gl.deleteShader(sh);throw Error('WebGL shader: '+m);}return sh;}
 function init(){
  if(gl)return;
  gl=canvas.getContext('webgl2',{alpha:false,antialias:true,depth:true,preserveDrawingBuffer:false});
  if(!gl)throw Error('WebGL2 is unavailable or disabled in this browser.');
  const vertex=`#version 300 es
precision highp float;
in vec3 a_position;
in vec3 a_normal;
in vec2 a_uv;
uniform mat4 u_viewproj;
out vec3 v_normal;
out vec2 v_uv;
void main(){gl_Position=u_viewproj*vec4(a_position,1.0);v_normal=a_normal;v_uv=a_uv;}`;
  const fragment=`#version 300 es
precision highp float;
in vec3 v_normal;
in vec2 v_uv;
uniform vec3 u_color;
uniform float u_alpha;
uniform bool u_hasTexture;
uniform sampler2D u_tex;
uniform bool u_correctDiffuseUV;
uniform int u_colorMode;
uniform bool u_hasSphere;
uniform bool u_hasToon;
uniform sampler2D u_sphere;
uniform sampler2D u_toon;
uniform int u_sphereMode;
uniform vec3 u_eyeRight;
uniform vec3 u_eyeUp;
uniform vec3 u_eyeDirection;
uniform bool u_legacyLighting;
uniform vec3 u_ambient;
uniform vec3 u_specular;
uniform float u_shininess;
out vec4 outColor;
vec3 toLinear(vec3 srgb){
 vec3 low=srgb/12.92;
 vec3 high=pow((srgb+vec3(0.055))/1.055,vec3(2.4));
 return mix(low,high,step(vec3(0.04045),srgb));
}
vec3 toSrgb(vec3 linearRgb){
 vec3 c=clamp(linearRgb,0.0,1.0);
 vec3 low=c*12.92;
 vec3 high=1.055*pow(c,vec3(1.0/2.4))-0.055;
 return mix(low,high,step(vec3(0.0031308),c));
}
void main(){
 // PMX diffuse UV origin is top-left; legacy WebGL uploads flip image rows.
 // Correct only the diffuse sampler, leaving toon/sphere unchanged for isolated A/B.
 vec2 diffuseUV=vec2(v_uv.x,u_correctDiffuseUV?(1.0-v_uv.y):v_uv.y);
 vec4 texel=u_hasTexture?texture(u_tex,diffuseUV):vec4(1.0);
 float alpha=texel.a*u_alpha;
 if(alpha<0.05)discard;
 // Diagnostic modes isolate diffuse texture and material tint from lighting.
 vec3 base=u_hasTexture?toLinear(texel.rgb):vec3(1.0);
 if(u_colorMode==0 && u_hasTexture){outColor=vec4(texel.rgb,alpha);return;}
 if(u_colorMode==0){outColor=vec4(toSrgb(base),alpha);return;}
 base*=u_color;
 if(u_colorMode==1){outColor=vec4(toSrgb(base),alpha);return;}
 // Approximate MMD material lighting; not a pixel-identical DirectX renderer.
 vec3 n=normalize(v_normal);
 vec3 keyDir=normalize(vec3(0.25,0.45,0.86));
 // R8 legacy used abs(), illuminating back-facing surfaces as though front-facing.
 float ndl=u_legacyLighting ? clamp(abs(dot(n,keyDir)),0.0,1.0) : max(dot(n,keyDir),0.0);
 float light=u_legacyLighting ? (0.65+0.35*ndl) : (0.58+0.42*ndl);
 vec3 rgb=base * (light + 0.08*clamp(u_ambient,0.0,1.0));
 // Approximate Blinn-Phong highlights using the PMX specular fields, which R8 ignored.
 if(!u_legacyLighting && u_shininess>0.0){
   vec3 halfDir=normalize(keyDir+normalize(u_eyeDirection));
   float spec=pow(max(dot(n,halfDir),0.0),clamp(u_shininess,1.0,128.0));
   rgb+=0.22*clamp(u_specular,0.0,1.0)*spec;
 }
 // MMD toon custom textures act as directional shadow color ramps.
 // WebGL has flipped image rows on upload; UV.y=1 samples the original top.
 if(u_hasToon){
   vec3 toon=toLinear(texture(u_toon,vec2(0.04,clamp(ndl,0.002,0.998))).rgb);
   rgb*=toon;
 }
 // Sphere maps use eye-space normals, not the diffuse UV coordinates.
 if(u_hasSphere && (u_sphereMode==1||u_sphereMode==2)){
   vec2 sphereUV=vec2(0.5+0.5*dot(n,u_eyeRight),0.5+0.5*dot(n,u_eyeUp));
   vec3 sphere=toLinear(texture(u_sphere,clamp(sphereUV,0.001,0.999)).rgb);
   if(u_sphereMode==1)rgb*=sphere;
   if(u_sphereMode==2)rgb+=sphere;
 }
 outColor=vec4(toSrgb(rgb),alpha);
}`;
  let vs=shader(gl.VERTEX_SHADER,vertex),fs=shader(gl.FRAGMENT_SHADER,fragment);
  program=gl.createProgram();gl.attachShader(program,vs);gl.attachShader(program,fs);gl.linkProgram(program);gl.deleteShader(vs);gl.deleteShader(fs);
  if(!gl.getProgramParameter(program,gl.LINK_STATUS))throw Error('WebGL program: '+gl.getProgramInfoLog(program));
  attribs.pos=gl.getAttribLocation(program,'a_position');attribs.normal=gl.getAttribLocation(program,'a_normal');attribs.uv=gl.getAttribLocation(program,'a_uv');
  uniforms.proj=gl.getUniformLocation(program,'u_viewproj');uniforms.color=gl.getUniformLocation(program,'u_color');
  uniforms.alpha=gl.getUniformLocation(program,'u_alpha');uniforms.hasTexture=gl.getUniformLocation(program,'u_hasTexture');uniforms.tex=gl.getUniformLocation(program,'u_tex');uniforms.colorMode=gl.getUniformLocation(program,'u_colorMode');uniforms.correctDiffuseUV=gl.getUniformLocation(program,'u_correctDiffuseUV');
  uniforms.sphere=gl.getUniformLocation(program,'u_sphere');uniforms.toon=gl.getUniformLocation(program,'u_toon');
  uniforms.hasSphere=gl.getUniformLocation(program,'u_hasSphere');uniforms.hasToon=gl.getUniformLocation(program,'u_hasToon');
  uniforms.sphereMode=gl.getUniformLocation(program,'u_sphereMode');uniforms.eyeRight=gl.getUniformLocation(program,'u_eyeRight');
  uniforms.eyeUp=gl.getUniformLocation(program,'u_eyeUp');uniforms.eyeDirection=gl.getUniformLocation(program,'u_eyeDirection');uniforms.legacyLighting=gl.getUniformLocation(program,'u_legacyLighting');uniforms.ambient=gl.getUniformLocation(program,'u_ambient');
  uniforms.specular=gl.getUniformLocation(program,'u_specular');uniforms.shininess=gl.getUniformLocation(program,'u_shininess');
  posbo=gl.createBuffer();normbo=gl.createBuffer();uvbo=gl.createBuffer();ibo=gl.createBuffer();
  gl.activeTexture(gl.TEXTURE0);
  gl.enable(gl.DEPTH_TEST);gl.disable(gl.CULL_FACE);gl.enable(gl.BLEND);gl.blendFunc(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA);gl.clearColor(0.055,0.09,0.15,1);
  const ro=new ResizeObserver(()=>draw());ro.observe(canvas);
 }
 function perspective(fovy,aspect,near,far){let f=1/Math.tan(fovy/2),nf=1/(near-far);return new Float32Array([f/aspect,0,0,0,0,f,0,0,0,0,(far+near)*nf,-1,0,0,2*far*near*nf,0]);}
 function normalize(v){let n=Math.hypot(...v)||1;return v.map(x=>x/n);}
 function cross(a,b){return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];}
 function lookAt(eye,target,up){
  let z=normalize(eye.map((v,i)=>v-target[i]));let x=normalize(cross(up,z));let y=cross(z,x);
  return new Float32Array([x[0],y[0],z[0],0,x[1],y[1],z[1],0,x[2],y[2],z[2],0,-x.reduce((s,v,i)=>s+v*eye[i],0),-y.reduce((s,v,i)=>s+v*eye[i],0),-z.reduce((s,v,i)=>s+v*eye[i],0),1]);
 }
 function mul(a,b){const out=new Float32Array(16);for(let c=0;c<4;c++)for(let r=0;r<4;r++)for(let k=0;k<4;k++)out[c*4+r]+=a[k*4+r]*b[c*4+k];return out;}
 function resetCamera(){
  yaw=window.StudioCameraMath.defaultYaw;pitch=window.StudioCameraMath.defaultPitch;
  if(bounds){const rect=canvas.getBoundingClientRect();distance=window.StudioCameraMath.fitDistance(bounds,yaw,pitch,rect.width,rect.height);}
  else distance=Math.max(1,radius*2.8);
  draw();
 }
 function clear(){modelDigest='NOT_LOADED';modelName='NO_MODEL';loadVersion++;ready=false;bounds=null;segments=[];indexCount=0;for(const t of textures)if(t)gl?.deleteTexture(t);textures=[];textureAlphaFlags=[];textureBlendFlags=[];textureAlphaUnknown=[];pendingTextures=loadedTextures=failedTextures=0;message('Open a PMX model, then load its textured mesh.');stats.textContent='No mesh loaded.';draw();}
 function validate(d){
  if(!d||d.scope!=='STATIC_TEXTURE_PREVIEW_NO_SKINNING_NO_MOTION'||d.status!=='ok'||d.source_writes!==false)throw Error('Preview safety contract mismatch.');
  if(typeof d.source_sha256!=='string'||!(/^[0-9a-f]{64}$/.test(d.source_sha256)))throw Error('Missing verified source SHA-256.');
  if(!Array.isArray(d.positions)||!Array.isArray(d.normals)||!Array.isArray(d.uvs)||!Array.isArray(d.indices)||!Array.isArray(d.groups))throw Error('Geometry fields missing.');
  if(d.vertex_count<=0||d.vertex_count>100000||d.positions.length!==d.vertex_count*3||d.normals.length!==d.positions.length||d.uvs.length!==d.vertex_count*2)throw Error('Vertex data exceeds safe bound.');
  if(d.indices.length!==d.triangle_count*3||d.triangle_count<=0||d.triangle_count>150000)throw Error('Triangle data exceeds safe bound.');
  if(d.positions.some(x=>!Number.isFinite(x))||d.normals.some(x=>!Number.isFinite(x))||d.uvs.some(x=>!Number.isFinite(x)))throw Error('Non-finite vertex data.');
  if(d.indices.some(x=>!Number.isInteger(x)||x<0||x>=d.vertex_count))throw Error('Invalid triangle indices.');
  if(!d.bounds||!Array.isArray(d.bounds.min)||!Array.isArray(d.bounds.max)||d.bounds.min.length!==3||d.bounds.max.length!==3)throw Error('Invalid bounds.');
  let next=0;
  for(const g of d.groups){if(!Number.isInteger(g.start)||!Number.isInteger(g.count)||g.start!==next||g.count<0||g.count%3||!Array.isArray(g.color)||g.color.length!==3||g.color.some(x=>!Number.isFinite(x)||x<0||x>1)||!Number.isFinite(g.alpha)||g.alpha<0||g.alpha>1||!Number.isInteger(g.texture_index)||g.texture_index < -1)throw Error('Material partitions invalid.');next+=g.count;}
  if(next!==d.indices.length)throw Error('Material partition incomplete.');
  for(const g of d.groups){
    for(const ref of [g.sphere_texture_index,g.toon_texture_index]){
      if(!Number.isInteger(ref)||ref< -1||ref>=d.textures.length)throw Error('Invalid additional material texture reference.');
    }
    if(!Number.isInteger(g.sphere_mode)||g.sphere_mode<0||g.sphere_mode>3)throw Error('Invalid PMX sphere mode.');
    if(!['texture','shared'].includes(g.toon_reference_mode))throw Error('Invalid toon reference mode.');
    if(!Number.isInteger(g.toon_shared_index)||g.toon_shared_index< -1||g.toon_shared_index>9)throw Error('Invalid shared toon reference.');
    if(!Array.isArray(g.ambient)||g.ambient.length!==3||g.ambient.some(v=>!Number.isFinite(v)||v<0||v>1))throw Error('Invalid ambient.');
    if(!Array.isArray(g.specular)||g.specular.length!==3||g.specular.some(v=>!Number.isFinite(v)||v<0||v>1))throw Error('Invalid specular.');
    if(!Number.isFinite(g.specular_strength)||g.specular_strength<0||g.specular_strength>128)throw Error('Invalid specular strength.');
    if(!Number.isInteger(g.drawing_flags)||g.drawing_flags<0||g.drawing_flags>255)throw Error('Invalid PMX drawing flags.');
  }
  if(!Array.isArray(d.textures)||d.textures.length>128)throw Error('Texture manifest missing or excessive.');
  for(const t of d.textures){if(!t||typeof t!=='object'||(t.url!==null&&(typeof t.url!=='string'||!/^asset\/[0-9a-f]{32}$/.test(t.url))))throw Error('Unsafe local texture token.');}
  for(const g of d.groups){if(g.texture_index>=d.textures.length)throw Error('Texture reference outside declared list.');}
 }
 // A bounded coverage estimate: a single translucent texel must NOT make a
 // whole face/hair material a depth-write-disabled, back-to-front group.
 // This is intentionally a preview heuristic, not MMD alpha parity.
 function sampledTextureAlpha(image){
  try{
   const scratch=document.createElement('canvas');scratch.width=96;scratch.height=96;
   const ctx=scratch.getContext('2d',{willReadFrequently:true});
   if(!ctx)return {hasAlpha:false,needsBlend:false,unknown:true};
   ctx.clearRect(0,0,96,96);ctx.drawImage(image,0,0,96,96);
   return window.StudioAlphaPolicy.classify(ctx.getImageData(0,0,96,96).data);
  }catch(_){return {hasAlpha:false,needsBlend:false,unknown:true};}
 }
 function load(data){
  validate(data);init();
  modelDigest=data.source_sha256;
  modelName=typeof data.name==='string'?data.name.slice(0,90):'UNNAMED';
  for(const t of textures)if(t)gl.deleteTexture(t);textures=[];textureAlphaFlags=[];textureBlendFlags=[];textureAlphaUnknown=[];pendingTextures=loadedTextures=failedTextures=0;
  let positions=new Float32Array(data.positions),normals=new Float32Array(data.normals),uvs=new Float32Array(data.uvs),indices=new Uint32Array(data.indices);
  gl.bindBuffer(gl.ARRAY_BUFFER,posbo);gl.bufferData(gl.ARRAY_BUFFER,positions,gl.STATIC_DRAW);
  gl.bindBuffer(gl.ARRAY_BUFFER,normbo);gl.bufferData(gl.ARRAY_BUFFER,normals,gl.STATIC_DRAW);
  gl.bindBuffer(gl.ARRAY_BUFFER,uvbo);gl.bufferData(gl.ARRAY_BUFFER,uvs,gl.STATIC_DRAW);
  gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,ibo);gl.bufferData(gl.ELEMENT_ARRAY_BUFFER,indices,gl.STATIC_DRAW);
  segments=data.groups.map(g=>({...g}));indexCount=indices.length;
  // One bounded centroid per material for coarse camera-relative sorting only.
  // This does not sort individual triangles and cannot reproduce exact MMD transparency.
  for(const g of segments){
   let sx=0,sy=0,sz=0;
   for(let k=g.start;k<g.start+g.count;k++){
    const o=indices[k]*3;sx+=positions[o];sy+=positions[o+1];sz+=positions[o+2];
   }
   const denom=Math.max(1,g.count);g.previewCentroid=[sx/denom,sy/denom,sz/denom];
  }
  center=data.bounds.min.map((x,i)=>(x+data.bounds.max[i])*0.5);
  radius=Math.max(0.001,Math.hypot(...data.bounds.max.map((x,i)=>x-data.bounds.min[i]))/2);
  bounds={min:[...data.bounds.min],max:[...data.bounds.max]};
  ready=true;resetCamera();
  message('STATIC MESH READY — loading local textures…');
  const sphereGroups=segments.filter(g=>g.sphere_mode===1||g.sphere_mode===2).length;
  const toonGroups=segments.filter(g=>g.toon_reference_mode==='texture'&&g.toon_texture_index>=0).length;
  const unsupported=segments.filter(g=>g.sphere_mode===3||g.toon_reference_mode==='shared').length;
  stats.textContent=`${data.name} · sha256 ${modelDigest.slice(0,16)} · ${data.vertex_count.toLocaleString()} vertices · ${data.triangle_count.toLocaleString()} triangles · ${data.groups.length} materials · ${sphereGroups} sphere groups · ${toonGroups} toon groups · ${unsupported} unsupported effect group(s)`;
  const version=++loadVersion;
  data.textures.forEach((info,i)=>{if(!info.url)return;pendingTextures++;const pic=new Image();
   pic.onload=()=>{if(version!==loadVersion)return;try{if(pic.width>4096||pic.height>4096||pic.width*pic.height>16777216)throw Error('Texture dimensions oversized');const tex=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,tex);gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL,true);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.REPEAT);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.REPEAT);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR_MIPMAP_LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,pic);gl.generateMipmap(gl.TEXTURE_2D);textures[i]=tex;
    // A 96x96 local alpha probe is intentionally sampled, not an exact alpha-mask proof.
    const coverage=sampledTextureAlpha(pic);textureAlphaFlags[i]=coverage.hasAlpha;textureBlendFlags[i]=coverage.needsBlend;textureAlphaUnknown[i]=coverage.unknown;loadedTextures++;}catch(e){failedTextures++;}finishTexture(version);};
   pic.onerror=()=>{if(version!==loadVersion)return;failedTextures++;finishTexture(version);};
   pic.src=info.url;
  });
  finishTexture(version);
  // No cached source; geometry exists only in current in-memory GPU buffers.
 }
 function draw(){
  if(!gl)return;
  const box=canvas.getBoundingClientRect();if(box.width<=0||box.height<=0)return;
  const dpr=Math.min(2,window.devicePixelRatio||1);const w=Math.max(1,Math.floor(box.width*dpr)),h=Math.max(1,Math.floor(box.height*dpr));
  if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h;}
  gl.viewport(0,0,w,h);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);if(!ready)return;
  gl.useProgram(program);
  const eye=[center[0]+distance*Math.sin(yaw)*Math.cos(pitch),center[1]+distance*Math.sin(pitch),center[2]+distance*Math.cos(yaw)*Math.cos(pitch)];
  const near=Math.max(0.001,distance/1000),far=Math.max(distance+radius*5, radius*25);
  gl.uniformMatrix4fv(uniforms.proj,false,mul(perspective(Math.PI/3,w/h,near,far),lookAt(eye,center,[0,1,0])));
  gl.bindBuffer(gl.ARRAY_BUFFER,posbo);gl.enableVertexAttribArray(attribs.pos);gl.vertexAttribPointer(attribs.pos,3,gl.FLOAT,false,0,0);
  gl.bindBuffer(gl.ARRAY_BUFFER,normbo);gl.enableVertexAttribArray(attribs.normal);gl.vertexAttribPointer(attribs.normal,3,gl.FLOAT,false,0,0);
  gl.bindBuffer(gl.ARRAY_BUFFER,uvbo);gl.enableVertexAttribArray(attribs.uv);gl.vertexAttribPointer(attribs.uv,2,gl.FLOAT,false,0,0);
  gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,ibo);
  gl.uniform1i(uniforms.tex,0);gl.uniform1i(uniforms.sphere,1);gl.uniform1i(uniforms.toon,2);
  gl.uniform1i(uniforms.colorMode,colorMode);
  gl.uniform1i(uniforms.correctDiffuseUV,correctDiffuseUV?1:0);
  const back=normalize(eye.map((v,i)=>v-center[i]));
  const right=normalize(cross([0,1,0],back));const up=cross(back,right);
  gl.uniform3fv(uniforms.eyeRight,new Float32Array(right));
  gl.uniform3fv(uniforms.eyeUp,new Float32Array(up));
  gl.uniform3fv(uniforms.eyeDirection,new Float32Array(back));
  gl.uniform1i(uniforms.legacyLighting,legacyLighting?1:0);
  function drawGroup(g){
   gl.uniform3fv(uniforms.color,new Float32Array(g.color));gl.uniform1f(uniforms.alpha,g.alpha);
   gl.uniform3fv(uniforms.ambient,new Float32Array(g.ambient));
   gl.uniform3fv(uniforms.specular,new Float32Array(g.specular));gl.uniform1f(uniforms.shininess,g.specular_strength);
   const tex=textures[g.texture_index];
   const sphere=(useSphere && (g.sphere_mode===1||g.sphere_mode===2))?textures[g.sphere_texture_index]:null;
   const toon=(useToon && g.toon_reference_mode==='texture')?textures[g.toon_texture_index]:null;
   gl.uniform1i(uniforms.hasTexture,tex?1:0);
   gl.uniform1i(uniforms.hasSphere,sphere?1:0);gl.uniform1i(uniforms.sphereMode,g.sphere_mode);
   gl.uniform1i(uniforms.hasToon,toon?1:0);
   gl.activeTexture(gl.TEXTURE0);gl.bindTexture(gl.TEXTURE_2D,tex||null);
   gl.activeTexture(gl.TEXTURE1);gl.bindTexture(gl.TEXTURE_2D,sphere||null);
   gl.activeTexture(gl.TEXTURE2);gl.bindTexture(gl.TEXTURE_2D,toon||null);
   gl.drawElements(gl.TRIANGLES,g.count,gl.UNSIGNED_INT,g.start*4);
  }
  // Unknown alpha classification falls back to the proven R11 order for the
  // entire model, rather than asserting that an uninspected image is opaque.
  const uncertain=segments.some(g=>g.texture_index>=0 && textureAlphaUnknown[g.texture_index]===true);
  if(!alphaPass||uncertain){
   // Exact R11 drawing behavior available as a regression control.
   gl.enable(gl.BLEND);gl.depthMask(true);
   for(const g of segments)drawGroup(g);
  }else{
   const opaque=[],translucent=[];
   for(const g of segments){
    const likelyAlpha=g.alpha<0.999||(g.texture_index>=0&&textureBlendFlags[g.texture_index]===true);
    (likelyAlpha?translucent:opaque).push(g);
   }
   // Keep R11 blending + depth behavior for mostly-opaque/cutout textures.
   // Face masks are not classified as whole-material translucent merely
   // because <1% of their texels contain alpha. Opaque group order is stable.
   gl.enable(gl.BLEND);gl.depthMask(true);
   for(const g of opaque)drawGroup(g);
   translucent.sort((a,b)=>{
    const depth=g=>{const c=g.previewCentroid;return (c[0]-eye[0])**2+(c[1]-eye[1])**2+(c[2]-eye[2])**2;};
    return depth(b)-depth(a)||a.material_index-b.material_index;
   });
   gl.enable(gl.BLEND);gl.depthMask(false);
   for(const g of translucent)drawGroup(g);
  }
  gl.depthMask(true);gl.disable(gl.BLEND);
 }
 const modeLabels=['Original texture · no tint/light','Texture × PMX diffuse · no light','MMD-style approximate toon/sphere; not parity-certified'];
 function setColorMode(value){
  const mode=Number(value);
  if(!Number.isInteger(mode)||mode<0||mode>2)return;
  colorMode=mode;
  if(colorModeControl)colorModeControl.value=String(colorMode);
  if(colorModeNote)colorModeNote.textContent=modeLabels[colorMode];
  draw();
 }
 if(colorModeControl)colorModeControl.addEventListener('change',()=>setColorMode(colorModeControl.value));
 if(toonControl)toonControl.addEventListener('change',()=>{useToon=toonControl.checked;draw();});
 if(sphereControl)sphereControl.addEventListener('change',()=>{useSphere=sphereControl.checked;draw();});
 if(legacyControl)legacyControl.addEventListener('change',()=>{legacyLighting=legacyControl.checked;draw();});
 if(correctedUvControl)correctedUvControl.addEventListener('change',()=>{correctDiffuseUV=correctedUvControl.checked;draw();});
 if(transparencyControl)transparencyControl.addEventListener('change',()=>{alphaPass=transparencyControl.checked;message('R13 alpha pass '+(alphaPass?'ON — significant alpha only, coarse sort':'OFF — R11 legacy'));draw();});
 // Read back on the explicit user click after drawing; no file upload or source-model writes.
 // Report whether each effect materially changes rendered framebuffer pixels.
 function snapshot(){
  draw();
  const count=canvas.width*canvas.height;
  if(!ready||count<1||count>8000000)throw Error('Framebuffer size outside safe GPU probe limit.');
  const rgba=new Uint8Array(count*4);
  gl.readPixels(0,0,canvas.width,canvas.height,gl.RGBA,gl.UNSIGNED_BYTE,rgba);
  if(gl.getError()!==gl.NO_ERROR)throw Error('WebGL readPixels failed.');
  return rgba;
 }
 function changed(a,b){
  if(a.length!==b.length)throw Error('GPU snapshot dimensions differ.');
  let pixels=0,sum=0,max=0;
  for(let i=0;i<a.length;i+=4){
   const delta=Math.max(Math.abs(a[i]-b[i]),Math.abs(a[i+1]-b[i+1]),Math.abs(a[i+2]-b[i+2]));
   if(delta>3){pixels++;sum+=delta;max=Math.max(max,delta);}
  }
  return {pixels,max,average:pixels?(sum/pixels).toFixed(2):'0.00'};
 }
 function gpuCompare(){
  if(!ready||!gl){message('HOLD_GPU_AB_NO_MESH');return;}
  const saved={toon:useToon,sphere:useSphere,mode:colorMode,uv:correctDiffuseUV,alphaPass};
  try{
   colorMode=2;useToon=true;useSphere=true;
   const full=snapshot();
   useToon=false;const noToon=snapshot();
   useToon=true;useSphere=false;const noSphere=snapshot();
   const toonDelta=changed(full,noToon),sphereDelta=changed(full,noSphere);
   colorMode=0;correctDiffuseUV=true;const fixedUV=snapshot();
   correctDiffuseUV=false;const invertedUV=snapshot();
   const uvDelta=changed(fixedUV,invertedUV);
   correctDiffuseUV=true;colorMode=2;useToon=true;useSphere=true;alphaPass=false;const oldAlpha=snapshot();
   alphaPass=true;const newAlpha=snapshot();const alphaDelta=changed(oldAlpha,newAlpha);
   if(compareOutput)compareOutput.textContent=`GPU A/B: Diffuse V correction changed ${uvDelta.pixels.toLocaleString()} pixels (max Δ ${uvDelta.max}); Toon changed ${toonDelta.pixels.toLocaleString()} pixels; Sphere changed ${sphereDelta.pixels.toLocaleString()} pixels. R13 Alpha pass changed ${alphaDelta.pixels.toLocaleString()} pixels. These are NOT MMD parity scores.`;
   message('GPU_AB_CAPTURED — see pixel differences below viewport toolbar');
  }catch(err){
   if(compareOutput)compareOutput.textContent='HOLD_GPU_AB: '+String(err.message||err);
   message('HOLD_GPU_AB');
  }finally{
   useToon=saved.toon;useSphere=saved.sphere;colorMode=saved.mode;correctDiffuseUV=saved.uv;alphaPass=saved.alpha;
   draw();
  }
 }
 if(compareButton)compareButton.addEventListener('click',gpuCompare);
 // Explicit user-action only: save an image of the rendered viewport and verifiable
 // model digest. Never saves the PMX, textures, URL, or local filesystem path.
 function saveQaPng(){
  if(!ready||!gl){message('HOLD_QA_PNG_NO_MESH');return;}
  try{
   draw(); // draw & copy synchronously; preserveDrawingBuffer stays disabled.
   const w=canvas.width,h=canvas.height;
   if(w<1||h<1||w*h>8000000)throw Error('Screenshot outside 8M pixel safety bound.');
   const image=document.createElement('canvas');image.width=w;image.height=h+136;
   const ctx=image.getContext('2d');if(!ctx)throw Error('2D screenshot context unavailable.');
   ctx.fillStyle='#0e1929';ctx.fillRect(0,0,image.width,image.height);
   ctx.drawImage(canvas,0,0,w,h);
   const size=Math.max(12,Math.min(20,Math.round(w/75)));
   ctx.font=size+'px monospace';ctx.fillStyle='#ffffff';
   ctx.fillText('Anime MMD Studio R13 · READ ONLY · NOT MMD PARITY CERTIFIED',12,h+25);
   const caption='Model sha256 '+modelDigest.slice(0,20)+' · Correct PMX V '+(correctDiffuseUV?'ON':'OFF')+' · Toon '+(useToon?'ON':'OFF')+' · Sphere '+(useSphere?'ON':'OFF')+' · Mode '+colorMode;
   ctx.fillText(caption.slice(0,150),12,h+53);
   ctx.fillText(('Lighting '+(legacyLighting?'R8 LEGACY':'R9 EXPERIMENTAL')+' · Alpha Pass '+(alphaPass?'ON':'OFF')+' · sampled alpha textures '+textureAlphaFlags.filter(Boolean).length+' · blend textures '+textureBlendFlags.filter(Boolean).length).slice(0,145),12,h+79);
   ctx.fillText(('Camera yaw='+yaw.toFixed(4)+' pitch='+pitch.toFixed(4)+' distance='+distance.toFixed(4)+' · capture='+new Date().toISOString()).slice(0,145),12,h+105);
   if(!window.StudioQaExport?.save)throw Error('LOCAL_QA_EXPORT_UNAVAILABLE');
   message('QA_PNG_SAVING_TO_EVIDENCE');
   window.StudioQaExport.save(image,'VIEWPORT').then(result=>{
     window.StudioQaExport.showLink('qaDownloadLink',result);
     message('PNG_SAVED_TO_EVIDENCE=' + result.evidence_png + ' | SHA256=' + result.sha256);
   }).catch(error=>message('HOLD_QA_PNG_SAVE: '+String(error.message||error)));
  }catch(err){message('HOLD_QA_PNG: '+String(err.message||err));}
 }
 if(saveQaButton)saveQaButton.addEventListener('click',saveQaPng);
 setColorMode(colorMode);
 canvas.addEventListener('pointerdown',e=>{if(!ready||e.button!==0)return;drag=[e.clientX,e.clientY];canvas.setPointerCapture(e.pointerId);});
 canvas.addEventListener('pointermove',e=>{if(!drag||!ready)return;let dx=e.clientX-drag[0],dy=e.clientY-drag[1];yaw-=dx*.006;pitch=clamp(pitch-dy*.006,-1.52,1.52);drag=[e.clientX,e.clientY];draw();});
 canvas.addEventListener('pointerup',()=>{drag=null;});canvas.addEventListener('pointercancel',()=>{drag=null;});
 canvas.addEventListener('wheel',e=>{if(!ready)return;e.preventDefault();distance=clamp(distance*Math.exp(e.deltaY*.001),Math.max(radius*.15,.005),radius*18);draw();},{passive:false});
 window.StudioViewport={load,clear,resetCamera,setColorMode,requestFrame:()=>requestAnimationFrame(draw),cameraState:()=>({yaw,pitch,distance,ready,colorMode,useToon,useSphere,legacyLighting,correctDiffuseUV,alphaPass,sampledAlphaTextures:textureAlphaFlags.filter(Boolean).length,significantBlendTextures:textureBlendFlags.filter(Boolean).length})};
})();
