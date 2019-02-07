# -*- coding: utf-8 -*-
# This file is part of the current_account module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
from decimal import Decimal
from trytond.tools import reduce_ids
from trytond.model import fields
from trytond.pyson import PYSONEncoder
from trytond.wizard import Wizard, StateAction
from trytond.transaction import Transaction
from trytond.pool import Pool, PoolMeta
from trytond.modules.company import CompanyReport
from trytond.modules.product import price_digits

__all__ = ['Line', 'OpenMoveLineBalance', 'MoveLineList']


class Line(metaclass=PoolMeta):
    __name__ = 'account.move.line'

    balance = fields.Function(fields.Numeric('Balance', digits=price_digits),
        'get_balance')

    @classmethod
    def get_balance(cls, lines, name):
        if not lines:
            return {}

        ids = [x.id for x in lines]
        res = {}.fromkeys(ids, Decimal('0.0'))
        fiscalyear_id = journal_id = period_id = account_id = None
        party_id = account_kind = None

        from_fiscalyear = where_fiscalyear = ''
        if Transaction().context.get('fiscalyear'):
            fiscalyear_id = int(Transaction().context.get('fiscalyear'))
        if fiscalyear_id:
            from_fiscalyear = '''
                LEFT JOIN account_period ap ON (ap.id=am.period)
                LEFT JOIN account_fiscalyear af ON (af.id=ap.fiscalyear)
                '''
            where_fiscalyear = '''
                ap.fiscalyear = %d AND
                ''' % fiscalyear_id

        where_journal = ''
        if Transaction().context.get('journal'):
            journal_id = int(Transaction().context.get('journal'))
        if journal_id:
            where_journal = '''
                am.journal = %d AND
                ''' % journal_id

        where_period = ''
        if Transaction().context.get('period'):
            period_id = int(Transaction().context.get('period'))
        if period_id:
            where_period = '''
                am.period = %d AND
                ''' % period_id

        where_account = ''
        if Transaction().context.get('account'):
            account_id = int(Transaction().context.get('account'))
        if account_id:
            where_account = '''
                aml.account = %d AND
                ''' % account_id

        where_party = ''
        if Transaction().context.get('party'):
            party_id = int(Transaction().context.get('party'))
        if party_id:
            where_party = '''
                aml.party = %d AND
                ''' % party_id

        from_account_kind = where_account_kind = ''
        if Transaction().context.get('account_kind'):
            account_kind = list(Transaction().context.get('account_kind'))
        if account_kind:
            from_account_kind = ', account_account a'
            where_account_kind = ('aml.account = a.id '
                'AND a.kind IN (\'' +
                '\', \''.join(str(k) for k in account_kind) +
                '\') AND ')

        cursor = Transaction().connection.cursor()
        for line in lines:
            id = line.id
            date = line.move.date
            number = line.move.number
            debit = line.debit or Decimal('0.0')
            credit = line.credit or Decimal('0.0')
            cursor.execute("""
                SELECT
                    SUM(debit-credit)
                FROM
                    account_move am""" + from_fiscalyear + """,
                    account_move_line aml""" + from_account_kind + """
                WHERE """ + where_fiscalyear + where_journal +
                    where_period + where_account + where_party +
                    where_account_kind + """
                    aml.move = am.id
                    AND (
                        am.date < '%s'
                        OR (am.date = '%s' AND am.number < '%s')
                        OR (am.date = '%s' AND am.number = '%s'
                            AND aml.id < '%s')
                    )
                """ % (date, date, number, date, number, id))
            balance = cursor.fetchone()[0] or Decimal('0.0')
            if not isinstance(balance, Decimal):
                balance = Decimal(balance)
            balance += debit - credit
            res[id] = balance
        return res

    @classmethod
    def search(cls, args, offset=0, limit=None, order=None, count=False,
            query=False):
        lines = super(Line, cls).search(args, offset, limit, order,
            count, query)

        Move = Pool().get('account.move')
        cursor = Transaction().connection.cursor()

        table = cls.__table__()
        move = Move.__table__()

        if lines and isinstance(lines, list):
            red_sql = reduce_ids(table.id, [x.id for x in lines])

            # This sorting criteria must be the one used by the 'balance'
            # functional field above, so remember to modify that if you
            # want to change the order.
            cursor.execute(*table.join(move, condition=table.move == move.id
                    ).select(table.id,
                    where=red_sql,
                    order_by=(move.date, move.number, table.id)))

            result = cursor.fetchall()
            ids = [x[0] for x in result]
            lines = cls.browse(ids)
        return lines


class OpenMoveLineBalance(Wizard):
    'Open Type'
    __name__ = 'account.move.line.balance'
    start_state = 'open_'
    open_ = StateAction('current_account.act_move_line_balance')

    def do_open_(self, action):
        Party = Pool().get('party.party')

        party = Party(Transaction().context['active_id'])
        action['pyson_domain'] = PYSONEncoder().encode([
                ('party', '=', Transaction().context['active_id']),
                ('account.kind', 'in', ['payable', 'receivable'])
                ])
        action['pyson_context'] = PYSONEncoder().encode({
                'party': Transaction().context['active_id'],
                'account_kind': ['payable', 'receivable'],
                })
        action['name'] = 'Cuenta Corriente - %s' % (party.name)
        return action, {}


class MoveLineList(CompanyReport):
    'Move Line List'
    __name__ = 'account.move.line.move_line_list'

    @classmethod
    def get_context(cls, records, data):
        Invoice = Pool().get('account.invoice')
        report_context = super(MoveLineList, cls).get_context(records, data)

        for line in records:
            reference = ''
            model = str(line.origin)
            if model[:model.find(',')] == 'account.invoice':
                reference = Invoice(line.origin.id).reference
            line.reference = reference

        return report_context
