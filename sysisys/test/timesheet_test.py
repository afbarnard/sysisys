"""Tests timesheet library."""


# Copyright (c) 2020 Aubrey Barnard.
#
# This is free software released under the MIT License
# (https://choosealicense.com/licenses/mit/).


import io
import itertools as itools
import re
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
        ('2020-04-17: ', 11),
        ('2020/04/17:\t', 11),
        ('2020.04.17:\n', 11),
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
        '1900-10-01\\:',
        '1900-10-01:10:01',
        '1900-10-01:z',
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
        ('0:00 ', 4),
        ('10:00\t', 5),
        ('100:00\n', 6),
    )

    non_time_amounts = (
        '0:0',
        '0:012',
        '0:00a',
        '0:00.',
        '0\\:00',
        '\\0:00',
        '0.00',
    )

    time_ranges = (
        # Full
        '8795-7428',
        '87:95-74:28',
        # Continuing
        '-6251',
        '-62:51',
        # With trailing spaces
        ('8795-7428 ', 9),
        ('87:95-74:28\t', 11),
        ('-6251\n', 5),
        ('-62:51 ', 6),
    )

    non_time_ranges = (
        '8795-74288',
        '87955-7428',
        '8795-742',
        '879-7428',
        '87:95-7428',
        '87:95-74:28.',
        '8795-74:28',
        '8795\\-7428',
        '87:95-74\\:28',
        '-625',
        '-62512',
        '-6251a',
        '-6251.0',
        '-62:512',
        '\\-1234',
    )

    labels = (
        '-a:',
        '-a1:',
        '-_:',
        ('-a: ', 3),
        ('-a1:\t', 4),
        ('-_:\n', 3),
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
        '-a1:2',
        '-_:.',
        '-a-:',
        '-a\\:',
        '\\-a:',
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
        '\\#',
        '\\#123',
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

    all_texts = {
        dates, non_dates,
        time_amounts, non_time_amounts,
        time_ranges, non_time_ranges,
        labels, non_labels,
        whitespace,
        newlines,
        comments, non_comments,
        words,
    }

    def _test_pattern(self, pattern, texts, non_texts):
        # Matches
        for text in texts:
            with self.subTest(repr(text)):
                if isinstance(text, str):
                    match_len = len(text)
                else:
                    text, match_len = text
                match = pattern.match(text)
                self.assertIsNotNone(match)
                self.assertEqual(match_len, match.end())
        # Non matches
        for text in non_texts:
            with self.subTest(repr(text)):
                if not isinstance(text, str):
                    text, _ = text
                self.assertIsNone(pattern.match(text))

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
                self.whitespace,
                self.newlines,
            ),
        )


class ParseErrorTest(unittest.TestCase):

    def test___str__(self):
        e = ts.ParseError(
            text='¿¡!?',
            message='Not a word',
            filename='<str>',
            line='254',
            column='14',
        )
        msg = ("Parse error in '<str>' at line 254, column 14: "
               "Not a word: '¿¡!?'")
        self.assertEqual(str(e), msg)


