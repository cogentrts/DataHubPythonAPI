import asyncio
import time
import socket
import lispparse as lp
from random import random
from enum import Enum, IntFlag, IntEnum, Flag
from dataclasses import dataclass

from typing import Optional, Union
from uuid import UUID

class ModelEmitter:
    """
    Class to handle model emission for a connection.
    """
    def __init__(self, conn):
        """
        Initialize the ModelEmitter object.

        Arguments:
            conn: Connection object to send commands.
        """
        self.domains = []
        self.verbose = None
        self.conn = conn # Connection object to send commands

    def add_domain(self, name):
        """
        Add a domain if it doesn't already exist.

        Arguments:
            name: The name of the domain.
            
        Returns:
            The domain object.
        """
        domain = next((d for d in self.domains if d.name == name), None)
        if not domain:
            domain = ModelDomain(name)
            self.domains.append(domain)
        return domain

    def emit(self):
        """
        Emit commands to the connection, sorted by domain.
        """
        for domain in self.domains:
            domain.sort_instructions()
            cmd = f"(domain {domain.name})"
            self.conn.sendCommand(cmd)
            for instruction in domain.instructions:
                self.conn.sendCommand(instruction)

    def map_point(self, pointname, delimiters=".", type="R8", access="rw", depth=0):
        """
        Map a pointname to its domain and generate the necessary instructions.

        Arguments:
            pointname: The point name.
            delimiters: Delimiters for splitting the point name.
            type: The type of the point.
            access: Access type of the point.
            depth: Depth for splitting the point name.
        """
        chunks = pointname.split(":")
        domain = chunks[0]
        parts = chunks[1].split(delimiters)[:depth] if depth else chunks[1].split(delimiters)
        domaindata = self.add_domain(domain)

        parent = None
        for i in range(len(parts) - 1):
            child = f"{parent}.{parts[i]}" if parent else parts[i]
            cmd = f"(assembly {domain} {child})"
            domaindata.add_instruction(cmd)
            if i > 0:
                cmd = f"(subassembly {domain} {parent} {child} {parts[i]})"
                domaindata.add_instruction(cmd)
            parent = child

        if not parent:
            create_cmd = f"(create {parts[0]} 1)"
            type_cmd = f"(set_canonical {parts[0]} {type})"
            access_cmd = f"(set_access {parts[0]} {access})"
            domaindata.add_instruction(create_cmd)
            domaindata.add_instruction(type_cmd)
            domaindata.add_instruction(access_cmd)
        else:
            cmd = (f"(private_attribute {domain} {parent} {parts[-1]} {type} "
                   f"{access} \"\" 0)")
            domaindata.add_instruction(cmd)

        cmd = f"(instance {domain} {parts[0]} {parts[0]})"
        domaindata.add_instruction(cmd)


class ModelDomain:
    """
    Class to handle domain-specific instructions.
    """
    def __init__(self, name):
        """
        Initialize the ModelDomain object.

        Arguments:
            name: The name of the domain.
        """
        self.name = name
        self.instructions = []
        self.instruction_hash = {}

    def add_instruction(self, command):
        """
        Add an instruction to the domain.

        Arguments:
            command: The command to add.
        """
        if command not in self.instruction_hash:
            self.instructions.append(command)
            self.instruction_hash[command] = command

    def sort_instructions(self):
        """
        Sort instructions in the order of create, assembly, subassembly, 
        private_attribute, instance.
        """
        indices = {'c': 1, 'a': 2, 's': 3, 'p': 4, 'i': 5}

        def cmp_instructions(i1, i2):
            result = indices.get(i1[1], 0) - indices.get(i2[1], 0)
            if result == 0:
                result = (i1 > i2) - (i1 < i2)
            return result

        self.instructions.sort(key=lambda x: (indices.get(x[1], 0), x))

class ConnectionOptions:
    """
    Class to handle connection options.
    """    
    def __init__(self):
        """
        Initialize the ConnectionOptions object with default values.
        """
        self.Hostname = None
        self.Port = None
        self.WebPort = None
        self.IsHttps = None
        self.Domain = None
        self.Username = None
        self.Password = None
        self.ParentSessionId = UUID('00000000-0000-0000-0000-000000000000')
        self.DefaultDomain = None
        self.ProxyHostname = None
        self.ProxyPort = None
        self.ProxyUsername = None
        self.ProxyPassword = None
        self.Heartbeat = 0  # in Milliseconds
        self.Timeout = 0  # in Milliseconds
        self.ReconnectDelay = 5000  # in Milliseconds
        self.DomainListDelay = 5000 # in Milliseconds
        self.Organization = None

        self.IsSsl = None
        self.ClientCertificate = None
        self.AcceptInvalidCertificates = None

    @property
    def FullUsername(self):
        """
        Get the full username including the domain.

        Returns:
            str: The full username.
        """
        if not self.Username:
            return None
        if not self.Organization or '/' in self.Username:
            return self.Username
        return f"{self.Organization}/{self.Username}"

    @property
    def HasCredentials(self):
        """
        Check if the connection options have credentials.

        Returns:
            bool: True if both username and password are set, False otherwise.
        """
        return bool(self.Username) and bool(self.Password)

    @property
    def HasProxyCredentials(self):
        """
        Check if the connection options have proxy credentials.

        Returns:
            bool: True if both proxy username and proxy password are set, 
            False otherwise.
        """
        return bool(self.ProxyUsername) and bool(self.ProxyPassword)

    @property
    def HasParentSessionId(self):
        """
        Check if the connection options have a parent session ID.

        Returns:
            bool: True if the parent session ID is not the default value, 
            False otherwise.
        """
        return self.ParentSessionId != UUID('00000000-0000-0000-0000-000000000000')

class DataHubConnectionType(Enum):
    """
    Enum representing the type of DataHub connection.
    """
    NoType = 0
    TCP = 1
    WebSocket = 2
    WasmWebSocket = 3


class DataHubConnectionStatus(Enum):
    """
    Enum representing the status of a DataHub connection.
    """
    Idle = 0
    Connecting = 1
    Connected = 2
    RetryWait = 3
    Disconnected = 4
    Terminated = 5

class ChangeFlags(IntFlag):
    """
    IntFlag representing various change flags.
    """
    ECHO = 0x0001
    WAITING = 0x0002
    FOREIGN = 0x0004
    SYNCING = 0x0008

