from random import random

import DataHubConnection as DataHubConnection

import asyncio
from threading import Timer
import time

class MyConnection(DataHubConnection.DataHubConnection):
    """
    Custom connection class inheriting from DataHubConnection.

    Arguments:
        model: An instance of ModelEmitter associated with this 
        connection.
    """
    def __init__(self, loop):
        """Initialize the MyConnection object."""
        super().__init__(loop)
        self.model = DataHubConnection.ModelEmitter(self)

class PID:
    """
    Represents a PID controller.

    Attributes:
        domain (str): The domain name.
        name (str): The base name of the PID controller.
        conn: The connection associated with the PID controller.
        sp (float): Setpoint value.
        mv (float): Manipulated variable.
        pv (float): Process variable.
        ckd (float): Controller Kd value.
        cki (float): Controller Ki value.
        ckp (float): Controller Kp value.
        pki (float): Plant Ki value.
        pkp (float): Plant Kp value.
        amplitude (float): Amplitude value.
        offset (float): Offset value.
        automode (int): Auto mode flag.
        autotime (int): Auto time value.
        autotimeMs (int): Auto time in milliseconds.
        updatefrequency (int): Update frequency value.
        errorInt (float): Integral error.
        errorPrev (float): Previous error.
        errorDrv (float): Derivative error.
        setpointTimer: Timer for setpoint updates.
        mvPvTimer: Timer for MV and PV updates.
        dt (float): Time delta.
        next_call (float): Next call time.
        me: Model emitter.
    """
    def __init__(self, domain, basename, conn):
        """
        Initialize the PID object.

        Arguments:
            domain: The domain name.
            basename: The base name of the PID controller.
            conn: The connection associated with the PID controller.
        """
        self.name = basename
        self.domain = domain
        self.conn = conn

        self.sp = 50
        self.spTag = f"{basename}.Sp"
        self.mv = 0
        self.mvTag = f"{basename}.Mv"
        self.pv = 0
        self.pvTag = f"{basename}.Pv"

        self.ckd = 0.01
        self.ckdTag = f"{basename}.Controller.Kd"
        self.cki = 0.5
        self.ckiTag = f"{basename}.Controller.Ki"
        self.ckp = 0.25
        self.ckpTag = f"{basename}.Controller.Kp"

        self.pki = 0.5
        self.pkiTag = f"{basename}.Plant.Ki"
        self.pkp = 2
        self.pkpTag = f"{basename}.Plant.Kp"

        self.amplitude = 100
        self.amplitudeTag = f"{basename}.Range.Amplitude"
        self.offset = 50
        self.offsetTag = f"{basename}.Range.Offset"

        self.automode = 1
        self.automodeTag = f"{basename}.Setpoint.AutoMode"
        self.autotime = 5
        self.autotimeMs = 5000
        self.autotimeTag = f"{basename}.Setpoint.AutoTime"

        self.updatefrequency = 10
        self.updatefrequencyTag = f"{basename}.UpdateFrequency"

        self.errorInt = 0
        self.errorPrev = 0
        self.errorDrv = 0
        self.setpointTimer = None
        self.mvPvTimer = None

        self.dt = 0
        self.next_call = 0.01
        self.me = None

def qualify(client, pointname):
    """
    Qualify a point name with the client's domain.

    Arguments:
        client: The DataHub client.
        pointname: The point name to qualify.
    Returns:
        str: The qualified point name.
    """
    return f"{client.domain}:{pointname}"

def unqualifyName(pointname: str) -> str:
    """
    Remove the domain prefix from a point name.

        pointname: The qualified point name.
    Returns:
        str: The unqualified point name.
    """
    if pointname is not None:
        indx = pointname.find(':')
        if indx != -1:
            pointname = pointname[indx + 1:]
    return pointname

def updateOnPointChange(point, name, pid, dhclient):
    """
    Update PID attributes based on point changes.

    Arguments:
        point: The point that changed.
        name: The name of the attribute to update.
        pid: The PID controller.
        dhclient: The DataHub client.
    """
    if pid.name in point.name:
        if getattr(pid, name) == unqualifyName(point.name):
            setattr(pid, name.replace('Tag', ''), point.value)

    if "UpdateFrequency" in point.name:
        reset_timer(loop, dhclient, pid, pid.autotime)
    
    if "AutoTime" in point.name:
        pid.autotimeMs = pid.autotime * 1000
        reset_timer(loop, dhclient, pid, pid.autotime)

def pid_create_points(client, pid):
    """
    Create points for the PID controller.

    Arguments:
        client: The DataHub client.
        pid: The PID controller.
    """
    for attr in ['sp', 'mv', 'pv', 'ckd', 'cki', 'ckp', 'pki', 'pkp', 'amplitude', 'offset', 'automode', 'autotime', 'updatefrequency']:
        name = attr + "Tag"
        point = qualify(client,  getattr(pid, name))
        client.model.map_point(point)