class LineTokenizerTest(unittest.TestCase):

    # Simplified patterns
    letters_pattern = re.compile('[a-zA-Z]+')
    digits_pattern = re.compile('[0-9]+')
    whitespace_pattern = re.compile('[ \t\n]+')
    punctuation_pattern = re.compile('[-,.?!:;\'"–—()/]')

    def setUp(self):
        self.tknzr = ts.LineTokenizer(
            (self.letters_pattern,
             lambda m, f, l, c: ('w', m.end() - m.start(), m.group(0))),
            (self.digits_pattern,
             lambda m, f, l, c: ('n', m.end() - m.start(), m.group(0))),
            (self.whitespace_pattern,
             lambda m, f, l, c: ('s', m.end() - m.start(), m.group(0))),
            (self.punctuation_pattern,
             lambda m, f, l, c: ('p', m.end() - m.start(), m.group(0))),
        )

    def test_empty(self):
        self.assertEqual(list(self.tknzr.tokens('')), [])

    def test_word(self):
        self.assertEqual(
            list(self.tknzr.tokens('craquelure')),
            [('w', 10, 'craquelure')])

    def test_number(self):
        self.assertEqual(
            list(self.tknzr.tokens('2718')),
            [('n', 4, '2718')])

    def test_space(self):
        for c in ' \t\n':
            with self.subTest(repr(c)):
                self.assertEqual(
                    list(self.tknzr.tokens(c)),
                    [('s', 1, c)])

    def test_hello_world(self):
        self.assertEqual(
            list(self.tknzr.tokens('Hello, world!\n')),
            [('w', 5, 'Hello'), ('p', 1, ','), ('s', 1, ' '),
             ('w', 5, 'world'), ('p', 1, '!'), ('s', 1, '\n')])

    def test_sonnet(self):
        sonnet = io.StringIO('''
Cupid laid by his brand, and fell asleep.
A maid of Dian's this advantage found,
And his love-kindling fire did quickly steep
In a cold valley-fountain of that ground;
Which borrow'd from this holy fire of Love
A dateless lively heat, still to endure,
And grew a seething bath, which yet men prove
Against strange maladies a sovereign cure.
But at my mistress' eye Love's brand new-fired,
The boy for trial needs would touch my breast;
I, sick withal, the help of bath desired,
And thither hied, a sad distemper'd guest,
  But found no cure: the bath for my help lies
  Where Cupid got new fire—my mistress' eyes.
'''.strip())
        # Tokens per line:
        # 18 (18), 17 (35), 16 (51), 17 (68),
        # 18 (86), 16 (102), 19 (121), 13 (134),
        # 22 (156), 19 (175), 19 (194), 18 (212),
        # 21 (233), 18 (251),
        tokens = list(self.tknzr.tokens(sonnet))
        self.assertEqual(tokens[0], ('w', 5, 'Cupid'))
        self.assertEqual(
            tokens[13:17],
            [('w', 4, 'fell'), ('s', 1, ' '),
             ('w', 6, 'asleep'), ('p', 1, '.')])
        self.assertEqual(
            tokens[24:27],
            [('w', 4, 'Dian'), ('p', 1, "'"), ('w', 1, 's')])
        self.assertEqual(
            tokens[39:42],
            [('w', 4, 'love'), ('p', 1, '-'), ('w', 8, 'kindling')])
        self.assertEqual(
            tokens[233:],
            [('s', 1, '\n'), ('s', 2, '  '),
             ('w', 5, 'Where'), ('s', 1, ' '),
             ('w', 5, 'Cupid'), ('s', 1, ' '),
             ('w', 3, 'got'), ('s', 1, ' '),
             ('w', 3, 'new'), ('s', 1, ' '),
             ('w', 4, 'fire'), ('p', 1, '—'),
             ('w', 2, 'my'), ('s', 1, ' '),
             ('w', 8, 'mistress'), ('p', 1, "'"), ('s', 1, ' '),
             ('w', 4, 'eyes'), ('p', 1, '.')])

    def test_none_constructor(self):
        tknzr = ts.LineTokenizer(
            (self.letters_pattern,
             lambda m, f, l, c: ('w', m.end() - m.start(), m.group(0))),
            (self.digits_pattern, None),
            (self.whitespace_pattern, None),
            (self.punctuation_pattern, None),
            no_match=ts.LineTokenizer.NoMatchAction.skip_char,
        )
        self.assertEqual(
            list(tknzr.tokens('¡Hello, 1 _great_ *big* world!')),
            [('w', 5, 'Hello'), ('w', 5, 'great'), ('w', 3, 'big'),
             ('w', 5, 'world')])

    def test_no_match_action_quit(self):
        self.tknzr._no_match = ts.LineTokenizer.NoMatchAction.quit
        self.assertEqual(
            list(self.tknzr.tokens('Hello, garbl`d!')),
            [('w', 5, 'Hello'), ('p', 1, ','), ('s', 1, ' '),
             ('w', 5, 'garbl')])

    def test_no_match_action_skip_char(self):
        self.tknzr._no_match = ts.LineTokenizer.NoMatchAction.skip_char
        self.assertEqual(
            list(self.tknzr.tokens('Hello, garbl`d!')),
            [('w', 5, 'Hello'), ('p', 1, ','), ('s', 1, ' '),
             ('w', 5, 'garbl'), ('w', 1, 'd'), ('p', 1, '!')])

    def test_no_match_action_skip_line(self):
        self.tknzr._no_match = ts.LineTokenizer.NoMatchAction.skip_line
        self.assertEqual(
            list(self.tknzr.tokens('Hello, garbl`d!\r\nBye.')),
            [('w', 5, 'Hello'), ('p', 1, ','), ('s', 1, ' '),
             ('w', 5, 'garbl'), #('s', 2, '\r\n'), # TODO Skip or include EOL?
             ('w', 3, 'Bye'), ('p', 1, '.')])

    def test_no_match_action_raise_error(self):
        with self.assertRaises(ts.ParseError) as raises:
            list(self.tknzr.tokens(
                '\nHello, garbl`d~@#$%^&*_!', filename='<str>'))
        err = raises.exception
        self.assertEqual(err.filename, '<str>')
        self.assertEqual(err.line, 2)
        self.assertEqual(err.column, 13)
        self.assertEqual(err.text, '`d~@#$%^&*_!')

    def test_no_match_action_handler_function(self):
        def mk_unknown(text, filename, line, column):
            match = re.match('[^a-zA-Z0-9 \t\n,.?!:;\'"–—()/-]+', text)
            return (('?', len(match[0]), match[0]), len(match[0]))
        self.tknzr._no_match = mk_unknown
        self.assertEqual(
            list(self.tknzr.tokens('Hello|_garbl`ð¿\nErr@π𝑖¡»')),
            [('w', 5, 'Hello'), ('?', 2, '|_'),
             ('w', 5, 'garbl'), ('?', 3, '`ð¿'), ('s', 1, '\n'),
             ('w', 3, 'Err'), ('?', 5, '@π𝑖¡»')])


