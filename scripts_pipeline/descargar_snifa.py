#!/usr/bin/env python3
"""Descarga pública, incremental y trazable de la red adicional SNIFA.

No escribe en SINCA. Los originales se conservan y el procesamiento se ejecuta
por separado con preparar_snifa_modelado.py. Consultar docs/RED_ADICIONAL_SNIFA.md.
"""
from __future__ import annotations

import argparse
import concurrent.futures as futures
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import re
import shutil
import threading
import time
import unicodedata
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

REPO = Path(__file__).resolve().parents[1]
CONFIG = REPO / 'config/snifa_adicional/estaciones.json'
WEB = 'https://snifa.sma.gob.cl'
API = 'https://api-ssa.sma.gob.cl/api/v1'
VERSION = '1.0.0'
LOG = logging.getLogger('snifa_adicional')
_LOCAL = threading.local()


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def folded(text):
    return ''.join(c for c in unicodedata.normalize('NFKD', str(text))
                   if not unicodedata.combining(c)).lower()


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_name(path.name + '.part')
    with pending.open('w', encoding='utf8') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(pending, path)


def data_root():
    root = Path(os.environ.get('AIR_POLLUTION_DATA_ROOT') or
                str(Path(os.environ.get('ASESORIAS_DATA_ROOT', '/Volumes/Datos/Asesorias_Data')) /
                    'AirPollution/data'))
    return root.expanduser().resolve() / 'snifa_adicional'


def check_disk(path, reserve_gib=100):
    path = Path(path).resolve()
    # Un punto de montaje desaparecido nunca debe redirigir datos al disco interno.
    if str(path).startswith('/Volumes/'):
        mount = Path('/Volumes') / path.parts[2]
        if not mount.is_mount():
            raise RuntimeError(f'Disco externo no montado: {mount}')
    parent = path
    while not parent.exists():
        parent = parent.parent
    free = shutil.disk_usage(parent).free
    if free < reserve_gib * 2**30:
        raise RuntimeError(f'Reserva insuficiente: {free/2**30:.1f} GiB libres, mínimo {reserve_gib}')
    return free


def request(url, **kwargs):
    if not hasattr(_LOCAL, 'session'):
        _LOCAL.session = requests.Session()
        _LOCAL.session.headers['User-Agent'] = 'AirPollution-research-SNIFA/1.0 (public environmental data)'
    last = None
    for attempt in range(4):
        try:
            response = _LOCAL.session.get(url, timeout=(15, 90), **kwargs)
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            last = exc
            if attempt == 3:
                break
            time.sleep(min(2**attempt, 8))
    raise RuntimeError(f'{url}: {last}')


def cached_html(url, path, refresh=False):
    path = Path(path)
    if path.exists() and not refresh:
        return path.read_text(encoding='utf8')
    response = request(url)
    text = response.content.decode('utf8', errors='replace')
    if 'SNIFA' not in text or '<html' not in text.lower():
        raise ValueError(f'Respuesta inesperada de SNIFA: {url}')
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_name(path.name + '.part')
    pending.write_text(text, encoding='utf8')
    os.replace(pending, path)
    return text


def discover_reports(html):
    soup = BeautifulSoup(html, 'html.parser')
    result = []
    for a in soup.select('a[href*="/SeguimientoAmbiental/Ficha/"]'):
        row = a.find_parent('tr')
        if row is None:
            continue
        description = folded(row.get_text(' ', strip=True))
        if not any(token in description for token in ('gases', 'calidad del aire', 'calidad de aire')):
            continue
        match = re.search(r'/SeguimientoAmbiental/Ficha/(\d+)(?:[/?#]|$)', a['href'])
        if match:
            result.append(match.group(1))
    return sorted(set(result), key=int)


def document_role(name):
    """Conservar informes/tablas pertinentes y leyendas de calidad, sin ruido/calibraciones."""
    name = folded(name)
    suffix = Path(name).suffix
    if suffix not in ('.xls', '.xlsx', '.pdf', '.csv', '.zip'):
        return None
    if any(x in name for x in ('comprobante', 'bitacora', 'certific', 'acreditacion',
                              'mantencion', 'calibracion', 'resolucion', 'ruido',
                              'estabilidad', 'carta ', 'ordinario', 'responsables', 'laboratorio')):
        return None
    if any(x in name for x in ('invalid', 'nomenclatura', 'meteorolog')) and \
            not any(x in name for x in ('calidad', 'mca ', 'seb-')):
        return 'support'
    if any(x in name for x in ('informe lab', 'analisis de datos mp10')):
        return 'support'
    return 'measurements'


