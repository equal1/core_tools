CREATE TABLE coretools_export_updates (
   id INT GENERATED ALWAYS AS IDENTITY,
   uuid BIGINT NOT NULL UNIQUE,
   modify_count INT default 0,
   new_measurement BOOLEAN default FALSE, -- not really needed, but overwrite all data.
   data_changed BOOLEAN default FALSE, -- export previews, export metadata.
   completed BOOLEAN default FALSE, -- export raw data
   update_star BOOLEAN default FALSE, -- compare with exported metadata.
   update_name BOOLEAN default FALSE, -- compare with exported metadata.
   PRIMARY KEY(id)
);
CREATE INDEX IF NOT EXISTS qdl_export_updates_uuid_index ON coretools_export_updates USING BTREE (uuid);

CREATE TABLE coretools_exported (
   id INT GENERATED ALWAYS AS IDENTITY,
   uuid BIGINT NOT NULL UNIQUE,
   path TEXT,
   measurement_start_time timestamp, -- export raw after timeout and not completed.
   raw_final BOOLEAN default FALSE, -- Set when completed or after timeout.

   -- export state
   export_state INT default 0, -- (0:todo, 1:done, 99: failed),
   export_errors TEXT,

   PRIMARY KEY(id)
);
CREATE INDEX IF NOT EXISTS coretools_exported_uuid_index ON coretools_exported USING BTREE (uuid);

-- CORRECT THIS DEPENDING ON DATABASE
ALTER TABLE coretools_export_updates OWNER TO dbijl;
ALTER TABLE coretools_exported OWNER TO dbijl;


-- NOTE: new measurement first adds the dataset to the global_measurmeent_overview on the local database,
--       but the sync script first adds the measurement parameters and then creates the entry
--       in global_measurement_overview on the server.
--       So, a new measurement might already have an entry in the coretools_export table due to the
--       rows written to measurement_parameters
CREATE OR REPLACE FUNCTION export_new_measurement()
  RETURNS TRIGGER
  LANGUAGE PLPGSQL
  AS
$$
BEGIN
    INSERT INTO coretools_export_updates(uuid, new_measurement, data_changed, completed)
    VALUES (NEW.uuid, TRUE, TRUE, NEW.completed)
	ON CONFLICT (uuid) DO
	  UPDATE SET
	     modify_count = coretools_export_updates.modify_count + 1,
	     new_measurement = TRUE,
	     completed = NEW.completed;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION export_changed_measurement()
  RETURNS TRIGGER
  LANGUAGE PLPGSQL
  AS
$$
BEGIN
    INSERT INTO coretools_export_updates(uuid, update_star, update_name, completed)
    VALUES (NEW.uuid, NEW.starred <> OLD.starred, NEW.exp_name <> OLD.exp_name, NEW.completed)
	ON CONFLICT (uuid) DO
	  UPDATE SET
	     modify_count = coretools_export_updates.modify_count + 1,
	     update_star = coretools_export_updates.update_star OR (NEW.starred <> OLD.starred),
		 update_name = coretools_export_updates.update_name OR (NEW.exp_name <> OLD.exp_name),
		 completed = NEW.completed;
	RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION export_changed_measurement_data()
  RETURNS TRIGGER
  LANGUAGE PLPGSQL
  AS
$$
BEGIN
    INSERT INTO coretools_export_updates(uuid, data_changed)
    VALUES (NEW.exp_uuid, TRUE)
	ON CONFLICT (uuid) DO
	  UPDATE SET
	     modify_count = coretools_export_updates.modify_count + 1,
	     data_changed = TRUE;

	RETURN NEW;
END;
$$;

CREATE TRIGGER measurement_creation
  AFTER INSERT ON global_measurement_overview
  FOR EACH ROW
  EXECUTE PROCEDURE export_new_measurement();

CREATE TRIGGER measurement_data_insert
  AFTER INSERT ON measurement_parameters
  FOR EACH ROW
  EXECUTE PROCEDURE export_changed_measurement_data();

INSERT INTO coretools_export_updates(uuid, new_measurement, data_changed, completed)
    SELECT measurement.uuid, TRUE, TRUE, measurement.completed
	FROM global_measurement_overview as measurement
	ORDER BY measurement.uuid
	ON CONFLICT (uuid) DO NOTHING;

CREATE TRIGGER measurement_update
  AFTER UPDATE OF completed, exp_name, starred ON global_measurement_overview
  FOR EACH ROW
  EXECUTE PROCEDURE export_changed_measurement();

CREATE TRIGGER measurement_data_update
  AFTER UPDATE ON measurement_parameters
  FOR EACH ROW
  EXECUTE PROCEDURE export_changed_measurement_data();


--- updates

ALTER TABLE coretools_export_updates
  ADD COLUMN resume_after timestamp DEFAULT '2020-01-01 00:00:00',
  ADD COLUMN fail_count INT DEFAULT 0;
