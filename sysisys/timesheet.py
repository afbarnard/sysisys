"""
Library for reading a human-oriented timesheet format and working
with time entry records.


Timesheets
----------

A timesheet is a log of work or activities, organized by date and time.
It is effectively a list of time entry records, where each such record
has a date, an amount of time, a category label, and a description.  For
example, the following CSV records log a presentation and its preparation.

2020-04-20|2:30|analysis|compile quarterly report
2020-04-20|1:15|qtr_rvw|make presentation
2020-04-21|1:00|qtr_rvw|present quarterly report to Jack, Jill, VP

However, CSV and similar tabular formats are not very convenient for
humans to write or read, often being overly verbose and redundant.  This
library defines a format for logging activities that is natural and
convenient for humans to write and read, with a minimum of redundancy
and a maximum of flexibility.  Combined with tools for interpreting the
format and working with time entry records, it is hoped that this
library will more than meet your timesheet-keeping needs.


Timesheet Format
----------------

This timesheet format exists to provide a human-oriented shorthand for
keeping a log of time entries.  Through intuitive sequencing and spatial
locality, the format provides a convenient and minimal syntax for
expressing time entry records, imitating what one might jot down in a
note.  Accordingly, the syntax is flexible enough to allow for
organizing the information according to one's preferences or style.  The
idea is that you should be able to write down what you want how you want
and the system finds and assembles the relevant information.  This is
made possible by the overarching principle that any information that is
missing from an entry is filled in from the previous entry.

Here are some examples of the format that demonstrate the syntax and the
principle of filling in fields with information from previous entries.

The first example contains entries organized by date and time.  Its
first line is a comment introduced by `#`.  The second line is a date.
Lines three and four are the first two time entries, each containing a
time range, a category / label, and a description.  The times are
specified in 24-hour time.  Lines five through ten describe a single
entry with a multi-line description and a time amount rather than a time
range.  Note the syntax to distinguish labels from colons that naturally
occur in the description.

```
# Organized by date and time
2020-05-13:
09:00-10:30 -msw: brainstorm and plan new silly walks
13:30-14:15 -pet_shop: respond to Mr. Praline about dead parrot
0:15 -argument_clinic: merely contradiction:
  It is!
  No, it isn't!
  'Tis!
  'Tisn't!
  Time's up!

--14:
0900-1100 -msw: draft implementation of new silly walks
-1200 distribute to all ministry branches
```

Entries for the next day start on line twelve.  The year and month of
the date are filled in from the previous date.  Here the time ranges are
written without colons, and the start time of the second range is
omitted because it is the same as the end time of the previous range.
The label for the second entry is also copied forward.

While organizing entries by date and time is the most like a log and
therefore perhaps the most natural, it can easily make sense to organize
entries in other ways, such as by topic.  This can make it easier to
track individual projects, for example.  Here the dates are written with
slashes instead of dashes.  There is also a ditto mark ("''") to
explicitly copy forward the previous description in case one opts to
have empty descriptions instead of copying them forward automatically. # TODO

```
# Organized by topic
-acme:
develop UI for new Acme website
2020/05/13: 2:15
//14: 10:00-11:00 design meeting
//15: 09:00-12:00 write tests
      2:00 i18n
-widgets:
//12: 4:00 JS, CSS for new profile page
//13: 6:00 ''
      09:00-10:00 progress and planning meeting
```

The following example illustrates putting multiple time entries on a
single line to create a very compact format.  This can be done without
descriptions, or by providing descriptions before or after.  The rules
for associating descriptions TODO.  This example also shows that dates
can be written with dots, and that entries can be separated with commas
or semicolons if desired.

TODO default description is empty!
TODO associate descriptions with previous unless no previous exists.  syntax for associating with future, either spaces or a new record indicator: <sep> "." <sep>  OR  <newline>{3} (?)
TODO descriptions are single-use.  ditto syntax for copying forward.  ''  2-''  ''-3
TODO separating commas?  separating semicolons?  (optional)
TODO separator?: [,;] <sep> <non-word>


```
# Organized by date and topic
2020.01.29: -compsci: 0930-1045 -math: 1430-1545
..30: -research: 1100-1215 1245-1415 1730-1810
..31: 1000-1300 2:30
.02.01: 5:00

# Organized by topic, with descriptions before and after # TODO
Develop the ACME widget for https://www.acme.xyz/.
-dev: 2020-02-01: 1:00, 1:00, --03: 2:00, --04: 3:00
-tst: --04: 5:00; --05: 8:00
Test the ACME widget, send update to emca@acme.xyz.
```


Grammar
-------

### Tokens ###

```
# A digit is an ASCII digit
<digit> ::= ["0" - "9"]

# Whitespace is any sequence of Unicode whitespace characters that are
# not newlines
<whitespace> ::=
    ( " "
    | "\t"
    | "\u00a0"  # Non-breaking space
    | "\u1680"  # Ogham space mark
    | "\u2000"  # En quad (same as en space)
    | "\u2001"  # Em quad (same as em space)
    | "\u2002"  # En space (preferred to "en quad")
    | "\u2003"  # Em space (preferred to "em quad")
    | "\u2004"  # 1/3 em space
    | "\u2005"  # 1/4 em space
    | "\u2006"  # 1/6 em space
    | "\u2007"  # Non-breaking figure space
    | "\u2008"  # Punctuation space
    | "\u2009"  # Thin space
    | "\u200a"  # Hair space
    | "\u202f"  # Non-breaking narrow space
    | "\u205f"  # Mathematical space
    | "\u3000"  # Ideographic space, CJK cell width
    )+

# A newline is a pair of characters or an individual character used to
# separate / terminate lines
<newline> ::=
    | "\r\n"    # Carriage return, line feed.  DOS, Windows.
    | "\n\r"    # Line feed, carriage return.  Acorn.
    | "\n"      # Line feed.  Unix, Linux.
    | "\r"      # Carriage return.  Mac.
    | "\v"      # Vertical tab
    | "\f"      # Form feed
    | "\u0085"  # Next line (NEL)
    | "\u2028"  # Line separator
    | "\u2029"  # Paragraph separator

# A word is any sequence of non-whitespace possibly followed by more
# non-whitespace and non-breaking spaces
<word> ::=
    !<whitespace>
    (
    | !<whitespace>
    | "\u00a0"  # Non-breaking space
    | "\u2007"  # Non-breaking figure space
    | "\u202f"  # Non-breaking narrow space
    )*

# A comment is a hash / pound / octothorpe followed by anything up to a
# newline.  This means a comment is necessarily followed by a newline
# (or EOF), but that newline is not part of the comment.
<comment> ::=
    "#" (!<newline>)*

# A non-word is whitespace, a newline, or the end of input
<non-word> ::=
    | <whitespace>
    | <newline>
    | <eof>

# A date is the year, month, and day, as zero-padded numbers, separated
# by "-", "/", or ".".  To distinguish a date from a word, the date must
# be followed by non-word characters (negative lookahead assertion).
<date> ::=
    <date-fields> ":" ?=<non-word>
<date-fields> ::=
    | <digit>{4} "-" <digit>{2} "-" <digit>{2}
    | <digit>{4} "/" <digit>{2} "/" <digit>{2}
    | <digit>{4} "." <digit>{2} "." <digit>{2}

# A time amount is a number of hours and minutes separated with a colon.
# A time range is two times separated with a dash.  The first time in
# the range may be omitted.  To distinguish a time from a word, the time
# must be followed by non-word characters.
<time> ::=
    | <time-full>
    | <time-range-part>
<time-full> ::=
    | <time-amount>
    | <time-range-full>
<time-amount> ::=
    <digit>+ ":" <digit>{2} ?=<non-word>
<time-range-full> ::=
    (
    | <digit>{2} ":" <digit>{2} "-" <digit>{2} ":" <digit>{2}
    | <digit>{4} "-" <digit>{4}
    ) ?=<non-word>
<time-range-part> ::=
    (
    | "-" <digit>{2} ":" <digit>{2}
    | "-" <digit>{4}
    ) ?=<non-word>

# A label is a dash followed by a non-digit, identifier character,
# followed by other, non-whitespace characters.  To distinguish a label
# from a word, the label must be followed by non-word characters.
<label> ::=
    "-" ["a" - "z" | "A" - "Z" | "_"] (!<whitespace>)* ":" ?=<non-word>
```


### Structure ###

An basic, unstructured view of the input is as a stream of fields
separated by space.

```
<space> ::=
    (<whitespace> | <newline>)+

# A description is a non-empty sequence of words with comments possibly
# interspersed
<description> ::=
    <word> (<space> <comment>)?
    (<space> <word> (<space> <comment>)?)*

# The fields in a record
<field> ::=
    <date> | <time> | <label> | <description>

<input> ::=
    (<whitespace> | <newline>)*
    (
    (<field> | <comment>)
    ((<whitespace> | <newline>)+ (<field> | <comment>))*
    (<whitespace> | <newline>)*
    )?
```

However, structuring the input into records is a much more informative
(if complicated) view.

```
<sep> ::=
    (<space> | <comment>)+

<record> <date-label-context> ::=
    | <date> <sep> <time-full> <sep> <label> (<sep> <description>)? <sep>?
    | <date-label-context> <time> <sep> <label> (<sep> <description>)? <sep>?
    | <date-label-context> <time> (<sep> <description>)? <sep>?

<unused-date> ::=
    <date> <sep>?

<unused-label> ::=
    <label> <sep>?

<unused> ::=
    | <unused-date>
    | <unused-label>



<comment-block> ::=
    (<space>? <comment> <newline>)+




<record-group> ::=
    (<comment> <newline>)* (<record>+ <context> | 





<context> ::=
    | <unused>
    | <date-context>
    | <date-label>



<file> ::=
    <sep>?
    (
    <record-group>
    (<sep> <record-group>)*
    <sep>?
    )?

<record-group> ::=
    <record>* <context> <record-group-terminator>

<record-group-terminator> ::=
    | <lone-dot>
    | <newline>{$terminating_n_newlines,}
    | <eof>

"""