class PointFlags(IntFlag):
    """
    IntFlag representing various point flags.
    """
    DH_ITEM_READABLE = 0x000001
    DH_ITEM_WRITABLE = 0x000002
    DH_ITEM_LOCKED = 0x000004
    DH_ITEM_PROPERTY = 0x000008
    DH_ITEM_SUBASSEMBLY = 0x000010
    DH_ITEM_ASSEMBLY = 0x000020
    DH_ITEM_ATTRIBUTE = 0x000040
    DH_ITEM_TYPE = 0x000080
    DH_ITEM_ACTIVE = 0x000100
    DH_ITEM_PRIVATE_ATTRIBUTE = 0x000200
    DH_ITEM_PROCESSED = 0x000400
    DH_ITEM_HIDDEN = 0x000800
    DH_ITEM_AUTO_ID = 0x001000
    DH_ITEM_NO_MASTER_WRITE = 0x002000
    DH_ITEM_NO_SLAVE_WRITE = 0x004000
    DH_ITEM_FORCE_WRITE = 0x008000
    DH_ITEM_FORCE_INSIG = 0x010000
    DH_ITEM_MIRROR_ONLY = 0x020000
    DH_ITEM_TEMP_VALUE = 0x040000
    DH_ITEM_FORCE_WRITE_RO = 0x100000
    DH_ITEM_UNINITIALIZED = 0x200000
    DH_ITEM_FIRST_VALUE = 0x400000
    DH_ITEM_IMMUTABLE = 0x800000
    DH_ITEM_PUBLISH_MODEL = 0x01000000
    DH_ITEM_ZIP_MODEL = 0x02000000
    DH_ITEM_DELETED = 0x04000000
    DH_ITEM_CHILD = DH_ITEM_PROPERTY | DH_ITEM_SUBASSEMBLY | DH_ITEM_ATTRIBUTE
    DH_ITEM_ACCESS_MASK = DH_ITEM_WRITABLE | DH_ITEM_READABLE
    DH_ITEM_MODEL_BRANCH = DH_ITEM_SUBASSEMBLY | DH_ITEM_ASSEMBLY | DH_ITEM_TYPE
    DH_POINT_FLAGS_MIRRORED = DH_ITEM_HIDDEN | DH_ITEM_UNINITIALIZED | DH_ITEM_DELETED

class DomainFlags(IntFlag):
    """
    IntFlag representing various domain flags.
    """
    ALL = 0x01
    FUTURE = 0x02
    QUALIFY = 0x04
    ONCEONLY = 0x08
    MODEL = 0x10
    SYNC = 0x20
    UNREGISTER = 0x40
    METAINFO = 0x80
    NOEVENT = 0x0100
    ECHO = 0x0200

class LogSeverity(IntFlag):
    """
    IntFlag representing various Log Severity flags.
    """
    ERROR = 0x01
    WARNING = 0x02
    INFO = 0x04
    DEBUG = 0x08

class PointRegister(IntFlag):
    """
    IntFlag representing various point register flags.
    """
    QUALIFY = 0x04
    ONCEONLY = 0x08
    SYNC = 0x20
    UNREGISTER = 0x40

class DataHubStatus(IntEnum):
    """
    IntEnum representing various DataHub statuses.
    """
    OK = 0
    ERROR = 1
    NO_TASK = 2
    NO_MSG = 3
    WOULDBLOCK = 4
    INTR = 5
    FULL = 6
    LOCKED = 7
    SECURITY = 8
    NO_POINT = 9
    INSIG = 10
    UNKNOWN = 11
    NO_QUEUE = 12
    CMD_SYNTAX_ERROR = 13
    REPLIED = 14
    WRONG_TYPE = 15
    TOO_LARGE = 16
    NO_MEMORY = 17
    OLD_DATA = 18
    TIMEOUT = 19
    POINT_EXISTS = 20
    POINT_READONLY = 21
    IS_CONFIG = 22
    NOT_ALLOWED = 23
    NO_LICENSE = 24
    NOT_AVAILABLE = 25
    NOT_IMPLEMENTED = 26
    NO_DOMAIN = 27
    POINT_COMPUTED = 28

class VariantType(IntEnum):
    """
    IntEnum representing various variant types.
    """
    EMPTY = 0
    NULL = 1
    I2 = 2
    I4 = 3
    R4 = 4
    R8 = 5
    CY = 6
    DATE = 7
    BSTR = 8
    STRING = 8
    DISPATCH = 9
    ERROR = 10
    BOOL = 11
    VARIANT = 12
    UNKNOWN = 13
    DECIMAL = 14
    I1 = 16
    UI1 = 17
    UI2 = 18
    UI4 = 19
    I8 = 20
    UI8 = 21
    INT = 22
    UINT = 23
    VOID = 24
    HRESULT = 25
    PTR = 26
    SAFEARRAY = 27
    CARRAY = 28
    USERDEFINED = 29
    LPSTR = 30
    LPWSTR = 31
    RECORD = 36
    INT_PTR = 37
    UINT_PTR = 38
    ARRAY = 8192

@dataclass
class MetadataFlags(Flag):
    """
    Dataclass representing various metadata flags.
    """
    NONE = 0x0000
    EU = 0x0001
    DESCRIPTION = 0x0002
    EU_LOW = 0x0004
    EU_HIGH = 0x0008
    INSTR_LOW = 0x0010
    INSTR_HIGH = 0x0020
    OPEN = 0x0040
    CLOSE = 0x0080
    ORIGIN_NAME = 0x0100
    ORIGIN_DESCRIPTION = 0x0200
    ORIGIN_USER = 0x0400
    ORIGIN_HOST = 0x0800
    ORIGIN_TYPE = 0x1000

