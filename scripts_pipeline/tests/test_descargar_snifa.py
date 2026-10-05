"""Offline checks of discovery, provenance and resumable SNIFA downloads."""
from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import descargar_snifa as snifa


class Response:
    def __init__(self, body=b'', metadata=None, content_type='application/octet-stream'):
        self.body = body
        self.metadata = metadata
        self.headers = {'Content-Type': content_type}
        self.closed = False

    def json(self):
        return {'data': self.metadata}

    def iter_content(self, _size):
        # Multiple chunks exercise the streamed length/hash rather than a buffer.
        yield self.body[:7]
        yield b''
        yield self.body[7:]

    def close(self):
        self.closed = True


def report_html(period='01-07-2026 - 31-07-2026', report_id=42):
    return f'''<html><h3>Navegación</h3><section>
      <h3>Expediente: {report_id}<br/>INFORME CALIDAD DEL AIRE JULIO 2026</h3>
      <h4><b>Período:</b> {period}</h4>
      <table><tr><td>1</td><td>Tabla Hr Gases El Peñón.xls</td><td>25-08-2026</td>
        <td><a href="/General/DescargarInformeSeguimiento/123">Descargar</a></td></tr>
      <tr><td>2</td><td>Tabla Hr Invalidados.xls</td><td>25-08-2026</td>
        <td><a href="https://snifa.sma.gob.cl/General/DescargarInformeSeguimiento/124">Descargar</a></td></tr>
      <tr><td>3</td><td>Comprobante.pdf</td><td>25-08-2026</td>
        <td><a href="/General/DescargarInformeSeguimiento/125">Descargar</a></td></tr>
      </table></section></html>'''


class DiscoveryTest(unittest.TestCase):
    def test_discovery_keeps_historic_air_categories_without_noise_or_duplicates(self):
        html = '''<table>
          <tr><td>Gases y MP</td><td><a href="/SeguimientoAmbiental/Ficha/20">Ver</a></td></tr>
          <tr><td>Calidad del aire</td><td><a href="/SeguimientoAmbiental/Ficha/3">Ver</a></td></tr>
          <tr><td>CALIDAD DE AIRE</td><td><a href="/SeguimientoAmbiental/Ficha/3">Ver</a></td></tr>
          <tr><td>Informe acústico</td><td><a href="/SeguimientoAmbiental/Ficha/8">Ver</a></td></tr>
          <tr><td>Gases y MP</td><td><a href="/SeguimientoAmbiental/Ficha/no-id">Ver</a></td></tr>
          <tr><td>Gases y MP</td><td><a href="/SeguimientoAmbiental/Ficha/21bad">Ver</a></td></tr>
          </table><a href="/SeguimientoAmbiental/Ficha/5">Calidad del aire</a>'''
        self.assertEqual(snifa.discover_reports(html), ['3', '20'])

    def test_document_roles_keep_measurements_and_quality_references(self):
        expectations = {
            'MCA 053-04 07 07-26 v1.pdf': 'measurements',
            'INFORME CALIDAD DEL AIRE Y METEOROLOGÍA.pdf': 'measurements',
            'Estación SAPU - Junio 2025.mail.xlsx': 'measurements',
            'Datos Validados Estación El Peñon.xls': 'measurements',
            'Anexo datos históricos.zip': 'measurements',
            'Tabla Hr Invalidados.xls': 'support',
            'Nomenclatura para invalidación.pdf': 'support',
            'Tabla Hr Meteorología.xls': 'support',
            'Informe LAB2026-2498 El Peñon.pdf': 'support',
            'Análisis de datos MP10.pdf': 'support',
            'Comprobante_environmental_monitoring.pdf': None,
            'BITÁCORAS DE EQUIPO.pdf': None,
            'Certificado de calibración.pdf': None,
            'Anexo estabilidad atmosférica.pdf': None,
            'Informe ruido.pdf': None,
            'reporte.exe': None,
        }
        for filename, expected in expectations.items():
            with self.subTest(filename=filename):
                self.assertEqual(snifa.document_role(filename), expected)

    def test_parse_report_preserves_real_title_period_and_download_provenance(self):
        result = snifa.parse_report(report_html(), 42, {'id': 'el_penon'})
        self.assertEqual(result['report_title'], 'INFORME CALIDAD DEL AIRE JULIO 2026')
        self.assertEqual((result['period_start'], result['period_end']), ('2026-07-01', '2026-07-31'))
        self.assertEqual([d['document_id'] for d in result['documents']], ['123', '124'])
        self.assertEqual(result['documents'][0]['role'], 'measurements')
        self.assertEqual(result['documents'][1]['role'], 'support')
        for doc in result['documents']:
            self.assertEqual(doc['source_id'], 'el_penon')
            self.assertEqual(doc['report_id'], '42')
            self.assertTrue(doc['source_url'].startswith('https://snifa.sma.gob.cl/General/'))
            self.assertNotIn('https://snifa.sma.gob.clhttps:', doc['source_url'])

    def test_report_identity_must_match_exactly_not_as_substring(self):
        with self.assertRaisesRegex(ValueError, 'identificación'):
            snifa.parse_report(report_html(report_id=142), 42, {'id': 'el_penon'})

    def test_missing_period_is_not_invented_and_invalid_period_is_rejected(self):
        result = snifa.parse_report(report_html(period='No informado'), 42, {'id': 'el_penon'})
        self.assertEqual((result['period_start'], result['period_end']), ('', ''))
        for period in ('31-07-2026 - 01-07-2026', '30-02-2026 - 31-03-2026'):
            with self.subTest(period=period), self.assertRaises(ValueError):
                snifa.parse_report(report_html(period=period), 42, {'id': 'el_penon'})


class DownloadTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='snifa-download-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / 'network'
        self.root.mkdir()
        self.disk = patch.object(snifa, 'check_disk', return_value=200 * 2**30)
        self.disk.start()
        self.addCleanup(self.disk.stop)
        self.record = {'source_id': 'el_penon', 'report_id': '42', 'document_id': '123',
                       'original_filename': 'informe.pdf', 'status': 'pending'}
        self.body = b'%PDF-1.7\n' + b'original documented measurements\n' * 5 + b'%%EOF\n'

    def responses(self, body=None, name='informe.pdf', size='actual', content_type='application/pdf'):
        body = self.body if body is None else body
        metadata = {'InternalFileName': 'public-file-id', 'FileName': name}
        if size is not None:
            metadata['ContentLength'] = len(body) if size == 'actual' else size
        return [Response(metadata=metadata), Response(body, content_type=content_type)]

    def test_download_is_atomic_hashed_and_resumed_without_network(self):
        responses = self.responses()
        with patch.object(snifa, 'request', side_effect=responses) as request:
            result = snifa.download_document(self.record, self.root)
        self.assertEqual(request.call_count, 2)
        self.assertTrue(result['content_length_verified'])
        self.assertEqual(result['bytes'], len(self.body))
        self.assertEqual(result['sha256'], hashlib.sha256(self.body).hexdigest())
        path = self.root / result['relative_path']
        self.assertEqual(path.read_bytes(), self.body)
        self.assertEqual(list(self.root.rglob('*.part')), [])
        self.assertTrue(responses[1].closed)
        with patch.object(snifa, 'request', side_effect=AssertionError('No debe descargar de nuevo')):
            reused = snifa.download_document(result, self.root)
        self.assertTrue(reused['reused'])
        self.assertEqual(path.read_bytes(), self.body)

    def test_bad_cached_hash_triggers_download_and_preserves_previous_bytes(self):
        path = self.root / 'raw/el_penon/42/123_informe.pdf'
        path.parent.mkdir(parents=True)
        path.write_bytes(b'previous or corrupt bytes')
        record = {**self.record, 'relative_path': str(path.relative_to(self.root)),
                  'status': 'downloaded', 'sha256': 'not-the-current-hash'}
        with patch.object(snifa, 'request', side_effect=self.responses()):
            result = snifa.download_document(record, self.root)
        self.assertFalse(result['reused'])
        self.assertEqual(path.read_bytes(), self.body)
        previous = list(path.parent.glob('*.previous-*'))
        self.assertEqual(len(previous), 1)
        self.assertEqual(previous[0].read_bytes(), b'previous or corrupt bytes')

    def test_truncated_valid_header_never_replaces_previous_file(self):
        path = self.root / 'raw/el_penon/42/123_informe.pdf'
        path.parent.mkdir(parents=True)
        path.write_bytes(self.body)
        responses = self.responses(body=b'%PDF-1.7\ntruncated', size=len(self.body))
        with patch.object(snifa, 'request', side_effect=responses), \
                self.assertRaisesRegex(ValueError, 'incompleta o modificada'):
            snifa.download_document(self.record, self.root)
        self.assertEqual(path.read_bytes(), self.body)
        self.assertEqual(list(path.parent.glob('*.previous-*')), [])
        self.assertEqual(list(self.root.rglob('*.part')), [])
        self.assertTrue(responses[1].closed)

    def test_zero_missing_and_invalid_sizes_do_not_claim_verification(self):
        for size in (None, 0, '0', '', 'unknown', True):
            with self.subTest(size=size), patch.object(snifa, 'request', side_effect=self.responses(size=size)):
                result = snifa.download_document(self.record, self.root)
                self.assertFalse(result['content_length_verified'])
        with patch.object(snifa, 'request', side_effect=self.responses(size=str(len(self.body)))):
            self.assertTrue(snifa.download_document(self.record, self.root)['content_length_verified'])

    def test_html_json_and_incorrect_signatures_are_not_published_as_data(self):
        invalid = [
            (b'<!-- server error --> <html>error</html>', 'gases.xls', 'application/octet-stream'),
            (b'<!DOCTYPE html>Not authorized', 'gases.csv', 'text/html; charset=utf-8'),
            (b'{ "status": 500, "message": "error" }', 'gases.xls', 'application/json'),
            (b'not a PDF', 'informe.pdf', 'application/pdf'),
            (b'not a ZIP', 'gases.xlsx', 'application/octet-stream'),
        ]
        for body, name, content_type in invalid:
            with self.subTest(name=name, body=body):
                responses = self.responses(body=body, name=name, content_type=content_type)
                with patch.object(snifa, 'request', side_effect=responses), self.assertRaises(ValueError):
                    snifa.download_document(self.record, self.root)
                self.assertEqual([p for p in self.root.rglob('*') if p.is_file()], [])
                self.assertTrue(responses[1].closed)

    def test_real_api_legacy_kib_size_and_wrong_html_mime_keep_valid_documents(self):
        # Actual API behavior: doc1398966 has ContentLength848, HTTP868715,
        # while doc1398967 has ContentLength454, HTTP464896; both MIMEtext/html.
        for length, metadata_size, expected_unit in ((868715, 848, 'KiB_rounded'),
                                                       (464896, 454, 'KiB_exact')):
            body = b'%PDF-1.7\n' + b'x' * (length - 9)
            responses = self.responses(body=body, size=metadata_size, content_type='text/html; charset=utf-8')
            responses[1].headers['Content-Length'] = str(length)
            with self.subTest(length=length), patch.object(snifa, 'request', side_effect=responses):
                result = snifa.download_document(self.record, self.root)
            self.assertEqual(result['metadata_content_length_unit'], expected_unit)
            self.assertTrue(result['http_content_length_verified'])
            self.assertTrue(result['content_length_verified'])

    def test_http_length_catches_truncation_inside_metadata_kib_rounding(self):
        body = b'%PDF-1.7\n' + b'x' * (1150 - 9)
        responses = self.responses(body=body, size=1)
        responses[1].headers['Content-Length'] = '1200'
        with patch.object(snifa, 'request', side_effect=responses), \
                self.assertRaisesRegex(ValueError, 'HTTP declara 1200'):
            snifa.download_document(self.record, self.root)
        self.assertEqual([p for p in self.root.rglob('*') if p.is_file()], [])

    def test_http_wire_size_is_not_compared_with_decoded_compressed_body(self):
        responses = self.responses()
        responses[1].headers.update({'Content-Encoding': 'gzip', 'Content-Length': '35'})
        with patch.object(snifa, 'request', side_effect=responses):
            result = snifa.download_document(self.record, self.root)
        self.assertFalse(result['http_content_length_verified'])
        self.assertTrue(result['content_length_verified'])
        self.assertEqual(result['metadata_content_length_unit'], 'bytes')

    def test_rounded_metadata_without_exact_http_length_is_not_overclaimed(self):
        body = b'%PDF-1.7\n' + b'x' * (1100 - 9)
        with patch.object(snifa, 'request', side_effect=self.responses(body=body, size=1)):
            result = snifa.download_document(self.record, self.root)
        self.assertEqual(result['metadata_content_length_unit'], 'KiB_rounded')
        self.assertFalse(result['content_length_verified'])

    def test_conflicting_metadata_is_recorded_when_http_size_is_exact(self):
        responses = self.responses(size=999)
        responses[1].headers['Content-Length'] = str(len(self.body))
        with patch.object(snifa, 'request', side_effect=responses):
            result = snifa.download_document(self.record, self.root)
        self.assertTrue(result['http_content_length_verified'])
        self.assertEqual(result['metadata_content_length_unit'], 'unknown')
        self.assertEqual(result['api_metadata']['ContentLength'], 999)

    def test_remote_filename_cannot_escape_root(self):
        for name in ('../../gases.pdf', r'C:\private\gases.pdf', '/tmp/gases.pdf'):
            with self.subTest(name=name), patch.object(snifa, 'request', side_effect=self.responses(name=name)):
                result = snifa.download_document(self.record, self.root)
                relative = Path(result['relative_path'])
                self.assertEqual(relative, Path('raw/el_penon/42/123_gases.pdf'))
                self.assertEqual((self.root / relative).read_bytes(), self.body)

    def test_corrupt_manifest_paths_and_symlink_escapes_are_rejected(self):
        outside = self.root.parent / 'outside'
        outside.mkdir()
        (outside / 'original.pdf').write_bytes(self.body)
        (self.root / 'escape').symlink_to(outside, target_is_directory=True)
        for relative in ('../outside/original.pdf', str(outside / 'original.pdf'), 'escape/original.pdf'):
            record = {**self.record, 'relative_path': relative, 'status': 'downloaded',
                      'sha256': hashlib.sha256(self.body).hexdigest()}
            with self.subTest(relative=relative), patch.object(snifa, 'request') as request, \
                    self.assertRaisesRegex(ValueError, 'fuera del directorio'):
                snifa.download_document(record, self.root)
            request.assert_not_called()
        self.assertEqual((outside / 'original.pdf').read_bytes(), self.body)

    def test_oversized_metadata_is_rejected_before_fetching_body(self):
        responses = self.responses(size=251 * 2**20)
        with patch.object(snifa, 'request', side_effect=responses) as request, \
                self.assertRaisesRegex(ValueError, '250 MiB'):
            snifa.download_document(self.record, self.root)
        self.assertEqual(request.call_count, 1)
        self.assertEqual(list(self.root.rglob('*.part')), [])


if __name__ == '__main__':
    unittest.main()
