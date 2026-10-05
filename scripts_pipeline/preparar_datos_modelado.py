#!/usr/bin/env python3
"""Coordina transformaciones locales reproducibles; plan por defecto, sin red.

No entrena modelos, no imputa, no elimina fuentes y no modifica descargadores.
Los periodos finales se exigen explícitamente para no confundir disponibilidad
con cobertura completa. Cada conversor valida y versiona sus propios datos.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import uuid

SCRIPTS = Path(__file__).resolve().parent
OUTPUT = Path('/Volumes/Datos/Asesorias_Data/AirPollution/derived/modelado')
VOLUME_UUID = '54B3D309-A503-44C6-9229-581F3E4FECE3'
PRODUCTS = ('merra2', 'sinca', 'era5land')
LIMITATIONS = {
    'merra2': 'Conservación exacta de valores locales, horas y píxeles nativos; no recertifica procedencia histórica ni derivación de variables heredadas.',
    'sinca': 'Etiquetas civiles originales; ts_utc nulo, unidades y semántica del intervalo pendientes de confirmación. Solapes y calidad conservados. No unir automáticamente con UTC satelital.',
    'era5land': 'TP horario calculado según el endpoint declarado reanalysis-era5-land. Unidades históricas ausentes se documentan como inferidas. Negativos y faltantes conservados con flags.',
}


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def utc():
    return datetime.now(timezone.utc).isoformat()


def verify_code(fingerprints):
    for path, fingerprint in fingerprints.items():
        if sha256(path) != fingerprint:
            raise RuntimeError('Código cambió durante ejecución; detener para conservar identidad')


def months(first, last):
    def parse(value):
        parsed = datetime.strptime(value, '%Y-%m')
        if parsed.strftime('%Y-%m') != value:
            raise ValueError('Los meses requieren YYYY-MM')
        return parsed.year * 12 + parsed.month - 1
    start, end = parse(first), parse(last)
    if end < start:
        raise ValueError('Periodo mensual invertido')
    return [f'{n // 12:04d}-{n % 12 + 1:02d}' for n in range(start, end + 1)]


def build_plan(args):
    if len(set(args.productos)) != len(args.productos):
        raise ValueError('No repetir productos')
    jobs = []
    def add(product, period, name, flags):
        jobs.append({'product': product, 'period': period,
                     'command': [sys.executable, '-B', '-u', str(SCRIPTS / name), *flags]})
    if 'merra2' in args.productos:
        if not args.merra_hasta:
            raise ValueError('Se requiere --merra-hasta YYYY-MM')
        months(args.merra_desde, args.merra_hasta)
        add('merra2', f'{args.merra_desde}/{args.merra_hasta}', 'preparar_merra2_modelado.py',
            ['--desde', args.merra_desde, '--hasta', args.merra_hasta])
    if 'sinca' in args.productos:
        if not args.sinca_hasta:
            raise ValueError('Se requiere --sinca-hasta YYYY-MM-DD')
        if date.fromisoformat(args.sinca_hasta) < date.fromisoformat(args.sinca_desde):
            raise ValueError('Periodo SINCA invertido')
        add('sinca', f'{args.sinca_desde}/{args.sinca_hasta}', 'preparar_sinca_modelado.py',
            ['--desde', args.sinca_desde, '--hasta', args.sinca_hasta, '--max-series', '0', '--ejecutar'])
    if 'era5land' in args.productos:
        if not args.era_hasta:
            raise ValueError('Se requiere --era-hasta YYYY-MM')
        for month in months(args.era_desde, args.era_hasta):
            add('era5land', month, 'preparar_era5land_modelado.py', ['--mes', month])
    return {'schema': 'airpollution.modelado.coordinador.v1', 'jobs': jobs,
            'limitations': {p: LIMITATIONS[p] for p in args.productos},
            'source_deletion': False, 'network': False, 'imputation': False,
            'output_root': str(OUTPUT), 'execution_enabled': args.ejecutar}


def disk_guard():
    mount = Path('/Volumes/Datos')
    if not mount.is_mount() or not OUTPUT.resolve().is_relative_to(mount):
        raise RuntimeError('Disco externo no montado; no se escribe en disco interno')
    info = plistlib.loads(subprocess.check_output(['diskutil', 'info', '-plist', str(mount)]))
    if info.get('VolumeUUID') != VOLUME_UUID or info.get('MountPoint') != str(mount):
        raise RuntimeError('Identidad del disco externo distinta')
    if shutil.disk_usage(mount).free < 100 * 1024**3:
        raise RuntimeError('Reserva inferior a 100 GiB')


def fsync_dir(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def json_atomic(path, data):
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.pending')
    with temp.open('x', encoding='utf-8') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
    os.replace(temp, path)
    fsync_dir(path.parent)


def execute(plan):
    disk_guard()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with (OUTPUT / '_coordinador.lock').open('a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        run = OUTPUT / '_ejecuciones' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex)
        archive = run / 'codigo'; archive.mkdir(parents=True)
        paths = {Path(job['command'][3]) for job in plan['jobs']} | {Path(__file__).resolve()}
        fingerprints = {}
        for path in sorted(paths):
            content = path.read_bytes()
            fingerprints[str(path)] = hashlib.sha256(content).hexdigest()
            with (archive / path.name).open('xb') as stream:
                stream.write(content); stream.flush(); os.fsync(stream.fileno())
        fsync_dir(archive)
        json_atomic(run / 'plan.json', {**plan, 'code_sha256': fingerprints, 'created_utc': utc()})
        progress = {'status': 'running', 'completed_jobs': [], 'planned_jobs': len(plan['jobs']), 'limitations': plan['limitations']}
        json_atomic(run / 'progreso.json', progress)
        try:
            for i, job in enumerate(plan['jobs']):
                disk_guard()
                verify_code(fingerprints)
                log = run / f'{i:04d}_{job["product"]}.log'
                progress.update(current_job=job, updated_utc=utc())
                json_atomic(run / 'progreso.json', progress)
                print(json.dumps({'phase': 'start', 'job': i + 1, 'total': len(plan['jobs']), **job}, ensure_ascii=False), flush=True)
                with log.open('xb') as stream:
                    result = subprocess.run(job['command'], cwd=SCRIPTS.parent, stdout=stream, stderr=subprocess.STDOUT, check=False)
                    stream.flush(); os.fsync(stream.fileno())
                verify_code(fingerprints)
                record = {**job, 'returncode': result.returncode, 'log': str(log), 'log_sha256': sha256(log)}
                if result.returncode:
                    progress['failed_job'] = record
                    raise RuntimeError(f'Conversor detenido ({result.returncode}); ver {log}')
                progress['completed_jobs'].append(record)
                progress.update(current_job=None, updated_utc=utc())
                json_atomic(run / 'progreso.json', progress)
                print(json.dumps({'phase': 'validated_by_converter', 'job': i + 1, 'total': len(plan['jobs'])}), flush=True)
            verify_code(fingerprints)
            progress.update(status='complete_for_requested_transformations', current_job=None, updated_utc=utc())
            json_atomic(run / 'progreso.json', progress)
        except BaseException as error:
            progress.update(status='stopped_originals_preserved', error_type=type(error).__name__, updated_utc=utc())
            json_atomic(run / 'progreso.json', progress)
            raise
        return {'status': progress['status'], 'run': str(run), 'jobs': len(plan['jobs']), 'limitations': plan['limitations']}


def parser():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--productos', choices=PRODUCTS, nargs='+', default=list(PRODUCTS))
    ap.add_argument('--merra-desde', default='2000-01')
    ap.add_argument('--merra-hasta')
    ap.add_argument('--sinca-desde', default='2000-01-01')
    ap.add_argument('--sinca-hasta')
    ap.add_argument('--era-desde', default='2000-01')
    ap.add_argument('--era-hasta')
    ap.add_argument('--ejecutar', action='store_true')
    return ap


def main(argv=None):
    ap = parser()
    args = ap.parse_args(argv)
    try:
        plan = build_plan(args)
    except ValueError as error:
        ap.error(str(error))
    print(json.dumps(execute(plan) if args.ejecutar else plan, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
