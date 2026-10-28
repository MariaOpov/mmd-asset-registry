"""PySide6 GUI-A0 with model/VMD/template read-only bridge; no installers."""
from __future__ import annotations
import argparse
import json
import sys
import threading
from pathlib import Path
from gui_a0.operations import dispatch


def main(argv=None) -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument('--repo',type=Path,default=Path(r'D:\MMD\mmd-asset-registry'))
    args=parser.parse_args(argv)
    if not (args.repo/'check_assets.py').is_file():
        print('GUI_A0=HOLD_MISSING_CORE_ENTRYPOINT')
        return 4
    try:
        from PySide6.QtCore import QObject, QUrl, Signal, Slot
        from PySide6.QtWidgets import QApplication, QFileDialog
        from PySide6.QtWebChannel import QWebChannel
        from PySide6.QtWebEngineWidgets import QWebEngineView
        from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
    except (ImportError, OSError) as exc:
        print(f'GUI_A0=HOLD_MISSING_QT_RUNTIME {type(exc).__name__}: {exc}')
        return 3

    root=Path(__file__).resolve().parent
    class LocalPage(QWebEnginePage):
        def acceptNavigationRequest(self, url, navigation_type, isMainFrame):
            return url.scheme() in {'file','qrc'}

    class Bridge(QObject):
        resultReady=Signal(str)
        statusReady=Signal(str)
        @Slot(str, str)
        def inspectPath(self, kind, path):
            self.statusReady.emit(f'Inspecting {kind} — source remains read-only…')
            def job():
                try:
                    result=dispatch(kind, path, args.repo)
                    self.resultReady.emit(json.dumps(result,ensure_ascii=False))
                except Exception as exc:
                    self.statusReady.emit(f'HOLD {type(exc).__name__}: {exc}')
            threading.Thread(target=job,daemon=True,name='StudioReadOnlyInspection').start()
        @Slot(str)
        def openFile(self, kind):
            extensions={'model':'MMD Model (*.pmx *.pmd)','motion':'MMD Motion (*.vmd)',
                        'template':'Template manifest (*.json)'}
            if kind not in extensions:
                self.statusReady.emit('HOLD: unsupported picker kind');return
            source,_=QFileDialog.getOpenFileName(view,'Open read-only asset', '',extensions[kind])
            if source:
                self.inspectPath(kind, source)
    app=QApplication(sys.argv[:1]); app.setApplicationName('Anime MMD Studio R1')
    view=QWebEngineView()
    page=LocalPage(view)
    view.setPage(page)
    page.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls,False)
    page.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls,True)
    bridge=Bridge();channel=QWebChannel(page)
    channel.registerObject('studio',bridge);page.setWebChannel(channel)
    page.load(QUrl.fromLocalFile(str(root/'index.html')))
    view.resize(1420,880);view.setWindowTitle('Anime MMD Studio — R1 READ ONLY')
    view.show()
    return app.exec()

if __name__=='__main__':raise SystemExit(main())
