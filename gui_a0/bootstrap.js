'use strict';
(function(){
 function launch(){const s=document.createElement('script');s.src='app.js';document.body.appendChild(s);}
 if(typeof qt==='undefined'){launch();return;}
 const s=document.createElement('script');s.src='qrc:///qtwebchannel/qwebchannel.js';
 s.onload=launch;s.onerror=launch;document.body.appendChild(s);
})();