# Parsing derivation for working out what grammar should be
#
# -----
# # Comment
# 2020-06-26:
# 0900-0930 -lbl1: desc1
# -1000 -lbl2: desc2
# -1100 -lbl1: desc3
# -----
#
# Tokens:
# <comment txt="# Comment" line="1" col="1" />
# <newline txt="\n" line="1" col="10" />
# <date txt="2020-06-26:" line="2" col="1" year="2020" month="06" day="26" />
# <newline txt="\n" line="2" col="12" />
# etc.
#
# Bottom-up derivation of parse tree:
#
# <com-1> <nl-1>
# <date-1> <nl-2>
# <time-1> <ws-1> <lbl-1> <ws-2> <word-1> <nl-3>
# <time-2> <ws-3> <lbl-2> <ws-4> <word-2> <nl-4>
# <time-3> <ws-5> <lbl-3> <ws-6> <word-3> <nl-5>
# <eof-1>
#
# <sep-1> = (<com-1> <nl-1>)
# <date-1> <nl-2>
# <time-1> <ws-1> <lbl-1> <ws-2> <word-1> <nl-3>
# <time-2> <ws-3> <lbl-2> <ws-4> <word-2> <nl-4>
# <time-3> <ws-5> <lbl-3> <ws-6> <word-3> <nl-5>
# <eof-1>
#
# <sep-1>
# <dt-tm-1> = (<date-1> <nl-2> <time-1> <ws-1>)
# <lbl-1> <ws-2> <word-1> <nl-3>
# <time-2> <ws-3> <lbl-2> <ws-4> <word-2> <nl-4>
# <time-3> <ws-5> <lbl-3> <ws-6> <word-3> <nl-5>
# <eof-1>
#
# <sep-1>
# <dt-lbl-tm-1> = (<dt-tm-1> <lbl-1> <ws-2>)
# <word-1> <nl-3>
# <time-2> <ws-3> <lbl-2> <ws-4> <word-2> <nl-4>
# <time-3> <ws-5> <lbl-3> <ws-6> <word-3> <nl-5>
# <eof-1>
#
# <sep-1>
# (<rec-1> <dt-lbl-1>) = (<dt-lbl-tm-1> <word-1> <nl-3>)
# <time-2> <ws-3> <lbl-2> <ws-4> <word-2> <nl-4>
# <time-3> <ws-5> <lbl-3> <ws-6> <word-3> <nl-5>
# <eof-1>
#
# <sep-1> <rec-1>
# <dt-lbl-tm-2> = (<dt-lbl-1> <time-2> <ws-3>)
# <lbl-2> <ws-4> <word-2> <nl-4>
# <time-3> <ws-5> <lbl-3> <ws-6> <word-3> <nl-5>
# <eof-1>
#
# <sep-1> <rec-1>
# <dt-lbl-tm-3> = (<dt-lbl-tm-2> <lbl-2> <ws-4>)
# <word-2> <nl-4>
# <time-3> <ws-5> <lbl-3> <ws-6> <word-3> <nl-5>
# <eof-1>
#
# <sep-1> <rec-1>
# (<rec-2> <dt-lbl-2>) = (<dt-lbl-tm-3> <word-2> <nl-4>)
# <time-3> <ws-5> <lbl-3> <ws-6> <word-3> <nl-5>
# <eof-1>
#
# <sep-1> <rec-1> <rec-2>
# <dt-lbl-tm-4> = (<dt-lbl-2> <time-3> <ws-5>)
# <lbl-3> <ws-6> <word-3> <nl-5>
# <eof-1>
#
# <sep-1> <rec-1> <rec-2>
# <dt-lbl-tm-5> = (<dt-lbl-tm-4> <lbl-3> <ws-6>)
# <word-3> <nl-5>
# <eof-1>
#
# <sep-1> <rec-1> <rec-2>
# (<rec-3> <dt-lbl-3>) = (<dt-lbl-tm-5> <word-3> <nl-5>)
# <eof-1>
#
# <sep-1> <rec-1> <rec-2> <rec-3>
# <rec-end> = (<dt-lbl-3> <eof-1>)
#
# <sep-1>
# <rec-grp> = (<rec-1> <rec-2> <rec-3> <rec-end>)
#
# <file-1> = (<sep-1> <rec-grp>)


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
            pieces.append(f' in {self.filename!r}')
        if self.line is not None:
            pieces.append(f' at line {self.line}')
        if self.column is not None:
            pieces.append(' at' if self.line is None else ',')
            pieces.append(f' column {self.column}')
        if self.message is not None:
            pieces.append(': ')
            pieces.append(self.message)
        if self.text is not None:
            pieces.append(': ')
            pieces.append(f'{self.text!r}')
        return ''.join(pieces)


