# -*- coding: utf-8 -*-
import logging
_logger = logging.getLogger(__name__)
from odoo import models


class U8SyncScheduler(models.AbstractModel):
    _name = 'hc.u8.sync.scheduler'
    _description = 'U8 同步调度器'

    def run_sync(self):
        """ir.cron 定时调用入口"""
        account_model = self.env['hc.u8.account']
        accounts = account_model.search([('active', '=', True)])
        _logger.info('U8 cron: found %d active accounts', len(accounts))
        for acc in accounts:
            try:
                acc._sync_purchases()
                _logger.info('U8 sync OK: %s -> %s', acc.company_id.name, acc.database)
            except Exception as e:
                _logger.exception('U8 sync FAIL: %s -> %s', acc.company_id.name, acc.database)
