"""Python-stdlib offline browser fallback for GUI-A0, no Node or Qt needed.

The server binds ONLY 127.0.0.1 on an ephemeral port. A random per-run
session secret is required for every request. There is no upload, core write,
network API, or remote asset dependency. Do not expose the port externally.
"""
from __future__ import annotations
import argparse
import datetime
from gui_a0.qa_saver import save_png, QASaveHold, MAX_PNG_BYTES
import json
import secrets
import threading as _threading
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from gui_a0.operations import dispatch
from gui_a0.texture_assets import resolve_declared_texture, open_texture_bytes, MAX_TEXTURE_COUNT, TextureHold

MAX_REQUEST=8192
MIME={'index.html':'text/html; charset=utf-8','style.css':'text/css; charset=utf-8','app.js':'text/javascript; charset=utf-8','bootstrap.js':'text/javascript; charset=utf-8','viewport.js':'text/javascript; charset=utf-8','camera_math.js':'text/javascript; charset=utf-8','alpha_policy.js':'text/javascript; charset=utf-8','transparency_corpus.js':'text/javascript; charset=utf-8','transparency_edges.js':'text/javascript; charset=utf-8','real_alpha_audit.js':'text/javascript; charset=utf-8','qa_export.js':'text/javascript; charset=utf-8'}


