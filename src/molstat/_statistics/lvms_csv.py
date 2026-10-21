"""Read LVMS text fields without splitting multiline analysis comments."""
from __future__ import annotations

import csv
from collections.abc import Iterator
from typing import TextIO


def _quoted_lines(stream: TextIO) -> Iterator[str]:
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
                        # LVMS sometimes leaves narrative quotes unescaped.
                        # A quote followed by text cannot terminate a CSV field.
                        normalized.append('"')
            elif char == '"' and field_start:
                quoted = True
            if not quoted:
                field_start = char in (';', '\r', '\n')
            normalized.append(char)
            index += 1
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
