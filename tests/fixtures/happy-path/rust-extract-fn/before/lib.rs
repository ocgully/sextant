pub fn submit_order(order: &Order) -> Result<()> {
    if order.total <= 0 { return Err("bad total".into()); }
    if order.items.is_empty() { return Err("empty".into()); }
    save(order)
}
