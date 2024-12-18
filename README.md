
# Python DataHub API

This repository contains a Python implementation for connecting to the Cogent DataHub, along with examples of writing data using a PID Controller, as well as reading data and updating live to a Trend Chart.





## Contents
[Features](#Features)

[Components](#Components)

[Installation](#Installation)

[Usage/Examples](#Examples)

[Documentation](#Documentation)

[License](#License)



## Features

- Connection to the Cogent DataHub: Establishes a connection to the DataHub API.
- Real-time Data Visualization: Demonstrates how to read and plot data points in real-time, using Matplotlib.
- PID Controller: Demonstrates how to continuously write data points to the DataHub by creating a PID Controller. 




## Components

- DataHubConnection.py 
    - Provides classes and methods to establish and manage connections to the DataHub.

- lispparse.py
    - Contains utilities for parsing and handling LISP-like syntax used by DataHub commands.

- PID.py
    - Demonstrates how to continuously write data points to the DataHub by creating multiple PID Controllers. 

- TrendChart.py
    - A real-time data visualization tool based on Matplotlib, that reads data from the DataHub.

    
## Installation

Ensure you have Python 3 or later installed.

You may install the repository using pip from your command line:

```bash
pip install PythonDataHubAPI 
```

 


    

## Examples

1. Ensure your DataHub instance is running, and accepting connections, for this example, on port 4502. If you need to install the DataHub, you can find it [here](https://cogentdatahub.com/download/).

2. Navigate to the downloaded PythonDataHubAPI folder. In here, there are 2 example files, PID.py, and TrendChart.py.

3. Run PID.py, using bash:
```bash
python PID.py
```
4. In the DataHub, navigate to the Data Browser. You will see that a DataPid domain was created, along with 8 sample PID Controllers. This is sampling 8 live PID controllers pushing live data, using the python DataHub connection.

5. While leaving the PID simulator running, open a new command prompt. Once again, navigate to the PythonDataHubAPI folder. this time, run Trendchart.py, using bash:
```bash
python TrendChart.py
```

6. A TrendChart should appear, drawing out the live data from the first PID controller that you are simulating, using PID.py. The points can be compared between the Data Browser in the DataHub, and the TrendChart. You can see the points updating live, using the Python API. 


## Documentation
Please refer to the documentation link below for an in depth view of the DataHubConnection, PID controller, TrendChart and lispparse. 

[Documentation](https://linktodocumentation)


## License

MIT License

Copyright (c) 2024 Cogent DataHub

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

