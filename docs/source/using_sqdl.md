# Using SQDL
Optional feature.

SQDL (Spin-Qubit Data Lake) is a piece of QuTech-specific infrastructure that chooses to store bulk data in S3-compatible Object Storage, as opposed to directly on the SQL database.

It is intended as the scalable long-term replacement for the remote PostgreSQL server.

## Components
### SQDL Client
```sqdl-client``` is an internal project that forms an abstraction over the SQDL API, simplifying the of reading from and writing to the remote object store.

#### Installing as part of core-tools
TODO: Look into managing optional dependencies and features. How to not break functionality for users that do now have access to sqdl-client.

#### Installing manually
To get started with ```sqdl-client```, install the project from its repository at the [TU Delft's GitLab](https://gitlab.tudelft.nl/sqdl/client/), either by making a clone first and installing locally, or by installing direclty:
```bash
python -m pip install -U git+https://gitlab.tudelft.nl/sqdl/client.git
```

### SQDL Reader
...

### SQDL Writer
...

## Configuration
Configuration for SQDL functionality is specified in the ```sqdl``` section of your ```config.yaml``` file. This section accepts the following parameters (default values are specified):

```yaml
sqdl:
    tick_rate: 6                    # (int) Minimal period of the event loop in seconds
    dev_mode: false                 # (bool) Whether or not to use the sqdl-client developer mode for local testing
    retry_failed_exports: false     # (bool) Whether or not to retry exporting previously failed exports when re-initialising the SQDL Writer
    retry_failed_uploads: false     # (bool) Whether or not to retry uploading previously failed uploads when re-initialising the SQDL Writer
    export_path: ~/.sqdl-export     # (str) Local (absolute) path where the exported data files will be saved before uploading
    api_key: None                   # (str) API key used to authenticate with
    setup_name_correction:          # (section) Section used for renaming setups
        from: to                    # (str) Represent local setup 'from' as 'to' in storage
```

Additionally, the ```scope``` parameter is checked for at the top level, just like ```project```, ```setup``` and ```sample```.
