def submit_order(order):
    if order.total <= 0:
        raise ValueError('bad total')
    if not order.items:
        raise ValueError('empty')
    return save(order)
