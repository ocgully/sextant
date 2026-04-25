package lib

func ValidateOrder(order *Order) error {
    if order.Total <= 0 {
        return errors.New("bad total")
    }
    if len(order.Items) == 0 {
        return errors.New("empty")
    }
    return nil
}

func SubmitOrder(order *Order) error {
    if err := ValidateOrder(order); err != nil { return err }
    return Save(order)
}