@dataclass
class PointMetaInfo:
    """
    Dataclass representing metadata information for a point.
    """
    ValidFlags: MetadataFlags = MetadataFlags.NONE
    Eu: Optional[str] = None
    Description: Optional[str] = None
    EuHigh: float = 0.0
    EuLow: float = 0.0
    InstrumentHigh: float = 0.0
    InstrumentLow: float = 0.0
    ContactCloseLabel: Optional[str] = None
    ContactOpenLabel: Optional[str] = None
    RefCount: int = 0

    def __eq__(self, other):
        """
        Check if two PointMetaInfo objects are equal.

        Arguments:
            other: The other PointMetaInfo object.
        Returns:
            bool: True if equal, False otherwise.
        """
        if not isinstance(other, PointMetaInfo):
            return False
        return (self.Eu == other.Eu and
                self.Description == other.Description and
                self.EuHigh == other.EuHigh and
                self.EuLow == other.EuLow and
                self.InstrumentHigh == other.InstrumentHigh and
                self.InstrumentLow == other.InstrumentLow and
                self.ContactCloseLabel == other.ContactCloseLabel and
                self.ContactOpenLabel == other.ContactOpenLabel and
                self.ValidFlags == other.ValidFlags)

    def __hash__(self):
        """
        Get the hash value of the PointMetaInfo object.

        Returns:
            int: The hash value.
        """
        return (hash(self.Eu) ^ hash(self.Description) ^ 
                hash(self.EuHigh) ^ hash(self.EuLow) ^ 
                hash(self.InstrumentHigh) ^ hash(self.InstrumentLow) ^
                hash(self.ContactCloseLabel) ^ hash(self.ContactOpenLabel) ^ 
                hash(self.ValidFlags))

    def __str__(self):
        """
        Get the string representation of the PointMetaInfo object.

        Returns:
            str: The string representation.
        """
        sb = []
        if self.ValidFlags & MetadataFlags.CLOSE:
            sb.append(f"({'close'} {self.escaped(self.ContactCloseLabel)})")
        if self.ValidFlags & MetadataFlags.OPEN:
            sb.append(f"({'open'} {self.escaped(self.ContactOpenLabel)})")
        if self.ValidFlags & MetadataFlags.EU:
            sb.append(f"({'eu'} {self.escaped(self.Eu)})")
        if self.ValidFlags & MetadataFlags.DESCRIPTION:
            sb.append(f"({'desc'} {self.escaped(self.Description)})")
        if self.ValidFlags & MetadataFlags.EU_LOW:
            sb.append(f"({'eulo'} {self.EuLow})")
        if self.ValidFlags & MetadataFlags.EU_HIGH:
            sb.append(f"({'euhi'} {self.EuHigh})")
        if self.ValidFlags & MetadataFlags.INSTR_LOW:
            sb.append(f"({'inslo'} {self.InstrumentLow})")
        if self.ValidFlags & MetadataFlags.INSTR_HIGH:
            sb.append(f"({'inshi'} {self.InstrumentHigh})")
        return ' '.join(sb).strip()


    def escaped(self, s: str) -> str:
        """
        Escape special characters in a string.

        Arguments:
            s: The string to escape.
        Returns:
            str: The escaped string.
        """
        lp.escaped_string(s, True, True)

    def copy_from(self, other):
        """
        Copy metadata from another PointMetaInfo object.

        Arguments:
            other: The other PointMetaInfo object.
        """
        self.ValidFlags = MetadataFlags.NONE
        self.set_metadata(other.ValidFlags, other.Eu, other.Description, 
                          other.EuHigh, other.EuLow, other.InstrumentHigh, 
                          other.InstrumentLow, other.ContactCloseLabel, 
                          other.ContactOpenLabel)
        self.ValidFlags = other.ValidFlags

    def clear(self):
        """
        Clear the metadata.
        """
        self.ValidFlags = MetadataFlags.NONE
        self.Eu = None
        self.Description = None
        self.EuHigh = 0
        self.EuLow = 0
        self.InstrumentHigh = 0
        self.InstrumentLow = 0
        self.ContactCloseLabel = None
        self.ContactOpenLabel = None

    def set_metadata(self, valid_flags: MetadataFlags, eu: str = "",
                     description: str = "", eu_high: float = 0, eu_low: float = 0,
                     instrument_high: float = 0, instrument_low: float = 0,
                     contact_close_label: str = "", contact_open_label: str = ""):
        """
        Set the metadata.

        Arguments:
            valid_flags: The valid flags.
            eu: The engineering units.
            description: The description.
            eu_high: The high engineering unit.
            eu_low: The low engineering unit.
            instrument_high: The high instrument value.
            instrument_low: The low instrument value.
            contact_close_label: The contact close label.
            contact_open_label: The contact open label.
        """
        if valid_flags & MetadataFlags.CLOSE:
            self.ContactCloseLabel = contact_close_label
        if valid_flags & MetadataFlags.OPEN:
            self.ContactOpenLabel = contact_open_label
        if valid_flags & MetadataFlags.DESCRIPTION:
            self.Description = description
        if valid_flags & MetadataFlags.EU:
            self.Eu = eu
        if valid_flags & MetadataFlags.EU_HIGH:
            self.EuHigh = eu_high
        if valid_flags & MetadataFlags.EU_LOW:
            self.EuLow = eu_low
        if valid_flags & MetadataFlags.INSTR_HIGH:
            self.InstrumentHigh = instrument_high
        if valid_flags & MetadataFlags.INSTR_LOW:
            self.InstrumentLow = instrument_low
        self.ValidFlags |= valid_flags

class Timer:
    """
    A custom timer that triggers a callback after an initial wait period, 
    then repeats at the specified interval.
    """
    def __init__(self, loop, initial_wait, interval, callback, *args, **kwargs):
        """
        Initialize the Timer object.

        Arguments:
            loop: The event loop.
            initial_wait: The initial wait period in milliseconds.
            interval: The interval period in milliseconds.
            callback: The callback function to trigger.
            args: Additional arguments for the callback.
            kwargs: Additional keyword arguments for the callback.
        """
        self.loop = loop
        self.initial_wait = initial_wait/1000
        self.interval = interval/1000
        self.callback = callback
        self.args = args
        self.kwargs = kwargs
        self._running = False

    def start(self):
        """
        Start the timer by waiting for the initial delay, then repeat.
        """
        self._running = True
        self.loop.call_later(self.initial_wait, self._run_and_repeat)

    def _run_and_repeat(self):
        """
        Run the callback and schedule the next callback after the interval.
        """
        if self._running:
            self.callback(*self.args, **self.kwargs)  # Call the callback with args and kwargs
            # Schedule the next callback after the repeat interval
            self.loop.call_later(self.interval, self._run_and_repeat)

    def stop(self):
        """
        Stop the timer.
        """
        self.loop.call_soon(self._stop_timer)

    def _stop_timer(self):
        """
        Stop the timer by canceling the scheduled callback.
        """
        self._running = False
        self.callback = None

class PreciseTimer:
    """
    A precise timer that triggers a callback at regular intervals.
    """
    def __init__(self, loop, initial_wait_ms, repeat_interval_ms, callback, *args, **kwargs):
        """
        Initialize the PreciseTimer object.

        Arguments:
            loop: The event loop.
            initial_wait_ms: The initial wait period in milliseconds.
            repeat_interval_ms: The repeat interval period in milliseconds.
            callback: The callback function to trigger.
            args: Additional arguments for the callback.
            kwargs: Additional keyword arguments for the callback.
        """
        self.loop = loop
        self.initial_wait = initial_wait_ms/1000
        self.repeat_interval = repeat_interval_ms/1000
        self.callback = callback
        self.args = args
        self.kwargs = kwargs
        self._running = False

    def start(self):
        """
        Start the timer.
        """
        self._running = True
        self.loop.create_task(self._run())

    async def _run(self):
        """
        Run the timer.
        """
        # Wait for the initial period
        await asyncio.sleep(self.initial_wait)

        next_call = time.perf_counter() + self.repeat_interval
        while self._running:
            # Call the callback function
            self.callback(*self.args, **self.kwargs)

            # Calculate the time for the next call
            next_call += self.repeat_interval

            # Calculate the sleep time, ensuring it doesn't go negative
            sleep_time = max(0, next_call - time.perf_counter())
            await asyncio.sleep(sleep_time)  # Sleep until the next call
  
    def cancel(self):
        """
        Stop the timer.
        """
        self._running = False

