# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class RealEstatePayment(models.Model):
    """A single scheduled collection (rent instalment or sale payment).
    Overdue lines drive the delinquency alerts."""
    _name = 'real.estate.payment'
    _description = 'Real Estate Collection'
    _order = 'due_date, id'

    contract_id = fields.Many2one(
        'real.estate.contract', string='Contract', required=True,
        ondelete='cascade', index=True)
    description = fields.Char(string='Description')
    company_id = fields.Many2one(
        'res.company', related='contract_id.company_id', store=True, string='Company')
    currency_id = fields.Many2one(
        'res.currency', related='contract_id.currency_id', string='Currency')

    # Related parties / property (handy for grouping in the dashboard)
    property_id = fields.Many2one(
        'real.estate.property', related='contract_id.property_id',
        store=True, string='Property')
    tenant_id = fields.Many2one(
        'res.partner', related='contract_id.tenant_id',
        store=True, string='Tenant / Buyer')

    amount = fields.Monetary(string='Amount', required=True, currency_field='currency_id')
    due_date = fields.Date(string='Due Date', required=True, index=True)
    payment_date = fields.Date(string='Payment Date')

    state = fields.Selection(
        selection=[
            ('pending', 'Pending'),
            ('overdue', 'Overdue'),
            ('paid', 'Paid'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status', default='pending', required=True, index=True)

    # Non-stored helpers for the UI (decorations / form banner)
    days_overdue = fields.Integer(
        string='Days Overdue', compute='_compute_days_overdue')

    @api.depends('state', 'due_date')
    def _compute_days_overdue(self):
        today = fields.Date.context_today(self)
        for payment in self:
            if payment.state in ('pending', 'overdue') and payment.due_date \
                    and payment.due_date < today:
                payment.days_overdue = (today - payment.due_date).days
            else:
                payment.days_overdue = 0

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def action_register_payment(self):
        for payment in self:
            payment.write({
                'state': 'paid',
                'payment_date': fields.Date.context_today(payment),
            })

    def action_reset_pending(self):
        self.write({'state': 'pending', 'payment_date': False})

    # ------------------------------------------------------------------
    # Scheduled job: flag overdue collections and raise alerts
    # ------------------------------------------------------------------
    @api.model
    def _cron_check_overdue_payments(self):
        """Daily job. Moves due 'pending' collections to 'overdue', posts a
        message on the contract and schedules a follow-up activity."""
        today = fields.Date.context_today(self)
        overdue = self.search([
            ('state', '=', 'pending'),
            ('due_date', '<', today),
        ])
        if not overdue:
            return
        overdue.write({'state': 'overdue'})
        for contract in overdue.mapped('contract_id'):
            lines = overdue.filtered(lambda p: p.contract_id == contract)
            total = sum(lines.mapped('amount'))
            contract.message_post(
                body=_(
                    'Delinquency alert: tenant %(tenant)s has %(count)s overdue '
                    'collection(s) for a total of %(amount)s.',
                    tenant=contract.tenant_id.display_name,
                    count=len(lines),
                    amount=total,
                ),
                subtype_xmlid='mail.mt_comment',
            )
            if contract.agent_id:
                contract.activity_schedule(
                    'mail.mail_activity_data_todo',
                    summary=_('Overdue collection - contact tenant'),
                    note=_('The tenant has overdue rent. Please follow up.'),
                    user_id=contract.agent_id.id,
                )
