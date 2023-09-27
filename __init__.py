# This file is part of the current_account module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.

from trytond.pool import Pool
from . import account


def register():
    Pool.register(
        account.PartyBalanceAccount,
        account.PartyBalanceAccountContext,
        account.PartyBalanceLine,
        account.Line,
        module='current_account', type_='model')
    Pool.register(
        account.OpenMoveLineBalance,
        module='current_account', type_='wizard')
    Pool.register(
        account.MoveLineList,
        account.MoveLineListSpreadSheet,
        account.PartyBalanceAccountReport,
        account.PartyBalanceLineReport,
        account.PartyBalanceLineSpreadSheet,
        module='current_account', type_='report')
