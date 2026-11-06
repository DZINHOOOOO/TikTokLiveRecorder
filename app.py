import json, os, re, shutil, subprocess, sys, time, urllib.request, logging, threading
from logging.handlers import RotatingFileHandler
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse, unquote, quote
from PySide6.QtCore import Qt, QThread, QTimer, Signal, QSize, QStringListModel
from updater import VERSION, latest_release, download_update, launch_helper, apply_update
from PySide6.QtGui import QPixmap, QPainter, QColor, QFont, QDesktopServices, QIcon, QAction
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
 QPushButton, QLineEdit, QListWidget, QListWidgetItem, QFileDialog, QMessageBox, QSpinBox,
 QCheckBox, QFrame, QAbstractItemView, QSystemTrayIcon, QMenu, QCompleter, QTabWidget, QComboBox, QTableWidget, QTableWidgetItem, QHeaderView, QSlider)

ROOT = Path(os.getenv('LOCALAPPDATA') or (Path.home() / 'AppData' / 'Local')) / 'TikTokLiveRecorder'
ROOT.mkdir(parents=True, exist_ok=True)
CONFIG = ROOT / 'config.json'
LOG_FILE = ROOT / 'recorder.log'
logger = logging.getLogger('TikTokLiveRecorder')
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=3, encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s | %(levelname)s | %(message)s'))
    logger.addHandler(handler)

def startup_shortcut():
    return Path(os.getenv('APPDATA', str(Path.home() / 'AppData' / 'Roaming'))) / 'Microsoft' / 'Windows' / 'Start Menu' / 'Programs' / 'Startup' / 'TikTokLiveRecorder.cmd'

def configure_startup(enabled):
    if os.name != 'nt' or not getattr(sys, 'frozen', False):
        raise RuntimeError('Compile o EXE no Windows para ativar a inicialização automática.')
    shortcut = startup_shortcut()
    if enabled:
        shortcut.parent.mkdir(parents=True, exist_ok=True)
        exe = str(Path(sys.executable).resolve())
        if '"' in exe or chr(10) in exe: raise ValueError('Caminho inválido')
        shortcut.write_text('@echo off\nstart "" "' + exe + '" --minimized\n', encoding='utf-8')
    else:
        shortcut.unlink(missing_ok=True)

DEFAULT_FOLDER = Path.home() / 'Videos' / 'TikTokLiveRecorder'
USER_RE = re.compile(r'^[A-Za-z0-9._]{2,24}$')

def username_from_input(value):
    value = value.strip()
    if value.startswith('@'):
        value = value[1:]
    elif 'tiktok.com' in value.lower():
        if not value.startswith(('http://', 'https://')):
            value = 'https://' + value
        url = urlparse(value)
        host = (url.hostname or '').lower()
        if host not in ('tiktok.com', 'www.tiktok.com', 'm.tiktok.com'):
            raise ValueError('O link precisa ser de um perfil do TikTok.')
        match = re.match(r'^/@([^/]+)', unquote(url.path))
        if not match:
            raise ValueError('Use o link do perfil: https://www.tiktok.com/@usuario')
        value = match.group(1)
    if not USER_RE.fullmatch(value):
        raise ValueError('Informe um @usuário ou link válido do perfil.')
    return value

def load_config():
    try:
        obj = json.loads(CONFIG.read_text(encoding='utf-8'))
        return obj if isinstance(obj, dict) else {}
    except (OSError, ValueError):
        return {}

def save_config(config):
    tmp = CONFIG.with_suffix('.tmp')
    tmp.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(CONFIG)

def streamlink_binary():
    found = shutil.which('streamlink')
    if found: return found
    for base in (Path(os.getenv('PROGRAMFILES', 'C:/Program Files')), Path(os.getenv('LOCALAPPDATA', ''))):
        for path in (base / 'Streamlink' / 'bin' / 'streamlink.exe', base / 'Streamlink' / 'streamlink.exe'):
            if path.is_file(): return str(path)
    return None

