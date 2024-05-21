# -*- coding: utf-8 -*-
# This file is part of the current_account module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
from decimal import Decimal
from sql import Column, Literal, Null
from sql.aggregate import Sum, Window
from sql.conditionals import Coalesce

from trytond.model import fields, ModelSQL, ModelView
from trytond.wizard import Wizard, StateAction
from trytond.pool import Pool, PoolMeta
from trytond.pyson import PYSONEncoder, Eval, If
from trytond.transaction import Transaction
from trytond.tools import reduce_ids, grouped_slice
from trytond.report import Report
from trytond.modules.company import CompanyReport


class OriginTextMixin:
    __slots__ = ()

    @classmethod
    def get_origin_text(cls, lines, name):
        result = {}
        for line in lines:
            reference = ''
            document = line.move_origin
            origin = str(document)
            model = origin[:origin.find(',')]
            if model == 'account.invoice':
                reference = cls._get_invoice_text(document)
            elif model == 'account.voucher':
                reference = cls._get_voucher_text(document)
            elif model == 'account.move':
                reference = 'Asiento %s' % str(document.number)
            elif model == 'account.statement':
                reference = 'Extracto %s' % str(document.rec_name)
            result[line.id] = reference
        return result

    @classmethod
    def _get_invoice_text(cls, invoice):
        if invoice.type == 'in':
            invoice_names = {
                '001': 'FC A',
                '002': 'ND A',
                '003': 'NC A',
                '004': 'RC A',
                '005': 'NV A',
                '006': 'FC B',
                '007': 'ND B',
                '008': 'NC B',
                '009': 'RC B',
                '010': 'NV B',
                '011': 'FC C',
                '012': 'ND C',
                '013': 'NC C',
                '015': 'RC C',
                '016': 'NV C',
                '017': 'LQ A',
                '018': 'LQ B',
                '019': 'FC EXT',
                '020': 'ND EXT',
                '021': 'NC EXT',
                '037': 'ND RG1415',
                '038': 'NC RG1415',
                '051': 'FC M',
                '052': 'ND M',
                '053': 'NC M',
                '054': 'RC M',
                '055': 'NV M',
                '063': 'LQ A',
                '064': 'LQ B',
                '066': 'D IMP',
                '068': 'LQ C',
                '081': 'TF A',
                '082': 'TF B',
                '083': 'T',
                '089': 'RD',
                '091': 'RM R',
                '110': 'TNC',
                '111': 'TF C',
                '112': 'TNC A',
                '113': 'TNC B',
                '114': 'TNC C',
                '115': 'TND A',
                '116': 'TND B',
                '117': 'TND C',
                '118': 'TF M',
                '119': 'TNC M',
                '120': 'TND M',
                }
            if invoice.tipo_comprobante in invoice_names:
                invoice_name = invoice_names[invoice.tipo_comprobante]
            else:
                invoice_name = invoice.tipo_comprobante_string or 'FC'
            invoice_number = invoice.reference or ''
        else:
            invoice_names = {
                '1': 'FC A',
                '2': 'ND A',
                '3': 'NC A',
                '4': 'RC A',
                '5': 'NV A',
                '6': 'FC B',
                '7': 'ND B',
                '8': 'NC B',
                '9': 'RC B',
                '10': 'NV B',
                '11': 'FC C',
                '12': 'ND C',
                '13': 'NC C',
                '15': 'RC C',
                '16': 'NV C',
                '19': 'FC E',
                '20': 'ND E',
                '21': 'NC E',
                '201': 'FCE A',
                '202': 'NDE A',
                '203': 'NCE A',
                '206': 'FCE B',
                '207': 'NDE B',
                '208': 'NCE B',
                '211': 'FCE C',
                '212': 'NDE C',
                '213': 'NCE C',
                }
            if invoice.invoice_type.invoice_type in invoice_names:
                invoice_name = invoice_names[invoice.invoice_type.invoice_type]
            else:
                invoice_name = invoice.invoice_type.invoice_type_string or 'FC'
            invoice_number = invoice.number or ''
        return '%s %s' % (invoice_name, invoice_number)

    @classmethod
    def _get_voucher_text(cls, voucher):
        if voucher.voucher_type == 'payment':
            voucher_name = 'Pago'
        else:
            voucher_name = 'Recibo'
        voucher_number = voucher.number or ''
        return '%s %s' % (voucher_name, voucher_number)


