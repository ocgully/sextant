def submit_order(order):
    if order.total <= 0:
        raise ValueError('bad')
    return save(order)
