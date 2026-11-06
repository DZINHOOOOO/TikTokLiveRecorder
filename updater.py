"""GitHub Releases updater. No shell execution of downloaded content."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

VERSION = '5.2.0'
EXE_NAME = 'TikTokLiveRecorder.exe'
MAX_BYTES = 250 * 1024 * 1024


def repo_config():
    path = Path(getattr(sys, '_MEIPASS', Path(__file__).parent)) / 'release_config.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    owner, repo = data.get('owner', ''), data.get('repo', '')
    if not all(re.fullmatch(r'[A-Za-z0-9_.-]{1,100}', s) for s in (owner, repo)) or owner == 'SEU_USUARIO':
        raise ValueError('Configure owner e repo em release_config.json antes de compilar.')
    return owner, repo


def request_bytes(url, max_bytes=1000000):
    req = urllib.request.Request(url, headers={'User-Agent': 'TikTokLiveRecorder-Updater/5', 'Accept': 'application/vnd.github+json'})
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = resp.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise ValueError('Resposta excede limite permitido')
        return data


def parts(version):
    return tuple(int(v) for v in version.lstrip('v').split('.'))


def latest_release():
    owner, repo = repo_config()
    api = f'https://api.github.com/repos/{owner}/{repo}/releases/latest'
    release = json.loads(request_bytes(api))
    version = release.get('tag_name', '').lstrip('v')
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ValueError('Tag de versão inválida (use v5.1.0, por exemplo)')
    if parts(version) <= parts(VERSION):
        return None
    assets = {a['name']: a['browser_download_url'] for a in release.get('assets', []) if 'name' in a and 'browser_download_url' in a}
    if EXE_NAME not in assets or EXE_NAME + '.sha256' not in assets:
        raise ValueError('Release precisa incluir o EXE e o arquivo .exe.sha256')
    expected_prefix = f'https://github.com/{owner}/{repo}/releases/download/'
    for key in (EXE_NAME, EXE_NAME + '.sha256'):
        if not assets[key].startswith(expected_prefix):
            raise ValueError('URL do asset não pertence ao repositório configurado')
    return {'version': version, 'exe': assets[EXE_NAME], 'sha256': assets[EXE_NAME + '.sha256'], 'notes': release.get('body', '')[:1200]}


def download_update(info, progress=None):
    sha_text = request_bytes(info['sha256'], 512).decode('ascii', errors='strict').strip()
    match = re.match(r'^([0-9a-fA-F]{64})(?:\s+\*?TikTokLiveRecorder\.exe)?$', sha_text)
    if not match:
        raise ValueError('Checksum SHA-256 inválido')
    expected = match.group(1).lower()
    folder = Path(tempfile.mkdtemp(prefix='tlr-update-'))
    dest = folder / EXE_NAME
    digest = hashlib.sha256()
    total = 0
    try:
        req = urllib.request.Request(info['exe'], headers={'User-Agent': 'TikTokLiveRecorder-Updater/5'})
        with urllib.request.urlopen(req, timeout=40) as resp, dest.open('wb') as out:
            size = int(resp.headers.get('Content-Length', '0'))
            if size > MAX_BYTES: raise ValueError('Arquivo muito grande')
            while True:
                chunk = resp.read(1024 * 512)
                if not chunk: break
                total += len(chunk)
                if total > MAX_BYTES: raise ValueError('Arquivo muito grande')
                out.write(chunk)
                digest.update(chunk)
                if progress and size: progress(min(100, int(total * 100 / size)))
        if digest.hexdigest() != expected:
            raise ValueError('Falha na verificação SHA-256; atualização cancelada')
        if dest.read_bytes()[:2] != b'MZ':
            raise ValueError('O arquivo baixado não é um executável Windows')
        return dest
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise


def launch_helper(downloaded):
    if not getattr(sys, 'frozen', False) or os.name != 'nt':
        raise RuntimeError('Atualização automática requer o EXE compilado no Windows.')
    current = Path(sys.executable).resolve()
    if current.name.lower() != EXE_NAME.lower():
        raise RuntimeError('Renomeie o executável para TikTokLiveRecorder.exe.')
    # Helper is a copy of our own installed app, never the untrusted new binary.
    helper = downloaded.parent / 'updater-helper.exe'
    shutil.copy2(current, helper)
    flags = getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0) | getattr(subprocess, 'DETACHED_PROCESS', 0)
    subprocess.Popen([str(helper), '--apply-update', str(current), str(downloaded), str(os.getpid())],
                     cwd=str(downloaded.parent), creationflags=flags, close_fds=True)


def apply_update(argv):
    if len(argv) != 5: return 2
    _, _, target_s, source_s, pid_s = argv
    target, source = Path(target_s), Path(source_s)
    try:
        pid = int(pid_s)
        if target.name.lower() != EXE_NAME.lower() or source.name != EXE_NAME:
            return 3
        # Avoid replacing unrelated executables and arbitrary paths.
        if not source.parent.name.startswith('tlr-update-') or not source.is_file(): return 4
        backup = target.with_suffix('.exe.bak')
        for _ in range(90):
            try:
                if backup.exists(): backup.unlink()
                target.replace(backup)
                break
            except PermissionError:
                time.sleep(1)
        else: return 5
        try:
            shutil.copy2(source, target)
            subprocess.Popen([str(target)], cwd=str(target.parent), close_fds=True)
        except Exception:
            target.unlink(missing_ok=True)
            backup.replace(target)
            return 6
        # Leave backup for manual rollback; never delete user configuration.
        return 0
    except Exception:
        return 7
