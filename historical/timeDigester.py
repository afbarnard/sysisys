#!/usr/bin/python
# Program to process my time sheet data

import csv
import datetime
import re
import sys

# Time entry
class TimeEntry(object):
    def __init__(self, date, label="default", startTime=None, endTime=None, amount=None, description=None):
        self.date = date
        self.label = label if label is not None else "default"
        self.startTime = startTime
        self.endTime = endTime
        self.amount = amount
        self.description = description

    # Appends the given text to the existing description inserting whitespace as needed
    def appendDescription(self, text):
        if self.description is None:
            self.description = text
        else:
            self.description += " " + text

    # Create a printable representation
    def __str__(self):
        fieldStrings = (str(self.date), str(self.label), str(self.startTime), str(self.endTime), str(self.amount), repr(self.description))
        return "TimeEntry(%s, %s, %s, %s, %s, %s)" % fieldStrings

    # Redirect repr to use str
    def __repr__(self):
        return str(self)

# Parse Exception
class ParseException(Exception):
    def __init__(self, type, message, token=None):
        self.type = type
        self.message = message
        self.token = token

    def __str__(self):
        if self.token is None:
            return "%s:\n%s" % (self.type, self.message)
        else:
            return "%s at line %i, token %i ('%s'):\n%s" % (self.type, self.token.lineNumber, self.token.tokenNumber, self.token.text, self.message)

# A date node in an AST
class ASTDate(object):
    def __init__(self, year, month, day, token):
        self.year = int(year)
        self.month = int(month)
        self.day = int(day)
        self.date = datetime.date(self.year, self.month, self.day)
        self.token = token

    def __repr__(self):
        return "date"

# A label node in an AST
class ASTLabel(object):
    def __init__(self, label, token):
        self.label = label
        self.token = token

    def __repr__(self):
        return "label"

# A time interval node in an AST
class ASTTimeInterval(object):
    def __init__(self, start, end, token):
        # Save the parsed tokens
        self.start = start
        self.end = end
        self.token = token

        # Create start and end times from the hours and minutes in the strings
        self.startTime = datetime.time(int(start[:2]), int(start[2:]))
        self.endTime = datetime.time(int(end[:2]), int(end[2:]))
        # Create the time delta represented by the interval
        self.timeAmount = datetime.timedelta(hours=(self.endTime.hour - self.startTime.hour),
                                             minutes=(self.endTime.minute - self.startTime.minute))
        # Correct amount if negative
        if self.timeAmount < datetime.timedelta(0):
            # Add one day
            self.timeAmount = self.timeAmount + datetime.timedelta(days=1)

    def __repr__(self):
        return "timeInterval"

# A time amount node in an AST
class ASTTimeAmount(object):
    def __init__(self, hours, minutes, token):
        self.hours = int(hours)
        self.minutes = int(minutes)
        self.token = token
        self.timeAmount = datetime.timedelta(hours=self.hours, minutes=self.minutes)

    def __repr__(self):
        return "timeAmount"

# A description node in an AST
class ASTDescription(object):
    def __init__(self, text, token):
        self.text = text
        self.tokens = [token]

    def __repr__(self):
        return "description"

    # Appends the text of another AST object to this description
    def append(self, anotherObject):
        if isinstance(anotherObject, ASTDescription):
            self.text += " " + anotherObject.text
            self.tokens.extend(anotherObject.tokens)
        else:
            self.text += " " + anotherObject.token.text
            self.tokens.append(anotherObject.token)

# A comment node in an AST
class ASTComment(ASTDescription):
    def __repr__(self):
        return "comment"

# A whitespace node in an AST
class ASTWhitespace(object):
    def __init__(self):
        pass

    def __repr__(self):
        return "whitespace"

# A token in the input
class Token(object):
    def __init__(self, text, lineNumber, tokenNumber):
        self.text = text
        self.lineNumber = lineNumber
        self.tokenNumber = tokenNumber