# Tokens


class Token:

    def __eq__(self, other):
        return self.__dict__ == other.__dict__

    def __hash__(self):
        return hash(self.__dict__)

    @classmethod
    def from_match(cls, match, filename, line, column):
        return cls(match.group(1))

    @classmethod
    def tokenizer_pair(cls):
        return cls.pattern, cls.from_match


class Date(Token):

    pattern = re.compile(r'(\d{4})?([-/.])(\d{2})?\2(\d{2}):(?=\s|\Z)')

    def __init__(self, year=None, month=None, day=None, sep=None):
        self._year = year
        self._month = month
        self._day = day
        self._sep = sep

    def __repr__(self):
        return (f'Date({self._year!r}, {self._month!r}, '
                f'{self._day!r}, {self._sep!r})')

    @staticmethod
    def from_match(match, filename, line, column):
        return Date(*match.group(1, 3, 4, 2))


class TimeAmount(Token):

    pattern = re.compile(r'(\d+):(\d{2})(?=\s|\Z)')

    def __init__(self, hours=None, minutes=None):
        self._hours = hours
        self._minutes = minutes

    def __repr__(self):
        return f'TimeAmount({self._hours!r}, {self._minutes!r})'

    @staticmethod
    def from_match(match, filename, line, column):
        return TimeAmount(*match.group(1, 2))


