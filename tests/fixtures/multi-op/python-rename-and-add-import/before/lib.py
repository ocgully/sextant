def get_user_id(conn):
    return conn.execute('SELECT user_id')
