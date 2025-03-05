--- Global Measurement Overview
CREATE TABLE IF NOT EXISTS global_measurement_overview (
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
    sync_location text  -- Note [SdS]: Column is abused for migration to new measurement_parameters table
);                   

CREATE INDEX IF NOT EXISTS id_indexed ON global_measurement_overview USING BTREE (id);

CREATE INDEX IF NOT EXISTS uuid_indexed ON global_measurement_overview USING BTREE (uuid);
CREATE INDEX IF NOT EXISTS starred_indexed ON global_measurement_overview USING BTREE (starred);
CREATE INDEX IF NOT EXISTS date_day_index ON global_measurement_overview USING BTREE (project, set_up, sample);

CREATE INDEX IF NOT EXISTS data_synced_index ON global_measurement_overview USING BTREE (data_synchronized);
CREATE INDEX IF NOT EXISTS table_synced_index ON global_measurement_overview USING BTREE (table_synchronized);

ALTER TABLE global_measurement_overview ADD COLUMN IF NOT EXISTS data_update_count INT DEFAULT 0;
--- Measurement Parameters
CREATE TABLE IF NOT EXISTS measurement_parameters (
        id SERIAL primary key, 
        exp_uuid BIGINT NOT NULL,
        param_index INT NOT NULL,
        param_id BIGINT, 
        nth_set INT, 
        nth_dim INT, 
        param_id_m_param BIGINT, 
        setpoint BOOL, 
        setpoint_local BOOL, 
        name_gobal text, 
        name text NOT NULL,
        label text NOT NULL,
        unit text NOT NULL,
        depencies jsonb, 
        shape jsonb, 
        write_cursor INT, 
        total_size INT, 
        oid INT
);

CREATE INDEX IF NOT EXISTS exp_uuid_index ON measurement_parameters USING BTREE (exp_uuid);
CREATE INDEX IF NOT EXISTS oid_index ON measurement_parameters USING BTREE (oid);

--- Sample Info Overview
CREATE TABLE IF NOT EXISTS sample_info_overview (
    sample_info_hash TEXT NOT NULL UNIQUE,
    set_up TEXT NOT NULL,
    project TEXT NOT NULL,
    sample TEXT NOT NULL
);
