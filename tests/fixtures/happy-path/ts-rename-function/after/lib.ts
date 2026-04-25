export function getAccountId(conn: any): string {
    return conn.execute('SELECT user_id');
}

export function fetch(conn: any) {
    return getAccountId(conn);
}
