"""
Library for parsing my timesheet format and working with timesheet
data.
"""


# Copyright (c) 2020 Aubrey Barnard.
#
# This is free software released under the MIT License
# (https://choosealicense.com/licenses/mit/).


import re


# Tokens


class Token:

    def __eq__(self, other):
        return self.__dict__ == other.__dict__

    def __hash__(self):
        return hash(self.__dict__)


class Date(Token):

    pattern = re.compile(r'(\d{4})?([-/.])(\d{2})?\2(\d{2}):')

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

    pattern = re.compile(r'(\d+):(\d{2})')


class TimeRange(Token):

    pattern = re.compile(
        r'(?:(\d{2})(:?)(\d{2}))?-(\d{2})(?(2)\2|:?)(\d{2})')


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

    pattern = re.compile(r'-[a-zA-Z_]\w*:')


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
