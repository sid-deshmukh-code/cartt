-- schema.sql - AWS RDS (MySQL) schema for the Smart Shopping Cart
--
-- Run this once against your RDS instance, e.g.:
--   mysql -h <rds-endpoint> -P 3306 -u <master-user> -p < schema.sql
--
-- This mirrors the local SQLite schema on the Pi (see ../db.py) plus an
-- admin_users table for the dashboard login.

CREATE DATABASE IF NOT EXISTS smart_cart
    CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE smart_cart;

CREATE TABLE IF NOT EXISTS products (
    barcode       VARCHAR(32) PRIMARY KEY,
    name          VARCHAR(255) NOT NULL,
    price         DECIMAL(10, 2) NOT NULL,
    stock         INT NOT NULL DEFAULT 100,
    weight_grams  DECIMAL(10, 2) NOT NULL DEFAULT 0,
    updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS transactions (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    transaction_time DATETIME NOT NULL,
    items_json       JSON NOT NULL,
    total            DECIMAL(10, 2) NOT NULL,
    payment_method   VARCHAR(20) NOT NULL,
    status           VARCHAR(20) NOT NULL,
    synced_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_transaction_time (transaction_time)
);

CREATE TABLE IF NOT EXISTS admin_users (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    username       VARCHAR(64) UNIQUE NOT NULL,
    password_hash  VARCHAR(255) NOT NULL
);

-- Recommended: create a separate, low-privilege user for the Pi that can
-- only INSERT transactions and read/write products - NOT touch admin_users.
-- Run this manually (replace the password), it's not auto-applied:
--
-- CREATE USER 'pi_writer'@'%' IDENTIFIED BY 'choose-a-strong-password';
-- GRANT SELECT, INSERT, UPDATE ON smart_cart.products TO 'pi_writer'@'%';
-- GRANT INSERT ON smart_cart.transactions TO 'pi_writer'@'%';
-- FLUSH PRIVILEGES;
--
-- And a read-only user for the admin webapp:
--
-- CREATE USER 'dashboard_reader'@'%' IDENTIFIED BY 'choose-a-strong-password';
-- GRANT SELECT ON smart_cart.transactions TO 'dashboard_reader'@'%';
-- GRANT SELECT ON smart_cart.products TO 'dashboard_reader'@'%';
-- GRANT SELECT ON smart_cart.admin_users TO 'dashboard_reader'@'%';
-- FLUSH PRIVILEGES;
