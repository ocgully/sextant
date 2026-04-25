function validateOrder(order: any) {
    if (order.total <= 0) throw new Error('bad total');
    if (!order.items) throw new Error('empty');
}

function submitOrder(order: any) {
    validateOrder(order);
    return save(order);
}