class ProfileFetcher(QThread):
    ready = Signal(str, bytes)
    def __init__(self, name):
        super().__init__(); self.name = name
    def run(self):
        # Avatar best-effort: public HTML may not expose the profile picture.
        try:
            req = urllib.request.Request(f'https://www.tiktok.com/@{self.name}', headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=9) as resp:
                html = resp.read(1_000_000).decode('utf-8', errors='ignore')
            matches = re.findall(r'<meta[^>]+(?:property|name)=["\'](?:og:image|twitter:image)["\'][^>]+content=["\']([^"\']+)', html, re.I)
            if not matches:
                matches = re.findall(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\'](?:og:image|twitter:image)', html, re.I)
            if not matches: return
            from html import unescape
            image_url = unescape(matches[0])
            if not image_url.startswith('https://'): return
            with urllib.request.urlopen(urllib.request.Request(image_url, headers={'User-Agent':'Mozilla/5.0'}), timeout=8) as resp:
                if not resp.headers.get('Content-Type', '').startswith('image/'): return
                data = resp.read(500_000)
            self.ready.emit(self.name, data)
        except Exception:
            pass

def ffmpeg_binary(tool='ffmpeg'):
    result = shutil.which(tool)
    if result: return result
    for base in (Path(os.getenv('PROGRAMFILES', 'C:/Program Files')) / 'ffmpeg' / 'bin', Path(sys.executable).parent):
        candidate = base / (tool + '.exe')
        if candidate.is_file(): return str(candidate)
    return None

def inspect_media(path):
    probe = ffmpeg_binary('ffprobe')
    if not probe: return False, 'FFprobe não instalado; integridade não verificada'
    try:
        result = subprocess.run([probe, '-v', 'error', '-show_entries', 'stream=codec_type', '-of', 'json', str(path)],
            capture_output=True, text=True, timeout=35, creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if result.returncode: return False, (result.stderr or 'Arquivo inválido')[:160]
        streams = json.loads(result.stdout).get('streams', [])
        return any(x.get('codec_type') == 'video' for x in streams), 'FFprobe: fluxo de vídeo encontrado' if streams else 'Nenhum fluxo encontrado'
    except Exception as exc: return False, str(exc)[:160]

def cleanup_ts(folder, days):
    # Apenas arquivos .ts de nossa pasta de originais; nunca apaga gravações ainda ativas.
    root = Path(folder) / '_TS_originais'
    if not root.is_dir(): return 0
    count = 0; cutoff = time.time() - int(days)*86400
    for f in root.glob('*.ts'):
        if f.is_file() and f.stat().st_mtime < cutoff and (root.parent / (f.stem + '.mp4')).is_file():
            # MP4 validado antes de apagar original.
            ok, _ = inspect_media(root.parent / (f.stem + '.mp4'))
            if ok:
                f.unlink(); count += 1
    return count

class Recorder(QThread):
    update = Signal(str, str, str)
    def __init__(self, name, folder, options=None):
        super().__init__(); self.name=name; self.folder=Path(folder); self.options=options or {}; self.proc=None; self.stopping=False
    def run(self):
        binary=streamlink_binary()
        if not binary:
            self.update.emit(self.name,'erro','Streamlink não encontrado no PATH.'); return
        url=f'https://www.tiktok.com/@{self.name}/live'
        flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
        try:
            self.update.emit(self.name,'checando','Diagnóstico: consultando Streamlink...')
            probe=subprocess.run([binary,'--json',url,'best'],capture_output=True,text=True,timeout=40,creationflags=flags)
            if self.stopping: return
            if probe.returncode:
                msg=(probe.stderr or probe.stdout or '').strip()
                if 'No plugin can handle' in msg: self.update.emit(self.name,'erro','Streamlink não suporta esta URL; instale um plugin compatível.')
                else: self.update.emit(self.name,'offline','Sem stream acessível: '+msg[-130:])
                return
            base=self.folder; originals=base/'_TS_originais'; originals.mkdir(parents=True,exist_ok=True)
            stamp=datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
            ts=originals/f'{self.name}_{stamp}.ts'
            self.update.emit(self.name,'gravando',f'Gravando: {ts.name}')
            self.proc=subprocess.Popen([binary,'--retry-open','2',url,'best','-o',str(ts)],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,creationflags=flags)
            try: _, err=self.proc.communicate()
            finally: self.proc=None
            if not ts.is_file() or ts.stat().st_size < 188:
                self.update.emit(self.name,'erro','Captura vazia: '+(err or b'').decode(errors='replace')[-120:]); return
            valid, reason=inspect_media(ts)
            if not valid:
                self.update.emit(self.name,'erro','TS preservado, verificação: '+reason); return
            if self.options.get('format','MP4')=='TS':
                self.update.emit(self.name,'salvo',f'TS validado: {ts.name}'); return
            ffmpeg=ffmpeg_binary()
            if not ffmpeg:
                self.update.emit(self.name,'erro','TS preservado. Instale FFmpeg e FFprobe para gerar MP4.'); return
            mp4=base/(ts.stem+'.mp4'); temp=base/(ts.stem+'.partial.mp4')
            self.update.emit(self.name,'convertendo','Convertendo TS para MP4 sem recodificar...')
            result=subprocess.run([ffmpeg,'-hide_banner','-loglevel','error','-y','-i',str(ts),'-map','0:v:0','-map','0:a?','-c','copy','-movflags','+faststart',str(temp)],capture_output=True,text=True,timeout=3600,creationflags=flags)
            ok, detail=inspect_media(temp) if temp.exists() else (False,'Arquivo MP4 não criado')
            if result.returncode==0 and ok and temp.stat().st_size>0:
                temp.replace(mp4)
                self.update.emit(self.name,'salvo',f'MP4 validado: {mp4.name}')
            else:
                temp.unlink(missing_ok=True)
                self.update.emit(self.name,'erro','MP4 falhou, TS preservado: '+(result.stderr or detail)[-140:])
        except subprocess.TimeoutExpired:
            self.update.emit(self.name,'erro','Tempo limite na verificação ou conversão.')
        except Exception as exc:
            self.update.emit(self.name,'erro',f'Falha: {str(exc)[:150]}')
        finally: self.proc=None
    def stop(self):
        self.stopping=True
        if self.proc and self.proc.poll() is None:
            try: self.proc.terminate()
            except OSError: pass

class ProfileCard(QWidget):
    def __init__(self, name, status, detail, avatar=None):
        super().__init__()
        row = QHBoxLayout(self); row.setContentsMargins(12, 8, 12, 8); row.setSpacing(12)
        pic = QLabel(); pic.setFixedSize(46,46)
        pix = QPixmap(46,46); pix.fill(QColor('#312744'))
        if avatar:
            raw = QPixmap(); raw.loadFromData(avatar)
            if not raw.isNull(): pix = raw.scaled(46,46,Qt.AspectRatioMode.KeepAspectRatioByExpanding,Qt.TransformationMode.SmoothTransformation)
        if not avatar:
            painter = QPainter(pix); painter.setPen(QColor('#dfcaff')); painter.setFont(QFont('Segoe UI', 19, QFont.Weight.Bold)); painter.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, name[:1].upper()); painter.end()
        pic.setPixmap(pix); row.addWidget(pic)
        middle = QVBoxLayout(); middle.setSpacing(2)
        handle = QLabel('@'+name); handle.setObjectName('handle'); middle.addWidget(handle)
        sub = QLabel(detail); sub.setObjectName('muted'); sub.setWordWrap(True); middle.addWidget(sub)
        row.addLayout(middle, 1)
        badge = QLabel(status.upper()); badge.setObjectName('badge')
        badge.setStyleSheet('color:' + ('#4adea2' if status=='gravando' else '#f6bd60' if status in ('erro','checando') else '#b4a7cc') + ';')
        row.addWidget(badge)

