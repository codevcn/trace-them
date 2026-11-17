"""Evidence and input data must survive every export without executable cells."""
import csv
import json
from importlib.resources import files
from pathlib import Path

import pytest
from openpyxl import load_workbook
from jsonschema import Draft202012Validator, FormatChecker

from trace_them.models import Candidate, Evidence, Finding, Status
from trace_them.reporting import make_report, safe_filename, write_reports
from trace_them.resolvers import Resolution
from trace_them.transport import RequestBudget


def fixture_report():
    evidence = Evidence('inferred', 'input:email', 'Email local-part is a hypothesis only')
    finding = Finding('Fixture', 'fixture', 'https://example.com/fixture', Status.FOUND,
                      'Public profile responded', evidence=[evidence], association='unverified')
    candidate = Candidate('fixture', origin='email_local_part', evidence=[evidence])
    resolution = Resolution('Gravatar', Status.NOT_FOUND, 'No public Gravatar profile; others unknown')
    return make_report('email', 'fixture@example.com', [finding],
                       resolutions=[resolution], candidates=[candidate], budget=RequestBudget(5))


def test_canonical_report_keeps_existence_separate_from_association():
    report = fixture_report()
    assert report['schema_version'] == '1.0'
    assert report['tool']['name'] == 'Trace Them'
    assert report['findings'][0]['status'] == 'found'
    assert report['findings'][0]['association'] == 'unverified'
    assert report['candidates'][0]['origin'] == 'email_local_part'
    assert report['request_budget']['used'] == 0
    assert 'confidence' not in json.dumps(report)


def test_report_validates_against_shipped_versioned_schema():
    schema = json.loads(files('trace_them').joinpath('resources/report.schema.json').read_text(encoding='utf-8'))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    validator.validate(fixture_report())


def test_every_export_preserves_candidate_and_resolution_evidence(tmp_path):
    report = fixture_report()
    paths = write_reports(report, tmp_path, ['json', 'txt', 'csv', 'xlsx'])
    assert len(paths) == 4
    paths = {path.suffix: path for path in paths}
    assert json.loads(paths['.json'].read_text(encoding='utf-8')) == report
    text = paths['.txt'].read_text(encoding='utf-8')
    assert 'email_local_part' in text and 'unverified' in text
    assert 'Gravatar' in text and 'hypothesis' in text
    with paths['.csv'].open(encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.DictReader(stream))
    assert {row['record_type'] for row in rows} == {'finding', 'resolution', 'candidate'}
    finding_row = next(row for row in rows if row['record_type'] == 'finding')
    assert finding_row['association'] == 'unverified'
    assert json.loads(finding_row['evidence'])[0]['kind'] == 'inferred'
    workbook = load_workbook(paths['.xlsx'])
    sheet = workbook.active
    records = list(sheet.values)
    assert len(records) == 4
    workbook.close()


@pytest.mark.parametrize('name', ['../../outside', '..\\..\\outside', 'CON', 'aux.txt',
                                 'NUL', 'name:stream', 'a\nb', '.', '', 'Émile', 'a' * 1000])
def test_safe_filename_is_portable_and_contains_no_path(name):
    filename = safe_filename(name)
    assert filename
    assert not any(char in filename for char in '/\\:\n\r\x00')
    assert filename not in {'.', '..'}
    assert filename.split('.')[0].upper() not in {'CON', 'AUX', 'NUL'}
    assert len(filename) < 120


def test_filename_normalization_collisions_remain_distinct():
    assert safe_filename('a/b') != safe_filename('a\\b')


def test_export_stem_cannot_escape_output_directory(tmp_path):
    output = tmp_path / 'reports'
    paths = write_reports(fixture_report(), output, ['json', 'csv'], stem='../../escape')
    assert all(path.resolve().parent == output.resolve() for path in paths)
    assert not (tmp_path / 'escape.json').exists()


@pytest.mark.parametrize('dangerous', ['=HYPERLINK("https://example.com")', '+cmd', '-cmd',
                                      '@SUM(1,1)', ' \t=1+1'])
def test_spreadsheet_values_are_literal(tmp_path, dangerous):
    report = fixture_report()
    report['findings'][0]['reason'] = dangerous
    paths = write_reports(report, tmp_path, ['csv', 'xlsx'])
    csv_path, xlsx_path = paths
    with csv_path.open(encoding='utf-8-sig', newline='') as stream:
        row = next(csv.DictReader(stream))
    assert row['reason'] == "'" + dangerous
    workbook = load_workbook(xlsx_path, data_only=False)
    sheet = workbook.active
    columns = {cell.value: cell.column for cell in sheet[1]}
    cell = sheet.cell(row=2, column=columns['reason'])
    assert cell.data_type == 's'
    assert cell.value == dangerous
    assert cell.hyperlink is None
    workbook.close()


def test_empty_run_still_exports_run_metadata(tmp_path):
    report = make_report('username', 'fixture', [])
    path = write_reports(report, tmp_path, ['csv'])[0]
    with path.open(encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 1
    assert rows[0]['record_type'] == 'run'
    assert json.loads(rows[0]['run_metadata'])['input']['value'] == 'fixture'


def test_unknown_format_rejected_without_output_files(tmp_path):
    with pytest.raises(ValueError):
        write_reports(fixture_report(), tmp_path, ['pdf'])
    assert not list(Path(tmp_path).glob('*'))


def test_same_slug_sources_keep_distinct_origins_in_spreadsheets(tmp_path):
    source = Evidence('source_reported_email_association', 'https://api.gravatar.com', 'Source-scoped email link')
    direct = Finding('Gravatar', 'fixture', 'https://gravatar.com/fixture', Status.FOUND,
                     'Source resolved profile', association='source_reported',
                     association_evidence=[source], origin='public_email_resolution')
    candidate = Candidate('fixture', origin='email_local_part',
                          evidence=[Evidence('inferred', 'input:email', 'Local-part hypothesis')])
    inferred = Finding('Other', 'fixture', 'https://example.com/fixture', Status.FOUND,
                       'Profile exists', origin='email_local_part')
    report = make_report('email', 'fixture@example.com', [direct, inferred], candidates=[candidate])
    path = write_reports(report, tmp_path, ['csv'])[0]
    with path.open(encoding='utf-8-sig', newline='') as stream:
        rows = [row for row in csv.DictReader(stream) if row['record_type'] == 'finding']
    assert rows[0]['origin'] == 'public_email_resolution'
    assert rows[0]['association'] == 'source_reported'
    assert rows[1]['origin'] == 'email_local_part'
    assert rows[1]['association'] == 'unverified'


def test_query_timing_is_retained_in_spreadsheet_exports(tmp_path):
    report = fixture_report()
    report['findings'][0]['query_time'] = 0.123
    paths = write_reports(report, tmp_path, ['csv', 'xlsx'])
    with paths[0].open(encoding='utf-8-sig', newline='') as stream:
        finding = next(csv.DictReader(stream))
    assert float(finding['query_time']) == 0.123
    workbook = load_workbook(paths[1])
    rows = list(workbook.active.values)
    index = rows[0].index('query_time')
    assert float(rows[1][index]) == 0.123
    workbook.close()