def output_point(pid, name, value):
    """
    Output a point value.

    Arguments:
        pid: The PID controller.
        name: The name of the point.
        value: The value to output.
    """
    pid.conn.writePoint(name, value)

def pid_calculate(pid):
    """
    Calculate the manipulated variable (MV) for the PID controller.

    Arguments:
        pid: The PID controller.
    Returns:
        float: The calculated MV.
    """
    hilimit = pid.offset + pid.amplitude / 2
    lolimit = 0  

    err = pid.sp - pid.pv

    pid.errorInt += err * pid.dt * pid.cki
    pid.errorInt = max(min(pid.errorInt, hilimit), lolimit)

    pid.errorDrv = (err - pid.errorPrev) / pid.dt * pid.ckd

    pid.mv = pid.ckp * err + pid.errorInt + pid.errorDrv
    pid.mv = max(min(pid.mv, hilimit), lolimit)

    pid.errorPrev = err

    return pid.mv

def pid_calculate_procvar(pid):
    """
    Calculate the process variable (PV) for the PID controller.

    Arguments:
        pid: The PID controller.
    Returns:
        float: The calculated PV.
    """
    hilimit = pid.offset + pid.amplitude / 2
    lolimit = pid.offset - pid.amplitude / 2
    newval = pid.pv + ((pid.mv * pid.pkp) - pid.pv) * pid.pki * pid.dt
    pid.pv = max(min(newval, hilimit), lolimit)

    return pid.pv

def update_setpoint(pid):
    """
    Update the setpoint (SP) for the PID controller.

    Arguments:
        pid: The PID controller.
    """
    if pid.automode == 1:
        pid.sp = (pid.offset - pid.amplitude / 2 + random()) * pid.amplitude
        output_point(pid, "DataPid:" + pid.spTag, pid.sp)

def update_pids(pid):
    """
    Update the PID controller.

    Arguments:
        pid: The PID controller.
    """
    recalculate_dt(pid)
    change_controller(pid)
    change_procvar(pid)

def recalculate_dt(pid):
    """
    Recalculate the time delta (dt) for the PID controller.

    Arguments:
        pid: The PID controller.
    """
    if pid.dt == 0:
        pid.dt = pid.next_call
        pid.next_call = time.perf_counter()
    else:
        pid.dt = time.perf_counter() - pid.next_call 
        pid.next_call = time.perf_counter()


def change_controller(pid):
    """
    Change the manipulated variable (MV) for the PID controller.

    Arguments:
        pid: The PID controller.
    """
    pid.mv = pid_calculate(pid)
    output_point(pid, "DataPid:" + pid.mvTag, pid.mv)

def change_procvar(pid):
    """
    Change the process variable (PV) for the PID controller.

    Arguments:
        pid: The PID controller.
    """
    pid.pv = pid_calculate_procvar(pid)
    output_point(pid, "DataPid:" + pid.pvTag, pid.pv)

def have_connection(client : MyConnection, allpids):
    """
    Handle a successful connection.

    Arguments:
        client: The DataHub client.
        allpids: List of all PID controllers.
    """
    print(f"Connection succeeded on {client.name}")
    # Mark all data from this connection as Not Connected when the connection is lost
    client.sendCommand("(set_authoritative 1)")

    # Register all points for the PID controllers and transmit the model to create a data point hierarchy.
    for pid in allpids:
        register_pid(client, pid, True)
        outputControlPoints(client, pid)
    client.model.emit()

def lost_connection(client, allpids):
    """
    Handle a lost connection.

    Arguments:
        client: The DataHub client.
        allpids: List of all PID controllers.
    """
    print(f"Connection lost for {client.name}")
    for pid in allpids:
        register_pid(client, pid, False)

def register_pid(client, pid, is_register):
    """
    Register or unregister points for the PID controller.

    Arguments:
        client: The DataHub client.
        pid: The PID controller.
        is_register: Whether to register or unregister the points.
    """
    for attr in ['spTag', 'mvTag', 'pvTag', 'ckdTag', 'ckiTag', 'ckpTag', 'pkiTag', 'pkpTag', 'amplitudeTag', 'offsetTag', 'automodeTag', 'autotimeTag', 'updatefrequencyTag']:
        point = qualify(client, getattr(pid, attr))
        if is_register:
            client.registerPoint(point, True)
        else:
            client.unregisterPoint(point)

