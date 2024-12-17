import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.widgets import Button
from datetime import datetime, timedelta
import DataHubConnection as DataHubConnection
import lispparse as lp
import asyncio

class MyConnection(DataHubConnection.DataHubConnection):
    """
    Custom connection class inheriting from DataHubConnection.

    Arguments:
        model: An instance of ModelEmitter associated with this connection.
    """
    def __init__(self, loop):
        """
        Initialize the MyConnection object.

        Arguments:
            loop: The event loop.
        """     
        super().__init__(loop)
        self.model = DataHubConnection.ModelEmitter(self)
        self.points = dict()
        self.latest_timestamp = datetime.now()

class Trace:
    """
    Class representing a trace for plotting.

    Attributes:
        name: The name of the trace.
        x: The x data points.
        y: The y data points.
        square: Whether the trace should be a square wave.
        extend: Whether the trace should extend the last value.
    """
    def __init__(self, name, square=False, extend=False):
        """
        Initialize the Trace object.

        Arguments:
            name: The name of the trace.
            square: Whether the trace should be a square wave.
            extend: Whether the trace should extend the last value.
        """
        self.name = name
        self.x = []
        self.y = []
        self.square = square
        self.extend = extend

def start_client(loop, host, port, name):
    """
    Create and configure a DataHub client connection.

    Arguments:
        loop: The event loop.
        host: The host address.
        port: The port number.
        name: The name of the connection.
    Returns:
        MyConnection: The configured client connection.
    """
    print(f"Create client {name} to {host}:{port}")
    client = MyConnection(loop)
    client.onConnected = lambda: have_connection(client)
    client.onDisconnected = lambda: lost_connection(client)
    client.onPointChange = lambda x: on_point_changed(client, x)
    client.onLog = lambda severity, message: print(f"{severity}: {message}")
    client.name = name
    client.setConnectionParms(host, port)
    client.setHeartbeatTimes(5000, 15000)
    client.setReconnectionDelay(30000)
    return client

def lost_connection(client):
    """
    Print out that the connection was lost.

    Arguments:
        client: The DataHub client.
    """
    print(f"Connection lost for {client.name}")

def have_connection(client):
    """
    Register points with the DataHub client upon connection.

    Arguments:
        client: The DataHub client.
    """
    print(f"Connection succeeded on {client.name}")
    registerPoint(client, "DataPid:PID1.Mv", False, False)
    registerPoint(client, "DataPid:PID1.Pv", False, False)
    registerPoint(client, "DataPid:PID1.Sp", True, True)

def registerPoint(client, point_name, square=False, extend=False):
    """
    Register a point with the DataHub client.

    Arguments:
        client: The DataHub client.
        point_name: The name of the point.
        square: Whether the trace should be a square wave.
        extend: Whether the trace should extend the last value.
    """
    client.registerPoint(point_name)
    client.points[point_name] = Trace(point_name, square, extend)
    traceDictionary[point_name] = ax.plot([], [], lw=2, label=point_name)
    plt.legend()

def on_point_changed(client, point):
    """
    Handle point change events and update trend data.

    Arguments:
        client: The DataHub client.
        point: The point that changed.
    """
    timestamp = datetime.fromtimestamp(point[0].timestamp)
    client.defaultOnPointChange(point)
    client.latest_timestamp = timestamp
    trace = client.points.get(point[0].name, None)
    if trace is not None:
        if trace.square and len(trace.y) > 0:
            trace.x.append(timestamp)
            trace.y.append(trace.y[-1])
        #if an extension happened, but it has a value for that extended timestamp, remove it
        elif not trace.square and trace.extend and len(trace.x) > 0:
            if trace.x[-1] == timestamp:
                trace.x.pop()
                trace.y.pop()
        trace.x.append(timestamp)
        trace.y.append(point[0].value)
    for value in client.points.values():
        if value.extend and value.name != point[0].name and len(value.y) > 0:
            value.x.append(timestamp)
            value.y.append(value.y[-1])

def update_plot(client):
    """
    Update the plot with new data.

    Arguments:
        client: The DataHub client.
    """
    for point, trace in traceDictionary.items():
        x_data = client.points[point].x
        y_data = client.points[point].y
        trace[0].set_data(x_data[:len(y_data)], y_data)

    # Define the current time window for a 1-minute scroll
    # Update x-axis limits to create a scrolling effect
    end_time = client.latest_timestamp
    start_time = end_time - timedelta(seconds=window_size)
    ax.set_xlim(start_time, end_time)

    fig.canvas.draw()
    fig.canvas.flush_events()

traceDictionary = dict()

# Create the plot
fig, ax = plt.subplots()
ax.set_ylim(0, 100)
ax.set_xlabel('Timestamp')
ax.set_ylabel('Value')
ax.set_title('Trend Chart')

# Format x-axis for timestamps
ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
ax.xaxis.set_major_locator(mdates.AutoDateLocator())
fig.autofmt_xdate()  # Rotate date labels
plt.legend()
window_size = 60  # 1 minute in seconds

current_time = datetime.now()
# Set initial x-axis limits to the current time and current time minus 1 minute
start_time = current_time - timedelta(minutes=1)
ax.set_xlim(start_time, current_time)
# Function to update the plot

async def main():
    """
    Main function to run everything.
    """
    loop = asyncio.get_event_loop()

    host_name = "localhost"
    port_name = "4502"
    dhclient = start_client(loop, host_name, port_name, "Trend Chart connection")

    asyncio.create_task(dhclient.connect())
    
    # Start the data collection and plot update concurrently
    while True:
        update_plot(dhclient)  # Update the plot with new data
        plt.pause(0.01)  # Allow Matplotlib to process events (non-blocking)
        await asyncio.sleep(0.01)  # Async sleep

# Run the event loop
if __name__ == "__main__":
    asyncio.run(main())  # Run the main async function
