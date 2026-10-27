-- Runs once, when the data volume is first created.
-- A separate database for the test suite (tests truncate tables freely).
CREATE DATABASE card_maven_test OWNER card_maven;