class PartyBalanceAccount(ModelSQL, ModelView):
    'Party Balance Account'
    __name__ = 'party.balance.account'

    name = fields.Char('Name')
    code = fields.Char('Code')
    tax_identifier = fields.Function(fields.Many2One(
        'party.identifier', 'Tax Identifier'),
        'get_tax_identifier', searcher='search_tax_identifier')
    currency_digits = fields.Function(fields.Integer('Currency Digits'),
        'get_currency_digits')
    balance = fields.Function(fields.Numeric('Balance',
        digits=(16, Eval('currency_digits', 2))),
        'get_balance', searcher='search_balance')
    lines = fields.One2Many('party.balance.line', 'balance_account', 'Lines',
        readonly=True)

    @classmethod
    def __setup__(cls):
        super().__setup__()
        cls._order.insert(0, ('name', 'ASC'))

    @classmethod
    def table_query(cls):
        pool = Pool()
        Party = pool.get('party.party')
        Category = pool.get('party.category')

        party = Party.__table__()
        category_parties = Literal(True)
        category = Transaction().context.get('category')
        if category:
            categories = Category.search([
                ('parent', 'child_of', [category]),
                ])
            parties = Party.search([
                ('categories', 'in', [c.id for c in categories])
                ])
            if parties:
                category_parties = party.id.in_([p.id for p in parties])
            else:
                category_parties = Literal(False)

        columns = []
        for fname, field in cls._fields.items():
            if not hasattr(field, 'set'):
                columns.append(Column(party, fname).as_(fname))
        return party.select(*columns,
            where=(party.active == Literal(True)
                   & category_parties))

    @classmethod
    def get_tax_identifier(cls, parties, names):
        pool = Pool()
        Party = pool.get('party.party')

        result = {'tax_identifier': dict((p.id, None) for p in parties)}
        types = Party.tax_identifier_types()
        # Add Argentine DNI if not included
        if 'ar_dni' not in types:
            types.append('ar_dni')
        for p in parties:
            party, = Party.browse([p.id])
            for identifier in party.identifiers:
                result['tax_identifier'][p.id] = identifier.id \
                    if identifier.type in types else None
        return result

    @classmethod
    def search_tax_identifier(cls, name, clause):
        pool = Pool()
        Party = pool.get('party.party')

        _, operator, value = clause
        types = Party.tax_identifier_types()
        if 'ar_dni' not in types:
            types.append('ar_dni')
        domain = [
            ('identifiers', 'where', [
                    ('code', operator, value),
                    ('type', 'in', types),
                    ]),
            ]
        # Add party without tax identifier
        if ((operator == '=' and value is None)
                or (operator == 'in' and None in value)):
            domain = ['OR',
                domain, [
                    ('identifiers', 'not where', [
                            ('type', 'in', types),
                            ]),
                    ],
                ]
        ids = [p.id for p in Party.search(domain)]
        return [('id', 'in', ids)]

    @classmethod
    def get_currency_digits(cls, parties, name):
        pool = Pool()
        Company = pool.get('company.company')
        company_id = Transaction().context.get('company')
        if company_id:
            company = Company(company_id)
            digits = company.currency.digits
        else:
            digits = 2
        return {p.id: digits for p in parties}

    @classmethod
    def get_balance(cls, parties, names):
        '''
        Function to compute balance for party ids.
        '''
        result = {}
        pool = Pool()
        Move = pool.get('account.move')
        MoveLine = pool.get('account.move.line')
        Account = pool.get('account.account')
        AccountType = pool.get('account.account.type')
        User = pool.get('res.user')
        cursor = Transaction().connection.cursor()

        move = Move.__table__()
        line = MoveLine.__table__()
        account = Account.__table__()
        account_type = AccountType.__table__()

        result['balance'] = dict((p.id, Decimal('0.0')) for p in parties)

        user = User(Transaction().user)
        if not user.company:
            return result
        company_id = user.company.id
        exp = Decimal(str(10.0 ** -user.company.currency.digits))

        amount = Sum(Coalesce(line.debit, 0) - Coalesce(line.credit, 0))
        from_date_where = to_date_where = Literal(True)
        if Transaction().context.get('from_date'):
            from_date_where = (move.date >=
                    Transaction().context.get('from_date'))
        if Transaction().context.get('to_date'):
            to_date_where = (move.date <=
                    Transaction().context.get('to_date'))
        for sub_parties in grouped_slice(parties):
            sub_ids = [p.id for p in sub_parties]
            party_where = reduce_ids(line.party, sub_ids)
            cursor.execute(*line.join(move,
                    condition=move.id == line.move
                    ).join(account,
                    condition=account.id == line.account
                    ).join(account_type,
                    condition=account.type == account_type.id
                    ).select(line.party, amount,
                    where=(
                        (getattr(account_type, 'payable')
                         | getattr(account_type, 'receivable'))
                        & (account.company == company_id)
                        & party_where
                        & from_date_where
                        & to_date_where),
                    group_by=line.party))
            for party, value in cursor.fetchall():
                # SQLite uses float for SUM
                if not isinstance(value, Decimal):
                    value = Decimal(str(value))
                result['balance'][party] = value.quantize(exp)
        return result

    @classmethod
    def search_balance(cls, name, clause):
        pool = Pool()
        Move = pool.get('account.move')
        MoveLine = pool.get('account.move.line')
        Account = pool.get('account.account')
        AccountType = pool.get('account.account.type')
        User = pool.get('res.user')

        move = Move.__table__()
        line = MoveLine.__table__()
        account = Account.__table__()
        account_type = AccountType.__table__()

        _, operator, value = clause

        user = User(Transaction().user)
        if not user.company:
            return []
        company_id = user.company.id

        from_date_where = to_date_where = Literal(True)
        if Transaction().context.get('from_date'):
            from_date_where = (move.date >=
                    Transaction().context.get('from_date'))
        if Transaction().context.get('to_date'):
            to_date_where = (move.date <=
                    Transaction().context.get('to_date'))

        Operator = fields.SQL_OPERATORS[operator]

        # Need to cast numeric for sqlite
        cast_ = MoveLine.debit.sql_cast
        amount = cast_(Sum(Coalesce(line.debit, 0) - Coalesce(line.credit, 0)))
        if operator in {'in', 'not in'}:
            value = [cast_(Literal(Decimal(v or 0))) for v in value]
        else:
            value = cast_(Literal(Decimal(value or 0)))
        query = (line.join(move, condition=move.id == line.move
                ).join(account, condition=account.id == line.account
                ).join(account_type, condition=account.type == account_type.id
                ).select(line.party,
                where=(
                    (getattr(account_type, 'payable')
                    | getattr(account_type, 'receivable'))
                    & (line.party != Null)
                    & (account.company == company_id)
                    & from_date_where
                    & to_date_where),
                group_by=line.party,
                having=Operator(amount, value)))
        return [('id', 'in', query)]


