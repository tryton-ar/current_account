# __init__.py
from trytond.pool import Pool

from .account import *

def register():
    Pool.register(
        Line,
        module='current_account', type_='model')
    Pool.register(
        OpenMoveLineBalance,
        module='current_account', type_='wizard')
    Pool.register(
        MoveLineList,
        module='current_account', type_='report')
