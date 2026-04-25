pub fn get_account_id(conn: &Conn) -> String {
    conn.execute("SELECT user_id")
}

pub fn fetch(conn: &Conn) -> String {
    get_account_id(conn)
}
