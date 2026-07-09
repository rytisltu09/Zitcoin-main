import os

import mysql.connector
from mysql.connector import errorcode


def _resolve_database_name(db_name):
    return db_name or os.getenv("MYSQL_DATABASE", "zitcoin")


def _connect_mysql(db_name=None):
    database = _resolve_database_name(db_name)
    config = {
        "host": os.getenv("MYSQL_HOST", "localhost"),
        "port": int(os.getenv("MYSQL_PORT", "3306")),
        "user": os.getenv("MYSQL_USER"),
        "password": os.getenv("MYSQL_PASSWORD"),
        "database": database,
        "autocommit": False,
    }

    if not config["user"] or not config["password"]:
        raise ValueError("MYSQL_USER and MYSQL_PASSWORD must be set in environment variables.")

    try:
        return mysql.connector.connect(**config)
    except mysql.connector.Error as err:
        if err.errno != errorcode.ER_BAD_DB_ERROR:
            raise

        bootstrap_config = dict(config)
        bootstrap_config.pop("database", None)
        bootstrap_conn = mysql.connector.connect(**bootstrap_config)
        bootstrap_cursor = bootstrap_conn.cursor()
        bootstrap_cursor.execute(
            f"CREATE DATABASE IF NOT EXISTS `{database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        )
        bootstrap_conn.commit()
        bootstrap_cursor.close()
        bootstrap_conn.close()
        return mysql.connector.connect(**config)

class FinanceDB:
    def __init__(self, db_name=None):
        self.conn = _connect_mysql(db_name)
        self.cursor = self.conn.cursor()
        self.create_tables()
    
    def create_tables(self):
        self.cursor.execute(
            '''CREATE TABLE IF NOT EXISTS users (
                discord_id BIGINT PRIMARY KEY,
                mc_username VARCHAR(255),
                balance DOUBLE DEFAULT 0
            )'''
        )

        # Backfill required columns for older schemas created before new fields existed.
        self.cursor.execute('SHOW COLUMNS FROM users')
        existing_columns = {row[0] for row in self.cursor.fetchall()}

        if 'discord_id' not in existing_columns:
            self.cursor.execute('ALTER TABLE users ADD COLUMN discord_id BIGINT PRIMARY KEY')

        if 'mc_username' not in existing_columns:
            self.cursor.execute('ALTER TABLE users ADD COLUMN mc_username VARCHAR(255)')

        if 'balance' not in existing_columns:
            self.cursor.execute('ALTER TABLE users ADD COLUMN balance DOUBLE NOT NULL DEFAULT 0')

        self.conn.commit()
    
    def add_user(self, discord_id, mc_username):
        self.cursor.execute('INSERT INTO users (discord_id, mc_username) VALUES (%s, %s)', (discord_id, mc_username))
        self.conn.commit()
    
    def remove_user(self, discord_id):
        self.cursor.execute('DELETE FROM users WHERE discord_id = %s', (discord_id,))
        self.conn.commit()
    
    def user_exists(self, discord_id):
        self.cursor.execute('SELECT * FROM users WHERE discord_id = %s', (discord_id,))
        return self.cursor.fetchone() is not None
    
    def get_user_by_mc_username(self, mc_username):
        self.cursor.execute('SELECT * FROM users WHERE mc_username = %s', (mc_username,))
        return self.cursor.fetchone()
    
    def get_user_by_discord_id(self, discord_id):
        self.cursor.execute('SELECT * FROM users WHERE discord_id = %s', (discord_id,))
        return self.cursor.fetchone()

    def get_balance(self, discord_id):
        self.cursor.execute('SELECT balance FROM users WHERE discord_id = %s', (discord_id,))
        result = self.cursor.fetchone()
        return result[0] if result else None
    
    def get_all_users(self):
        self.cursor.execute('SELECT * FROM users')
        return self.cursor.fetchall()

class BankDB:
    def __init__(self, db_name=None):
        self.conn = _connect_mysql(db_name)
        self.cursor = self.conn.cursor()
        self.create_tables()

    def create_tables(self):
        self.cursor.execute(
            '''CREATE TABLE IF NOT EXISTS loans (
                discord_id BIGINT PRIMARY KEY,
                amount DOUBLE,
                interest_rate DOUBLE,
                due_date VARCHAR(255)
            )'''
        )
        self.conn.commit()
    
    def add_loan(self, discord_id, amount, interest_rate, due_date):
        self.cursor.execute(
            'INSERT INTO loans (discord_id, amount, interest_rate, due_date) VALUES (%s, %s, %s, %s)',
            (discord_id, amount, interest_rate, due_date),
        )
        self.conn.commit()
    
    def remove_loan(self, discord_id):
        self.cursor.execute('DELETE FROM loans WHERE discord_id = %s', (discord_id,))
        self.conn.commit()
    
    def get_loan(self, discord_id):
        self.cursor.execute('SELECT * FROM loans WHERE discord_id = %s', (discord_id,))
        return self.cursor.fetchone()

    def get_all_loans(self):
        self.cursor.execute('SELECT * FROM loans')
        return self.cursor.fetchall()

class RequestsDB:
    def __init__(self, db_name=None):
        self.conn = _connect_mysql(db_name)
        self.cursor = self.conn.cursor()
        self.create_tables()

    def create_tables(self):
        self.cursor.execute(
            '''CREATE TABLE IF NOT EXISTS requests (
                request_id INT AUTO_INCREMENT PRIMARY KEY,
                discord_id BIGINT,
                request_type VARCHAR(255),
                status VARCHAR(255),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )'''
        )

        # Backfill created_at for older schemas that predate request timestamps.
        self.cursor.execute('SHOW COLUMNS FROM requests')
        existing_columns = {row[0] for row in self.cursor.fetchall()}
        if 'created_at' not in existing_columns:
            self.cursor.execute('ALTER TABLE requests ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP')

        self.conn.commit()
    
    def add_request(self, discord_id, request_type, status):
        self.cursor.execute(
            'INSERT INTO requests (discord_id, request_type, status) VALUES (%s, %s, %s)',
            (discord_id, request_type, status),
        )
        self.conn.commit()
    
    def update_request_status(self, request_id, new_status):
        self.cursor.execute(
            'UPDATE requests SET status = %s WHERE request_id = %s',
            (new_status, request_id),
        )
        self.conn.commit()
    
    def get_request(self, request_id):
        self.cursor.execute(
            'SELECT request_id, discord_id, request_type, status, created_at FROM requests WHERE request_id = %s',
            (request_id,),
        )
        return self.cursor.fetchone()

    def get_all_requests(self):
        self.cursor.execute('SELECT request_id, discord_id, request_type, status, created_at FROM requests')
        return self.cursor.fetchall()

    def get_requests_by_status(self, status):
        self.cursor.execute(
            'SELECT request_id, discord_id, request_type, status, created_at FROM requests WHERE status = %s',
            (status,),
        )
        return self.cursor.fetchall()
    
    def get_requests_by_discord_id(self, discord_id):
        self.cursor.execute(
            'SELECT request_id, discord_id, request_type, status, created_at FROM requests WHERE discord_id = %s',
            (discord_id,),
        )
        return self.cursor.fetchall()

class TransactionsDB:
    def __init__(self, db_name=None):
        self.conn = _connect_mysql(db_name)
        self.cursor = self.conn.cursor()
        self.create_tables()

    def create_tables(self):
        self.cursor.execute(
            '''CREATE TABLE IF NOT EXISTS transactions (
                transaction_id INT AUTO_INCREMENT PRIMARY KEY,
                discord_id BIGINT,
                amount DOUBLE,
                transaction_type VARCHAR(255),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )'''
        )
        self.conn.commit()
    
    def add_transaction(self, discord_id, amount, transaction_type):
        self.cursor.execute(
            'INSERT INTO transactions (discord_id, amount, transaction_type) VALUES (%s, %s, %s)',
            (discord_id, amount, transaction_type),
        )
        self.conn.commit()
    
    def get_transaction(self, transaction_id):
        self.cursor.execute('SELECT * FROM transactions WHERE transaction_id = %s', (transaction_id,))
        return self.cursor.fetchone()

    def get_all_transactions(self):
        self.cursor.execute('SELECT * FROM transactions')
        return self.cursor.fetchall()

    def get_transactions_by_discord_id(self, discord_id):
        self.cursor.execute('SELECT * FROM transactions WHERE discord_id = %s', (discord_id,))
        return self.cursor.fetchall()
