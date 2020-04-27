"""
Library for parsing my timesheet format and working with timesheet
data.
"""


# Copyright (c) 2020 Aubrey Barnard.
#
# This is free software released under the MIT License
# (https://choosealicense.com/licenses/mit/).


import re


# Errors


class ParseError(Exception):

    def __init__(
            self,
            filename=None,
            line=None,
            column=None,
            text=None,
            message=None,
    ):
        self.filename = filename
        self.line = line
        self.column = column
        self.text = text
        self.message = message

    def __str__(self):
        pieces = ['Parse error']
        if self.filename is not None:
            pieces.append(f" in '{self._filename!r}'")
        if self.line is not None:
            pieces.append(f' at line {self._line}')
        if self.column is not None:
            pieces.append(' at' if self._line is None else ',')
            pieces.append(f' column {self._column}')
        if self.message is not None:
            pieces.append(': ')
            pieces.append(self._message)
        if self.text is not None:
            pieces.append(': ')
            pieces.append(f'{self._text!r}')
        return ''.join(pieces)


# Tokens


class Token:

    def __eq__(self, other):
        return self.__dict__ == other.__dict__

    def __hash__(self):
        return hash(self.__dict__)


class Date(Token):

    pattern = re.compile(r'(\d{4})?([-/.])(\d{2})?\2(\d{2}):(?=\s|\Z)')

    def __init__(self, year, month, day):
        self._year = year
        self._month = month
        self._day = day

    @staticmethod
    def from_match(match, line, column):
        return Date(*match.groups(1, 3, 4))

    def __repr__(self):
        return f'Date({self._year!r}, {self._month!r}, {self._day!r})'


class TimeAmount(Token):

    pattern = re.compile(r'(\d+):(\d{2})(?=\s|\Z)')


class TimeRange(Token):

    pattern = re.compile(
        r'(?:(\d{2})(:?)(\d{2}))?-(\d{2})(?(2)\2|:?)(\d{2})(?=\s|\Z)')


class Label(Token):

    # colon options prioritizing the label:
    # * label: desc\:
    # colon options prioritizing the description: ("desc:" is just a word)
    # * label-: label=: label.: label,: label;: label:: label_: label+: label|: label<: label>:
    # * label:- label:= label:. label:, label:; label:: label:_ label:+ label:| label:< label:>
    # * -label: =label: .label: ,label: ;label: :label: _label: +label: |label: <label: >label:
    # * -label- =label= .label. ,label, ;label; :label: _label_ +label+ |label|
    # * -label-: =label=: .label.: ,label,: ;label;: /label/: \label\:
    # * _label_: +label+: ?label?: :label:: |label|: ~label~: !label!: @label@: $label$: %label%: ^label^: &label&: *label*:
    # * <label>: (label): [label]: {label}:
    # other:
    # * first "text:" on line is label unless post label ":text"

    pattern = re.compile(r'-[a-zA-Z_]\w*:(?=\s|\Z)')


class Whitespace(Token):

    # Any sequence of Unicode whitespace characters that are not newlines
    pattern = re.compile(
        '['
        # ASCII space and tab
        ' \t'
        # Unicode, ordered by expected frequency
        '\u00a0' # Non-breaking space
        '\u2002' # En space (preferred)
        '\u2003' # Em space (preferred)
        '\u2004' # 1/3 em space
        '\u2005' # 1/4 em space
        '\u2006' # 1/6 em space
        '\u2007' # Non-breaking figure space
        '\u2008' # Punctuation space
        '\u2009' # Thin space
        '\u200a' # Hair space
        '\u202f' # Non-breaking narrow space
        '\u205f' # Mathematical space
        '\u3000' # Ideographic space, CJK cell width
        '\u2000' # En quad (same as en space)
        '\u2001' # Em quad (same as em space)
        '\u1680' # Ogham space mark
        ']+'
    )


class Newline(Token):

    # Newlines as pairs or individual characters.  DOS, Acorn, Unix,
    # Mac, vertical tab, form feed, line separator, paragraph separator,
    # next line (NEL)
    pattern = re.compile('\r\n|\n\r|[\n\r\v\f\u2028\u2029\u0085]')


class Comment(Token):

    pattern = re.compile(r'#[^\n\r\v\f\u2028\u2029\u0085]*')


class Word(Token):

    # Any sequence of non-whitespace possibly followed by more
    # non-whitespace and non-breaking spaces
    pattern = re.compile(r'\S[\S\u00a0\u2007\u202f]*')


class LineTokenizer: # TODO doc # TODO make adaptive

    class NoMatchAction:

        @staticmethod
        def quit(text, filename, line, column):
            return StopIteration(), 0

        @staticmethod
        def skip_char(text, filename, line, column):
            return None, 1

        @staticmethod
        def skip_line(text, filename, line, column):
            return None, len(text)

        @staticmethod
        def raise_error(text, filename, line, column):
            raise ParseError(filename, line, column, text)

    def __init__(
            self,
            *pattern_constructor_pairs,
            no_match=NoMatchAction.raise_error,
    ):
        self._patterns = list(pattern_constructor_pairs)
        if not callable(no_match):
            raise TypeError('`no_match` is not a callable: '
                            '{no_match!r}')
        self._no_match = no_match

    def tokens(self, file, filename=None):
        # Make sure `file` is an iterable of strings
        if isinstance(file, str):
            file = file.splitlines(keepends=True)
        # Split the input into tokens
        n_lines = 0
        # Process each line separately
        for line in file:
            n_lines += 1
            idx = 0
            # Split this line into tokens by matching a pattern at the
            # start of the unprocessed input, capturing that match in a
            # token, advancing the input, and repeating
            while idx < len(line):
                matched = False
                for pattern, constructor in self._patterns:
                    match = pattern.match(line, idx)
                    if match is not None:
                        matched = True
                        if constructor is not None:
                            yield constructor(
                                match, filename, n_lines, idx + 1)
                        idx = match.end()
                        break
                # If no match, call the no match handler and proceed
                if not matched:
                    token, length = self._no_match(
                        line[idx:], filename, n_lines, idx + 1)
                    if token is None:
                        pass
                    elif isinstance(token, StopIteration):
                        return
                    else:
                        yield token
                    idx += length
