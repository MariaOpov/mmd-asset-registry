/* R13 bounded alpha coverage policy; no network or source writes. */
'use strict';
(function(root){
 function classify(rgba){
  if(!rgba||!Number.isInteger(rgba.length)||rgba.length===0||rgba.length%4!==0)
   return {hasAlpha:false,needsBlend:false,unknown:true};
  const samples=rgba.length/4;
  let hasAlpha=false,partiallyTranslucent=0;
  for(let i=3;i<rgba.length;i+=4){
   const a=rgba[i];
   if(!Number.isFinite(a)||a<0||a>255)
    return {hasAlpha:false,needsBlend:false,unknown:true};
   if(a<250)hasAlpha=true;
   // Ignore near-opaque alpha (245..254), sparse cutouts and antialiased
   // outlines; whole-material sorting would hide eyes / fringe overlays.
   if(a>=16&&a<240)partiallyTranslucent++;
  }
  return {hasAlpha,needsBlend:partiallyTranslucent/samples>=0.05,unknown:false};
 }
 root.StudioAlphaPolicy=Object.freeze({classify});
})(typeof window!=='undefined'?window:globalThis);
