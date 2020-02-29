"""Tests timesheet library."""


import string
import unittest

from .. import timesheet


class TokenTest(unittest.TestCase):

    def test_empty(self):
        pass

    def test_date_full(self):
        text = '950-08-10:'

    def test_date_no_year(self):
        text = '-06-20:'

    def test_date_no_month(self):
        text = '--15:'

    def test_time_amount(self):
        text = '123:45'

    def test_time_range_full(self):
        text = '8795-7428'

    def test_time_range_no_start(self):
        text = '-6251'

    def test_label(self):
        text = 'a:'

    def test_whitespace(self):
        string.whitespace # ASCII whitespace

    def test_description(self):
        pass

    def test_description_all_ascii(self):
        ascii = string.digits + string.ascii_letters + string.punctuation
        text = ' '.join(c for c in ascii if c != '\\')

    def test_escape(self):
        pass


class FillInDataTest(unittest.TestCase):
    pass


# colon options:
# 1. label: \desc: desc\:
# 2. label:: desc:


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
