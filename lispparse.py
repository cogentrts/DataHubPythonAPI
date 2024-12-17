import threading

import datetime

from enum import IntEnum

class PointQuality(IntEnum):
    """
    Enum representing various point quality states.
    """
    QUALITY_MASK = 0xC0
    STATUS_MASK = 0xFC
    LIMIT_MASK = 0x03
    BAD = 0x00
    UNCERTAIN = 0x40
    GOOD = 0xC0
    CONFIG_ERROR = 0x04
    NOT_CONNECTED = 0x08
    DEVICE_FAILURE = 0x0c
    SENSOR_FAILURE = 0x10
    LAST_KNOWN = 0x14
    COMM_FAILURE = 0x18
    OUT_OF_SERVICE = 0x1C
    LAST_USABLE = 0x44
    SENSOR_CAL = 0x50
    EGU_EXCEEDED = 0x54
    SUB_NORMAL = 0x58
    LOCAL_OVERRIDE = 0xD8
    INITIALIZING = 0x20

class PointType(IntEnum):
    """
    Enum representing various point types.
    """
    STRING = 0
    REAL = 1
    INT64 = 2
    VOID = 3

UT_ParseFlagExpressions = 1

def SlEscapeChar(inbuf, offset, outbuf, outoffset):
    """
    Escapes a character in the input buffer and writes it to the 
    output buffer.

    Arguments:
        inbuf: Input buffer.
        offset: Offset in the input buffer.
        outbuf: Output buffer.
        outoffset: Offset in the output buffer.

    Returns:
        int: Length of the escaped character.
    """
    if offset >= len(inbuf):
        return -1
    
    ch = inbuf[offset]
    outch = ch
    len = 1
    if ch == 'n':
        outch = '\n'
    elif ch == 'r':
        outch = '\r'
    elif ch == 't':
        outch = '\t'
    elif ch == 'f':
        outch = '\f'
    elif ch == '0':
        outch = '\0'
    outbuf[outoffset] = outch
    return (len)

# stops should be " \t\n()\""
def SlSkipTo(inbuf, offset, stops, maxbuf):
    """
    Skips characters in the input buffer until a stop character is found.

    Arguments:
        inbuf: Input buffer.
        offset: Starting offset in the input buffer.
        stops: String of stop characters.
        maxbuf: Maximum buffer length.

    Returns:
        int: Offset of the first stop character or None if not found.
    """
    done = False
    while not done:
        ch = inbuf[offset]
        if ch in stops:
            done = True
        elif ch == '\\':
            offset += 1
            esclen = 1 if offset < maxbuf else -1
            if esclen == -1:
                done = True
            else:
                offset += esclen
        else:
            offset += 1
            if offset >= maxbuf:
                break
    return offset if offset < maxbuf else None

# return the offset of the first stop character, or maxbuf if none found
def SlSkipFast(inbuf, offset, stop, maxbuf):
    """
    Skips characters in the input buffer quickly until a stop character 
    is found.

    Arguments:
        inbuf: Input buffer.
        offset: Starting offset in the input buffer.
        stop: Stop character.
        maxbuf: Maximum buffer length.

    Returns:
        int: Offset of the first stop character or maxbuf if not found.
    """
    tmppos = offset
    while tmppos != None:
        tmppos = inbuf.find(stop, tmppos)
        if tmppos >= maxbuf or tmppos == -1:
            tmppos = None
        else:
            count = 0
            while tmppos - count - 1 >= 0 and inbuf[tmppos - count - 1] == '\\':
                count += 1
            if count % 2 == 0:  # even number of backslashes preceding hit, so hit is not escaped
                break
            else:
                tmppos += 1

	# pstop points at the first character after the enclosed string, which is
	# either the stop character or the end of the buffer
    pstop = tmppos if tmppos != None else len(inbuf)
            
    return pstop

# returns the offset of the closing character
def SlSkipToClosing(buffer, offset, maxbuf, opening, closing):
    """
    Skips characters in the buffer until the closing character is found.

    Arguments:
        buffer: Input buffer.
        offset: Starting offset in the buffer.
        maxbuf: Maximum buffer length.
        opening: Opening character.
        closing: Closing character.

    Returns:
        int: Offset of the closing character or None if not found.
    """
    depth = 0
    while offset < maxbuf:
        if buffer[offset] == opening:
            depth += 1
        elif buffer[offset] == closing:
            depth -= 1
            if depth == 0:
                break
        elif buffer[offset] == '\\':
            offset += 1
        elif buffer[offset] == '"':
            offset = SlSkipFast(buffer, offset + 1, '"', maxbuf)
        offset += 1
    return offset if offset < maxbuf else None

