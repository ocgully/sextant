def validate_order(order):
    if order.total <= 0:
        raise ValueError('bad total')
    if not order.items:
        raise ValueError('empty')

def submit_order(order):
    validate_order(order)
    return save(order)