def reset_timer(loop, client, pid, timeoutSecs):
    """
    Reset the timers for the PID controller.

    Arguments:
        loop: The event loop.
        client: The DataHub client.
        pid: The PID controller.
        timeoutSecs: The timeout in seconds.
    """
    if not isinstance(timeoutSecs, (int, float)):
        timeoutSecs = 5

    if pid.setpointTimer:
        delete_timer(pid.setpointTimer)
        pid.setpointTimer = None

    if pid.mvPvTimer:
        delete_timer(pid.mvPvTimer)
        pid.mvPvTimer = None

    if timeoutSecs > 0:
        pid.setpointTimer = client.Timer(loop, 1, pid.autotimeMs, lambda: update_setpoint(pid))
        pid.setpointTimer.start()
        pid.mvPvTimer = client.Timer(loop, 1, 1000/pid.updatefrequency, lambda: update_pids(pid))
        pid.mvPvTimer.start()

def delete_timer(timer):
    """
    Delete a timer.

    Arguments:
        timer: The timer to delete.
    """
    timer.stop()

def start_client(loop, host, port, domain, name, allpids):
    """
    Start a DataHub client.

    Arguments:
        loop: The event loop.
        host: The host address.
        port: The port number.
        domain: The domain name.
        name: The name of the client.
        allpids: List of all PID controllers.
    Returns:
        MyConnection: The started client.
    """
    print(f"Create client {name} to {host}:{port} in domain {domain}")
    client = MyConnection(loop)
    client.onConnected = lambda: have_connection(client, allpids)
    client.onDisconnected = lambda: lost_connection(client, allpids)
    client.onLog = lambda severity, message: print(f"{severity}: {message}")
    client.name = name
    client.domain = domain
    client.setConnectionParms(host, port)
    client.setHeartbeatTimes(5000, 15000)
    client.setReconnectionDelay(30000)
    return client

def RegisterPointChangeCallback(pid, sym, dhclient):
    """
    Register a callback for point change events.

    Arguments:
        pid: The PID controller.
        sym: The symbol name.
        dhclient: The DataHub client.
    """
    qualifed = qualify(dhclient, getattr(pid, sym))
    point = dhclient.lookupPoint(qualifed)
    point.AddOnPointChangeMethod(lambda x: updateOnPointChange(x, sym, pid, dhclient))

def outputControlPoints(client, pid):
    """
    Output control points for the PID controller.

    Arguments:
        client: The DataHub client.
        pid: The PID controller.
    """
    for attr in ['ckd', 'cki', 'ckp', 'pki', 'pkp', 'amplitude', 'offset', 'automode', 'autotime', 'updatefrequency']:
        name = attr + "Tag"
        point = qualify(client,  getattr(pid, name))
        value =  getattr(pid, attr)
        output_point(pid, point, value)

async def main(loop):
    """
    Main function to run the PID controllers.

    Arguments:
        loop: The event loop.
    """
    try:    
        host_name = "localhost"
        port_name = "4502"
        domain = "DataPid"
        allpids = []
        allpids2 = []

        dhclient1 = start_client(loop, host_name, port_name, domain, "PID Controller 1", allpids)
        dhclient2 = start_client(loop, host_name, port_name, domain, "PID Controller 2", allpids2)

        for pidname in ["PID1", "PID2", "PID3", "PID4"]:
            pid = PID(domain, pidname, dhclient1)
            allpids.append(pid)
            pid_create_points(dhclient1, pid)
            attributes = ['sp', 'mv', 'pv', 'ckd', 'cki', 'ckp', 'pki', 'pkp', 'amplitude', 'offset', 'automode', 'autotime', 'updatefrequency']
            for attr in attributes:
                sym = attr + "Tag"
                RegisterPointChangeCallback(pid, sym, dhclient1)
            reset_timer(loop, dhclient1, pid, pid.autotime)

        for pidname in ["PID5", "PID6", "PID7", "PID8"]:
            pid = PID(domain, pidname, dhclient2)
            allpids2.append(pid)
            pid_create_points(dhclient2, pid)
            attributes = ['sp', 'mv', 'pv', 'ckd', 'cki', 'ckp', 'pki', 'pkp', 'amplitude', 'offset', 'automode', 'autotime', 'updatefrequency']
            for attr in attributes:
                sym = attr + "Tag"
                RegisterPointChangeCallback(pid, sym, dhclient2)
            reset_timer(loop, dhclient2, pid, pid.autotime)

        asyncio.create_task(dhclient1.connect())
        asyncio.create_task(dhclient2.connect())

        
        while True:
            await asyncio.sleep(1)
        
    except KeyboardInterrupt:
        print("Interrupt")
        dhclient1.shutdown()
        dhclient2.shutdown()

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        loop.run_until_complete(main(loop))  # Start the main function
    except KeyboardInterrupt:
        print("Main program terminated by user.")
    except Exception as e:
        print(f"An error occurred: {e}")
 