def parse_report(html, report_id, source):
    soup = BeautifulSoup(html, 'html.parser')
    report_id = str(report_id)
    prefix = re.compile(r'^\s*Expediente\s*:\s*(\d+)\b', re.I)
    heading = next((h for h in soup.find_all('h3')
                    if (match := prefix.match(h.get_text(' ', strip=True))) and
                    match.group(1) == report_id), None)
    if heading is None:
        raise ValueError(f'Ficha {report_id}: sin identificación de expediente')
    report_title = prefix.sub('', heading.get_text(' ', strip=True), count=1).strip()
    dates = re.search(r'Per[ií]odo:\s*(\d{2}-\d{2}-\d{4})\s*-\s*(\d{2}-\d{2}-\d{4})',
                      soup.get_text(' ', strip=True))
    start, end = ('', '')
    if dates:
        start, end = (dt.datetime.strptime(d, '%d-%m-%Y').date().isoformat() for d in dates.groups())
        if start > end:
            raise ValueError(f'Ficha {report_id}: período invertido {start} - {end}')
    record = {'source_id': source['id'], 'report_id': str(report_id),
              'report_url': f'{WEB}/SeguimientoAmbiental/Ficha/{report_id}',
              'report_title': report_title,
              'period_start': start, 'period_end': end}
    documents = []
    for a in soup.select('a[href*="/DescargarInformeSeguimiento/"]'):
        tr = a.find_parent('tr')
        cells = tr.find_all('td') if tr else []
        if len(cells) < 2:
            continue
        name = cells[1].get_text(' ', strip=True)
        role = document_role(name)
        if role is None:
            continue
        match = re.search(r'/DescargarInformeSeguimiento/(\d+)(?:[/?#]|$)', a['href'])
        if not match:
            continue
        document_id = match.group(1)
        documents.append({**record, 'document_id': document_id, 'original_filename': name,
                          'role': role, 'source_url': urljoin(WEB, a['href']), 'status': 'pending'})
    return {**record, 'documents': documents}


def safe_name(name):
    # El nombre es dato remoto: nunca interpretarlo como ruta.
    name = name.replace('\\', '/').split('/')[-1]
    return re.sub(r'[^\w.() -]+', '_', name, flags=re.UNICODE)[:180] or 'documento'


def contained_path(root, relative):
    """No leer ni escribir fuera del destino aunque un manifiesto esté corrupto."""
    root, relative = Path(root).resolve(), Path(relative)
    path = (root / relative).resolve()
    if relative.is_absolute() or not path.is_relative_to(root):
        raise ValueError(f'Ruta fuera del directorio de datos: {relative}')
    return path


def positive_size(value):
    if not isinstance(value, bool) and re.fullmatch(r'\d+', str(value or '')):
        number = int(value)
        return number if number > 0 else None
    return None


