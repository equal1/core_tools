import numpy as np

import core_tools as ct
from core_tools.sweeps.scans import Scan, sweep, Function, Break

from qcodes import ManualParameter
from qcodes.parameters.specialized_parameters import ElapsedTimeParameter

# %% -- Initialisation --
# In order to get started with core-tools measurements, some configuration is
#  required. This includes information about your setup, as well as where to store
#  the collected data. You can use the specified .yml file as a reference.

ct.configure("./setup_config/ct_config_measurement_minimal.yml")

# Use the DataBrowser for user-friendly access to your collected data.
ct.launch_qt_databrowser()


# %% -- Defining parameters --
# Core-tools builds on the qcodes Parameter interface for data acquisition. To learn
#  more about qcodes, check out their "15 minutes of QCoDeS" documentation.

# ManualParameters are good for demonstrations because they are not associated with
#  measurement hardware
x = ManualParameter("x", initial_value=0)
y = ManualParameter("y", initial_value=9)

# ElapsedTimeParameters collect the real time that has elapsed since its last reset.
t = ElapsedTimeParameter("t")


# %% -- Running a measurement --
# Core-tools measurements are defined by Scans. A Scan is constructed from one or
#  more qcodes Parameters, which can Set or Get data (similar to how typical
#  electrical measurement can either Force or Sense on a line).

# Sweep() defines a range of values that the parameter should set, one by one. It
#  is possible to sweep multiple parameters. Nested sweeps are ordered the same way
#  that nested for-loops are:

# The Scan defined below will perform the following measurement:
#  The parameter 'y' will be set to 7 points between 1 and 100, spaced equally on a
#  logarithmic scale. (roughly: 1, 2.15, 4.64, 10, 21.5, 46.4, 100)
#  For each value of 'y', the parameter 'x' will be set to 11 points between -20 and
#  20, spaced linearly. (-20, -16, -12, etc...)
#  At each value for 'y' and 'x', parameter 't' will record how much time has
#  passed since the last timer reset.

scan1 = Scan(
    sweep(y, np.geomspace(1, 100, 7), delay=0.5),
    sweep(x, -20, 20, 11, delay=0.1),
    # identical: sweep(x, np.linspace(-20, 20, 11), delay=0.1)
    t,
    name="test_scan",
    silent=True,
)

t.reset_clock()  # Don't forget to reset the timer before measurement.
dataset1 = scan1.run()

# side-note: it's fine to define and run a scan at once, instead of using the
#  intermediary steps like above:
#
#  t.reset_clock()
#  dataset = Scan(...).run()

# %% -- Inspecting measurement data --
# You can inspect the newly generated data in your DataBrowser. Here you can clearly
#  see the order of the sweeps, with the data along the x-axis being much closer
#  together.

# The DataBrowser is good for visual representation and organisation, but if you
#  want to work with your data, the core-tools DataSet object we called 'dataset1'
#  is not the easiest to work with.
# As an alternative, core-tools provides an exporting tool, allowing you to export
#  your core-tools data into a DataArray from the commonly used x-array package.

from core_tools.data.ds.ds2xarray import ds2xarray

ds1x = ds2xarray(dataset1)

# Here, ds1x is an x-array DataArray, which you can inspect in all the usual ways.
# For more info on DataArray objects, see the x-array documentation.

print(ds1x)


# %% -- Retrieving measurement data --
# In the previous section, we had access to our measurement data through the
#  'dataset1' DataSet object. If you need to access the same data at a later date,
#  this can be done through retrieval by UUID (Universal Unique IDentifier).

# You can find the UUID either in your DataBrowser, or by extracting it from a
#  datasets 'exp_uuid' parameter.

dataset_uuid = dataset1.exp_uuid

# The dataset can then be retrieved with the following helper method:

from core_tools.data.ds.data_set import load_by_uuid

retrieved_dataset = load_by_uuid(dataset_uuid)

print(retrieved_dataset)

# %% -- Example Scans: Nested Scans --
# ...

t.reset_clock()

ds_inner = []
def inner_scan():
    ds = Scan(
        sweep(x, -20, 20, 11, delay=0.01),
        t,
        name="test_inner_scan",
        silent=True,
        ).run()
    ds_inner.append(ds)


