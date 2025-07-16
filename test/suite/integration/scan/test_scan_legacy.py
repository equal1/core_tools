from math import isclose
from itertools import chain

import core_tools as ct
from core_tools.sweeps import sweeps
from core_tools.sweeps import sweeps_legacy
from core_tools.data.ds.ds2xarray import ds2xarray

from qcodes.parameters import Parameter
import pytest


def test_validate_new_scan_0d_against_legacy():
    # -- initialise --
    ct.configure("test/suite/integration/scan/ct_config_tests.yml")

    name = "test_legacy_0d"

    x = Parameter(
        name="x",
        initial_value=0,
        get_cmd=lambda: 1,
        set_cmd=None,
    )

    # -- perform --
    ds_new = sweeps.do0D(*[x], name=name, silent=True).run()
    dxs_new = ds2xarray(ds_new, snapshot=None)
    with pytest.warns(DeprecationWarning):
        ds_legacy = sweeps_legacy.do0D(*[x], name=name, silent=True).run()
    dxs_legacy = ds2xarray(ds_legacy, snapshot=None)

    # -- validate --
    assert isclose(dxs_new.x.values, dxs_legacy.x.values)
    assert dxs_new.title == dxs_legacy.title
    assert dxs_new.sizes == dxs_legacy.sizes


def test_validate_new_scan_1d_against_legacy():
    # -- initialise --
    ct.configure("test/suite/integration/scan/ct_config_tests.yml")

    name = "test_legacy_1d"

    x = Parameter(
        name="x",
        initial_value=0,
        get_cmd=None,
        set_cmd=None,
    )

    y = Parameter(
        name="y",
        initial_value=0,
        get_cmd=x.get_raw,
        set_cmd=None,
    )

    # -- perform --
    ds_new = sweeps.do1D(
        x, 0, 1, 6, 0,
        y,
        name=name, silent=True
    ).run()
    dxs_new = ds2xarray(ds_new, snapshot=None)
    with pytest.warns(DeprecationWarning):
        ds_legacy = sweeps_legacy.do1D(
            x, 0, 1, 6, 0,
            y,
            name=name, silent=True
        ).run()
    dxs_legacy = ds2xarray(ds_legacy, snapshot=None)

    # -- validate --
    assert all([
        isclose(new, legacy)
        for new, legacy
        in zip(dxs_new.x.values, dxs_legacy.x.values)
    ])
    assert all([
        isclose(new, legacy)
        for new, legacy
        in zip(dxs_new.y.values, dxs_legacy.y.values)
    ])
    assert dxs_new.title == dxs_legacy.title
    assert dxs_new.sizes == dxs_legacy.sizes


def test_validate_new_scan_2d_against_legacy():
    # -- initialise --
    ct.configure("test/suite/integration/scan/ct_config_tests.yml")

    name = "test_legacy_2d"

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
    ds_new = sweeps.do2D(
        x, 0, 1, 6, 0,
        y, 1, 2, 6, 0,
        z,
        name=name, silent=True
    ).run()
    dxs_new = ds2xarray(ds_new, snapshot=None)
    with pytest.warns(DeprecationWarning):
        ds_legacy = sweeps_legacy.do2D(
            x, 0, 1, 6, 0,
            y, 1, 2, 6, 0,
            z,
            name=name, silent=True
        ).run()
    dxs_legacy = ds2xarray(ds_legacy, snapshot=None)

    # -- validate --
    assert all([
        isclose(new, legacy)
        for new, legacy
        in zip(dxs_new.x.values, dxs_legacy.x.values)
    ])
    assert all([
        isclose(new, legacy)
        for new, legacy
        in zip(dxs_new.y.values, dxs_legacy.y.values)
    ])
    assert all([
        isclose(new, legacy)
        for new, legacy
        in zip(
            list(chain.from_iterable(dxs_new.z.values)),
            list(chain.from_iterable(dxs_legacy.z.values)),
        )
    ])
    assert dxs_new.title == dxs_legacy.title
    assert dxs_new.sizes == dxs_legacy.sizes
