-- BigQuery DDL for the acme.analytics dataset, exported from the console.
-- Constraints are mostly missing, as is usual in BigQuery; events are sharded by day.
CREATE TABLE `acme.analytics.users` (
  user_id STRING NOT NULL,
  signup_date DATE,
  country STRING,
  referrer_user_id STRING
);

CREATE TABLE `acme.analytics.sessions` (
  session_id STRING NOT NULL,
  user_id STRING,
  started_at TIMESTAMP,
  device STRING
);

CREATE TABLE `acme.analytics.events_20261101` (
  event_id STRING NOT NULL,
  session_id STRING,
  user_id STRING,
  event_name STRING,
  event_ts TIMESTAMP,
  item_id STRING
);

CREATE TABLE `acme.analytics.events_20261102` (
  event_id STRING NOT NULL,
  session_id STRING,
  user_id STRING,
  event_name STRING,
  event_ts TIMESTAMP,
  item_id STRING
);

CREATE TABLE `acme.analytics.events_20261103` (
  event_id STRING NOT NULL,
  session_id STRING,
  user_id STRING,
  event_name STRING,
  event_ts TIMESTAMP,
  item_id STRING
);

CREATE TABLE `acme.analytics.items` (
  item_id STRING NOT NULL,
  item_name STRING,
  category STRING,
  PRIMARY KEY (item_id) NOT ENFORCED
);

CREATE TABLE `acme.analytics.purchases` (
  purchase_id STRING NOT NULL,
  user_id STRING,
  item_id STRING,
  amount NUMERIC,
  currency STRING,
  purchased_at TIMESTAMP,
  PRIMARY KEY (purchase_id) NOT ENFORCED,
  FOREIGN KEY (item_id) REFERENCES `acme.analytics.items`(item_id) NOT ENFORCED
);

CREATE TABLE `acme.analytics.campaigns` (
  campaign_id INT64 NOT NULL,
  name STRING,
  channel STRING
);

CREATE TABLE `acme.analytics.user_campaigns` (
  user_id STRING NOT NULL,
  campaign_id STRING NOT NULL,
  first_touch_ts TIMESTAMP
);

CREATE VIEW `acme.analytics.v_daily_active` AS
SELECT DATE(event_ts) AS day, COUNT(DISTINCT user_id) AS dau
FROM `acme.analytics.events_*`
GROUP BY day;

CREATE VIEW `acme.analytics.v_user_revenue` AS
SELECT u.user_id, u.country, SUM(p.amount) AS revenue
FROM `acme.analytics.users` AS u
LEFT JOIN `acme.analytics.purchases` AS p ON p.user_id = u.user_id
GROUP BY u.user_id, u.country;

CREATE VIEW `acme.analytics.v_country_revenue` AS
SELECT r.country, SUM(r.revenue) AS revenue, COUNT(*) AS users
FROM `acme.analytics.v_user_revenue` r
GROUP BY r.country;
