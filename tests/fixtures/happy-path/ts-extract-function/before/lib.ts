function submitOrder(order: any) {
    if (order.total <= 0) throw new Error('bad total');
    if (!order.items) throw new Error('empty');
    return save(order);
}