class PartyBalanceAccountContext(ModelView):
    'Party Balance Account Context'
    __name__ = 'party.balance.account.context'

    company = fields.Many2One('company.company', 'Company', required=True)
    category = fields.Many2One('party.category', 'Category')
    from_date = fields.Date("From Date",
        domain=[
            If(Eval('to_date') & Eval('from_date'),
                ('from_date', '<=', Eval('to_date')),
                ()),
            ])
    to_date = fields.Date("To Date",
        domain=[
            If(Eval('from_date') & Eval('to_date'),
                ('to_date', '>=', Eval('from_date')),
                ()),
            ])

    @classmethod
    def default_company(cls):
        return Transaction().context.get('company')

    @classmethod
    def default_from_date(cls):
        return Transaction().context.get('from_date')

    @classmethod
    def default_to_date(cls):
        return Transaction().context.get('to_date')


class PartyBalanceLine(OriginTextMixin, ModelSQL, ModelView):
    'Party Balance Line'
    __name__ = 'party.balance.line'

    balance_account = fields.Many2One('party.balance.account',
        'Party Balance Account')
    move = fields.Many2One('account.move', 'Move')
    date = fields.Date('Date')
    maturity_date = fields.Date('Maturity Date')
    origin_text = fields.Function(fields.Char('Origin'), 'get_origin_text')
    move_origin = fields.Function(
        fields.Reference("Move Origin", selection='get_move_origin'),
        'get_move_field', searcher='search_move_field')
    party = fields.Many2One('party.party', 'Party',
        states={'invisible': ~Eval('party_required', False)},
        context={'company': Eval('company', -1)}, depends={'company'})
    company = fields.Many2One('company.company', 'Company')
    debit = fields.Numeric('Debit',
        digits=(16, Eval('currency_digits', 2)))
    credit = fields.Numeric('Credit',
        digits=(16, Eval('currency_digits', 2)))
    balance = fields.Numeric('Balance',
        digits=(16, Eval('currency_digits', 2)))
    move_description = fields.Char('Move Description')
    currency_digits = fields.Function(fields.Integer('Currency Digits'),
        'get_currency_digits')

    @classmethod
    def __setup__(cls):
        super().__setup__()
        cls._order.insert(0, ('date', 'ASC'))

    @classmethod
    def table_query(cls):
        pool = Pool()
        Line = pool.get('account.move.line')
        Move = pool.get('account.move')
        Account = pool.get('account.account')
        AccountType = pool.get('account.account.type')

        transaction = Transaction()
        context = Transaction().context
        database = transaction.database
        line = Line.__table__()
        move = Move.__table__()
        account = Account.__table__()
        account_type = AccountType.__table__()
        columns = []
        for fname, field in cls._fields.items():
            if hasattr(field, 'set'):
                continue
            field_line = getattr(Line, fname, None)
            if fname == 'balance_account':
                column = line.party.as_('balance_account')
            elif fname == 'balance':
                if database.has_window_functions():
                    w_columns = [line.party]
                    column = Sum(line.debit - line.credit,
                        window=Window(w_columns,
                            order_by=[move.date.asc, line.id])).as_('balance')
                else:
                    column = (line.debit - line.credit).as_('balance')
            elif fname == 'move_description':
                column = Column(move, 'description').as_(fname)
            elif (not field_line
                    or fname == 'state'
                    or isinstance(field_line, fields.Function)):
                column = Column(move, fname).as_(fname)
            else:
                column = Column(line, fname).as_(fname)
            columns.append(column)

        company_id = context.get('company')
        party_id = context.get('party')
        where_from_date = where_to_date = Literal(True)
        if context.get('from_date'):
            where_from_date = (move.date >= context.get('from_date'))
        if context.get('to_date'):
            where_to_date = (move.date <= context.get('to_date'))

        with Transaction().set_context():
            line_query, fiscalyear_ids = Line.query_get(line)
        return line.join(move, condition=line.move == move.id
            ).join(account, condition=line.account == account.id
            ).join(account_type, condition=account.type == account_type.id
            ).select(*columns, where=(
                line_query
                & (move.company == company_id)
                & (line.party == party_id)
                & where_from_date & where_to_date
                & (getattr(account_type, 'payable')
                | getattr(account_type, 'receivable'))))

    def get_currency_digits(self, name):
        return self.company.currency.digits

    @classmethod
    def get_move_origin(cls):
        Move = Pool().get('account.move')
        return Move.get_origin()

    def get_move_field(self, name):
        field = getattr(self.__class__, name)
        if name.startswith('move_'):
            name = name[5:]
        value = getattr(self.move, name)
        if isinstance(value, ModelSQL):
            if field._type == 'reference':
                return str(value)
            return value.id
        return value

    @classmethod
    def search_move_field(cls, name, clause):
        nested = clause[0].lstrip(name)
        if name.startswith('move_'):
            name = name[5:]
        return [('move.' + name + nested,) + tuple(clause[1:])]


class Line(OriginTextMixin, metaclass=PoolMeta):
    __name__ = 'account.move.line'

    origin_text = fields.Function(fields.Char('Origin'), 'get_origin_text')
    balance = fields.Function(fields.Numeric('Balance',
        digits=(16, 2)), 'get_balance')

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


class OpenStatementOfAccount(Wizard):
    'Open Statement of Account'
    __name__ = 'account.move.line.balance'

    start_state = 'open_'
    open_ = StateAction('current_account.act_statement_of_account')

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


class StatementOfAccountReport(CompanyReport):
    'Statement of Account'
    __name__ = 'account.move.line.move_line_list'


class StatementOfAccountSpreadSheet(CompanyReport):
    'Statement of Account'
    __name__ = 'account.move.line.move_line_list_spreadsheet'


class PartyBalanceAccountReport(Report):
    'Party Balance Account Report'
    __name__ = 'party.balance.account.report'


class PartyBalanceLineReport(CompanyReport):
    'Party Balance Line Report'
    __name__ = 'party.balance.line.report'


class PartyBalanceLineSpreadSheet(CompanyReport):
    'Party Balance Line Spreadsheet'
    __name__ = 'party.balance.line.spreadsheet'
