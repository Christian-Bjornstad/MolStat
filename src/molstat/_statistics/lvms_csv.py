"""Read LVMS text fields without splitting multiline analysis comments."""
from __future__ import annotations

import csv
from collections.abc import Iterator
from typing import TextIO


def _quoted_lines(stream: TextIO) -> Iterator[str]:
    quoted = False
    field_start = True
    for line in stream:
        quote = line.find('"')
        if quote < 0:
            if line and not quoted:
                field_start = line[-1] in (';', '\r', '\n')
            yield line
            continue
        normalized = []
        index = 0
        while quote >= 0:
            # Ordinary text cannot change quoted state. Outside a quoted
            # field, only the character immediately before a quote matters.
            if quote > index:
                normalized.append(line[index:quote])
                if not quoted:
                    field_start = line[quote - 1] in (';', '\r', '\n')
            following = line[quote + 1:quote + 2]
            if quoted:
                if following == '"':
                    normalized.append('""')
                    index = quote + 2
                    quote = line.find('"', index)
                    continue
                if following in (';', '\r', '\n', ''):
                    quoted = False
                else:
                    # LVMS sometimes leaves narrative quotes unescaped.
                    # A quote followed by text cannot terminate a CSV field.
                    normalized.append('"')
            elif field_start:
                quoted = True
            if not quoted:
                field_start = False
            normalized.append('"')
            index = quote + 1
            quote = line.find('"', index)
        if index < len(line):
            normalized.append(line[index:])
            if not quoted:
                field_start = line[-1] in (';', '\r', '\n')
        yield ''.join(normalized)
    if quoted:
        raise ValueError("LVMS-uttrekket har et uavsluttet tekstfelt.")


def read_lvms_rows(stream: TextIO) -> Iterator[list[str]]:
    """Keep ordinary CSV quoting and =T wrappers; repair embedded narrative quotes.

    Reports containing analysis comments must retain their complete column
    layout. Do not turn comment fragments into padded, apparently valid rows.
    Errors deliberately omit source values and comments.
    """
    try:
        reader = csv.reader(_quoted_lines(stream), delimiter=';', strict=True)
        header = next(reader, None)
        if header is None:
            return
        yield header
        comments = any(name.replace('.', ' ').strip() == 'Ekstern analysekommentar' for name in header)
        for row in reader:
            if any(value.strip() for value in row):
                if len(row) > len(header) or (comments and len(row) != len(header)):
                    raise ValueError("LVMS-uttrekket har en rad med feil antall kolonner.")
            yield row
    except csv.Error as exc:
        raise ValueError("LVMS-uttrekket har ugyldig CSV-format.") from exc
