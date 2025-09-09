Configurating database access
=============================

The database connections are configured in a YAML file.
The call `ct.configure(yaml_file)` loads the configuration for the database connection and other
core-tools components. If the local and/or remote database connections are configured, then it
will open and test the connections.

The values for the local database are the set by the person who created this local database.
See [Installation database](installation_database.md) and ask other users of the PC.

The remote database will be configured by the adminstrator of the server.

The setup, project and sample should also be configured. If you also use the configuration to
view and retrieve data you may specify `any` for setup, project and/or sample.

```yaml
setup: my-setup
project: my-project
sample: my-sample

local_database:
    user: my-user-name
    password: my-password
    database: my-local-database-name

remote_database:
    user: remote-user-name
    password: remote-password
    database: remote-database-name
    address: server-name.tudelft.nl:5432

```

NOTE: When local and remote connection are configured, then both connection attempts must succeed.
If the connection to the remote database fails, then `ct.configure(...)` will fail.
This is a known flaw in the configuration.