class TimeRange(Token):

    pattern = re.compile(
        r'(?:(\d{2})(:?)(\d{2}))?-(\d{2})((?(2)\2|:?))(\d{2})'
        r'(?=\s|\Z)')

    def __init__(self, beg=None, end=None, sep=None):
        self._beg = beg if beg != (None, None) else None
        self._end = end
        self._sep = sep

    def __repr__(self):
        return (f'TimeRange({self._beg!r}, {self._end!r}, '
                f'{self._sep!r})')

    @staticmethod
    def from_match(match, filename, line, column):
        return TimeRange(match.group(1, 3), match.group(4, 6),
                         match.group(5))


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

    pattern = re.compile(r'-([a-zA-Z_]\w*):(?=\s|\Z)')

    def __init__(self, name):
        self._name = name

    def __repr__(self):
        return f'Label({self._name!r})'


class Whitespace(Token):

    # Any sequence of Unicode whitespace characters that are not newlines
    pattern = re.compile(
        '(['
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
        ']+)'
    )

    def __init__(self, text):
        self._text = text

    def __repr__(self):
        return f'Whitespace({self._text!r})'


class Newline(Token):

    # Newlines as pairs or individual characters.  DOS, Acorn, Unix,
    # Mac, vertical tab, form feed, line separator, paragraph separator,
    # next line (NEL)
    pattern = re.compile('(\r\n|\n\r|[\n\r\v\f\u2028\u2029\u0085])')

    def __init__(self, text):
        self._text = text

    def __repr__(self):
        return f'Newline({self._text!r})'