class DataHubConnection:
    """
    Represents a connection to the DataHub.

    Attributes:
        onConnected: Callback for when the connection is established.
        onDisconnected: Callback for when the connection is disconnected.
        onPointChange: Callback for when a point changes.
        onCommand: Callback for when a command is received.
        onEcho: Callback for when an echo message is received.
        onAsyncMessage: Callback for when an asynchronous 
        message is received.
        onAlive: Callback for when an alive message is received.
        onSuccess: Callback for when an operation is successful.
        onError: Callback for when an error occurs.
        onLog: Callback for logging messages.
        onConnectionSuccess: Callback for when the connection is 
        successfully established.
        onConnectionFailure: Callback for when the connection fails.
        onConnecting: Callback for when the connection is in the 
        process of connecting.
        onStatusChange: Callback for when the connection status changes.
        data: Bytearray to store data.
        m_connstate: Current connection state.
        ConnectionStatus: Alias for the current connection state.
        m_aliveTimer: Timer for the alive message.
        m_retrytimer: Timer for retrying the connection.
        m_domainlisttimer: Timer for domain list updates.
        Options: Connection options.
        loop: Event loop.
        writer: Stream writer.
        reader: Stream reader.
        name: Connection name.
        m_datamodel: Data model dictionary.
        message_queue: Queue for messages.
        m_timeoutTimer: Timer for connection timeout.
        dataWasRead: Flag indicating if data was read.
    """
    def __init__(self, loop):
        """
        Initialize the DataHubConnection object.

        Arguments:
            loop: The event loop.
        """
        self.onConnected = None
        self.onDisconnected = None
        self.onPointChange = lambda x : self.defaultOnPointChange(x)
        self.onCommand = None
        self.onEcho = None
        self.onAsyncMessage = None
        self.onAlive = None
        self.onSuccess = None
        self.onError = None
        self.onLog = None
        self.onConnectionSuccess = None
        self.onConnectionFailure = None
        self.onConnecting = None
        self.onStatusChange = None 
        self.data = bytearray()
        self.m_connstate = DataHubConnectionStatus.Idle
        self.ConnectionStatus = self.m_connstate      
        self.m_aliveTimer = None
        self.m_retrytimer = None
        self.m_domainlisttimer = None
        self.Options = ConnectionOptions()
        self.loop = loop
        self.writer = None
        self.reader = None
        self.name = None
        self.m_datamodel = dict()
        self.message_queue = asyncio.Queue()
        self.m_timeoutTimer = None
        self.dataWasRead = False

    async def performConnect(self):
        """
        Attempt to connect to the server and start reading/writing.
        """
        try:
            self.log(LogSeverity.INFO, f"Attempting to connect to {self.Options.Hostname}:{self.Options.Port}...")
            self.reader, self.writer = await asyncio.open_connection(self.Options.Hostname, self.Options.Port)
            self.Connection_Connecting(self.Options.Hostname, self.Options.Port)
            self.Connection_ConnectSucceeded(self.Options.Hostname, self.Options.Port)
            self.sendCommand(f"(acksuccess 0)")
            self.runCallback(self.onConnected)

            # Start reading incoming messages
            asyncio.create_task(self.message_writer())
            await self.read_messages()
        
        except Exception as e:
            self.log(LogSeverity.ERROR, f"Connection Exception: {e}")

        self.setConnState(DataHubConnectionStatus.Disconnected)
        self.closeConnection()
        self.Connection_ConnectFailed(self.Options.Hostname, self.Options.Port)       

    async def connect(self):
        """
        Start the reconnection timer and attempt to connect.
        """
        self.startReconnectionTimer()
        await self.performConnect()

    def defaultOnPointChange(self, point):
        """
        Default handler for point change events.

        Arguments:
            point: The point that changed.
        """
        self.runPointChangeMethod(point)

    def runAllPointChangeMethods(self):
        """
        Run point change methods for all points in the data model.
        """
        for key, value in self.m_datamodel.items():
            self.runPointChangeMethod(value)

    def log(self, severity, message):
        """
        Log a message with the given severity.

        Arguments:
            severity: The severity of the log message.
            message: The log message.
        """
        if self.onLog:
            self.runCallback(self.onLog(severity, message))

    def runPointChangeMethod(self, point):
        """
        Run the point change method for a given point.

        Arguments:
            point: The point that changed.
        """
        if (isinstance(point[0], lp.DataHubPoint)):
            pointname = point[0].name
        else:
            pointname = point[0]

        modelPoint = self.m_datamodel.get(pointname)
        if (modelPoint.OnPointChangeMethod is not None):
            for method in modelPoint.OnPointChangeMethod:
                self.runCallback(method(point[0]))

    def runCallback(self, callback):
        """
        Run a callback if it is set.

        Arguments:
            callback: The callback to run.
        """
        if callback:
            self.loop.call_soon_threadsafe(callback)

    def getCnxState(self):
        """
        Get the current connection state.

        Returns:
            DataHubConnectionStatus: The current connection state.
        """
        return self.m_connstate
    
    def getCnxStateString(self):
        """
        Get the current connection state as a string.

        Returns:
            str: The current connection state as a string.
        """
        return str(self.m_connstate)
           
    def MarkAllPointsAsNotConnected(self):
        """
        Mark all points in the data model as not connected.
        """
        for key, value in self.m_datamodel.items():
            if (value.quality != lp.PointQuality.NOT_CONNECTED):
                previous = lp.DataHubPoint(value.name, value.value, value.quality, value.timestamp, value.flags)
                value.quality = lp.PointQuality.NOT_CONNECTED
                self.writePoint(value.name, value.value, None, value.quality, value.timestamp, value.flags)
                if self.onPointChange:
                    self.loop.call_soon_threadsafe(self.onPointChange, (value,))
            
    async def read_messages(self):  
        """
        Continuously read messages from the server.
        """
        while self.getCnxState() == DataHubConnectionStatus.Connected:
            try:
                timeout=False
                chunk = None
                chunk = await self.reader.read(1024)
                if len(chunk) == 0:
                    chunk = None
            except socket.timeout:
                timeout=True
            except:
                pass

            # if we did not get a chunk or a timeout, it's a socket failure
            if not timeout and not chunk:
                self.setConnState(DataHubConnectionStatus.Disconnected)

            if chunk:
                self.dataWasRead = True
                index = chunk.find(b'\n')
                priorLen = len(self.data)
                self.data.extend(chunk)
                if index != -1:
                    index += priorLen
                    # break the byte array into before and after the newline
                    chunk = self.data[:index].decode("utf-8")
                    self.data = self.data[index+1:]

                    # parse the incoming string up to the newline into an array of arrays of strings
                    expressions = lp.parse(chunk)

                    #extra loop set last point change or echo

                    for expression in expressions:
                        payload = expression
                        # Marshal the token array into the main thread for processing
                        if expression[0] == 'point' or expression[0] == 'echo':
                            payload = lp.DataHubPoint(expression[1], self.changeType(int(expression[2]), expression[3]),
                                                        int(expression[10]),
                                                        int(expression[7]) + float(expression[8]) / 1.0e9,
                                                        int(expression[9]))
                            if self.onPointChange and expression[0] == 'point':
                                point = self.lookupPoint(expression[1])
                                if point != None:
                                    previous = lp.DataHubPoint(point.name, point.value, point.quality, point.timestamp, point.flags)
                                    point.name = expression[1]
                                    point.value = self.changeType(int(expression[2]), expression[3])
                                    point.quality = int(expression[10])
                                    point.timestamp = int(expression[7]) + float(expression[8]) / 1.0e9
                                    point.flags = int(expression[9])
                                self.loop.call_soon_threadsafe(self.onPointChange, (payload, previous, point.ChangeFlags))

                            elif self.onEcho and expression[0] == 'echo':
                                point = self.lookupPoint(expression[1])
                                if point != None:
                                    previous = lp.DataHubPoint(point.name, point.value, point.quality, point.timestamp, point.flags)
                                    point.name = expression[1]
                                    point.value = self.changeType(int(expression[2]), expression[3])
                                    point.quality = int(expression[10])
                                    point.timestamp = int(expression[7]) + float(expression[8]) / 1.0e9
                                    point.flags = int(expression[9])
                                self.loop.call_soon_threadsafe(self.onEcho, (payload, previous, point.ChangeFlags))
                        elif self.onError and expression[0] == 'error':
                            self.loop.call_soon_threadsafe(self.onError, (payload,))
                        elif self.onSuccess and expression[0] == 'success':
                            self.loop.call_soon_threadsafe(self.onSuccess, (payload,))

                        elif expression[0] == 'set_canonical':
                            if len(expression) > 2:
                                point = self.lookupPoint(expression[1])
                                if isinstance(expression[2], int):
                                    point.CanonicalType = VariantType(expression[2])
                    
                        elif expression[0] == 'alive':
                            self.runCallback(self.onAlive)

                        elif self.onCommand:
                            self.loop.call_soon_threadsafe(self.onCommand, payload)

                        else:
                            if self.onAsyncMessage:
                                self.loop.call_soon_threadsafe(self.onAsyncMessage, payload)

    async def message_writer(self):
        """
        Continuously sends messages from the queue to the socket.
        """
        try:
            while self.getCnxState() == DataHubConnectionStatus.Connected:
                message = await self.message_queue.get()  # Get a message from the queue
                self.writer.write(message.encode("utf-8"))  # Send the message
                await self.writer.drain()  # Ensure the message is written to the socket
                self.message_queue.task_done()  # Indicate that the message was processed
        except asyncio.CancelledError:
            self.log(LogSeverity.WARNING, "Writer task was cancelled.")

        except Exception as e:
            self.log(LogSeverity.ERROR, f"An error occurred in the writer task: {e}")

        finally:
            if not self.writer.is_closing():
                self.writer.close()
                try:
                    await self.writer.wait_closed()
                except Exception as close_err:
                    self.log(LogSeverity.ERROR, f"Error while closing the writer: {close_err}")

    def startDomainListTimer(self):
        """
        Start the domain list timer.
        """
        self.cancelDomainListTimer()
        self.m_domainlisttimer = self.preciseTimer(self.loop, self.Options.DomainListDelay, self.Options.DomainListDelay, self.DomainListEventHandler)
        self.m_domainlisttimer.start()

    def cancelDomainListTimer(self):
        """
        Cancel the domain list timer.
        """
        if self.m_domainlisttimer is not None:
            self.m_domainlisttimer.cancel()
            self.m_domainlisttimer = None

    def DomainListEventHandler(self):
        """
        Handle the domain list event.
        """
        self.sendCommand("(domains)")

    def sendAlive(self):
        """
        Send an alive message to the server.
        """
        self.sendCommand("(alive)\n")

    def timeoutCheck(self):
        """
        Check for connection timeout.
        """
        if self.getCnxState() == DataHubConnectionStatus.Connected and not self.dataWasRead:
            self.log(LogSeverity.ERROR, "Connection timed out")
            self.closeConnection()
        self.dataWasRead = False

    def sendLogin(self):
        """
        Send login credentials to the server.
        """
        if self.Options.HasParentSessionId:
            return self.sendCommand("(auth_clone " +
                                lp.escaped_string_auto(str(self.Options.ParentSessionId), True) + ")\n")
        elif self.Options.HasCredentials:

            return self.sendCommand("(auth" +
                                lp.escaped_string_auto(self.Options.FullUsername, True) + " " +
                                lp.escaped_string_auto(self.Options.Password, True) + ")\n")
        else:
            return None

    def sendWantSuccess(self):
        """
        Send a success acknowledgment request to the server.
        """
        self.sendCommand("(acksuccess " + ("1" if False else "0") + ")")

    def appendPointValueMetaData(self, sb: list, valid_flags: MetadataFlags, value: Union[str, float, None], flag: MetadataFlags):
        """
        Append point value metadata to a list.

        Arguments:
            sb: The list to append to.
            valid_flags: The valid metadata flags.
            value: The value to append.
            flag: The metadata flag.
        """
        if valid_flags & flag:
            sb.append(" (")
            sb.append(self.MetadataNames.Get(flag))
            sb.append(" ")
            if isinstance(value, str):
                sb.append(lp.EscapedString(value, True, True))
            else:
                sb.append("" if value is None else str(value))
            sb.append(")")

    def writeMetadata(self, point_name: str, metadata: Optional[PointMetaInfo]) -> Optional[Exception]:
        """
        Write metadata for a point.

        Arguments:
            point_name: The name of the point.
            metadata: The metadata to write.
        Returns:
            Optional[Exception]: An exception if an error occurs, 
            otherwise None.
        """
        data_point = self.lookupPoint(point_name)
        if not lp.DataPoint.IsQualifiedName(point_name):
            return KeyError(f"Point not found: {point_name}")
        if metadata is None:
            return None

        if not data_point.equals(metadata):
            sb = []
            sb.append("(set_meta ")
            sb.append(lp.EscapedString(point_name, True, True))
            sb.append(" ")
            sb.append(str(int(metadata.ValidFlags)))
            sb.append(" ")
            self.appendPointValueMetaData(sb, metadata.ValidFlags, metadata.Eu, MetadataFlags.Eu)
            self.appendPointValueMetaData(sb, metadata.ValidFlags, metadata.Description, MetadataFlags.Description)
            self.appendPointValueMetaData(sb, metadata.ValidFlags, metadata.EuHigh, MetadataFlags.EuHigh)
            self.appendPointValueMetaData(sb, metadata.ValidFlags, metadata.EuLow, MetadataFlags.EuLow)
            self.appendPointValueMetaData(sb, metadata.ValidFlags, metadata.InstrumentHigh, MetadataFlags.InstrHigh)
            self.appendPointValueMetaData(sb, metadata.ValidFlags, metadata.InstrumentLow, MetadataFlags.InstrLow)
            self.appendPointValueMetaData(sb, metadata.ValidFlags, metadata.ContactCloseLabel, MetadataFlags.Close)
            self.appendPointValueMetaData(sb, metadata.ValidFlags, metadata.ContactOpenLabel, MetadataFlags.Open)

            sb.append(")\n")
            command = ''.join(sb)
            return self.sendCommand(command)
        
        return None
    
    def setDefaultDomain(self, domain: str) -> Exception:
        """
        Set the default domain.

        Arguments:
            domain: The domain to set as default.
        Returns:
            Exception: An exception if the domain is invalid.
        """
        if domain:
            self.Options.DefaultDomain = domain
            command = f"(domain {lp.escaped_string_auto(domain, True)})"
            return self.sendCommand(command)
        else:
            return Exception("No default domain set")

    def sendHeartbeatTimes(self):
        """
        Send heartbeat times to the server.
        """
        if self.getCnxState() == DataHubConnectionStatus.Connected:
            self.sendCommand(f"(heartbeat {self.Options.Heartbeat}) (timeout {self.Options.Timeout})")

    def startHeartbeatTimers(self):
        """
        Start the heartbeat timers.
        """
        if (self.Options.Heartbeat > 0 and self.Options.Timeout > 0):
            if (self.m_aliveTimer is not None):
                self.cancelHeartbeatTimers()
            self.m_aliveTimer = self.preciseTimer(self.loop, self.Options.Heartbeat, self.Options.Heartbeat, self.sendAlive)
            self.m_timeoutTimer = self.preciseTimer(self.loop, self.Options.Timeout, self.Options.Timeout, self.timeoutCheck)
            self.m_aliveTimer.start()
            self.m_timeoutTimer.start()
            self.sendHeartbeatTimes()

    def activeHeartbeatTimers(self):
        """
        Check if heartbeat timers are active.

        Returns:
            bool: True if heartbeat timers are active, False otherwise.
        """
        return self.m_aliveTimer is not None

    def cancelHeartbeatTimers(self):
        """
        Cancel the heartbeat timers.
        """
        if (self.m_aliveTimer is not None):
            self.m_aliveTimer.cancel()
            self.m_aliveTimer = None
        if (self.m_timeoutTimer is not None):
            self.m_timeoutTimer.cancel()
            self.m_timeoutTimer = None

    def setHeartbeatTimes(self, heartbeat_ms, timeout_ms):
        """
        Set the heartbeat and timeout times.

        Arguments:
            heartbeat_ms: The heartbeat time in milliseconds.
            timeout_ms: The timeout time in milliseconds.
        """
        self.Options.Heartbeat = heartbeat_ms
        self.Options.Timeout = timeout_ms
        if (self.m_aliveTimer is not None):
            self.cancelHeartbeatTimers()
            self.startHeartbeatTimers()
    
    def getPort(self):
        """
        Get the port number.

        Returns:
            int: The port number.
        """
        return self.Options.Port
    
    def getHostName(self):
        """
        Get the host name.

        Returns:
            str: The host name.
        """
        return self.Options.Hostname
    
    def getReconnectionDelay(self):
        """
        Get the reconnection delay.

        Returns:
            int: The reconnection delay in milliseconds.
        """
        return self.Options.ReconnectDelay
    
    def getHeartbeat(self):
        """
        Get the heartbeat time.

        Returns:
            int: The heartbeat time in milliseconds.
        """
        return self.Options.Heartbeat    
   
    def getTimeout(self):
        """
        Get the timeout time.

        Returns:
            int: The timeout time in milliseconds.
        """
        return self.Options.Timeout    
   
    def setConnState(self, newstate):
        """
        Set the connection state.

        Arguments:
            newstate: The new connection state.
        """
        oldstate = self.m_connstate
        self.m_connstate = newstate
        if self.onStatusChange:
            self.loop.call_soon_threadsafe(self.onStatusChange, [oldstate, newstate])

    def startReconnectionTimer(self):
        """
        Start the reconnection timer.
        """
        if (self.getReconnectionDelay() > 0):
            self.cancelReconnectionTimer()
            self.m_retrytimer = self.preciseTimer(self.loop, self.getReconnectionDelay(), self.getReconnectionDelay(), lambda: self.RetryEventHandler())
            self.m_retrytimer.start()

    def RetryEventHandler(self):
        """
        Handle the retry event.
        """
        if(not self.getCnxState() == DataHubConnectionStatus.Connected):
            self.loop.create_task(self.performConnect())

    def setReconnectionDelay(self, recon_ms):
        """
        Set the reconnection delay.

        Arguments:
            recon_ms: The reconnection delay in milliseconds.
        """
        if (recon_ms >= 0):
            self.Options.ReconnectDelay = recon_ms
            if(self.m_retrytimer is not None):
                self.cancelReconnectionTimer()
                self.startReconnectionTimer()

    def cancelReconnectionTimer(self):
        """
        Cancel the reconnection timer.
        """
        if (self.m_retrytimer is not None):
            self.m_retrytimer.cancel()
            self.m_retrytimer = None
        if (self.getCnxState() != DataHubConnectionStatus.Connected and self.getCnxState() != DataHubConnectionStatus.Connecting):
            self.setConnState(DataHubConnectionStatus.Idle)

    def setUsername(self, username, password):
        """
        Set the username and password.

        Arguments:
            username: The username.
            password: The password.
        """
        self.closeConnection()
        self.Options.Username = username
        self.Options.Password = password

    def setSsl(self, isSSL, acceptInvalidCertificates, clientCertificate):
        """
        Set SSL options.

        Arguments:
            isSSL: Whether to use SSL.
            acceptInvalidCertificates: Whether to accept invalid certificates.
            clientCertificate: The client certificate.
        """
        self.Options.IsSsl = isSSL
        self.Options.AcceptInvalidCertificates = acceptInvalidCertificates
        self.Options.ClientCertificate = clientCertificate

    def setProxyParms(self, proxyHostname, proxyPort, proxyUsername, proxyPassword):
        """
        Set proxy parameters.

        Arguments:
            proxyHostname: The proxy hostname.
            proxyPort: The proxy port.
            proxyUsername: The proxy username.
            proxyPassword: The proxy password.
        """
        self.Options.ProxyHostname = proxyHostname
        self.Options.ProxyPassword = proxyPassword
        self.Options.ProxyPort = proxyPort
        self.Options.ProxyUsername = proxyUsername
    
    def setWebparms(self, httpPort, isHttps):
        """
        Set web parameters.

        Arguments:
            httpPort: The HTTP port.
            isHttps: Whether to use HTTPS.
        """
        self.Options.WebPort = httpPort
        self.Options.IsHttps = isHttps

    def setConnectionParms(self, hostname, port, username=None, password=None, parent_session_id=None):
        """
        Set connection parameters.

        Arguments:
            hostname: The hostname.
            port: The port.
            username: The username. Defaults to None.
            password: The password. Defaults to None.
            parent_session_id: The parent session ID. Defaults to None.
        """
        if isinstance(port, str):
            port = int(port)  # Convert port from string to int if necessary

        # Check if the hostname or port has changed
        if hostname != self.Options.Hostname or port != self.Options.Port:
            self.closeConnection()

        # Update connection parameters
        self.Options.Hostname = hostname
        self.Options.Port = port

        if username is not None and password is not None:
            self.Options.Username = username
            self.Options.Password = password

        if parent_session_id is not None:
            self.Options.ParentSessionId = parent_session_id

    def getPointCache(self):
        """
        Get the point cache.

        Returns:
            dict: The point cache.
        """
        return self.m_datamodel
    
    def registerDomain(self, domainname, flags):
        """
        Register a domain.

        Arguments:
            domainname: The domain name.
            flags: The domain flags.
        """
        return self.sendCommand(f"(report_domain {lp.escaped_string_auto(domainname, True)} {flags})\n")

    def registerPoint(self, point_or_name, create=False):
        """
        Register a point.

        Arguments:
            point_or_name: The point or point name.
            create: Whether to create the point if it doesn't exist. 
            Defaults to False.
        """
        if isinstance(point_or_name, lp.DataHubPoint):
            pointname = point_or_name.Name
        elif isinstance(point_or_name, str):
            pointname = point_or_name
        else:
            raise TypeError("Expected DataHubPoint or str")

        cmd = "creport" if create else "report"
        return self.sendCommand(f"({cmd} {lp.escaped_string_auto(pointname, False)})\n")

    def unregisterPoint(self, point):
        """
        Unregister a point.

        Arguments:
            point: The point or point name.
        """
        if isinstance(point, lp.DataHubPoint):
            pointname = point.name
        else:
            pointname = point
        return self.sendCommand(f"(unreport " + lp.escaped_string_auto(pointname, False) + ")\n")

    def LookupOrCreatePoint(self, point):
        """
        Lookup or create a point.

        Arguments:
            point: The point name.
        Returns:
            DataHubPoint: The point object.
        """
        if isinstance(point, lp.DataHubPoint):
            point = point.name
    
        if point not in self.m_datamodel.keys():
            self.m_datamodel[point] = lp.DataHubPoint(point, None, None, None, 0)
            self.sendCommand(f"(create {lp.escaped_string_auto(point, False)})\n")

        return self.m_datamodel.get(point)
    
    def lookupPoint(self, point):
        """
        Lookup a point.

        Arguments:
            point: The point name.
        Returns:
            DataHubPoint: The point object.
        """
        return self.LookupOrCreatePoint(point)
    
    def createPoint(self, point):
        """
        Create a point.

        Arguments:
            point: The point name.
        Returns:
            DataHubPoint: The created point object.
        """
        return self.LookupOrCreatePoint(point)
    
    def sendCommand(self, message):
        """
        Send a command to the server.

        Arguments:
            message: The command message.
        """
        if not message.endswith('\n'):
            message=message+'\n'

        self.loop.create_task(self.message_queue.put(message))  # Add message to the queue

    def preciseTimer(self, loop, delay, interval, callback, *args, **kwargs):
        """
        Create a precise timer with no drift. The precise timer is 
        slower than the regular timer but is extremely accurate.

        Arguments:
            loop: The event loop.
            delay: The initial delay in milliseconds.
            interval: The interval in milliseconds.
            callback: The callback function.
            *args: Additional arguments for the callback.
            **kwargs: Additional keyword arguments for the callback.
        Returns:
            PreciseTimer: The created precise timer.
        """
        newtimer = PreciseTimer(loop, delay, interval, callback, *args, **kwargs)
        return newtimer

    def Timer(self, loop, delay, interval, callback, *args, **kwargs):
        """
        Create a new timer. This timer is much quicker than the precise timer
        but without the same accuracy.

        Arguments:
            loop: The event loop.
            delay: The delay before the timer starts.
            interval: The interval between timer executions.
            callback: The callback function to execute.
            *args: Additional arguments for the callback.
            **kwargs: Additional keyword arguments for the callback.
        Returns:
            Timer: The created timer.
        """
        newtimer = Timer(loop, delay, interval, callback, *args, **kwargs)
        return newtimer

    def writePoint(self, pointname, value, type = None, seconds = None, nanoseconds = None, quality = None, create = None, force = None):
        """
        Write a value to a point.

        Arguments:
            pointname: The name of the point.
            value: The value to write.
            type: The type of the point.
            seconds: The seconds part of the timestamp.
            nanoseconds: The nanoseconds part of the timestamp.
            quality: The quality of the point.
            create: Whether to create the point if it doesn't exist.
            force: Whether to force the write.
        """
        if type == None:
            if isinstance(value, str):
                type = lp.PointType.STRING
            elif isinstance(value, int):
                type = lp.PointType.INT64
                value = str(value)
            elif isinstance(value, float):
                type = lp.PointType.REAL
                value = str(value)
        if seconds == None:
            seconds = 0
        if nanoseconds == None:
            nanoseconds = 0
        if quality == None:
            quality = lp.PointQuality.GOOD    
        if create == None:
            create = True
        if force == None:
            force = False
        if type == lp.PointType.STRING:
            value = str(value)

        self.LookupOrCreatePoint(pointname)
        self.performWritePoint(pointname, type, value, seconds, nanoseconds, quality, create, force)
        
    def performWritePoint(self, pointname, point_type, strval, seconds, nanoseconds, quality, create, force):
        """
        Perform the actual write to a point. This is called by WritePoint.

        Arguments:
            pointname: The name of the point.
            point_type: The type of the point.
            strval: The value to write.
            seconds: The seconds part of the timestamp.
            nanoseconds: The nanoseconds part of the timestamp.
            quality: The quality of the point.
            create: Whether to create the point if it doesn't exist.
            force: Whether to force the write.
        Returns:
            The result of the sendCommand function.
        """
        command = "cwrite" if create else "write"
        escaped_pointname = lp.escaped_string_auto(pointname, False)
        escaped_strval = lp.escaped_string_auto(strval, True) if point_type == lp.PointType.STRING else strval
        return self.sendCommand(f"({command} {escaped_pointname} {point_type} {escaped_strval} 100 0 0 {seconds} {nanoseconds} 0 {quality})")

    def initializePointCache(self, model=None):
        """
        Initialize the point cache.

        Arguments:
            model: The data model to use for initialization.
        """
        if model is not None:
            self.m_datamodel = model
        elif self.m_datamodel is None:
            self.m_datamodel = dict()
    
    def getDefaultDomain(self):
        """
        Get the default domain.

        Returns:
            The default domain.
        """
        return self.Options.DefaultDomain

    def shutdown(self):
        """
        Shutdown the connection.
        """
        self.closeConnection()
        self.cancelHeartbeatTimers()
        self.cancelReconnectionTimer()
        self.cancelDomainListTimer()
        self.setConnState(DataHubConnectionStatus.Terminated)

    def changeType(self, valueType, stringValue):
        """
        Change the type of a value.

        Arguments:
            valueType: The type to change to.
            stringValue: The value as a string.
        Returns:
            The value converted to the specified type.
        """
        if valueType == 2:
            return int(stringValue)
        elif valueType == 1:
            return float(stringValue)
        else:
            return stringValue

    def mathPointValue(self, operation, pointname, value, sec, nsec):
        """
        Perform a mathematical operation on a point value.

        Arguments:
            operation: The operation to perform.
            pointname: The name of the point.
            value: The value to use in the operation.
            sec: The seconds part of the timestamp.
            nsec: The nanoseconds part of the timestamp.
        Returns:
            The result of the sendCommand function.
        """
        return self.sendCommand(f"({operation} {lp.escaped_string_auto(pointname, False)} {value} {sec} {nsec})")
    
    def dividePointValue(self, point, value):
        """
        Divide a point value.

        Arguments:
            point: The point to divide.
            value: The value to divide by.
        Returns:
            The result of the mathPointValue function.
        Throws:
            TypeError: If the point is not of type DataHubPoint or str.
        """
        if isinstance(point, lp.DataHubPoint):
            return self.mathPointValue("div", point.name, value, point.seconds, point.nanoseconds)
        elif isinstance(point, str):
            return self.mathPointValue("div", point, value, 0, 0)
        else:
            raise TypeError("point must be of type DataHubPoint or str")

    def multiplyPointValue(self, point, value):
        """
        Multiply a point value.

        Arguments:
            point: The point to multiply.
            value: The value to multiply by.
        Returns:
            The result of the mathPointValue function.
        Throws:
            TypeError: If the point is not of type DataHubPoint or str.
        """
        if isinstance(point, lp.DataHubPoint):
            return self.mathPointValue("mult", point.name, value, point.seconds, point.nanoseconds)
        elif isinstance(point, str):
            return self.mathPointValue("mult", point, value, 0, 0)
        else:
            raise TypeError("point must be of type DataHubPoint or str")

    def addPointValue(self, point, value):
        """
        Add a value to a point.

        Arguments:
            point: The point to add to.
            value: The value to add.
        Returns:
            The result of the mathPointValue function.
        """
        if isinstance(point, lp.DataHubPoint):
            point = point.PointName
            seconds = point.Seconds
            nanoseconds = point.Nanoseconds
        else:
            seconds = 0
            nanoseconds = 0

        return self.mathPointValue("add", point, value, seconds, nanoseconds)

    def appendPointValue(self, point, value):
        """
        Append a value to a point.

        Arguments:
            point: The point to append to.
            value: The value to append.
        Returns:
            The result of the sendCommand function.
        """
        if isinstance(point, lp.DataHubPoint):
            point = point.PointName
        return self.sendCommand(f"(append {lp.escaped_string_auto(point, False)} {lp.escaped_string_auto(value, True)} 0 0)")
        
    def setPointTimeStamp(point, datetime_obj):
        """
        Set the timestamp of a point.

        Arguments:
            point: The point to set the timestamp for.
            datetime_obj: The datetime object representing the timestamp.
        
        Throws:
            TypeError: If the point is not of type DataHubPoint.
        """
        if isinstance(point, lp.DataHubPoint):
            point.setTimeStamp(datetime_obj)
        else:
            raise TypeError("point must be of type DataHubPoint")

    def sendConnectionCommands(self):
        """
        Send the initial connection commands.
        """
        self.sendWantSuccess()
        self.sendLogin()
        self.setDefaultDomain(self.Options.DefaultDomain)
        self.sendHeartbeatTimes()
        self.startHeartbeatTimers()
        self.startDomainListTimer()

    def Connection_ConnectFailed(self, host, port):
        """
        Handle a failed connection attempt.

        Arguments:
            host: The host that was attempted to connect to.
            port: The port that was attempted to connect to.
        """
        if (self.m_retrytimer is not None):
            self.setConnState(DataHubConnectionStatus.RetryWait)
        else:
            self.setConnState(DataHubConnectionStatus.Disconnected)
        
        if self.onConnectionFailure:
            self.loop.call_soon_threadsafe(self.onConnectionFailure, [host, port])
    
    def Connection_ConnectSucceeded(self, host, port):
        """
        Handle a successful connection attempt.

        Arguments:
            host: The host that was connected to.
            port: The port that was connected to.
        """
        self.setConnState(DataHubConnectionStatus.Connected)
        self.sendConnectionCommands()
        if self.onConnectionSuccess:
            self.loop.call_soon_threadsafe(self.onConnectionSuccess, [host, port])

    def Connection_Connecting(self, host, port):
        """
        Handle an ongoing connection attempt.

        Arguments:
            host: The host that is being connected to.
            port: The port that is being connected to.
        """
        self.setConnState(DataHubConnectionStatus.Connecting)
        if self.onConnecting:
            self.loop.call_soon_threadsafe(self.onConnecting, [host, port])

    def closeConnection(self):
        """
        Close the connection.
        """
        if self.getCnxState() == DataHubConnectionStatus.Connected:
            self.writer.close()
            self.setConnState(DataHubConnectionStatus.Disconnected)
            self.runCallback(self.onDisconnected)