# returns the offset of the first non-whitespace character in the buffer
def SlSkipWhite(buffer, offset, maxbuf):
    """
    Skips whitespace characters in the buffer.

    Arguments:
        buffer: Input buffer.
        offset: Starting offset in the buffer.
        maxbuf: Maximum buffer length.

    Returns:
        int: Offset of the first non-whitespace character or 
        None if not found.
    """
    while offset < maxbuf and buffer[offset] in " \t\n":
        offset += 1
    return offset if offset < maxbuf else None

# adds the offset and length of the current argument to the argument list
def addArg(arglist, inbuf, offset, length):
    """
    Adds an argument to the argument list.

    Arguments:
        arglist: List of arguments.
        inbuf: Input buffer.
        offset: Starting offset in the input buffer.
        length: Length of the argument.
    """
    arglist.append(inbuf[offset:offset + length])

# returns two items:
# 1. the offset of the first character after the expression, or None if the end of the buffer was reached
# 2. an array of strings containing the arguments
def UT_LispParseSafe(buffer, offset, buflen, flags):
    """
    Parses a LISP expression safely.

    Arguments:
        buffer: Input buffer.
        offset: Starting offset in the buffer.
        buflen: Length of the buffer.
        flags: Parsing flags.

    Returns:
        tuple: Offset of the first character after the expression and 
        an array of arguments.
    """
    islist = 0
    nargs = 0
    len = 0
    done = 0
    bufptr = offset
    maxbuf = buflen
    tptr = None
    maxargs = 0
    args = []

    bufptr = SlSkipWhite(buffer, bufptr, maxbuf)

    if bufptr == None:
        # Do nothing. NULL input.
        pass
    elif (flags & UT_ParseFlagExpressions) == 0 and buffer[bufptr] == '(':
        # If we are breaking multiple expressions then do not skip the opening bracket
        bufptr += 1
        islist = 1

    while not done:
        bufptr = SlSkipWhite(buffer, bufptr, maxbuf)
        if bufptr == None:
            break

        if buffer[bufptr] == '\"':
            bufptr += 1
            tptr = SlSkipFast(buffer, bufptr, '\"', maxbuf)
            if tptr == None:  # Ran out of characters
                tptr = maxbuf
            len = tptr - bufptr
            addArg(args, buffer, bufptr, len)
            if tptr < maxbuf:
                tptr += 1
            bufptr = tptr
        elif buffer[bufptr] == '(':
            tptr = SlSkipToClosing(buffer, bufptr, maxbuf, '(', ')')
            if tptr == None:  # Ran out of characters
                tptr = maxbuf
            else:
                tptr += 1  # accept the closing parenthesis
            len = tptr - bufptr
            addArg(args, buffer, bufptr, len)
            bufptr = tptr
        elif buffer[bufptr] == ')' and islist:
            bufptr += 1
            break
        else:
            tptr = SlSkipTo(buffer, bufptr, " \t\n()\"", maxbuf)
            if tptr == None:
                tptr = maxbuf
            len = tptr - bufptr
            if len > 0:
                addArg(args, buffer, bufptr, len)
                bufptr = tptr
            else:
                # Something went wrong. The parser is stuck on an unexpected character, like a closing parenthesis.
                done = 1
            # We have a situation where a closing parenthesis could be at the end of a string that is
            # the tail of a long list of arguments that therefore had no opening parenthesis. If that happens
            # then we would get a zero-length argument. We want to drop out without incrementing
            # nargs and capturing a spurious zero-length argument.
            if len == 0 and done == 1:
                break

        if tptr >= maxbuf:
            done = 1

    # If we have reached the end of the string, return null indicating end of input
    tptr = SlSkipWhite(buffer, bufptr, maxbuf)
    if tptr == None:
        bufptr = None

    return bufptr, args

def parse(buffer):
    """
    Parses a buffer containing LISP expressions.

    Arguments:
        buffer: Input buffer.

    Returns:
        list: List of parsed expressions.
    """
    expressions = []
    offset = 0
    buflen = len(buffer)
    while offset != None and offset < buflen:
        offset, args = UT_LispParseSafe(buffer, offset, buflen, 0)
        if args:
            expressions.append(args)
    return expressions

# Using character tables turns out to be about 25% faster than any other method I have come up with.
# The tables are all static, so we only pay the penalty of creating them once.

# Normal terminators are ones that would terminate an extended LISP token, essentially punctuation.
# In C we use these terminators:  \\ \t\r\n\'\"()[]#;`,{}
NormalTerminators = set(['\\', ' ', '\t', '\n', '\f', '\r', '\'', '\"', '(', ')', '[', ']', '#', ';', '`', ',', '{', '}', chr(0), chr(0x1b)])

