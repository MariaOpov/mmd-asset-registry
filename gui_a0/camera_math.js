/* GUI-A2-P1 camera-only UX math: no PMX writes, network or runtime dependencies. */
'use strict';
(function(global){
 function finiteBounds(bounds){
   if(!bounds || !Array.isArray(bounds.min) || !Array.isArray(bounds.max) || bounds.min.length!==3 || bounds.max.length!==3)
     throw Error('Invalid camera bounds.');
   for(let i=0;i<3;i++)if(!Number.isFinite(bounds.min[i])||!Number.isFinite(bounds.max[i])||bounds.min[i]>bounds.max[i])
     throw Error('Invalid camera bounds.');
 }
 function dotAbs(axis,half){return Math.abs(axis[0])*half[0]+Math.abs(axis[1])*half[1]+Math.abs(axis[2])*half[2];}
 /** Fit all 8 bounding-box corners for the actual view orientation and viewport aspect.
  * Returns camera-center distance; occupancy 0.78 leaves ~22% framing margin. */
 function fitDistance(bounds,yaw,pitch,width,height){
   finiteBounds(bounds);
   if(!Number.isFinite(yaw)||!Number.isFinite(pitch))throw Error('Invalid camera angles.');
   const half=bounds.min.map((v,i)=>(bounds.max[i]-v)/2);
   const radius=Math.max(.001,Math.hypot(...half));
   const w=Number.isFinite(width)&&width>0?width:1280;
   const h=Number.isFinite(height)&&height>0?height:720;
   const aspect=Math.max(.25,Math.min(8,w/h));
   const sy=Math.sin(yaw),cy=Math.cos(yaw),sp=Math.sin(pitch),cp=Math.cos(pitch);
   const viewZ=[sy*cp,sp,cy*cp];
   const viewX=[cy,0,-sy];
   const viewY=[-sy*sp,cp,-cy*sp];
   const depth=dotAbs(viewZ,half);
   const right=dotAbs(viewX,half),top=dotAbs(viewY,half);
   const tanHalf=Math.tan(Math.PI/6); // match 60-degree perspective in viewport.js
   const fill=.90;
   // Conservative AABB projection: nearest corner depth plus horizontal/vertical extent.
   const needed=depth+Math.max(right/(aspect*tanHalf*fill),top/(tanHalf*fill));
   return Math.max(radius*1.08,needed,.01);
 }
 const API=Object.freeze({fitDistance,defaultYaw:Math.PI,defaultPitch:.10});
 if(global)global.StudioCameraMath=API;
 if(typeof module!=='undefined' && module.exports)module.exports=API;
})(typeof window!=='undefined'?window:null);
