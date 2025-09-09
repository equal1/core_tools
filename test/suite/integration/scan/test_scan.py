from math import isclose
from itertools import product, chain

import core_tools as ct
from core_tools.sweeps.scans import Scan, sweep
from core_tools.sweeps import sweeps
from core_tools.data.ds.ds2xarray import ds2xarray

import numpy as np
from qcodes.parameters import Parameter


def test_scan_0d_for_correct_data():
    # -- initialise --
    ct.configure("test/suite/integration/scan/ct_config_tests.yml")

    name = "test_scan_0d"
    x = Parameter(
        name="x",
        initial_value=0,
        get_cmd=lambda: 1,
        set_cmd=None,
    )

    # -- perform --
    ds = sweeps.do0D(x, name=name, silent=True).run()
    dxs = ds2xarray(ds, snapshot=None)

    # -- validate --
    assert isclose(dxs.x.values, 1)
    assert dxs.title == name
    assert dxs.sizes == {}


def test_scan_1d_for_correct_data():
    # -- initialise --
    ct.configure("test/suite/integration/scan/ct_config_tests.yml")

    name = "test_dataset_1d"

    x = Parameter(
        name="x",
        initial_value=0,
        get_cmd=None,
        set_cmd=None,
    )

    def double_x():
        return x.get_raw() * 2

    y = Parameter(
        name="y",
        initial_value=0,
        get_cmd=double_x,
        set_cmd=None,
    )

    x_sweep = sweep(x, np.linspace(0, 1, 11))

    # -- perform --
    ds = Scan(
        x_sweep,
        y,
        name=name,
        silent=True,
    ).run()
    dxs = ds2xarray(ds, snapshot=None)

    # -- validate --
    assert all([
        isclose(2 * x, y)
        for x, y
        in zip(dxs.x.values, dxs.y.values)
    ])
    assert dxs.title == name
    assert dxs.sizes == {"x": 11}


def test_scan_2d_for_correct_data():
    # -- initialise --
    ct.configure("test/suite/integration/scan/ct_config_tests.yml")

    name = "test_dataset_2d"

    x = Parameter(
        name="x",
        initial_value=0,
        get_cmd=None,
        set_cmd=None,
    )

    y = Parameter(
        name="y",
        initial_value=0,
        get_cmd=None,
        set_cmd=None,
    )

    def sum_x_and_y():
        return x.get_raw() + y.get_raw()

    z = Parameter(
        name="z",
        initial_value=0,
        get_cmd=sum_x_and_y,
        set_cmd=None,
    )

    # -- perform --
    ds = Scan(
        sweep(x, np.linspace(0, 1, 6)),
        sweep(y, np.linspace(1, 2, 6)),
        z,
        name=name,
        silent=True,
    ).run()
    dxs = ds2xarray(ds, snapshot=None)

    # -- validate --
    assert all([
        isclose(x + 1, y)
        for x, y
        in zip(dxs.x.values, dxs.y.values)
    ])
    assert all([
        isclose(x, y)
        for x, y
        in zip(
            list(chain.from_iterable(dxs.z.values)),
            list(map(sum, product(dxs.x.values, dxs.y.values))),
        )
    ])
    assert dxs.title == name
    assert dxs.sizes == {"x": 6, "y": 6}
