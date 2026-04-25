import logging

def get_account_id(conn):
    logging.info('fetching')
    return conn.execute('SELECT user_id')
