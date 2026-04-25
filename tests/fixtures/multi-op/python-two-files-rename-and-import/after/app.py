import logging
from store import fetch_account

def run():
    logging.info('run')
    return fetch_account(1)
