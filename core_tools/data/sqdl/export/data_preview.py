import logging
import re

import numpy as np
import matplotlib
import matplotlib.pyplot as pt

from .utils import atomic_write

logger = logging.getLogger(__name__)

# use headless backend
matplotlib.use('agg')


def get_plottable(da):
    empty_axes = []
    shape = da.shape
    for i, n in enumerate(da.shape):
        if n == 1:
            empty_axes.append(i)
    for ax in empty_axes[::-1]:
        da = da.mean(axis=ax)
        logger.info(f'Reduced dimensions: {shape} -> {da.shape} {list(da.coords.keys())}')
    while da.ndim > 2:
        da = da.mean(axis=-1)
    return da


def is_log(x):
    x_ind = np.argwhere(np.isfinite(x)).T[0]
    if len(x_ind) < 3:
        # need at least 3 points to check for logarithmic axis
        return False
    x_finite = x[x_ind] + 1e-100
    x_ratio = x_finite[:-1] / x_finite[1:]
    mean_ratio = np.mean(x_ratio)
    is_log = (
        0.99999 < np.min(x_ratio) / np.max(x_ratio) < 1.00001
        and (mean_ratio < 0.99 or mean_ratio > 1.01)
    )
    return is_log


def fix_axes_missing_data(dsx):
    uuid = dsx.attrs["uuid"]
    for coord in dsx.coords.values():
        x = coord.data
        if np.any(np.isnan(x)):
            logger.info(f'Fixing axis {coord.name} {uuid}')
            n = len(x)
            # get indices of not nan values
            x_ind = np.argwhere(np.isfinite(x)).T[0]
            if len(x_ind) >= 2:
                min_ind, max_ind = [np.min(x_ind), np.max(x_ind)]
                x_min, x_max = (x[min_ind], x[max_ind])
                x_scale = (x_max - x_min) / (max_ind - min_ind)
                if len(x_ind) >= 3:
                    x_finite = x[x_ind] + 1e-100
                    x_ratio = x_finite[1:] / x_finite[:-1]
                    mean_ratio = np.mean(x_ratio)
                    is_log = (
                        0.99999 < np.min(x_ratio) / np.max(x_ratio) < 1.00001
                        and (mean_ratio < 0.99 or mean_ratio > 1.01)
                    )
                else:
                    is_log = False

                if is_log:
                    coord.data[:] = x_min * mean_ratio**(np.arange(n) - min_ind)
                    logger.debug(f'is LOG ({n} {coord.name}, {mean_ratio}, {coord.data[0]} -> {coord.data[-1]})')
                else:
                    coord.data[:] = x_min + x_scale * (np.arange(n) - min_ind)
            elif len(x_ind) == 1:
                coord.data[:] = x[x_ind[0]] + np.arange(n)
            else:
                logger.warning(f'*** No data for {coord.name} {uuid} ***')


def fix_filename(filename):
    invalid_chars = re.compile(r'[*/\<>:"|?]')
    m = invalid_chars.search(filename)
    while m:
        filename = filename[:m.start()] + '_' * (m.end() - m.start()) + filename[m.end():]
        m = invalid_chars.search(filename)
    return filename


def generate_previews(dsx, ds_path, var_descr, timer):
    pt.ioff()
    uuid = dsx.attrs['uuid']
    fix_axes_missing_data(dsx)

    for i, da in enumerate(dsx.values()):
        try:
            name = da.attrs.get('long_name', da.name)
            fname = f'{name}({",".join(da.dims)})'
            if var_descr[i]['written'] == 0:
                logger.warning(f'no data for var {name} of {uuid}')
                continue
            if da.ndim == 0:
                continue
            timer.time(f'plot_{i}')
            pt.figure()
            da = get_plottable(da)
            if da.ndim == 1:
                plot = 'line'
                xscale = 'log' if is_log(da.coords[da.dims[0]].data) else 'linear'
                da.plot.line(xscale=xscale)
            elif da.ndim >= 2:
                plot = 'mesh'
                xscale = 'log' if is_log(da.coords[da.dims[1]].data) else 'linear'
                yscale = 'log' if is_log(da.coords[da.dims[0]].data) else 'linear'
                da = da.sortby(list(da.dims))
                # do not use diverging color maps: center=False
                da.plot.pcolormesh(xscale=xscale, yscale=yscale, center=False)
            else:
                plot = 'none'
                logger.info(f'No preview for {fname}')
            if plot != 'none':
                pt.title(name)
                timer.time(f'save {plot}')
                filename = fix_filename(fname)
                with atomic_write(ds_path + f'/{filename}.png') as tmp_file:
                    try:
                        pt.savefig(tmp_file, format='png')
                    except Exception:
                        logger.error(f"Failure saving '{ds_path}/{filename}.png'", exc_info=True)
                logger.info(f'Saved {plot} {fname}')
        except Exception as ex:
            logger.error(f'Preview error {uuid}, {i}:{name} {type(ex).__name__} {ex}')
        finally:
            pt.close()
