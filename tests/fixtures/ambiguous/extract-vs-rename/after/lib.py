def validate(order):
    if order.total <= 0:
        raise ValueError('bad')

def submit_order(order):
    validate(order)
    return save(order)