# Special terminators are ones that would cause a quoted string to be misinterpreted if they were not handled.
SpecialTerminators = set(['\t', '\n', '\f', '\r', chr(0), chr(0x1b), '\\', '\"'])

BNormalTerminators = [False] * 128
BSpecialTerminators = [False] * 128
BSymbolTerminators = [False] * 128
TerminatorsConfigured = False
terminators_lock = threading.Lock()

def initialize_terminators():
    """
    Initializes the terminator tables.
    """  
    global TerminatorsConfigured

    if not TerminatorsConfigured:
        with terminators_lock:
            # Check to see if another thread configured these while we were held in the lock
            if not TerminatorsConfigured:
                TerminatorsConfigured = True
                for c in NormalTerminators:
                    BNormalTerminators[ord(c)] = True
                for c in SpecialTerminators:
                    BSpecialTerminators[ord(c)] = True
                for i in range(128):
                    BSymbolTerminators[i] = True
                for i in range(ord('a'), ord('z') + 1):
                    BSymbolTerminators[i] = False
                for i in range(ord('A'), ord('Z') + 1):
                    BSymbolTerminators[i] = False
                for i in range(ord('0'), ord('9') + 1):
                    BSymbolTerminators[i] = False
                BSymbolTerminators[ord('_')] = False

def escaped_string(string, quoted, terminators):
    """
    Escapes a string based on the provided terminators.

    Arguments:
        string: Input string.
        quoted: Whether the string should be quoted.
        terminators: List of terminator characters.

    Returns:
        str: Escaped string.
    """
    if string is None:
        string = ""

    initialize_terminators()

    result = []
    pos = 0
    length = len(string)
    buf = [''] * (length * 2 + 1 + (2 if quoted else 0))

    if quoted:
        buf[pos] = '\"'
        pos += 1

    for i in range(length):
        c = string[i]
        if ord(c) < 128 and terminators[ord(c)]:
            buf[pos] = '\\'
            pos += 1
            if c == '\t':
                buf[pos] = 't'
            elif c == '\n':
                buf[pos] = 'n'
            elif c == '\f':
                buf[pos] = 'f'
            elif c == '\r':
                buf[pos] = 'r'
            elif c == chr(0x1b):
                buf[pos] = 'e'
            elif c == chr(0):
                buf[pos] = '0'
            else:
                buf[pos] = c
            pos += 1
        else:
            buf[pos] = c
            pos += 1

    if quoted:
        buf[pos] = '\"'
        pos += 1

    result = ''.join(buf[:pos])
    return result

def escaped_string2(string, quoted, terminators):
    """
    Escapes a string based on the provided terminators 
    (alternative implementation).

    Arguments:
        string: Input string.
        quoted: Whether the string should be quoted.
        terminators: List of terminator characters.

    Returns:
        str: Escaped string.
    """
    if string is None:
        string = ""

    initialize_terminators()

    buf = []
    length = len(string)

    if quoted:
        buf.append('\"')

    for i in range(length):
        c = string[i]
        if ord(c) < 128 and terminators[ord(c)]:
            buf.append('\\')
            if c == '\t':
                buf.append('t')
            elif c == '\n':
                buf.append('n')
            elif c == '\f':
                buf.append('f')
            elif c == '\r':
                buf.append('r')
            elif c == chr(0x1b):
                buf.append('e')
            elif c == chr(0):
                buf.append('0')
            else:
                buf.append(c)
        else:
            buf.append(c)

    if quoted:
        buf.append('\"')

    result = ''.join(buf)
    return result

def escaped_string_with_options(string, quoted, special_only):
    """
    Escapes a string with options for special terminators.

    Arguments:
        string: Input string.
        quoted: Whether the string should be quoted.
        special_only: Whether to use special terminators only.

    Returns:
        str: Escaped string.
    """
    if special_only:
        terminators = BSpecialTerminators
    else:
        terminators = BNormalTerminators

    return escaped_string(string, quoted, terminators)

def escaped_string_auto(string, quoted):
    """
    Automatically escapes a string based on whether it is quoted.

    Arguments:
        string: Input string.
        quoted: Whether the string should be quoted.

    Returns:
        str: Escaped string.
    """
    return escaped_string_with_options(string, quoted, quoted)

def escaped_symbol(string):
    """
    Escapes a symbol.

    Arguments:
        string: Input string.

    Returns:
        str: Escaped symbol.
    """
    result = escaped_string(string, False, BSymbolTerminators)
    if result[0].isdigit():
        result = "\\" + result
    return result
   