class TokensTest(unittest.TestCase):

    def test_date(self):
        self.assertEqual(list(ts.tokens('2020-04-28:')),
                         [ts.Date('2020', '04', '28', '-')])
        self.assertEqual(list(ts.tokens('-04-28:')),
                         [ts.Date(month='04', day='28', sep='-')])
        self.assertEqual(list(ts.tokens('--28:')),
                         [ts.Date(day='28', sep='-')])

    def test_time_amount(self):
        self.assertEqual(list(ts.tokens('12:34')),
                         [ts.TimeAmount('12', '34')])

    def test_time_range(self):
        self.assertEqual(
            list(ts.tokens('2020-0428')),
            [ts.TimeRange(('20', '20'), ('04', '28'), sep='')])
        self.assertEqual(
            list(ts.tokens('-0428')),
            [ts.TimeRange((None, None), ('04', '28'), sep='')])

    def test_label(self):
        self.assertEqual(list(ts.tokens('-lbl:')),
                         [ts.Label('lbl')])

    def test_words(self):
        text = ('2020-04-28 --01:0 //12 12:345 1234-56789 -12345 '
                '-word!: \\#123')
        tkns = [
            ts.Word('2020-04-28'), ts.Whitespace(' '),
            ts.Word('--01:0'), ts.Whitespace(' '),
            ts.Word('//12'), ts.Whitespace(' '),
            ts.Word('12:345'), ts.Whitespace(' '),
            ts.Word('1234-56789'), ts.Whitespace(' '),
            ts.Word('-12345'), ts.Whitespace(' '),
            ts.Word('-word!:'), ts.Whitespace(' '),
            ts.Word('\\#123'),
        ]
        self.assertEqual(list(ts.tokens(text)), tkns)

    def test_comment(self):
        self.assertEqual(list(ts.tokens('# comment')),
                         [ts.Comment('# comment')])

    def test_whitespace(self):
        self.assertEqual(list(ts.tokens('\t\t  ')),
                         [ts.Whitespace('\t\t  ')])

    def test_newline(self):
        self.assertEqual(list(ts.tokens('\r\n')),
                         [ts.Newline('\r\n')])

    def test_excerpt(self):
        file = io.StringIO('''
# Test time entries
2020-04-28:  0:14 -play:  abc\r\n123\u00a0456
--29:\t2002-2020 hard
-05-01:\r0808-0909 -work: e-mail
\t-1010 calendar, planning! # What to do?  When?
'''.lstrip())
        tkns = [
            ts.Comment('# Test time entries'), ts.Newline('\n'),
            ts.Date('2020', '04', '28', '-'), ts.Whitespace('  '),
            ts.TimeAmount('0', '14'), ts.Whitespace(' '),
            ts.Label('play'), ts.Whitespace('  '),
            ts.Word('abc'), ts.Newline('\r\n'),
            ts.Word('123\u00a0456'), ts.Newline('\n'),
            ts.Date(day='29', sep='-'), ts.Whitespace('\t'),
            ts.TimeRange(('20', '02'), ('20', '20'), sep=''),
            ts.Whitespace(' '),
            ts.Word('hard'), ts.Newline('\n'),
            ts.Date(month='05', day='01', sep='-'), ts.Newline('\r'),
            ts.TimeRange(('08', '08'), ('09', '09'), sep=''),
            ts.Whitespace(' '),
            ts.Label('work'), ts.Whitespace(' '),
            ts.Word('e-mail'), ts.Newline('\n'), ts.Whitespace('\t'),
            ts.TimeRange(end=('10', '10'), sep=''), ts.Whitespace(' '),
            ts.Word('calendar,'), ts.Whitespace(' '),
            ts.Word('planning!'), ts.Whitespace(' '),
            ts.Comment('# What to do?  When?'), ts.Newline('\n'),
        ]
        self.assertEqual(list(ts.tokens(file)), tkns)


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
