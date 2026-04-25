import os
import sys

def completely_different_function():
    return os.environ['HOME'] + sys.path[0]

class TotallyNew:
    def method(self):
        return 'nope'