# Parser for the time data
class Parser(object):
    def __init__(self):
        self.splitPattern = re.compile("\\s+")
        self.commentPattern = re.compile("#.*")
        self.datePattern = re.compile("(\\d{4})?-(\\d{2})?-(\\d{2}):")
        self.labelPattern = re.compile("([a-zA-Z][\\w-]*):")
        self.intervalPattern = re.compile("(\\d{4})?-(\\d{4}),?")
        self.amountPattern = re.compile("(\\d+):(\\d{2}),?")
        # For a description there must be a word character somewhere.
        # This includes common constructions like dollar amounts and quotations,
        # but eliminates likely errors, I hope.
        # Don't allow the description to look like a comment (no leading #).
        self.descriptionPattern = re.compile("[^#]*\\w.*")
        # The following are listed in rough order of expected frequency
        # However, parseDescription must follow all of the more specific token types
        self.parsingFunctions = [self.parseTimeInterval, self.parseLabel, self.parseDate, self.parseTimeAmount, self.parseComment, self.parseDescription, self.parseWhitespace]
        self.lastDate = None
        self.lastTimeIntervalEnd = None

    # Function to parse the input file
    def parse(self, timeFile):
        return self.combineNodes(self.makeBasicAST(timeFile))

    # Makes the basic AST
    def makeBasicAST(self, timeFile):
        # Create the AST (which is just a list of lines)
        ast = list()

        # Keep track of the lines for error reporting purposes
        lineCount = 0

        # Iterate over the lines in the file
        for line in timeFile:
            # Increment the line count (1-based line numbers)
            lineCount += 1

            # Tokenize the line
            lineTokens = self.splitPattern.split(line.strip())

            # Parse the new line of tokens
            parsedTokens = list()
            ast.append(parsedTokens)
            tokenCount = 1
            for token in lineTokens:
                # Create a token object
                tokenObj = Token(token, lineCount, tokenCount)

                # Process the token
                for function in self.parsingFunctions:
                    object = function(token, tokenObj)
                    if object is not None:
                        parsedTokens.append(object)
                        break

                # See if a parse error occurred
                if object is None:
                    raise ParseException("Syntax error", "What the hell is this supposed to mean?: '%s'" % token, tokenObj)

                # Increment the token count for the next token
                tokenCount += 1

        # Return the data structure obtained from the parsing
        return ast

    # Parses a date from the input
    def parseDate(self, token, tokenObj):
        # Check if the token is a date
        matched = self.datePattern.match(token)
        if matched is not None:
            # Get the matched data
            year = matched.group(1)
            month = matched.group(2)

            # Check for a fully-specified date
            if (year is None or month is None) and self.lastDate is None:
                raise ParseException("Syntax error", "The first date in the file must be fully specified.", tokenObj)

            # Fill in data
            if year is None:
                year = self.lastDate.year
            if month is None:
                month = self.lastDate.month

            # Create a date from the data
            date = ASTDate(year, month, matched.group(3), tokenObj)

            # Since this is a new date, clear the last time interval end
            self.lastTimeIntervalEnd = None
            # Save and return the date
            self.lastDate = date
            return date
        else:
            return None

    # Parses a label from the input
    def parseLabel(self, token, tokenObj):
        # Check that the token is a label
        matched = self.labelPattern.match(token)
        if matched is not None:
            return ASTLabel(matched.group(1), tokenObj)
        else:
            return None

    # Parses a time interval from the input
    def parseTimeInterval(self, token, tokenObj):
        # Check that the token is a time interval
        matched = self.intervalPattern.match(token)
        if matched is not None:
            # Get the matched data
            start = matched.group(1)
            end = matched.group(2)

            # Check if the time interval is specified enough
            if start is None and self.lastTimeIntervalEnd is None:
                raise ParseException("Syntax error", "The first time interval for a date must have a start time.", tokenObj)

            # Fill in data
            if start is None:
                start = self.lastTimeIntervalEnd

            # Create a time interval from the matched data
            timeInterval = ASTTimeInterval(start, end, tokenObj)

            # Save and return the time interval
            self.lastTimeIntervalEnd = end
            return timeInterval
        else:
            return None

    # Parses a time amount from the input
    def parseTimeAmount(self, token, tokenObj):
        # Check that the token is a time amount
        matched = self.amountPattern.match(token)
        if matched is not None:
            return ASTTimeAmount(matched.group(1), matched.group(2), tokenObj)
        else:
            return None

    # Parses a description
    def parseDescription(self, token, tokenObj):
        # Check that the token is part of a description
        matched = self.descriptionPattern.match(token)
        if matched is not None:
            return ASTDescription(token, tokenObj)
        else:
            return None

    # Parses a comment
    def parseComment(self, token, tokenObj):
        # Check that tht token is the start of a comment
        matched = self.commentPattern.match(token)
        if matched is not None:
            return ASTComment(token, tokenObj)
        else:
            return None

    # Parses significant whitespace
    def parseWhitespace(self, token, tokenObj):
        # Check if this token is empty
        if token == "":
            return ASTWhitespace()
        else:
            return None

    # Combines basic AST nodes into semantic units
    def combineNodes(self, ast):
        # Iterate over each line in the AST
        for line in ast:
            # Combine the like nodes in this line
            # Only do this if there are at least two objects
            if len(line) < 2:
                continue

            # Loop over the line combining adjacent and like objects (descriptions and comments)
            objectIndex = 0
            currentCombinable = None
            while objectIndex < len(line):
                # If this is a comment, consume the rest of the line
                if isinstance(line[objectIndex], ASTComment):
                    currentCombinable = line[objectIndex]
                    objectIndex += 1
                    while objectIndex < len(line):
                        currentCombinable.append(line[objectIndex])
                        del line[objectIndex]
                # If this is a description, prepare to append adjacent descriptions
                elif isinstance(line[objectIndex], ASTDescription):
                    # If no current description, set this as current
                    # Otherwise, append this description to the current one
                    if currentCombinable is None:
                        currentCombinable = line[objectIndex]
                        objectIndex += 1
                    else:
                        currentCombinable.append(line[objectIndex])
                        del line[objectIndex]
                # Otherwise, just skip
                else:
                    currentCombinable = None
                    objectIndex += 1

        return ast

