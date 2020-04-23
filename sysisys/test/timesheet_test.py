"""Tests timesheet library."""


# Copyright (c) 2020 Aubrey Barnard.
#
# This is free software released under the MIT License
# (https://choosealicense.com/licenses/mit/).


import itertools as itools
import string
import unittest

from .. import timesheet as ts


class PatternTest(unittest.TestCase):

    dates = (
        # Full dates
        '0000-00-00:',
        '2020-04-17:',
        '2020/04/17:',
        '2020.04.17:',
        # Dates without a year
        '-06-20:',
        '/06/20:',
        '.06.20:',
        # Dates without a month
        '--15:',
        '//15:',
        '..15:',
    )

    non_dates = (
        '1900-10-01',
        '1900-10-1:',
        '1900-10/01:',
        '1900-10-01\:',
        '-06-20',
        '/06/2:',
        '.06-20:',
        '-11/20:',
        '--15',
        '//1:',
        './15:',
    )

    time_amounts = (
        '0:00',
        '0:01',
        '0:12',
        '1:23',
        '12:34',
        '123:45',
        '1234:56',
    )

    non_time_amounts = (
        '0:0',
        '0:012',
        '0.00',
    )

    time_ranges = (
        # Full
        '8795-7428',
        '87:95-74:28',
        # Continuing
        '-6251',
        '-62:51',
    )

    non_time_ranges = (
        '8795-742',
        '879-7428',
        '87:95-7428',
        '8795-74:28',
        '8795\-7428',
        '87:95-74\:28',
        '-625',
        '-62512',
        '-62:512',
    )

    labels = (
        '-a:',
        '-a1:',
        '-_:',
    )

    non_labels = (
        '-:',
        'a:',
        '-a',
        'a',
        'a1:',
        '-a1',
        'a1',
        '_:',
        '-_',
        '_',
        '-1:',
        '-1',
        '1:',
        '-a:b',
        '-a-:',
        r'-a\:',
        r'\-a:',
        r'\-a\:',
    )

    whitespace = (
        # https://en.wikipedia.org/wiki/Whitespace_character
        ' ', # ASCII space
        '\t', # ASCII tab
        '\t\t  \t \t ', # Mixed tabs and spaces
        # All the Unicode spaces (both breaking and non-breaking)
        '\u00a0', # Non-breaking space
        '\u1680', # Ogham space mark
        '\u2000', # En quad (same as en space)
        '\u2001', # Em quad (same as em space)
        '\u2002', # En space (preferred)
        '\u2003', # Em space (preferred)
        '\u2004', # 1/3 em space
        '\u2005', # 1/4 em space
        '\u2006', # 1/6 em space
        '\u2007', # Non-breaking figure space (used to group digits of
                  # numbers)
        '\u2008', # Punctuation space
        '\u2009', # Thin space
        '\u200a', # Hair space
        '\u202f', # Non-breaking narrow space
        '\u205f', # 4/18 em space, "medium mathematical space", e.g. for
                  # binary operators
        '\u3000', # Ideographic space, CJK cell width
    )

    newlines = (
        # https://en.wikipedia.org/wiki/Newline
        '\n', # LF.  Unix, etc.
        '\r', # CR.  MAC, etc.
        '\r\n', # CR+LF.  DOS, Windows, etc.
        '\n\r', # LF+CR.  Acorn, Risc OS
        # Unicode (repeat above to test despite Python's interpretation
        # of \n)
        '\u000a', # LF
        '\u000d', # CR
        '\u000d\u000a', # CR+LF
        '\u000a\u000d', # LF+CR
        # Others considered line terminators under Unicode
        '\u000b', # VT, vertical tab, \v
        '\u000c', # FF, form feed, \f
        '\u0085', # NEL, next line
        '\u2028', # LS, line separator
        '\u2029', # PS, paragraph separator
    )

    comments = (
        '#',
        '#####',
        '# #  #   #    #     ',
        '#comment',
    )

    non_comments = (
        '\#',
        '\#123',
    )

    words = (
        # Typical words containing letters
        'alpha-numeric',
        # Numbers
        '00000',
        '1',
        '+1',
        '-1',
        '0.0',
        '0e0',
        '-1.1e-1',
        'NaN',
        '+inf',
        '1_234_567_890',
        '1/3',
        # Math / Programming
        '+',
        '-',
        '*',
        '/',
        '**',
        '^',
        '=',
        ':=',
        '==',
        '!=',
        '<',
        '>',
        '<=',
        '>=',
        # Punctuation
        'Thus,',
        "don't",
        'think!',
        'What?',
        'Yes.',
        'i.e.,',
        'e.g.,',
        '(aside)',
        '[editorial]',
        'and/or',
        'whereas:',
        'UW–Madison', # En dash
        'One!—Two!', # Em dash
        '10#',
        # Quotes
        '"quoth"'
        "'the_raven'",
        "''", # Ditto
        '"no',
        'strings"',
        # Markup
        '*emphasis*',
        '_underline_',
        '**bold**',
        '`code`',
        # Other common forms
        'a@b.com',
        '<a@b.com>',
        'https://yaml.org',
        '<tag>',
        '</tag>',
        '123-456-7890',
        '1pm',
        '3am',
        '53706-1613',
        # Non-breaking spaces
        'Mr.\u00a0Rogers',
        'Slim\u202fJim',
        # Number with figure space as thousands separator
        '1\u2007234\u2007567\u2007890',
        # Categories of characters
        string.ascii_letters,
        string.digits,
        string.punctuation,
    )

    non_words = (
        # Non-breaking spaces on their own
        '\u00a0\u2007\u202f',
        # Characters with intervening spaces
        '—\u2003—',
        # Strings with spaces
        "'the raven'",
        '"no strings"',
    )

    all_texts = {
        dates, non_dates,
        time_amounts, non_time_amounts,
        time_ranges, non_time_ranges,
        labels, non_labels,
        whitespace,
        newlines,
        comments, non_comments,
        words, # Except `non_words`
    }

    def _test_pattern(self, pattern, texts, non_texts):
        # Matches
        for text in texts:
            with self.subTest(repr(text)):
                self.assertIsNotNone(pattern.fullmatch(text))
        # Non matches
        for text in non_texts:
            with self.subTest(repr(text)):
                self.assertIsNone(pattern.fullmatch(text))

    def test_date(self):
        self._test_pattern(
            ts.Date.pattern, self.dates,
            itools.chain.from_iterable(
                self.all_texts - {self.dates}))

    def test_time_amount(self):
        self._test_pattern(
            ts.TimeAmount.pattern, self.time_amounts,
            itools.chain.from_iterable(
                self.all_texts - {self.time_amounts}))

    def test_time_range(self):
        self._test_pattern(
            ts.TimeRange.pattern, self.time_ranges,
            itools.chain.from_iterable(
                self.all_texts - {self.time_ranges}))

    def test_label(self):
        self._test_pattern(
            ts.Label.pattern, self.labels,
            itools.chain.from_iterable(
                self.all_texts - {self.labels}))

    def test_whitespace(self):
        self._test_pattern(
            ts.Whitespace.pattern, self.whitespace,
            itools.chain.from_iterable(
                self.all_texts - {self.whitespace}))

    def test_newline(self):
        self._test_pattern(
            ts.Newline.pattern, self.newlines,
            itools.chain.from_iterable(
                self.all_texts - {self.newlines}))

    def test_comment(self):
        self._test_pattern(
            ts.Comment.pattern, self.comments,
            itools.chain.from_iterable(
                self.all_texts - {self.comments}))

    def test_word(self):
        self._test_pattern(
            ts.Word.pattern,
            itools.chain(
                self.words,
                self.non_dates,
                self.non_time_amounts,
                self.non_time_ranges,
                self.non_labels,
                self.non_comments,
            ),
            itools.chain(
                self.non_words,
                self.whitespace,
                self.newlines,
            ),
        )


