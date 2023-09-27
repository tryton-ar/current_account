# -*- coding: utf-8 -*-
# This file is part of the current_account module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
from decimal import Decimal

from trytond.model import fields
from trytond.wizard import Wizard, StateAction
from trytond.pool import Pool, PoolMeta
from trytond.pyson import PYSONEncoder, Eval
from trytond.transaction import Transaction
from trytond.tools import reduce_ids
from trytond.modules.company import CompanyReport


class Line(metaclass=PoolMeta):
    __name__ = 'account.move.line'

    origin_text = fields.Function(fields.Char('Origin'), 'get_origin_text')
    balance = fields.Function(fields.Numeric('Balance',
        digits=(16, Eval('currency_digits', 2))),
        'get_balance')

    @classmethod
    def get_balance(cls, lines, name):
        if not lines:
            return {}

        ids = [x.id for x in lines]
        res = {}.fromkeys(ids, Decimal('0.0'))
        fiscalyear_id = journal_id = period_id = account_id = None
        from_date = to_date = None
        company_id = party_id = account_kind = None

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

        where_from_date = ''
        if Transaction().context.get('from_date'):
            from_date = Transaction().context.get('from_date')
        if from_date:
            where_from_date = '''
                am.date >= '%s' AND
                ''' % from_date

        where_to_date = ''
        if Transaction().context.get('to_date'):
            to_date = Transaction().context.get('to_date')
        if to_date:
            where_to_date = '''
                am.date <= '%s' AND
                ''' % to_date

        where_account = ''
        if Transaction().context.get('account'):
            account_id = int(Transaction().context.get('account'))
        if account_id:
            where_account = '''
                aml.account = %d AND
                ''' % account_id

        where_company = ''
        if Transaction().context.get('company'):
            company_id = int(Transaction().context.get('company'))
        if company_id:
            where_company = '''
                am.company = %d AND
                ''' % company_id

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
            from_account_kind = ', account_account a, account_account_type at'
            where_account_kind = ('aml.account = a.id '
                'AND a.type = at.id '
                'AND (at.payable IS TRUE OR at.receivable IS TRUE) AND ')

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
                WHERE """ + where_fiscalyear + where_journal
                    + where_from_date + where_to_date + where_company
                    + where_period + where_account + where_party
                    + where_account_kind + """
                    aml.move = am.id
                    AND (
                        am.date < %s
                        OR (am.date = %s AND am.number < %s)
                        OR (am.date = %s AND am.number = %s
                            AND aml.id < %s)
                    )
                """, (date, date, number, date, number, id))
            balance = cursor.fetchone()[0] or Decimal('0.0')
            if not isinstance(balance, Decimal):
                balance = Decimal(balance)
            balance += debit - credit
            res[id] = balance
        return res

    @classmethod
    def search(cls, args, offset=0, limit=None, order=None, count=False,
            query=False):
        lines = super().search(args, offset, limit, order, count, query)

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

    @classmethod
    def get_origin_text(cls, lines, name):
        result = {}
        for line in lines:
            reference = ''
            origin = str(line.move_origin)
            model = origin[:origin.find(',')]
            if model == 'account.invoice':
                invoice = line.move_origin
                reference = 'Factura '
                if invoice.type == 'in':
                    reference += invoice.reference or ''
                else:
                    reference += invoice.number or ''
            elif model == 'account.voucher':
                reference = 'Comprobante %s' % str(line.move_origin.number)
            elif model == 'account.move':
                reference = 'Asiento %s' % str(line.move_origin.number)
            result[line.id] = reference
        return result


class OpenMoveLineBalance(Wizard):
    'Open Type'
    __name__ = 'account.move.line.balance'

    start_state = 'open_'
    open_ = StateAction('current_account.act_move_line_balance')

    def do_open_(self, action):
        Party = Pool().get('party.party')

        party = Party(Transaction().context['active_id'])
        pyson_domain = [
                ('move.company', '=', Transaction().context['company']),
                ('party', '=', Transaction().context['active_id']),
                ['OR',
                    ('account.type.payable', '=', True),
                    ('account.type.receivable', '=', True)],
                ]
        pyson_context = {
                'company': Transaction().context['company'],
                'party': Transaction().context['active_id'],
                'account_kind': ['payable', 'receivable'],
                }

        if Transaction().context.get('from_date'):
            pyson_domain.append(
                ('date', '>=', Transaction().context['from_date']))
            pyson_context['from_date'] = Transaction().context['from_date']
        if Transaction().context.get('to_date'):
            pyson_domain.append(
                ('date', '<=', Transaction().context['to_date']))
            pyson_context['to_date'] = Transaction().context['to_date']

        action['pyson_domain'] = PYSONEncoder().encode(pyson_domain)
        action['pyson_context'] = PYSONEncoder().encode(pyson_context)
        action['name'] = 'Cuenta corriente - %s' % (party.name)
        return action, {}


class MoveLineList(CompanyReport):
    'Move Line List'
    __name__ = 'account.move.line.move_line_list'


class MoveLineListSpreadSheet(CompanyReport):
    'Move Line List'
    __name__ = 'account.move.line.move_line_list_spreadsheet'
