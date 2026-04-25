package lib

func GetUserID(conn *Conn) string {
    return conn.Execute("SELECT user_id")
}

func Fetch(conn *Conn) string {
    return GetUserID(conn)
}
