CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE TABLE robot_state (
    ts        TIMESTAMPTZ NOT NULL,
    joints    DOUBLE PRECISION[] NOT NULL,
    ee_x      DOUBLE PRECISION NOT NULL,
    ee_y      DOUBLE PRECISION NOT NULL,
    ee_z      DOUBLE PRECISION NOT NULL
);
SELECT create_hypertable('robot_state', 'ts');