# Groups the data necessary to make a time entry
class DataGroup(object):
    # Initializes this data group
    def __init__(self):
        self.clear()

    # Clears the data from this group
    def clear(self):
        self.date = None
        self.label = None
        self.time = None
        self.desc = None

    # Whether this group has a date
    def hasDate(self):
        return self.date is not None

    # Whether this group has a label
    def hasLabel(self):
        return self.label is not None

    # Whether this group has a time
    def hasTime(self):
        return self.time is not None

    # Whether this group has a description
    def hasDescription(self):
        return self.desc is not None

    # Fills in missing data in this group using data from the given group
    def fillIn(self, anotherGroup):
        if self.date is None:
            self.date = anotherGroup.date
        if self.label is None:
            self.label = anotherGroup.label
        if self.time is None:
            self.time = anotherGroup.time
        if self.desc is None:
            self.desc = anotherGroup.desc

    # Copies another groups data to this group
    def copy(self, anotherGroup):
        self.date = anotherGroup.date
        self.label = anotherGroup.label
        self.time = anotherGroup.time
        self.desc = anotherGroup.desc

    # Overlays data in this group using data from the given group.
    # Only copies data from the given group if it is meaningful
    def overlay(self, anotherGroup):
        if anotherGroup.date is not None:
            self.date = anotherGroup.date
        if anotherGroup.label is not None:
            self.label = anotherGroup.label
        if anotherGroup.time is not None:
            self.time = anotherGroup.time
        if anotherGroup.desc is not None:
            self.desc = anotherGroup.desc

    # Whether this group is a complete group of data
    def isComplete(self):
        return (self.date is not None) and (self.label is not None) and (self.time is not None) and (self.desc is not None)

    # Whether this group contains data
    def hasData(self):
        return (self.date is not None) or (self.label is not None) or (self.time is not None) or (self.desc is not None)

    def __str__(self):
        return "DataGroup(%s, %s, %s, '%s')" % (self.date, self.label, self.time, self.desc)