class Comment(Token):

    pattern = re.compile(r'(#[^\n\r\v\f\u2028\u2029\u0085]*)')

    def __init__(self, text):
        self._text = text

    def __repr__(self):
        return f'Comment({self._text!r})'


class Word(Token):

    # Any sequence of non-whitespace possibly followed by more
    # non-whitespace and non-breaking spaces
    pattern = re.compile(r'\S[\S\u00a0\u2007\u202f]*')

    def __init__(self, text):
        self._text = text

    def __repr__(self):
        return f'Word({self._text!r})'

    @staticmethod
    def from_match(match, filename, line, column):
        return Word(match.group(0))

    @staticmethod
    def match(text, filename, line, column):
        match = Word.pattern.match(text)
        if match is None:
            raise ParseError(filename, line, column, text, 'Not a word')
        return (Word.from_match(match, filename, line, column),
                match.end() - match.start())


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


_tokenizer = LineTokenizer(
    Date.tokenizer_pair(),
    TimeAmount.tokenizer_pair(),
    TimeRange.tokenizer_pair(),
    Label.tokenizer_pair(),
    Comment.tokenizer_pair(),
    Whitespace.tokenizer_pair(),
    Newline.tokenizer_pair(),
    no_match=Word.match,
)


def tokens(file, filename=None):
    return _tokenizer.tokens(file, filename)


# Parsing

# See the library documentation for a description of the timesheet
# format.  The main idea is that flexibility in writing the time entries
# can be achieved by accumulating fields until a complete record has
# been assembled, filling in from previous records as needed / directed.
# Thus, parsing is mainly about accumulating fields until a complete
# record can be emitted.  A record is complete if it has a time range or
# amount, because the date can default to the current date and the label
# and description can be empty.  However, fields on the same line
# override fields on previous lines, so the rest of the line must be
# read before emitting a record.  Within a line, a record can be emitted
# as soon as it has all of its fields.

# For now, only do specific descriptions.  That is, descriptions do not
# copy forward.  They can get used only once.  Newlines only matter for
# descriptions.  All that is needed for a complete record is a time
# range or amount; the date defaults to the current date and the label
# and description are empty.

# TODO warn about all discarded information (except comments and whitespace)
# TODO? trailing commas / semicolons on elements
# TODO? descriptions unique unless specified -> syntax for copying descriptions, syntax for desription at a higher level, perhaps that applies to groups of records?