class UpdateWorker(QThread):
    result = Signal(object)
    progress = Signal(int)
    failure = Signal(str)
    def __init__(self, info=None):
        super().__init__()
        self.info = info
    def run(self):
        try:
            value = download_update(self.info, self.progress.emit) if self.info else latest_release()
            self.result.emit(value)
        except Exception as exc:
            self.failure.emit(str(exc))

class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.cfg = load_config(); self.cfg.setdefault('profiles', [])
        self.update_worker = None; self.update_workers = []; self.pending_update = None
        self.workers = {}; self.fetchers = {}; self.avatars = {}; self.states = {}; self.last_check = 0
        self.setWindowTitle('TikTok Live Recorder ' + VERSION); self.resize(1080, 790); self.setMinimumSize(760, 600)
        root = QWidget(); self.setCentralWidget(root)
        outer = QVBoxLayout(root); outer.setContentsMargins(30,26,30,24); outer.setSpacing(16)
        header = QHBoxLayout(); headings = QVBoxLayout()
        title = QLabel('LIVE RECORDER'); title.setObjectName('title'); headings.addWidget(title)
        subtitle = QLabel('Perfis públicos  /  Monitoramento automático  /  Gravações locais'); subtitle.setObjectName('muted'); headings.addWidget(subtitle)
        header.addLayout(headings,1)
        self.count = QLabel('0 PERFIS'); self.count.setObjectName('counter'); header.addWidget(self.count)
        outer.addLayout(header)
        self.tabs=QTabWidget(); outer.addWidget(self.tabs, 1)
        monitoring=QWidget(); self.tabs.addTab(monitoring, 'Monitoramento')
        monitor_layout=QVBoxLayout(monitoring); monitor_layout.setSpacing(12)
        panel = QFrame(); panel.setObjectName('panel'); entryrow = QHBoxLayout(panel); entryrow.setContentsMargins(16,16,16,16)
        self.entry = QLineEdit(); self.entry.setPlaceholderText('Cole o link do perfil ou digite @usuario')
        self.entry.returnPressed.connect(self.add_profile); entryrow.addWidget(self.entry,1)
        self.suggestion_model = QStringListModel(self)
        self.completer = QCompleter(self.suggestion_model, self)
        self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.entry.setCompleter(self.completer)
        self.entry.textEdited.connect(self.update_suggestions)
        self.completer.activated.connect(self.on_suggestion_selected)
        search_btn = QPushButton('Pesquisar no TikTok')
        search_btn.setToolTip('Abre a pesquisa oficial no navegador. A busca pública não é fornecida pela API oficial.')
        search_btn.clicked.connect(self.search_tiktok)
        entryrow.addWidget(search_btn)
        add = QPushButton('+ Adicionar perfil'); add.clicked.connect(self.add_profile); entryrow.addWidget(add)
        monitor_layout.addWidget(panel)
        caption = QHBoxLayout(); caption.addWidget(QLabel('PERFIS MONITORADOS'))
        caption.addStretch(); self.activity = QLabel('Aguardando'); self.activity.setObjectName('muted'); caption.addWidget(self.activity)
        monitor_layout.addLayout(caption)
        self.list = QListWidget(); self.list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list.setSpacing(6); monitor_layout.addWidget(self.list,1)
        actions = QHBoxLayout()
        for label, callback in [('Verificar agora',self.check_all),('Parar gravações',self.stop_all),('Remover perfil',self.remove_profile)]:
            btn = QPushButton(label); btn.clicked.connect(callback); actions.addWidget(btn)
        monitor_layout.addLayout(actions)
        settings = QFrame(); settings.setObjectName('panel'); srow = QHBoxLayout(settings); srow.setContentsMargins(16,14,16,14)
        self.auto = QCheckBox('Monitorar automaticamente'); self.auto.setChecked(bool(self.cfg.get('auto', False)))
        self.auto.toggled.connect(self.persist); srow.addWidget(self.auto)
        srow.addWidget(QLabel('A cada'))
        self.interval = QSpinBox(); self.interval.setRange(2,60); self.interval.setValue(max(2,min(60,int(self.cfg.get('interval',5)))))
        self.interval.setSuffix(' min'); self.interval.valueChanged.connect(self.persist); srow.addWidget(self.interval)
        srow.addStretch()
        folder = QPushButton('Alterar pasta'); folder.clicked.connect(self.choose_folder); srow.addWidget(folder)
        open_btn = QPushButton('Abrir gravações'); open_btn.clicked.connect(self.open_folder); srow.addWidget(open_btn)
        outer.addWidget(settings)
        extra = QHBoxLayout()
        self.startup = QCheckBox('Iniciar com o Windows (minimizado)')
        self.startup.setChecked(startup_shortcut().exists())
        self.startup.toggled.connect(self.toggle_startup)
        extra.addWidget(self.startup)
        self.notify = QCheckBox('Notificar quando começar a gravar')
        self.notify.setChecked(bool(self.cfg.get('notify', True)))
        self.notify.toggled.connect(self.persist)
        extra.addWidget(self.notify)
        extra.addStretch()
        log_btn = QPushButton('Abrir logs')
        log_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(ROOT))))
        extra.addWidget(log_btn)
        outer.addLayout(extra)
        updater_row = QHBoxLayout()
        self.version_label = QLabel('Versão ' + VERSION); self.version_label.setObjectName('muted')
        updater_row.addWidget(self.version_label); updater_row.addStretch()
        self.update_status = QLabel('Atualizações via GitHub Releases'); self.update_status.setObjectName('muted')
        updater_row.addWidget(self.update_status)
        self.update_button = QPushButton('Verificar atualizações')
        self.update_button.clicked.connect(self.check_updates)
        updater_row.addWidget(self.update_button)
        outer.addLayout(updater_row)
        self.note = QLabel('O Streamlink precisa reconhecer o stream público. Busca remota de perfis não está disponível pela API pública oficial.')
        self.note.setObjectName('muted'); self.note.setWordWrap(True); outer.addWidget(self.note)
        # Biblioteca e indicadores locais (não bloqueiam a UI)
        library=QWidget(); self.tabs.addTab(library,'Biblioteca')
        lib_layout=QVBoxLayout(library)
        self.stats=QLabel('Calculando estatísticas...'); lib_layout.addWidget(self.stats)
        self.library_table=QTableWidget(0,4)
        self.library_table.setHorizontalHeaderLabels(['Arquivo','Formato','Tamanho','Data'])
        self.library_table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
        self.library_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.library_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        lib_layout.addWidget(self.library_table)
        lib_actions=QHBoxLayout()
        refresh_library=QPushButton('Atualizar biblioteca'); refresh_library.clicked.connect(self.refresh_library)
        play=QPushButton('Reproduzir selecionado'); play.clicked.connect(self.play_selected)
        lib_actions.addWidget(refresh_library); lib_actions.addWidget(play); lib_layout.addLayout(lib_actions)
        format_page=QWidget(); self.tabs.addTab(format_page,'Formatos e limpeza')
        fmt=QVBoxLayout(format_page)
        fmt.addWidget(QLabel('Formato de saída (novas gravações)'))
        self.output_format=QComboBox(); self.output_format.addItems(['MP4','TS']); self.output_format.setCurrentText(self.cfg.get('format','MP4'))
        self.output_format.currentTextChanged.connect(self.persist); fmt.addWidget(self.output_format)
        self.retention=QSpinBox(); self.retention.setRange(1,365); self.retention.setSuffix(' dias'); self.retention.setValue(int(self.cfg.get('retention',3)))
        self.retention.valueChanged.connect(self.persist)
        fmt.addWidget(QLabel('Excluir originais TS após (somente se MP4 validado)')); fmt.addWidget(self.retention)
        cleanup=QPushButton('Limpar TS antigos agora'); cleanup.clicked.connect(self.clean_now); fmt.addWidget(cleanup)
        fmt.addWidget(QLabel('TS fica em cada pasta de perfil / _TS_originais. Nunca apagamos um TS sem MP4 válido.'))
        fmt.addStretch()
        self.refresh_library()
        self.exiting = False
        self.tray = None
        icon_path = Path(__file__).resolve().parent / 'assets' / 'recorder.ico'
        if getattr(sys, 'frozen', False):
            icon_path = Path(getattr(sys, '_MEIPASS', Path(sys.executable).parent)) / 'assets' / 'recorder.ico'
        self.app_icon = QIcon(str(icon_path))
        self.setWindowIcon(self.app_icon)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(self.app_icon, self)
            self.tray.setToolTip('TikTok Live Recorder • Monitoramento local')
            menu = QMenu(self)
            show_action = QAction('Abrir aplicativo', self)
            show_action.triggered.connect(self.show_from_tray)
            menu.addAction(show_action)
            check_action = QAction('Verificar perfis agora', self)
            check_action.triggered.connect(self.check_all)
            menu.addAction(check_action)
            menu.addSeparator()
            quit_action = QAction('Encerrar aplicativo', self)
            quit_action.triggered.connect(self.exit_from_tray)
            menu.addAction(quit_action)
            self.tray.setContextMenu(menu)
            self.tray.activated.connect(self.tray_activated)
            self.tray.show()
        self.tray_hint_shown = False
        self.timer = QTimer(self); self.timer.timeout.connect(self.check_timer); self.timer.start(15000)
        self.setStyleSheet('''QTabWidget::pane{border:1px solid #30293d;border-radius:10px;} QTabBar::tab{background:#17141f;color:#b7a9d1;padding:12px 22px;border-radius:7px;margin-right:5px;} QTabBar::tab:selected{background:#6945b7;color:white;} QTableWidget{background:#14111b;alternate-background-color:#201a2a;gridline-color:#30293d;} QWidget{background:#0d0c12;color:#eeeaf6;font:13px "Segoe UI";}
          QLabel#title{font-size:27px;font-weight:800;letter-spacing:2px;color:#e4d4ff;}
          QLabel#muted{color:#978fa8;} QLabel#counter{color:#a58bff;font-weight:700;}
          QLabel#handle{font-size:15px;font-weight:700;} QLabel#badge{font-size:11px;font-weight:700;}
          QFrame#panel{background:#17141f;border:1px solid #30293d;border-radius:12px;}
          QCompleter QAbstractItemView{background:#211b2b;color:#eeeaf6;selection-background-color:#6945b7;border:1px solid #40334f;}
          QLineEdit,QSpinBox{background:#211b2b;border:1px solid #40334f;border-radius:8px;padding:11px;}
          QListWidget{background:#14111b;border:1px solid #30293d;border-radius:12px;padding:8px;outline:0;}
          QListWidget::item{background:#201a2a;border:1px solid #30283e;border-radius:10px;}
          QListWidget::item:selected{background:#302342;border:1px solid #8664c9;}
          QPushButton{background:#6945b7;border:0;border-radius:8px;padding:11px 14px;font-weight:600;}
          QPushButton:hover{background:#815bd0;} QPushButton:pressed{background:#51368e;}
          QCheckBox{spacing:8px;}''')
        self.refresh()
        self.update_suggestions('')
        for name in self.cfg['profiles']: self.fetch_avatar(name)
        QTimer.singleShot(3500, self.check_updates_silent)

    def check_updates_silent(self):
        self.check_updates(silent=True)

    def check_updates(self, silent=False):
        if any(w.isRunning() for w in self.update_workers): return
        self.update_button.setEnabled(False)
        self.update_status.setText('Consultando GitHub...')
        self.update_worker = UpdateWorker()
        self.update_workers.append(self.update_worker)
        self.update_worker.finished.connect(lambda: self.update_workers.__setitem__(slice(None), [w for w in self.update_workers if w.isRunning()]))
        self.update_worker.result.connect(lambda info: self.on_update_check(info, silent))
        self.update_worker.failure.connect(lambda err: self.on_update_error(err, silent))
        self.update_worker.finished.connect(lambda: self.update_button.setEnabled(True))
        self.update_worker.start()

    def on_update_error(self, err, silent=False):
        self.update_status.setText('Não foi possível verificar atualizações')
        if not silent: QMessageBox.warning(self, 'Atualização', err)

    def on_update_check(self, info, silent=False):
        if not info:
            self.update_status.setText('Você está na versão mais recente')
            if not silent: QMessageBox.information(self, 'Atualizações', 'Você já está na versão mais recente.')
            return
        self.update_status.setText('Nova versão: ' + info['version'])
        msg = ('Versão ' + info['version'] + ' disponível.\n\n' + info['notes'][:600] +
               '\n\nBaixar, verificar SHA-256 e instalar agora?\nGravações em andamento serão interrompidas ao reiniciar.')
        if QMessageBox.question(self, 'Atualização disponível', msg) != QMessageBox.StandardButton.Yes:
            return
        if not getattr(sys, 'frozen', False):
            QMessageBox.information(self, 'Atualização', 'Execute o aplicativo compilado em EXE para atualizar automaticamente.')
            return
        self.update_button.setEnabled(False)
        self.update_status.setText('Baixando atualização...')
        self.update_worker = UpdateWorker(info)
        self.update_workers.append(self.update_worker)
        self.update_worker.finished.connect(lambda: self.update_workers.__setitem__(slice(None), [w for w in self.update_workers if w.isRunning()]))
        self.update_worker.progress.connect(lambda p: self.update_status.setText(f'Baixando atualização: {p}%'))
        self.update_worker.result.connect(self.install_update)
        self.update_worker.failure.connect(lambda err: self.on_update_error(err, False))
        self.update_worker.finished.connect(lambda: self.update_button.setEnabled(True))
        self.update_worker.start()

    def install_update(self, downloaded):
        if QMessageBox.question(self, 'Atualização pronta', 'Download verificado. Fechar e instalar a atualização agora?') != QMessageBox.StandardButton.Yes:
            self.update_status.setText('Instalação adiada')
            return
        active = [w for w in self.workers.values() if w.isRunning()]
        if active:
            QMessageBox.warning(self, 'Gravações ativas', 'Pare as gravações antes de instalar a atualização.')
            return
        try:
            launch_helper(downloaded)
            self.exiting = True
            self.close()
        except Exception as exc:
            QMessageBox.warning(self, 'Falha ao instalar', str(exc))

    def toggle_startup(self, enabled):
        try:
            configure_startup(enabled)
            logger.info('Inicialização automática: %s', enabled)
        except Exception as exc:
            self.startup.blockSignals(True)
            self.startup.setChecked(not enabled)
            self.startup.blockSignals(False)
            QMessageBox.warning(self, 'Inicialização automática', str(exc))

    def persist(self, *_):
        self.cfg['format'] = self.output_format.currentText(); self.cfg['retention'] = self.retention.value()
        self.cfg['notify'] = self.notify.isChecked()
        self.cfg['auto'] = self.auto.isChecked(); self.cfg['interval'] = self.interval.value(); save_config(self.cfg)

    def refresh(self):
        selected = self.list.currentRow(); self.list.clear()
        for name in self.cfg['profiles']:
            state, detail = self.states.get(name, ('aguardando','Aguardando próxima verificação'))
            item = QListWidgetItem(); item.setSizeHint(QSize(100,72)); self.list.addItem(item)
            self.list.setItemWidget(item, ProfileCard(name, state, detail, self.avatars.get(name)))
        if 0 <= selected < self.list.count(): self.list.setCurrentRow(selected)
        self.count.setText(f'{len(self.cfg["profiles"])} PERFIS')

    def fetch_avatar(self, name):
        if name in self.fetchers: return
        worker = ProfileFetcher(name); self.fetchers[name] = worker
        worker.ready.connect(self.avatar_ready)
        worker.finished.connect(lambda n=name: self.fetchers.pop(n, None))
        worker.start()

    def avatar_ready(self, name, data):
        self.avatars[name] = data; self.refresh()

    def update_suggestions(self, value):
        # Sugestões locais verificáveis. Não inventa resultados remotos.
        needle = value.strip().lstrip('@').lower()
        profiles = self.cfg.get('profiles', [])
        matches = ['@' + p for p in profiles if needle and needle in p.lower()]
        self.suggestion_model.setStringList(matches[:12])

    def on_suggestion_selected(self, selected):
        self.entry.setText(selected)

    def search_tiktok(self):
        query = self.entry.text().strip()
        if not query:
            self.note.setText('Digite algumas letras para pesquisar no TikTok.')
            self.entry.setFocus()
            return
        # Link oficial da pesquisa de usuários. Nenhum scraping ou login necessário.
        url = 'https://www.tiktok.com/search/user?q=' + quote(query.lstrip('@'))
        QDesktopServices.openUrl(QUrl(url))
        self.note.setText('Pesquisa aberta no navegador. Copie o @usuário ou link do perfil encontrado e adicione aqui.')

    def add_profile(self):
        try: name = username_from_input(self.entry.text())
        except ValueError as exc:
            QMessageBox.warning(self, 'Perfil inválido', str(exc)); return
        if name.lower() in (p.lower() for p in self.cfg['profiles']):
            self.note.setText('Este perfil já foi adicionado.'); return
        self.cfg['profiles'].append(name); save_config(self.cfg)
        self.entry.clear(); self.refresh(); self.update_suggestions(''); self.fetch_avatar(name)
        self.note.setText(f'Perfil @{name} adicionado. Clique em Verificar agora ou ative o monitoramento automático.')

    def remove_profile(self):
        i = self.list.currentRow()
        if i < 0: return
        name = self.cfg['profiles'][i]
        if name in self.workers and self.workers[name].isRunning():
            QMessageBox.information(self,'Gravação ativa','Pare a tarefa deste perfil antes de removê-lo.'); return
        self.cfg['profiles'].pop(i); self.states.pop(name,None); save_config(self.cfg); self.refresh(); self.update_suggestions(self.entry.text())

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self,'Pasta de gravações',str(self.cfg.get('folder', DEFAULT_FOLDER)))
        if folder: self.cfg['folder'] = folder; save_config(self.cfg)

    def open_folder(self):
        folder = Path(self.cfg.get('folder', DEFAULT_FOLDER)); folder.mkdir(parents=True,exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def check_all(self):
        if not self.cfg['profiles']:
            self.note.setText('Adicione um perfil para começar.'); return
        self.last_check = time.monotonic()
        for name in self.cfg['profiles']:
            old = self.workers.get(name)
            if old and old.isRunning(): continue
            worker = Recorder(name, Path(self.cfg.get('folder', DEFAULT_FOLDER)) / name, {'format':self.output_format.currentText()})
            worker.update.connect(self.on_status)
            self.workers[name] = worker
            self.states[name] = ('checando','Iniciando verificação...')
            worker.start()
        self.activity.setText('Verificação iniciada'); self.refresh()

    def on_status(self, name, state, detail):
        previous = self.states.get(name, ('', ''))[0]
        logger.info('@%s | %s | %s', name, state, detail)
        if state == 'gravando' and previous != 'gravando' and self.notify.isChecked() and self.tray is not None:
            self.tray.showMessage('Gravação iniciada', '@' + name + ' • ' + detail, QSystemTrayIcon.MessageIcon.Information, 5000)
        self.states[name] = (state,detail)
        self.activity.setText(f'@{name}: {state}')
        self.refresh()
        if state in ('salvo','erro'): self.refresh_library()

    def stop_all(self):
        for worker in self.workers.values(): worker.stop()
        self.note.setText('Parada solicitada. Aguarde o encerramento das tarefas.')

    def check_timer(self):
        if self.auto.isChecked() and time.monotonic()-self.last_check >= self.interval.value()*60:
            self.check_all()
        # Limpeza periódica apenas de originais acompanhados de MP4 validado.
        if not hasattr(self,'last_cleanup') or time.monotonic()-self.last_cleanup>86400:
            self.last_cleanup=time.monotonic()
            threading.Thread(target=self.cleanup_background,daemon=True).start()

    def media_files(self):
        base=Path(self.cfg.get('folder',DEFAULT_FOLDER))
        if not base.exists(): return []
        return sorted((p for p in base.glob('*/*') if p.is_file() and p.suffix.lower() in ('.ts','.mp4') and p.parent.name!='_TS_originais'),key=lambda x:x.stat().st_mtime,reverse=True)[:2000]

    def refresh_library(self):
        files=self.media_files(); self.library_table.setRowCount(len(files))
        total=0
        for i,path in enumerate(files):
            stat=path.stat(); total+=stat.st_size
            for j,value in enumerate((path.name,path.suffix.upper(),f'{stat.st_size/1048576:.1f} MB',datetime.fromtimestamp(stat.st_mtime).strftime('%d/%m/%Y %H:%M'))):
                cell=QTableWidgetItem(value)
                if j==0: cell.setData(Qt.ItemDataRole.UserRole,str(path))
                self.library_table.setItem(i,j,cell)
        self.stats.setText(f'{len(self.cfg["profiles"])} perfis monitorados    •    {len(files)} vídeos    •    {total/1073741824:.2f} GB (biblioteca)')

    def play_selected(self):
        row=self.library_table.currentRow()
        if row<0: return
        item=self.library_table.item(row,0)
        if item: QDesktopServices.openUrl(QUrl.fromLocalFile(item.data(Qt.ItemDataRole.UserRole)))

    def cleanup_background(self):
        base=Path(self.cfg.get('folder',DEFAULT_FOLDER))
        for profile in self.cfg.get('profiles',[]):
            if profile in self.workers and self.workers[profile].isRunning(): continue
            try: cleanup_ts(base/profile,self.cfg.get('retention',3))
            except Exception: logger.exception('Falha ao limpar TS de %s',profile)

    def clean_now(self):
        threading.Thread(target=self.cleanup_background,daemon=True).start()
        QMessageBox.information(self,'Limpeza','Limpeza iniciada em segundo plano. Somente TS com MP4 validado serão excluídos.')

    def show_from_tray(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_from_tray()

    def exit_from_tray(self):
        self.exiting = True
        self.close()
        if self.isVisible():
            self.exiting = False

    def closeEvent(self, event):
        if self.tray is not None and not self.exiting:
            event.ignore()
            self.hide()
            if not self.tray_hint_shown:
                self.tray.showMessage('TikTok Live Recorder', 'Continuo na bandeja do Windows. Clique duas vezes no ícone para abrir.', QSystemTrayIcon.MessageIcon.Information, 3500)
                self.tray_hint_shown = True
            return

        active = [w for w in self.workers.values() if w.isRunning()]
        if active:
            if QMessageBox.question(self,'Sair','Existem gravações ou verificações ativas. Parar e sair?') != QMessageBox.StandardButton.Yes:
                event.ignore(); return
            self.stop_all()
            for worker in active: worker.wait(4000)
            if any(w.isRunning() for w in active):
                QMessageBox.warning(self,'Aguarde','As tarefas ainda estão encerrando. Tente novamente.')
                event.ignore(); return
        for update_worker in list(self.update_workers):
            if update_worker.isRunning(): update_worker.wait(30000)
        # Wait for short avatar fetches to avoid destroying running QThreads.
        for fetcher in list(self.fetchers.values()):
            if fetcher.isRunning(): fetcher.wait(10000)
        if self.tray is not None: self.tray.hide()
        event.accept()

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--apply-update':
        sys.exit(apply_update(sys.argv))
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    logger.info('Aplicativo iniciado, versão %s', VERSION)
    window = Window()
    if '--minimized' in sys.argv and window.tray is not None:
        window.hide()
    else:
        window.show()
    sys.exit(app.exec())