# Implements the semantics of the AST by converting it to time data
def convertASTToTimeData(ast):
    # Dates apply to all data that follows until next date.
    # Group: label + interval + desc: use the information in the group
    # Group: interval + desc: use previous label
    # Group: interval + label: use label, no desc
    # Group: label + desc: use on following intervals, clear on next label or desc
    # Groups do not span lines

    # Initialize data
    timeData = list()
    lastData = DataGroup()
    currentData = DataGroup()

    # Loop over the AST to build the time data entries
    for line in ast:
        # Use to see if entries were added during a line
        timeEntryCountAtLineStart = len(timeData)

        # Process the tokens for this line
        for token in line:
            # Skip comments, whitespace
            if isinstance(token, (ASTComment, ASTWhitespace)):
                continue
            # Start a new day
            elif isinstance(token, ASTDate):
                lastData.date = token.date
            # Add a label
            elif isinstance(token, ASTLabel):
                # Check for complete group
                if currentData.hasLabel():
                    timeData.append(makeTimeEntry(lastData, currentData))
                # Add the label to the current data
                currentData.label = token.label
                # Clear any saved description
                lastData.desc = None
            # Add a time interval or amount
            elif isinstance(token, (ASTTimeInterval, ASTTimeAmount)):
                # Check for a complete group
                if currentData.hasTime():
                    timeData.append(makeTimeEntry(lastData, currentData))
                # Add the time to the current data
                currentData.time = token
            # Add a description
            elif isinstance(token, ASTDescription):
                # Check for a complete group
                if currentData.hasDescription():
                    timeData.append(makeTimeEntry(lastData, currentData))
                # Add the description to the current data
                currentData.desc = token.text
                # Clear any saved description
                lastData.desc = None

        # Since this is the end of the line, complete any leftover group as appropriate (if any)
        if currentData.hasData():
            # If the leftover data contains a time, then create a time entry
            # Otherwise, see if the data is a "label header"
            if currentData.hasTime():
                timeData.append(makeTimeEntry(lastData, currentData))
            else:
                # If this is a "label header", save the values
                if currentData.hasLabel() and timeEntryCountAtLineStart == len(timeData):
                    lastData.overlay(currentData)
                elif currentData.hasLabel() and currentData.hasDescription():
                    label = None
                    desc = None
                    if isinstance(line[-2], ASTLabel):
                        label = line[-2]
                        desc = line[-1]
                    else:
                        label = line[-1]
                        desc = line[-2]
                    raise ParseException("Syntax error", "Extraneous label and description: '%s'" % desc.text, label.token)
                elif currentData.hasLabel():
                    raise ParseException("Syntax error", "Extraneous label.", line[-1].token)
                elif currentData.hasDescription():
                    raise ParseException("Syntax error", "Extraneous description: '%s'" % line[-1].text, line[-1].tokens[0])
                else:
                    raise ParseException("Syntax error", "Something crazy happened at the end of the line.", line[-1].token)

            # Regardless of anything, clear the current data since groups cannot span lines
            currentData.clear()

    return timeData

# Makes a time entry from groups of parsed data
def makeTimeEntry(previousDataGroup, currentDataGroup):
    #print "previousData:", previousDataGroup
    #print "currentData:", currentDataGroup
    # Fill in values from the previous data
    currentDataGroup.fillIn(previousDataGroup)

    # Remove any trailing comma from the description
    if currentDataGroup.desc is not None and currentDataGroup.desc.endswith(","):
        currentDataGroup.desc = currentDataGroup.desc[0:-1]

    # Create the time entry
    timeEntry = None
    if isinstance(currentDataGroup.time, ASTTimeInterval):
        timeEntry = TimeEntry(currentDataGroup.date,
                              currentDataGroup.label,
                              currentDataGroup.time.startTime,
                              currentDataGroup.time.endTime,
                              currentDataGroup.time.timeAmount,
                              currentDataGroup.desc)
    else:
        timeEntry = TimeEntry(currentDataGroup.date,
                              currentDataGroup.label,
                              amount=currentDataGroup.time.timeAmount,
                              description=currentDataGroup.desc)
    #print timeEntry

    # Make the current data the previous data (but don't copy any description)
    currentDataGroup.desc = None
    previousDataGroup.overlay(currentDataGroup)
    # Clear the current data
    currentDataGroup.clear()

    # Return the new entry
    return timeEntry

# Sums the time amounts in a list of time entries
def sumTimeAmounts(timeEntries):
    # Start the sum at zero
    sum = datetime.timedelta(0)

    # Sum all the time amounts
    for timeEntry in timeEntries:
        sum += timeEntry.amount

    # Return the sum
    return sum

# Sums the time amounts in a dictionary of partitioned time entries
def sumPartitionedTimeAmounts(timeDataByKey):
    # Start the sum at zero
    sum = datetime.timedelta(0)

    # Sum all the time amounts
    for key in timeDataByKey.keys():
        for timeEntry in timeDataByKey[key]:
            sum += timeEntry.amount

    # Return the sum
    return sum

# Partitions the given entries by a key
# getKey is a function that returns the key for a given entry
def partition(timeEntries, getKey):
    # Create a dictionary to map keys to entries
    partitionedEntries = dict()

    # Put the entries into buckets by their key
    for entry in timeEntries:
        key = getKey(entry)

        if key in partitionedEntries:
            partitionedEntries[key].append(entry)
        else:
            bucket = list()
            bucket.append(entry)
            partitionedEntries[key] = bucket

    # Return the partitioned entries
    return partitionedEntries

# Function to return the label of a time entry
def getLabel(timeEntry):
    return timeEntry.label