class TokenTest(unittest.TestCase):
    pass


class FillInDataTest(unittest.TestCase):
    pass


class ParseTest(unittest.TestCase):

    def test_by_label(self):
        text = '''
1414-11-09:
a:
0521-1304 1
-1723
6:33 2
2:05
'''.lstrip()

    def test_by_time_amount(self):
        text = '''
3943-07-21:
6:04 a: 1
11:11 b:
11:47 2
15:52
'''.lstrip()

    def test_by_time_range(self):
        text = '''
6240-05-01:
1509-1625 a: 1
0258-1148 b:
1849-2210 2
1129-1622
'''.lstrip()

    def test_sequential_ranges(self):
        text = '''
8701-08-12:
1008-1524 a: 1
-1605 b:
-1636 2
-1711
'''.lstrip()

    def test_time_range_wrap(self):
        text = '''
3578-10-08:
1934-0733 a: 1

1320-04-24:
2118-2359 b: 2
-0522 c: 3
'''.lstrip()

    def test_field_permutations(self):
        text = '''
8755-05-29:
a: 0855-1350 1
b: 15:46 2
c: 3 0708-2252
d: 4 0:35
0047-1234 e: 5
14:07 f: 6
0412-2106 7 g:
1:38 8 h:
9 i: 0558-0758
10 j: 12:02
11 0706-1151 k:
12 11:46 l:
'''.lstrip()

    def test_field_omissions(self):
        text = '''
'''.lstrip()

    def test_colon_in_description(self):
        pass
