CREATE TABLE IF NOT EXISTS global_measurement_overview 
    id SERIAL,
    uuid BIGINT NOT NULL unique,

    exp_name text NOT NULL,
    set_up text NOT NULL,
    project text NOT NULL,
    sample text NOT NULL,
    creasted_by text NOT NULL, -- database account used when ds was created

    start_time TIMESTAMP, 
    stop_time TIMESTAMP, 

    exp_data_location text, -- Database table name of parameter table. Older datasets. [SdS]
    snapshot BYTEA, 
    metadata BYTEA,
    keywords JSONB, 
    starred BOOL DEFAULT False, 

    completed BOOL DEFAULT False, 
    data_size int, -- Total size of data. Is written at finish.
    data_cleared BOOL DEFAULT False,      -- Note [SdS]: Column is not used
    data_update_count int DEFAULT 0,  -- number of times the data has been updated on local client

    data_synchronized BOOL DEFAULT False,  -- data + param table sync'd
    table_synchronized BOOL DEFAULT False, -- global_measurements_overview sync'd
    sync_location text);                   -- Note [SdS]: Column is abused for migration to new measurement_parameters table

    CREATE INDEX IF NOT EXISTS id_indexed ON global_measurement_overview USING BTREE (id);
    CREATE INDEX IF NOT EXISTS uuid_indexed ON global_measurement_overview USING BTREE (uuid);
    CREATE INDEX IF NOT EXISTS starred_indexed ON global_measurement_overview USING BTREE (starred);
    CREATE INDEX IF NOT EXISTS date_day_index ON global_measurement_overview USING BTREE (project, set_up, sample);

    CREATE INDEX IF NOT EXISTS data_synced_index ON global_measurement_overview USING BTREE (data_synchronized);
    CREATE INDEX IF NOT EXISTS table_synced_index ON global_measurement_overview USING BTREE (table_synchronized);