def download_document(record, root, reserve_gib=100):
    record = dict(record)
    root = Path(root).resolve()
    check_disk(root, reserve_gib)
    old_path = contained_path(root, record.get('relative_path', '__missing__'))
    if record.get('status') == 'downloaded' and old_path.is_file() and \
            record.get('sha256') == sha256(old_path):
        record['reused'] = True
        return record
    meta = request(f'{API}/GetDocumentoById/{record["document_id"]}').json()
    data = meta.get('data') or {}
    if not data.get('InternalFileName') or not data.get('FileName'):
        raise ValueError(f'Documento {record["document_id"]}: metadata sin archivo')
    # La API mezcla bytes con KiB truncados (p. ej., documentos 1398966/1398967).
    # La longitud HTTP sin compresión sí describe los bytes descargados.
    expected_size = positive_size(data.get('ContentLength'))
    if expected_size and expected_size > 250 * 2**20:
        raise ValueError('Documento supera el límite de 250 MiB')
    internal = data['InternalFileName']
    relative = Path('raw') / record['source_id'] / record['report_id'] / \
               (record['document_id'] + '_' + safe_name(data['FileName']))
    path = contained_path(root, relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_name(path.name + '.part')
    response = request(f'{API}/documentos/incidente/descargar', params={'nombre': internal}, stream=True)
    total = 0
    h = hashlib.sha256()
    try:
        with pending.open('wb') as stream:
            for chunk in response.iter_content(1024*1024):
                if not chunk:
                    continue
                total += len(chunk)
                if total > 250 * 2**20:
                    raise ValueError('Documento supera el límite de 250 MiB')
                h.update(chunk)
                stream.write(chunk)
            stream.flush()
            os.fsync(stream.fileno())
        with pending.open('rb') as stream:
            prefix = stream.read(512).lstrip().lower()
        # Algunos originales correctos se sirven como text/html: manda el cuerpo,
        # no el MIME erróneo publicado por el servidor.
        if not total or re.search(rb'<!doctype\s+html\b|<html\b', prefix) or \
                prefix.startswith((b'{', b'[')):
            raise ValueError('La descarga devolvió una página/error, no un documento')
        encoding = response.headers.get('Content-Encoding', '').lower().strip()
        http_size = positive_size(response.headers.get('Content-Length')) \
            if encoding in ('', 'identity') else None
        if http_size is not None and total != http_size:
            raise ValueError(f'Descarga incompleta: {total} bytes, HTTP declara {http_size}')
        metadata_size_unit = 'unknown'
        if expected_size == total:
            metadata_size_unit = 'bytes'
        elif expected_size is not None and expected_size * 1024 == total:
            metadata_size_unit = 'KiB_exact'
        elif expected_size is not None and total // 1024 == expected_size:
            metadata_size_unit = 'KiB_rounded'
        elif expected_size is not None and http_size is None:
            raise ValueError(f'Descarga incompleta o modificada: {total} bytes, '
                             f'metadata declara {expected_size}')
        if path.suffix.lower() == '.pdf' and not prefix.startswith(b'%pdf'):
            raise ValueError('PDF sin cabecera PDF')
        if path.suffix.lower() in ('.xlsx', '.zip') and not prefix.startswith(b'pk'):
            raise ValueError('Archivo comprimido sin cabecera ZIP')
        if path.exists() and sha256(path) != h.hexdigest():
            archive = path.with_name(path.name + '.previous-' + sha256(path)[:12])
            if not archive.exists():
                shutil.copy2(path, archive)
        os.replace(pending, path)
    finally:
        response.close()
        with contextlib.suppress(FileNotFoundError):
            pending.unlink()
    return {**record, 'status': 'downloaded', 'relative_path': str(relative),
            'filename': data['FileName'], 'sha256': h.hexdigest(), 'bytes': total,
            'downloaded_at': now(), 'api_metadata': data,
            'download_content_type': response.headers.get('Content-Type', ''),
            'metadata_content_length_unit': metadata_size_unit,
            'http_content_length_verified': http_size is not None,
            'content_length_verified': http_size is not None or
                                       metadata_size_unit in ('bytes', 'KiB_exact'),
            'reused': False, 'error': ''}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=CONFIG)
    parser.add_argument('--destino', type=Path, default=data_root())
    parser.add_argument('--desde', default='2000-01-01')
    parser.add_argument('--hasta', default=dt.date.today().isoformat())
    parser.add_argument('--fuentes', help='IDs separados por coma; omitir para las tres fuentes')
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--min-gb-libres', type=float, default=100)
    parser.add_argument('--actualizar', action='store_true', help='Refrescar también fichas de informes ya descubiertas')
    parser.add_argument('--solo-descubrir', action='store_true')
    parser.add_argument('--dry-run', action='store_true', help='Descubrir plan sin descargar originales')
    parser.add_argument('--limite-documentos', type=int)
    args = parser.parse_args(argv)
    start, end = dt.date.fromisoformat(args.desde), dt.date.fromisoformat(args.hasta)
    if (start > end or args.workers < 1 or args.workers > 8 or
            not math.isfinite(args.min_gb_libres) or args.min_gb_libres < 0 or
            (args.limite_documentos is not None and args.limite_documentos < 1)):
        parser.error('Rango de fechas, workers (1–8) o reserva incorrectos')
    root = args.destino.expanduser().resolve()
    check_disk(root, args.min_gb_libres)
    config = json.loads(args.config.read_text(encoding='utf8'))
    sources = config['sources']
    if args.fuentes:
        wanted = set(args.fuentes.split(','))
        if wanted - {x['id'] for x in sources}:
            parser.error('Fuente desconocida')
        sources = [x for x in sources if x['id'] in wanted]
    root.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s', datefmt='%H:%M:%S')
    with (root / '.download.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return run(args, config, sources, root, start, end)


def run(args, config, sources, root, start, end):
    metadata = root / 'metadata'
    manifest_path = metadata / 'download_manifest.json'
    previous = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    records = {str(x['document_id']): x for x in previous.get('documents', [])}
    discovered = []
    errors = []
    report_jobs = []
    for source in sources:
        url = f'{WEB}/UnidadFiscalizable/Ficha/{source["uf_id"]}'
        html = cached_html(url, metadata / 'html' / f'uf_{source["uf_id"]}.html', refresh=True)
        ids = discover_reports(html)
        LOG.info('%s: %d informes de aire descubiertos', source['id'], len(ids))
        if not ids:
            raise RuntimeError(f'No se encontraron informes de aire para {source["id"]}')
        report_jobs.extend((source, report_id) for report_id in ids)

    def read_report(job):
        source, report_id = job
        url = f'{WEB}/SeguimientoAmbiental/Ficha/{report_id}'
        html = cached_html(url, metadata / 'html' / f'report_{report_id}.html', args.actualizar)
        return parse_report(html, report_id, source)

    with futures.ThreadPoolExecutor(args.workers) as pool:
        pending = {pool.submit(read_report, job): job for job in report_jobs}
        for i, future in enumerate(futures.as_completed(pending), 1):
            source, report_id = pending[future]
            try:
                report = future.result()
                if report['period_start'] and report['period_end'] and \
                        (report['period_end'] < start.isoformat() or report['period_start'] > end.isoformat()):
                    continue
                discovered.append(report)
                for record in report['documents']:
                    old = records.get(record['document_id'], {})
                    records[record['document_id']] = {**old, **record, 'status': old.get('status', 'pending')}
            except Exception as exc:
                errors.append({'source_id': source['id'], 'report_id': report_id, 'error': str(exc)})
            if i % 25 == 0:
                LOG.info('Descubrimiento: %d/%d fichas', i, len(pending))

    active_ids = {x['document_id'] for r in discovered for x in r['documents']}
    selected = [records[k] for k in sorted(active_ids, key=int)]
    if args.limite_documentos is not None:
        selected = selected[:args.limite_documentos]
    manifest = {'schema_version': '1.0', 'network_id': 'snifa_adicional',
                'script_version': VERSION, 'script_sha256': sha256(Path(__file__)),
                'config_sha256': sha256(args.config), 'updated_at': now(),
                'range_requested': [str(start), str(end)], 'reports': discovered,
                'discovery_errors': errors, 'documents': list(records.values())}
    atomic_json(metadata / 'station_config.json', config)
    atomic_json(manifest_path, manifest)
    LOG.info('Plan: %d informes, %d archivos seleccionados, %d fallos de descubrimiento',
             len(discovered), len(selected), len(errors))
    if args.solo_descubrir or args.dry_run:
        return 2 if errors else 0
    completed = 0
    with futures.ThreadPoolExecutor(args.workers) as pool:
        pending = {pool.submit(download_document, r, root, args.min_gb_libres): r for r in selected}
        for future in futures.as_completed(pending):
            record = pending[future]
            try:
                record = future.result()
            except Exception as exc:
                # Una copia anterior válida no se pierde por un error de actualización.
                record = {**record, 'status': 'error', 'error': str(exc), 'last_attempt': now()}
                LOG.error('Documento %s: %s', record['document_id'], exc)
            records[record['document_id']] = record
            completed += 1
            if completed % 10 == 0 or completed == len(selected):
                manifest['documents'] = list(records.values())
                manifest['updated_at'] = now()
                atomic_json(manifest_path, manifest)
                LOG.info('Descarga: %d/%d archivos', completed, len(selected))
    failed = sum(records[x['document_id']]['status'] != 'downloaded' for x in selected)
    summary = {'network_id': 'snifa_adicional', 'finished_at': now(), 'reports': len(discovered),
               'selected_documents': len(selected), 'downloaded': len(selected)-failed,
               'failed': failed, 'discovery_errors': len(errors),
               'bytes_selected': sum(records[x['document_id']].get('bytes', 0) for x in selected)}
    atomic_json(metadata / 'download_summary.json', summary)
    LOG.info('Resultado: %s', json.dumps(summary, ensure_ascii=False))
    return 2 if failed or errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
