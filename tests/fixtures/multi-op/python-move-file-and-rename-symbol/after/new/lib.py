def get_account_id(conn):
    return conn.execute('SELECT user_id')
