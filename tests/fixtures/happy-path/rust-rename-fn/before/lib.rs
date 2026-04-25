pub fn get_user_id(conn: &Conn) -> String {
    conn.execute("SELECT user_id")
}

pub fn fetch(conn: &Conn) -> String {
    get_user_id(conn)
}