ds2 = Scan(
    sweep(y, -1, 1, 3, delay=0.2),
    Function(inner_scan),
    t,
    reset_param=True,
    name="outer_scan"
).run()


# %% -- Example Scans: Scan with Break --
# ...

def check_x(last_values, dataset):
    max_x = max(dataset.m1.x())
    if max_x > 4:
        raise Break(f"max x = {max_x}. Last {last_values}")


ds3 = Scan(
    sweep(x, -20, 20, 11, delay=0.1),
    t,
    Function(check_x, add_dataset=True, add_last_values=True),
    name="test_break"
).run()


# %% -- Example Scans: Scan with Timeout --
# ...

def check_t(last_values):
    # abort after 0.5 s
    t = last_values["t"]
    if t > 0.5:
        raise Break(f"t={t:5.2f} s")


t.reset_clock()


ds4 = Scan(
    sweep(x, -20, 20, 11, delay=0.1),
    sweep(y, -1, 1, 3),
    t,
    Function(check_t, add_last_values=True),
    name="test_break_2D"
).run()


# %% -- Example Scans: 2D Scan --
# ...

ds5 = Scan(
    sweep(x, -20, 20, 21),
    sweep(y, -10, 10, 41, delay=0.001),
    t,
    name="test_2D",
).run()


# %% -- Example Scan: Nested Scans --
# ...

from core_tools.sweeps.sweeps import do1D

t.reset_clock()

ds_inner2 = []
def inner_scan_do1D():
    ds = do1D(
        x, -20, 20, 11, 0.01,
        t,
        name="test_inner_do1D",
        silent=True,
    ).run()
    ds_inner2.append(ds)


ds6 = Scan(
    sweep(y, -1, 1, 5, delay=0.2),
    Function(inner_scan_do1D),
    t,
    name="Scan with inner scan",
    reset_param=True,
).run()


# %% -- Example Scans: Scans with Delegate Parameters --
# ...

from qcodes import DelegateParameter

i1 = ManualParameter("i1", initial_value=0)
i2 = ManualParameter("i2", initial_value=0)
v1 = ManualParameter("v1", initial_value=0)

current = ManualParameter("I", initial_value=0)
current1 = DelegateParameter("I1", current, label="I1")

ds11 = Scan(
        sweep(i1, range(1, 3)),
        sweep(i2, range(1, 5)),
        current,
        sweep(v1, -500, -1100, 30),
        current1,
        name='Scan with delegate parameter',
        reset_param=True).run()


# %% -- Example Scans: Putting it all together --
# ...

from core_tools.sweeps.scans import Section
from qcodes import DelegateParameter, Parameter

i1 = ManualParameter("i1", initial_value=0)
i2 = ManualParameter("i2", initial_value=0)
v1 = ManualParameter("v1", initial_value=0)
v2 = ManualParameter("v2", initial_value=0)
v3 = ManualParameter("v3", initial_value=0)


def get_current():
    return -0.001 * (v1() + v2() + v3())


meas_param = Parameter("I", unit="uA", get_cmd=get_current)


def param_alias(param, name):
    return DelegateParameter(name, param, label=name)


def break_at(param_name, Imax, resume_at):
    def check_break(last_values):
        I = last_values[param_name]
        if I > Imax:
            raise Break(f"I: {I}", resume_at_label=resume_at)
    return Function(check_break, add_last_values=True)


def reset_voltage():
    v1(0.0)


ds11 = Scan(
        sweep(i1, range(1, 16)),
        sweep(i2, range(1, 10), label="i2"),
        Section(
            sweep(v1, -500, -1100, 100, delay=0.001),
            param_alias(meas_param, "I1"),
            break_at("I1", Imax=0.8, resume_at="v2"),
        ),
        Section(
            sweep(v2, -500, -1100, 100, value_after="start", delay=0.01, label="v2"),
            param_alias(meas_param, "I2"),
        ),
        Section(
            sweep(v3, -500, -1100, 100, value_after="start", delay=0.01),
            param_alias(meas_param, "I3"),
        ),
        Function(reset_voltage),
        name='Scan with sections',
        reset_param=True).run()


ds11

