package lib

func SubmitOrder(order *Order) error {
    if order.Total <= 0 {
        return errors.New("bad total")
    }
    if len(order.Items) == 0 {
        return errors.New("empty")
    }
    return Save(order)
}