# Grammar:
#
# <file> := <sep>? (<record> (<sep> <record>)* <sep>?)?
# <sep> := (<space> | <newline> | <comment> <newline>)+
# <space> := [see Whitespace.pattern]
# <comment> := [see Comment.pattern]
# <newline> := [see Newline.pattern]
# <record> := (<date> <sep>)? <time> (<sep> <label>)? (<sep> <desc>)?
# <date> := [see Date.pattern]
# <time> := <time-amount> | <time-range-full> | <time-range-partial>
# <label> := [see Label.pattern]
# <desc> := <word> (<sep> <word>)*


# Deterministic finite automaton for parsing the timesheet format
#
# Token types: space, newline, comment, date, time_amount, time_range,
#   label, word, eof
#
# States: start, date, time, label, open_desc, date_time, date_label,
#   date_desc, time_label, time_desc, label_desc, date_time_label,
#   date_time_desc, date_label_desc, time_label_desc,
#   date_time_label_desc, error, end
#
# The DFA is encoded in the following mapping of (state, token)
# pairs to (action, new state) pairs.  Thus, the DFA is a LL(1) parser.
# The starting state is "start".
#
# -- Any token is acceptable from the start state
# start, {space, newline, comment} -> discard token; start
# start, date -> make new record, add date; date
# start, {time_amount, time_range} -> make new record, add time; time
# start, label -> make new record, add label; label
# start, word -> make new record, add word to description; open_desc
# start, eof -> ; end
#
# date, {space, comment, newline} -> discard token; date
#!date, date -> warn & discard partial record, add date to new record; date
# date, {time_amount, time_range} -> add time; date_time
# date, label -> add label; date_label
# date, word -> add word to description; date_open_desc
#!date, eof -> warn & discard partial record; end
#
# time, {space, comment, newline} -> discard token; time
# time, date -> add time; date_time
#!time, {time_amount, time_range} -> emit record, add time to new record; time
# time, label -> add label; time_label
# time, word -> add word to description; time_open_desc
# time, eof -> emit record; end
#
# label, {space, comment, newline} -> discard token; label
# label, date -> add date; date_label
# label, {time_amount, time_range} -> add time; time_label
#!label, label -> warn & discard partial record, add label to new record; label
# label, word -> add word to description; label_open_desc
#!label, eof -> warn & discard partial record; end
#
# open_desc, {space, newline} -> add token to description; open_desc
# open_desc, comment -> discard token; open_desc
# open_desc, date -> close description, add date; date_desc
# open_desc, {time_amount, time_range} -> close description, add time; time_desc
# open_desc, label -> close description, add label; label_desc
# open_desc, word -> add word to description; open_desc
#!open_desc, eof -> warn & discard partial record; end
# -- When a description is closed, trailing space and newlines are discarded
#
# date_time, {space, comment, newline} -> discard token; date_time
# date_time, date -> emit record, add date to new record; date
# date_time, {time_amount, time_range} -> emit record, add time to new record; time
# date_time, label -> add label; date_time_label
# date_time, word -> add word to description; date_time_open_desc
# date_time, eof -> emit record; end
#
# date_label
#
# date_open_desc
#
# time
#
# time_label
#
# time_open_desc
#
# date_label
#
# label_open_desc


class AbstractRecord:
    pass


#def parse(tokens):
#    record = AbstractRecord()
#    for token in tokens:
#        if isinstance(token, Whitespace):
#            # Discard whitespace unless it is part of a description
#            if record.open_description():
#                record.add_to_description(token):
#        elif isinstance(token, Word):
#            if record.open_description():
#                record.add_to_description(token)
#            else:
#                raise ParseError()
#        elif isinstance(token, Newline):

class Parser:
    pass






class Record:

    def __init__(
            self,
            date,
            time_start=None,
            time_end=None,
            time_amount=None,
            label=None,
            description=None,
    ):
        if (time_start is None and
            time_end is None and
            time_amount is None):
            raise ValueError()
        elif (time_start is None) != (time_end is None):
            raise ValueError()
        self._date = date
        self._beg = time_start
        self._end = time_end
        self._amt = time_amount
        self._lbl = label
        self._desc = description


def records(tokens):
    pass


def read(file, filename=None):
    return records(tokens(file, filename))
