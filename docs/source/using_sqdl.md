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
Configuration for SQDL functionality is specified in the ```sqdl_sync``` section of your ```config.yaml``` file. This section accepts the following parameters (default values are specified):

```yaml
sqdl_sync:
    tick_rate: 6                    # (int) Minimum period of the event loop in seconds
    retry_failed_exports: false     # (bool) Whether or not to retry exporting previously failed exports when re-initialising the SQDL Writer
    retry_failed_uploads: false     # (bool) Whether or not to retry uploading previously failed uploads when re-initialising the SQDL Writer
    base_path: ~/.sqdl              # (str) Local path where the exported data files will be saved before uploading
    use_personal_login: false       # (bool) Whether or not to use personal credentials for singing into SQDL
    dev_mode: false                 # (bool) Whether or not to use the sqdl-client developer mode for local testing
    setup_name_correction:          # (section) Section used for renaming setups
        from: to                    # (str) Represent local setup 'from' as 'to' in storage
```

Additionally, the ```scope``` parameter is checked for at the top level, just like ```project```, ```setup``` and ```sample```.

### Logging
The process started by ```core_tools.startup.launch_sqdl_sync.py``` inherrits some logging configuration from the ```launch_app(...)``` functionality.

As a result, you can configure your SQDL logging settings by adding the following ```logging``` section to your SQDL config (displayed values are defaults):
```yaml
sqdl_sync:
    logging:
        file_location: ~/.core_tools/logs
        file_name: sqdl_sync.log
        file_level: INFO
```

### SQDL Login
By default, the SQDL Writer is configured to be authenticated through the use of an API key. This key has to be provided by your local administrator, and should be unique to your setup.
This means that every measurement tool has it's own API key, and it should not by copied between systems.

If you are not using the SQDL Writer from a shared system, it is possible to use your personal credentials to log into SQDL. To do so, set the ```use_personal_login``` parameter to true.