def make_handler(ui_root: Path, repo: Path, token: str, address: str, evidence_root: Path | None = None):
    base=f'/s/{token}/'
    assets={}
    assets_lock=_threading.RLock()
    qa_lock=_threading.RLock()
    qa_files={}
    qa_folder=None
    qa_count=0
    if evidence_root is None:
        evidence_root=Path(r'D:\Assets\MMDRegistry\Studio\Evidence')
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            # Do not print or archive request URLs containing a session token.
            pass
        def _reject(self, code, message):
            self.send_response(code)
            self.send_header('Content-Type','application/json; charset=utf-8')
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Referrer-Policy','no-referrer')
            self.end_headers()
            self.wfile.write(json.dumps({'ok':False,'error':message}).encode('utf-8'))
        def _valid(self):
            return self.headers.get('Host') == address and urlsplit(self.path).path.startswith(base)
        def do_GET(self):
            if not self._valid():return self._reject(403,'Local session denied')
            name=urlsplit(self.path).path[len(base):] or 'index.html'
            if name.startswith('qa/'):
                key=name[len('qa/'):]
                if not key or '/' in key or len(key)>128:
                    return self._reject(404,'Not found')
                with qa_lock:
                    saved=qa_files.get(key)
                if saved is None:
                    return self._reject(404,'Not found')
                try:
                    content=saved.read_bytes()
                except OSError:
                    return self._reject(404,'Not found')
                self.send_response(200)
                self.send_header('Content-Type','image/png')
                self.send_header('Content-Length',str(len(content)))
                self.send_header('Content-Disposition','attachment; filename="'+saved.name+'"')
                self.send_header('Cache-Control','no-store')
                self.send_header('X-Content-Type-Options','nosniff')
                self.send_header('Referrer-Policy','no-referrer')
                self.end_headers()
                self.wfile.write(content)
                return
            if name.startswith('asset/'):
                asset_id = name[len('asset/'):]
                if not asset_id or '/' in asset_id or len(asset_id)>64:
                    return self._reject(404,'Not found')
                with assets_lock:
                    registered = assets.get(asset_id)
                if registered is None:
                    return self._reject(404,'Not found')
                try:
                    kind, content = open_texture_bytes(registered)
                except (OSError, ValueError):
                    return self._reject(404,'Image unavailable')
                self.send_response(200)
                self.send_header('Content-Type', kind)
                self.send_header('Content-Length',str(len(content)))
                self.send_header('Cache-Control','no-store')
                self.send_header('X-Content-Type-Options','nosniff')
                self.send_header('Referrer-Policy','no-referrer')
                self.end_headers()
                self.wfile.write(content)
                return
            if name not in MIME:return self._reject(404,'Not found')
            try:content=(ui_root/name).read_bytes()
            except OSError:return self._reject(500,'UI asset unavailable')
            self.send_response(200)
            self.send_header('Content-Type',MIME[name]);self.send_header('Content-Length',str(len(content)))
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Referrer-Policy','no-referrer')
            self.send_header('Cache-Control','no-store')
            self.send_header('Content-Security-Policy',"default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
            self.end_headers();self.wfile.write(content)
        def do_POST(self):
            nonlocal qa_folder, qa_count
            if not self._valid():
                return self._reject(403,'Local session denied')
            resource=urlsplit(self.path).path
            if resource==base+'api/qa-png':
                if self.headers.get('Origin')!='http://'+address:
                    return self._reject(403,'Origin denied')
                if self.headers.get('Content-Type','').split(';')[0].strip()!='image/png':
                    return self._reject(415,'PNG only')
                kind=self.headers.get('X-MMD-QA-Kind')
                if kind not in ('VIEWPORT','ALPHA_AB'):
                    return self._reject(422,'QA kind invalid')
                try:
                    length=int(self.headers.get('Content-Length','-1'))
                except ValueError:
                    return self._reject(400,'Malformed body length')
                if length < 45 or length > MAX_PNG_BYTES:
                    return self._reject(413,'PNG size bound')
                body=self.rfile.read(length)
                if len(body)!=length:
                    return self._reject(400,'Truncated PNG body')
                with qa_lock:
                    if qa_count>=20:
                        return self._reject(429,'QA screenshot count bound')
                    if qa_folder is None:
                        stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
                        qa_folder=evidence_root/('MMD_STUDIO_CP16F_GUI_'+stamp+'_'+secrets.token_hex(5))
                    try:
                        record=save_png(qa_folder,body,kind)
                    except (OSError,QASaveHold) as exc:
                        return self._reject(422,type(exc).__name__+': '+str(exc))
                    qa_count+=1
                    qa_files[record['filename']]=qa_folder/record['filename']
                    record['download_url']='qa/'+record['filename']
                data=json.dumps({'ok':True,'result':record},ensure_ascii=False).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type','application/json; charset=utf-8')
                self.send_header('Content-Length',str(len(data)))
                self.send_header('Cache-Control','no-store')
                self.send_header('X-Content-Type-Options','nosniff')
                self.end_headers()
                self.wfile.write(data)
                return
            if resource!=base+'api/inspect':
                return self._reject(403,'Local session denied')
            # Reject cross-origin forms/scripts; browser app sends JSON preflight.
            origin=self.headers.get('Origin')
            if origin is not None and origin != 'http://'+address:
                return self._reject(403,'Cross-origin request denied')
            if self.headers.get('Content-Type','').split(';')[0].strip()!='application/json':
                return self._reject(415,'JSON only')
            try:
                size=int(self.headers.get('Content-Length','-1'))
            except ValueError:
                return self._reject(400,'Malformed body length')
            if size<1 or size>MAX_REQUEST:return self._reject(413,'Body size bound')
            try:
                body=json.loads(self.rfile.read(size).decode('utf-8'))
                if type(body) is not dict:raise ValueError()
                result=dispatch(body.get('kind'),body.get('path'),repo)
                if body.get('kind')=='preview':
                    data=result['data']
                    declared=data.pop('texture_paths', [])
                    if not isinstance(declared,list) or len(declared)>MAX_TEXTURE_COUNT:
                        raise TextureHold('Too many declared texture paths for local preview.')
                    source=Path(body['path']).resolve(strict=True)
                    prepared=[]
                    new_assets={}
                    for item in declared:
                        path=resolve_declared_texture(source,item)
                        if path is None:
                            prepared.append({'url':None,'status':'missing_or_unsupported'})
                        else:
                            opaque=secrets.token_hex(16)
                            new_assets[opaque]=path
                            prepared.append({'url':'asset/'+opaque,'status':'available'})
                    with assets_lock:
                        assets.clear()  # Old model textures must never remain readable.
                        assets.update(new_assets)
                    data['textures']=prepared
            except Exception as exc:
                return self._reject(422,f'{type(exc).__name__}: {exc}')
            data=json.dumps({'ok':True,'result':result},ensure_ascii=False).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type','application/json; charset=utf-8')
            self.send_header('Content-Length',str(len(data)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.end_headers();self.wfile.write(data)
        def do_OPTIONS(self):return self._reject(405,'CORS disabled')
    return Handler


def main(argv=None):
    ap=argparse.ArgumentParser()
    ap.add_argument('--repo',type=Path,default=Path(r'D:\MMD\mmd-asset-registry'))
    ap.add_argument('--no-browser',action='store_true')
    ap.add_argument('--evidence-root',type=Path,default=Path(r'D:\Assets\MMDRegistry\Studio\Evidence'))
    args=ap.parse_args(argv)
    if not (args.repo/'check_assets.py').is_file():
        print('BROWSER_GUI=HOLD_MISSING_CORE');return 3
    secret=secrets.token_urlsafe(32)
    server=ThreadingHTTPServer(('127.0.0.1',0),BaseHTTPRequestHandler)
    port=server.server_address[1]
    server.server_close()
    address=f'127.0.0.1:{port}'
    # Bind selected port as close to initial allocation as possible; any collision fails cleanly.
    handler=make_handler(Path(__file__).resolve().parent,args.repo,secret,address,args.evidence_root)
    try:server=ThreadingHTTPServer(('127.0.0.1',port),handler)
    except OSError as exc:
        print(f'BROWSER_GUI=HOLD_PORT {type(exc).__name__}');return 3
    url=f'http://{address}/s/{secret}/'
    print('BROWSER_GUI=STARTED_LOCAL_READONLY_HOST',flush=True)
    print('Note: localhost read-only textured WebGL2 preview; no PMX editor.',flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:server.serve_forever(poll_interval=.2)
    except KeyboardInterrupt:pass
    finally:server.server_close()
    return 0

if __name__=='__main__':raise SystemExit(main())
