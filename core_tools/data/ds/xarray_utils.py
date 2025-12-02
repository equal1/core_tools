import json
import gzip

import xarray as xr


if not hasattr(xr.Dataset, "snapshot"):
    @xr.register_dataset_accessor("snapshot")
    class SnapshotAccessor:
        """Accessor to get decoded snapshot `snapshot()` from xarray dataset.

        Core-tools saves snapshots in hfd5 files as json string or as gzipped json string.
        This accessor returns the snapshot in a dictionary.

        Example:
            xr_dataset.snapshot()
        """

        def __init__(self, xr_ds):
            self._xr_ds = xr_ds
            self._snapshot = None

        def __call__(self, *args):
            if self._snapshot is None:
                attrs = self._xr_ds.attrs
                if 'snapshot-gzip' in attrs:
                    self._snapshot = json.loads(gzip.decompress(attrs['snapshot-gzip']))
                else:
                    self._snapshot = json.loads(attrs['snapshot'])
            return self._snapshot


def get_snapshot(xr_ds: xr.Dataset):
    # NOTE: This works, because the accessor has been registered just above!
    return xr_ds.snapshot()