# Function to return the week of a time entry
def getWeek(timeEntry):
    return timeEntry.date - datetime.timedelta(timeEntry.date.weekday())

# Function to return the day of a time entry
def getDay(timeEntry):
    return timeEntry.date

# Function to return the month of a time entry
def getMonth(timeEntry):
    return datetime.date(timeEntry.date.year, timeEntry.date.month, 1)

# Function to return a constant so that everything gets partitioned into one partition
def getDummyKey(timeEntry):
    return 314159

# Function to return a time delta in hh:mm format
def hoursMinutes(timedelta):
    hours = timedelta.seconds / 3600
    hours += timedelta.days * 24
    minutes = (timedelta.seconds % 3600) / 60
    return "%i:%02i" % (hours, minutes)

# Function to print a summary of the given time data
def printSummary(timeDataByKey, header):
    print header
    for key in sorted(timeDataByKey.keys()):
        print "  %s:" % key, hoursMinutes(sumTimeAmounts(timeDataByKey[key]))
    totalTime = sumPartitionedTimeAmounts(timeDataByKey)
    print "Total time:", hoursMinutes(totalTime),
    # Print the number of days if the time is more than one day
    if totalTime.days >= 1:
        print "(%s)" % totalTime
    else:
        print

# Function to print time information split by key and aggregated by key
def printReport(timeData, getSplitKey, getAggregateKey):
    # Print the totals for each partition of the data
    entriesByKey = partition(timeData, getSplitKey)
    for key in sorted(entriesByKey.keys()):
        printSummary(partition(entriesByKey[key], getAggregateKey), "Totals for %s:" % key)
        print

    # Print the overall totals for the data
    printSummary(partition(timeData, getAggregateKey), "Overall totals:")

# Function to do a time report
def timeReport(timeData, reportControl):
    # Break up the data according to the first part of the report control
    partitionedEntries = partition(timeData, reportControl[0])
    # Get the most recent data
    mostRecentData = partitionedEntries[sorted(partitionedEntries.keys())[-1]]
    # Print the report
    printReport(mostRecentData, reportControl[1], getLabel)

# Function to write out the time data in CSV format
def writeCSV(timeData, output):
    writer = csv.writer(output)
    for timeEntry in timeData:
        fields = [timeEntry.date, timeEntry.label, timeEntry.startTime, timeEntry.endTime, timeEntry.amount, timeEntry.description]
        fields = map(lambda x: x if x is not None else '', fields)
        writer.writerow(fields)


########################################
# Main
########################################

# Future features:
# search descriptions with regexes, including for empty descriptions ('^$')
# some way to reuse descriptions, perhaps a ditto notation
# better specifying of time intervals on the command line
# including/excluding categories?
# report formats including dump, CSV
# allow specification of exact date range
# - make aliases for common date ranges
# - aliases relative to most recent date in file
# two aspects to output:
# - what data to report on ('select')
# - what report to show
# ignore syntax error on last line of file?

# Check for the correct arguments
if len(sys.argv) < 2 or len(sys.argv) > 3:
    print "Error: Incorrect command line arguments."
    print "Usage: <time-file> <report>?"
    sys.exit(1)

# Open the file
timeFile = open(sys.argv[1], "r")

# Parse the file
parser = Parser()
try:
    ast = parser.parse(timeFile)
    timeData = convertASTToTimeData(ast)
except ParseException, e:
    print e
    sys.exit(1)

# Close the file
timeFile.close()

# Quit if there was a problem and there is no time data
if timeData is None:
    print "Warning: No time data. Aborting."
    sys.exit(1)

# Get the report specification from the command line
if len(sys.argv) == 3:
    reportSpec = sys.argv[2]
else:
    reportSpec = "week"

# Set up the report based on the specification
if reportSpec == "week":
    print "Reporting time for the last week...\n"
    reportControl = (getWeek, getDay)
elif reportSpec == "month":
    print "Reporting time for the last month...\n"
    reportControl = (getMonth, getWeek)
elif reportSpec == "all":
    print "Reporting all time...\n"
    reportControl = (getDummyKey, getWeek)
elif reportSpec == "dump":
    print timeData
    sys.exit(0)
elif reportSpec == "csv":
    writeCSV(timeData, sys.stdout)
    sys.exit(1)
else:
    print "Error: Unrecognized report specification '%s'." % reportSpec
    print "Options: week, month, all"
    sys.exit(1)

# Do the report
timeReport(timeData, reportControl)
