# Using SQDL
*Optional features*

SQDL (Spin-Qubit Data Lake) is a piece of QuTech-specific infrastructure that
chooses to store bulk data in S3-compatible Object Storage, as opposed to directly
on the SQL database.

It is intended as the scalable long-term replacement for the remote PostgreSQL
server.

## Components
### SQDL DataBrowser
When using the ```qt_databrowser``` package, you can get a SQDL-specific version of
the DataBrowser as follows:
```python
from qt_dataviewer.sqdl import SqdlDataBrowser

# If not yet logged your internet browser will show a login page.
browser = SqdlDataBrowser()

# or launch with scope:
browser = SqdlDataBrowser("scope-name")
```

### SQDL Reader
The module ```core_tools.data.sqdl``` exposes some useful methods for
retrieving data from SQDL:
```python
from core_tools.data.sqdl import init_sqdl, load_by_uuid

# If not yet logged in, your internet browser will open a login page.
init_sdql("scope-name")

dataset = load_by_uuid(uuid)
```
Other useful methods include ```sqdl_query``` for searching measurement information,
and ```list_scopes``` for seeing what scopes are available to you. 

### SQDL Sync
SQDL Sync exists as a successor to DB Sync, and is intended as a replacement.

It is responsible for exporting measurement data into an SQDL-compatible format, and 
then upload those files. This process can run completely in the background.

To start from a python script:
```python
import core_tools as ct
from core_tools.startup.launch_sqdl_sync import launch_sqdl_sync

ct.configure("~/path/to/config.yml")
launch_sqdl_sync()
```

To start from the terminal (with an active virtual environment):
```bash
python core_tools/startup/sqdl_sync.py ~/path/to/config.yml
```
See the Configuration section for more instructions.

## Dependencies
### SQDL Client and SQDL Uploader
 ```sqdl-client``` and ```sqdl-uploader``` are internal projects that form an abstraction
over the SQDL API, simplifying reading from and writing to the remote object store.

These packages are mostly used by tools like the DataBrowser, Reader and Sync, but
can also be used as standalone tools. For further instructions, see their
respective GitLab pages.


### Installation process
```sqdl-client``` and ```sqdl-uploader``` can be installed using pip as part of
QuTech QDLabs Software from the package registry in the [TUDelft GitLab QDLabs group](https://gitlab.tudelft.nl/qutech-qdlabs/).

Installing packages from this registry using pip requires keyring authentication.
For further instructions on installation and authentication, check the [QDLabs Wiki pages](https://gitlab.tudelft.nl/qutech-qdlabs/measurement-systems/documentation/-/wikis/home)
on 'Software Installation' and 'Credentials'.

## Configuration
Configuration for SQDL functionality is specified in the ```sqdl_sync``` section
of your ```config.yaml``` file. This section accepts the following parameters
(defaults for optional values are specified):

```yaml
# (str) Name of the Scope parameter associated with your experiments
scope: <required>

sqdl_sync:
    # (str) Local path where the exported data files will be saved before uploading
    base_path: ~/.sqdl

    # (str) Local file where the uploader will keep track of its tasks
    database_file: ~/.sqdl/uploader.db

    # (float) Minimum period of the event loop in seconds
    tick_rate: 0.1

    # (bool) Whether or not to retry uploading previously failed uploads when
    #  re-initialising the SQDL Sync
    retry_failed_uploads: true

    # (bool) Set to true when uploading data from a non-MeasurementPC setup,
    #  see the SQDL Login section for more info
    use_personal_login: false

    # (section) Apply scope name corrections when uploading data that was exported
    #  using an incorrect scope name. Don't forget to update the 'scope' parameter
    #  to the correct name as well.
    scope_correction:
        <original_name>: <corrected_name>
```

The ```scope``` parameter is checked for at the top level, just like ```project```, ```setup``` and ```sample```.

### SQDL Login
By default, the SQDL Sync is configured to be authenticated through the use of an
API key. This key has to be provided by your local administrator, and should be
unique to your setup. This means that every measurement tool has it's own API key,
and it should not by copied between systems.

You can store the API key in the correct location using the following method:
```python
from sqdl_uploader import store_api_key
store_api_key("your-key-here")
# OR
store_api_key("your-key-here", config_path="~/path/to/config.yml")
```
Where the 'config_path' parameter is only necessary if you want to change the
default database configuration.

If you are not using SQDL Sync from a shared system, it is possible to use
your personal credentials to log into SQDL. This can be activated by setting the
```use_personal_login``` configuration parameter in your .yml file.

## Development
When developing SQDL related features, it is possible to test them against a local
deployment of the Backend (see the SQDL Backend page for more instructions on this).

When doing local development, there are two methods of user authentication that you
can use: HTTP Basic Auth and API-key Auth. You can choose either method by setting
the ```local_dev_mode``` configuration parameter to ```basic``` or ```api_key```,
respectively.

Basic Auth requires you to set up a ```.netrc``` file with the username and password
that you used for your local deployment. See [this page](https://everything.curl.dev/usingcurl/netrc.html)for more info.
API-key Auth follows the normal configuration procedure.

#### Logging
Logging can be configured by using the app-wrapper format. This can be done by adding the following subsection (default values included):
```yaml
sqdl_sync:
    logging:
        file_location: ~/.core_tools/logs
        file_name: sqdl_sync.log
        file_level: INFO
```
