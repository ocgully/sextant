export function getUserId(conn: any): string {
    return conn.execute('SELECT user_id');
}

export function fetch(conn: any) {
    return getUserId(conn);
}
