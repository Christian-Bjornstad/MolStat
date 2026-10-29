"""CSV repair equivalence checks and a standalone synthetic timing benchmark."""
import csv
import io
import json
import random
import statistics
import time

import pytest

from molstat._statistics.lvms_csv import _quoted_lines, read_lvms_rows


def _reference_quoted_lines(stream):
    """The original character scanner, retained independently as an oracle."""
    quoted = False
    field_start = True
    for line in stream:
        normalized = []
        index = 0
        while index < len(line):
            char = line[index]
            following = line[index + 1:index + 2]
            if quoted:
                if char == '"':
                    if following == '"':
                        normalized.extend(('"', '"'))
                        index += 2
                        continue
                    if following in (';', '\r', '\n', ''):
                        quoted = False
                    else:
                        normalized.append('"')
            elif char == '"' and field_start:
                quoted = True
            if not quoted:
                field_start = char in (';', '\r', '\n')
            normalized.append(char)
            index += 1
        yield ''.join(normalized)
    if quoted:
        raise ValueError('LVMS-uttrekket har et uavsluttet tekstfelt.')


def _reference_rows(stream):
    try:
        reader = csv.reader(_reference_quoted_lines(stream), delimiter=';', strict=True)
        header = next(reader, None)
        if header is None:
            return
        yield header
        comments = any(name.replace('.', ' ').strip() == 'Ekstern analysekommentar' for name in header)
        for row in reader:
            if any(value.strip() for value in row):
                if len(row) > len(header) or (comments and len(row) != len(header)):
                    raise ValueError('LVMS-uttrekket har en rad med feil antall kolonner.')
            yield row
    except csv.Error as exc:
        raise ValueError('LVMS-uttrekket har ugyldig CSV-format.') from exc


def _outcome(reader, text):
    rows = []
    try:
        rows.extend(reader(io.StringIO(text, newline='')))
    except ValueError as exc:
        return rows, type(exc), str(exc)
    return rows, None, None


@pytest.mark.parametrize('newline', ['\n', '\r\n', '\r'])
@pytest.mark.parametrize('record', [
    'SYNTHETIC;ordinary;21.10.2026',
    'SYNTHETIC;=T("wrapped");21.10.2026',
    'SYNTHETIC;"quoted;semicolon";21.10.2026',
    'SYNTHETIC;"narrative "word" and more";21.10.2026',
    'SYNTHETIC;"escaped ""word"" and more";21.10.2026',
    'SYNTHETIC;"line one\nline two "word" and more";21.10.2026',
    'SYNTHETIC;"\n\n";21.10.2026',
    'SYNTHETIC;"";21.10.2026',
    'SYNTHETIC;"unterminated',
    'SYNTHETIC;"quoted"unexpected;21.10.2026',
    'SYNTHETIC;too;many;columns',
    'SYNTHETIC;missing',
    ';;',
    '',
])
def test_quoted_repair_and_parse_match_original_across_line_endings(newline, record):
    text = 'Sample;Ekstern analysekommentar;Dato' + newline + record.replace('\n', newline) + newline
    assert _outcome(_quoted_lines, text) == _outcome(_reference_quoted_lines, text)
    assert _outcome(read_lvms_rows, text) == _outcome(_reference_rows, text)


def test_quote_scanner_matches_original_for_generated_field_and_line_boundaries():
    randomizer = random.Random(209417)
    alphabet = ['ordinary', ';', '"', '""', '\r\n', '\n', '\r', '=T(', ')', ' ', 'Ø']
    cases = ['', '"', '""', '"""', '""""', ';"', 'a"', '"a"b"', '\n"']
    cases.extend(''.join(randomizer.choices(alphabet, k=randomizer.randrange(1, 65)))
                 for _ in range(1200))
    for text in cases:
        assert _outcome(_quoted_lines, text) == _outcome(_reference_quoted_lines, text)
        for header in ('A;B;C\n', 'A;Ekstern.analysekommentar;C\n'):
            report = header + text
            assert _outcome(read_lvms_rows, report) == _outcome(_reference_rows, report)


def test_multiline_repair_preserves_narrative_wrappers_and_following_dates():
    text = ('Sample;Ekstern analysekommentar;Dato\r\n'
            'SYNTHETIC;"First line; narrative "word" retained\r\n'
            'next ""escaped"" line";=T("21.10.2026")\r\n')
    assert list(read_lvms_rows(io.StringIO(text, newline=''))) == [
        ['Sample', 'Ekstern analysekommentar', 'Dato'],
        ['SYNTHETIC', 'First line; narrative "word" retained\r\nnext "escaped" line',
         '=T("21.10.2026")'],
    ]


@pytest.mark.parametrize(('record', 'message'), [
    ('SYNTHETIC;"private unfinished', 'LVMS-uttrekket har et uavsluttet tekstfelt.'),
    ('SYNTHETIC;private;21.10.2026;extra', 'LVMS-uttrekket har en rad med feil antall kolonner.'),
    ('SYNTHETIC;private', 'LVMS-uttrekket har en rad med feil antall kolonner.'),
])
def test_invalid_reports_raise_without_source_values(record, message):
    with pytest.raises(ValueError, match='^' + message.replace('.', '\\.') + '$') as raised:
        list(read_lvms_rows(io.StringIO('Sample;Ekstern analysekommentar;Dato\n' + record)))
    assert 'private' not in str(raised.value)
    assert 'SYNTHETIC' not in str(raised.value)


def _synthetic_report(rows, *, quoted):
    fields = ['Prøvenummer', 'Ekstern analysekommentar', 'Dato'] + [f'Kolonne {index}' for index in range(13)]
    output = io.StringIO(newline='')
    writer = csv.writer(output, delimiter=';', lineterminator='\r\n')
    writer.writerow(fields)
    for index in range(rows):
        comment = 'Synthetic analysis result with ordinary explanatory text and no personal data. ' * 2
        if quoted:
            comment += 'Quoted "synthetic" result; another line\r\nretained here.'
        writer.writerow([f'SYNTHETIC-{index}', comment, '=T("21.10.2026")' if quoted else '21.10.2026']
                        + ['SYNTHETIC-VALUE'] * 13)
    return output.getvalue()


def benchmark(rows=50_000, repeats=3):
    results = {}
    for quoted in (False, True):
        text = _synthetic_report(rows, quoted=quoted)
        expected = list(_reference_rows(io.StringIO(text, newline='')))
        assert list(read_lvms_rows(io.StringIO(text, newline=''))) == expected
        timings = {}
        for name, reader in [('reference', _reference_rows), ('current', read_lvms_rows)]:
            samples = []
            for _ in range(repeats):
                started = time.perf_counter()
                count = sum(1 for _ in reader(io.StringIO(text, newline='')))
                samples.append(time.perf_counter() - started)
                assert count == rows + 1
            timings[name] = statistics.median(samples)
        results['quoted_multiline' if quoted else 'ordinary'] = {
            'rows': rows, 'characters': len(text), 'median_seconds': timings,
            'speedup': timings['reference'] / timings['current'],
        }
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    benchmark()