class DataHubPoint:
    """
    Class representing a datahub point.
    """
    def __init__(self, name, value, quality, timestamp, flags=0):
        """
        Initializes a DataHubPoint instance.

        Arguments:
            name: Name of the point.
            value: Value of the point.
            quality: Quality of the point.
            timestamp: Timestamp of the point.
            flags: Flags associated with the point. Defaults to 0.
        """
        self.name = name
        self.value = value
        self.timestamp = timestamp
        self.quality = quality
        self.flags = flags
        self.DomainName = None
        self.confidence = None
        self.CanonicalType = None
        self.OnPointChangeMethod = [] 
        self.ChangeFlags = None

    def setDomainName(self, name):
        """
        Sets the domain name of the point.

        Arguments:
            name: Domain name.
        """
        idx = name.find(':')
        if idx != -1:
            self.DomainName = name[:idx]

    def AddOnPointChangeMethod(self, callback):
        """
        Adds a callback method for point change.

        Arguments:
            callback: Callback function.
        """
        self.OnPointChangeMethod.append(callback)
        
    def RemoveOnPointChangeMethod(self, callback):
        """
        Removes a callback method for point change.

        Arguments:
            callback: Callback function.
        """
        self.OnPointChangeMethod.remove(callback)

    def __repr__(self):
        """
        Returns a string representation of the DataHubPoint instance.

        Returns:
            str: String representation.
        """
        return "DataHubPoint(%s, %s, %s, %s)" % (self.name, self.value, self.quality, self.timestamp)
    
    def setTimeStamp(self, windowstime=None, datetime_obj=None, seconds=None, nanoseconds=None):
        """
        Sets the timestamp of the point.

        Arguments:
            windowstime: Windows time. Defaults to None.
            datetime_obj: Datetime object. Defaults to None.
            seconds: Unix time seconds. Defaults to None.
            nanoseconds: Unix time nanoseconds. Defaults to None.
        """
        if windowstime is not None:
            self.timestamp = windowstime
        elif datetime_obj is not None:
            date = self.datetime_to_oatime(datetime_obj)
            self.setTimeStamp(date)
        elif seconds is not None and nanoseconds is not None:
            windows_time = self.unix_time_to_windows_time(seconds, nanoseconds)
            self.setTimeStamp(windows_time)
        else:
            current_time = datetime.datetime.now(datetime.utc)
            self.setTimeStamp(datetime_obj=current_time)

    def datetime_to_oatime(self, datetime_obj):
        """
        Converts a datetime object to OLE Automation date format.

        Arguments:
            datetime_obj: Datetime object.

        Returns:
            float: OLE Automation date.
        """
        OLE_TIME_ZERO = datetime.datetime(1899, 12, 30, 0, 0, 0)
        return (datetime_obj - OLE_TIME_ZERO).total_seconds() / 86400.0

    def unix_time_to_windows_time(self, seconds, nanoseconds):
        """
        Converts Unix time to Windows time.

        Arguments:
            seconds: Unix time seconds.
            nanoseconds: Unix time nanoseconds.

        Returns:
            float: Windows time.
        """
        UNIX_EPOCH = datetime.datetime(1970, 1, 1, 0, 0, 0)
        WINDOWS_EPOCH = datetime.datetime(1601, 1, 1, 0, 0, 0)
        EPOCH_DIFF = (UNIX_EPOCH - WINDOWS_EPOCH).total_seconds()
        windows_time = seconds + EPOCH_DIFF + nanoseconds / 1e9
        return windows_time
    
    def unqualifyName(pointname: str) -> str:
        """
        Removes the domain prefix from a point name if it exists.

        Arguments:
            pointname: The qualified point name.

        Returns:
            str: The unqualified point name.
        """
        if pointname is not None:
            indx = pointname.find(':')
            if indx != -1:
                pointname = pointname[indx + 1:]
        return pointname

    def unqualifyNameWithDomain(pointname: str) -> tuple:
        """
        Splits a qualified point name into its domain and unqualified name.

        Arguments:
            pointname: The qualified point name.
        Returns:
            tuple: A tuple containing the unqualified point name 
            and the domain name.
        """
        domain_name = None
        if pointname is not None:
            indx = pointname.find(':')
            if indx != -1:
                domain_name = pointname[:indx]
                pointname = pointname[indx + 1:]
        return pointname, domain_name

    def qualifyName(self, domainname: str, pointname: str) -> str:
        """
        Combines a domain name and an unqualified point name into a 
        qualified point name.

        Arguments:
            domainname: The domain name.
            pointname: The unqualified point name.
        Returns:
            str: The qualified point name.
        """
        return f"{domainname}:{self.unqualifyName(pointname)}"

    def IsQualifiedName(self, name: str) -> bool:
        """
        Checks if a point name is qualified.

        Arguments:
            name: The point name to check.
        Returns:
            bool: True if the name is qualified, False otherwise.
        """
        if name:
            _, domain_name = self.unqualifyNameWithDomain(name)
            return domain_name is not None
        return False
    
    def getType(self):
        """
        Gets the type of the value.

        Returns:
            type: The type of the value.
        """
        return type(self.value)
    
    def setValue(self, value):
        """
        Sets the value.

        Arguments:
            value: The value to set.
        """
        self.value = value
        
    def setValueFromString(self, value, type):
        """
        Sets the value from a string based on the type.

        Arguments:
            value: The value as a string.
            type: The type of the value.
        """
        if type == PointType.STRING:
            self.value = value
        elif type == PointType.REAL:
            self.value = float(value)
        elif type == PointType.INT64:
            self.value = int(value)
        
    def getDoubleValue(self):
        """
        Gets the value as a double.

        Returns:
            float: The value as a double.
        """
        return float(self.value)
    
    def getIntValue(self):
        """
        Gets the value as an integer.

        Returns:
            int: The value as an integer.
        """
        return int(self.value)
    
    def getStringValue(self):
        """
        Gets the value as a string.

        Returns:
            str: The value as a string.
        """
        return str(self.value)
    
    def setInfo(self, iconf, iquality, timestamp, flags):
        """
        Sets the information for the point.

        Arguments:
            iconf: The confidence value.
            iquality: The quality value.
            timestamp: The timestamp.
            flags: The flags.
        """
        self.confidence = iconf
        self.quality = iquality
        self.timestamp = timestamp
        self.flags = flags

    def setQuality(self, iquality):
        """
        Sets the quality of the point.

        Arguments:
            iquality: The quality value.
        """
        self.quality = iquality

    def getQuality(self):
        """
        Gets the quality of the point.

        Returns:
            The quality value.
        """
        return self.quality
    
    def getQualityString(self):
        """
        Gets the quality of the point as a string.

        Returns:
            str: The quality as a string.
        """
        if self.quality == PointQuality.BAD:
            return "Bad"
        elif self.quality == PointQuality.UNCERTAIN:
            return "Uncertain"
        elif self.quality == PointQuality.GOOD:
            return "Good"
        elif self.quality == PointQuality.CONFIG_ERROR:
            return "Config Error"
        elif self.quality == PointQuality.NOT_CONNECTED:
            return "Not Connected"
        elif self.quality == PointQuality.DEVICE_FAILURE:
            return "Device Failure"
        elif self.quality == PointQuality.SENSOR_FAILURE:
            return "Sensor Failure"
        elif self.quality == PointQuality.LAST_KNOWN:
            return "Last Known"
        elif self.quality == PointQuality.COMM_FAILURE:
            return "Comm Failure"
        elif self.quality == PointQuality.OUT_OF_SERVICE:
            return "Out of Service"
        elif self.quality == PointQuality.LAST_USABLE:
            return "Last Usable"
        elif self.quality == PointQuality.SENSOR_CAL:
            return "Sensor Calibration"
        elif self.quality == PointQuality.EGU_EXCEEDED:
            return "EGU Exceeded"
        elif self.quality == PointQuality.SUB_NORMAL:
            return "Subnormal"
        elif self.quality == PointQuality.LOCAL_OVERRIDE:
            return "Local Override"
        else:
            return "Unknown"

    def clear(self):
        """
        Clears the point information.
        """
        self.name = None
        self.DomainName = None
        self.value = None
        self.timestamp = 0
        self.quality = 0x00
        self.flags = 0

    def getName(self):
        """
        Gets the name of the point.

        Returns:
            str: The name of the point.
        """
        return self.name
    
    def setName(self, name):
        """
        Sets the name of the point.

        Arguments:
            name: The name to set.
        """
        self.name = name

    def setConfidence(self, iconfidence):
        """
        Sets the confidence value of the point.

        Arguments:
            iconfidence: The confidence value.
        """
        self.confidence = iconfidence

    def getConfidence(self):
        """
        Gets the confidence value of the point.

        Returns:
            The confidence value.
        """
        return self.confidence
    
    def setFlags(self, flags):
        """
        Sets the flags of the point.

        Arguments:
            flags: The flags to set.
        """
        self.flags = flags

    def getFlags(self):
        """
        Gets the flags of the point.

        Returns:
            The flags.
        """
        return self.flags
    
    
