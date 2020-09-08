# This file is part of Tryton.  The COPYRIGHT file at the top level of
# this repository contains the full copyright notices and license terms.

try:
    from trytond.modules.current_account.tests.test_current_account \
        import suite
except ImportError:
    from .test_current_account import suite

__all__ = ['suite']
