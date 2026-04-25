package lib

func GetAccountID(conn *Conn) string {
    return conn.Execute("SELECT user_id")
}

func Fetch(conn *Conn) string {
    return GetAccountID(conn)
}
