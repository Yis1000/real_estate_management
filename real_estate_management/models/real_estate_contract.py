# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class RealEstateContract(models.Model):
    """Rental or sale contract bound to a property. Generates the collection
    schedule and tracks delinquency (overdue payments)."""
    _name = 'real.estate.contract'
    _description = 'Real Estate Contract'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_start desc, id desc'

    name = fields.Char(
        string='Contract Reference', copy=False, readonly=True, index=True,
        default=lambda self: _('New'))
    active = fields.Boolean(string='Active', default=True)
    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company)
    currency_id = fields.Many2one(
        'res.currency', related='company_id.currency_id', string='Currency')

    contract_type = fields.Selection(
        selection=[('rent', 'Rental'), ('sale', 'Sale')],
        string='Contract Type', default='rent', required=True, tracking=True)
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('running', 'Running'),
            ('expired', 'Expired'),
            ('done', 'Closed'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status', default='draft', required=True, tracking=True)

    # ------------------------------------------------------------------
    # Parties & property
    # ------------------------------------------------------------------
    property_id = fields.Many2one(
        'real.estate.property', string='Property', required=True,
        tracking=True, ondelete='restrict')
    owner_id = fields.Many2one(
        'res.partner', string='Owner', related='property_id.owner_id',
        store=True, readonly=True)
    tenant_id = fields.Many2one(
        'res.partner', string='Tenant / Buyer', required=True, tracking=True,
        domain=['|', ('is_property_tenant', '=', True), ('is_property_owner', '=', True)])
    agent_id = fields.Many2one(
        'res.users', string='Responsible Agent', tracking=True,
        default=lambda self: self.env.user)

    # ------------------------------------------------------------------
    # Dates & amounts
    # ------------------------------------------------------------------
    date_signed = fields.Date(string='Signature Date', default=fields.Date.context_today)
    date_start = fields.Date(string='Start Date', required=True,
                             default=fields.Date.context_today, tracking=True)
    date_end = fields.Date(string='End Date', tracking=True)
    payment_day = fields.Integer(
        string='Collection Day', default=1,
        help='Day of the month on which the rent is collected (1-28).')
    rent_amount = fields.Monetary(string='Monthly Rent', currency_field='currency_id')
    sale_amount = fields.Monetary(string='Sale Price', currency_field='currency_id')
    deposit = fields.Monetary(string='Security Deposit', currency_field='currency_id')
    note = fields.Html(string='Terms & Conditions')
    occupants_description = fields.Text(
        string='Occupants',
        help='Number and identification of persons who will occupy the dwelling '
             '(e.g. "Lessee and spouse, plus two children under 18").')
    landlord_iban = fields.Char(
        string='Landlord IBAN',
        help='Bank account where the rent is paid by transfer. '
             'Shown in the printed contract.')

    # ------------------------------------------------------------------
    # Collections
    # ------------------------------------------------------------------
    payment_ids = fields.One2many(
        'real.estate.payment', 'contract_id', string='Collections')
    payment_count = fields.Integer(
        compute='_compute_payment_stats', string='Number of Collections', store=True)
    amount_collected = fields.Monetary(
        string='Collected', compute='_compute_payment_stats', store=True,
        currency_field='currency_id')
    amount_pending = fields.Monetary(
        string='Pending', compute='_compute_payment_stats', store=True,
        currency_field='currency_id')
    amount_overdue = fields.Monetary(
        string='Overdue', compute='_compute_payment_stats', store=True,
        currency_field='currency_id')
    overdue_count = fields.Integer(
        string='Overdue Collections', compute='_compute_payment_stats', store=True)
    next_payment_date = fields.Date(
        string='Next Collection', compute='_compute_payment_stats', store=True)

    # ------------------------------------------------------------------
    # Delinquency alert  ->  this is the field that "turns red"
    # ------------------------------------------------------------------
    payment_state = fields.Selection(
        selection=[
            ('no_payment', 'No Collections'),
            ('on_track', 'On Track'),
            ('overdue', 'Overdue'),
            ('paid', 'Fully Paid'),
        ],
        string='Collection Status', compute='_compute_payment_stats',
        store=True, tracking=True)
    is_overdue = fields.Boolean(
        string='Has Overdue', compute='_compute_payment_stats', store=True,
        help='True when the tenant has at least one overdue collection.')

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------
    @api.depends('payment_ids.state', 'payment_ids.amount', 'payment_ids.due_date')
    def _compute_payment_stats(self):
        for contract in self:
            payments = contract.payment_ids
            contract.payment_count = len(payments)
            contract.amount_collected = sum(
                payments.filtered(lambda p: p.state == 'paid').mapped('amount'))
            pending = payments.filtered(lambda p: p.state in ('pending', 'overdue'))
            overdue = payments.filtered(lambda p: p.state == 'overdue')
            contract.amount_pending = sum(pending.mapped('amount'))
            contract.amount_overdue = sum(overdue.mapped('amount'))
            contract.overdue_count = len(overdue)
            contract.is_overdue = bool(overdue)
            contract.next_payment_date = min(
                pending.mapped('due_date'), default=False)
            # Derive the global collection status of the contract
            if not payments:
                contract.payment_state = 'no_payment'
            elif overdue:
                contract.payment_state = 'overdue'
            elif pending:
                contract.payment_state = 'on_track'
            else:
                contract.payment_state = 'paid'

    # ------------------------------------------------------------------
    # ORM overrides
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'real.estate.contract') or _('New')
        return super().create(vals_list)

    @api.onchange('property_id')
    def _onchange_property_id(self):
        if self.property_id:
            self.rent_amount = self.property_id.rent_price
            self.sale_amount = self.property_id.sale_price

    @api.constrains('payment_day')
    def _check_payment_day(self):
        for contract in self:
            if not 1 <= contract.payment_day <= 28:
                raise UserError(_('The collection day must be between 1 and 28.'))

    # ------------------------------------------------------------------
    # Collection schedule
    # ------------------------------------------------------------------
    def _generate_payment_schedule(self):
        """(Re)build the pending collection lines for this contract."""
        Payment = self.env['real.estate.payment']
        for contract in self:
            # Remove only collections that have not been paid yet
            contract.payment_ids.filtered(
                lambda p: p.state in ('pending', 'overdue')).unlink()
            if contract.contract_type == 'sale':
                if contract.sale_amount:
                    Payment.create({
                        'contract_id': contract.id,
                        'due_date': contract.date_start,
                        'amount': contract.sale_amount,
                        'description': _('Sale payment'),
                    })
                continue
            # Rental: one monthly collection from start to end date
            if not (contract.date_start and contract.date_end and contract.rent_amount):
                raise UserError(_(
                    'To generate the rent schedule set the start date, '
                    'end date and the monthly rent.'))
            cursor = contract.date_start
            index = 1
            while cursor <= contract.date_end:
                day = min(contract.payment_day, 28)
                due = cursor.replace(day=day)
                if due < contract.date_start:
                    due = contract.date_start
                Payment.create({
                    'contract_id': contract.id,
                    'due_date': due,
                    'amount': contract.rent_amount,
                    'description': _('Rent month %s', index),
                })
                cursor += relativedelta(months=1)
                index += 1

    # ------------------------------------------------------------------
    # Workflow actions
    # ------------------------------------------------------------------
    def action_confirm(self):
        for contract in self:
            contract._generate_payment_schedule()
            contract.state = 'running'
            if contract.contract_type == 'rent':
                contract.property_id.state = 'rented'
            else:
                contract.property_id.state = 'sold'
        return True

    def action_close(self):
        for contract in self:
            contract.state = 'done'
            if contract.property_id.state in ('rented', 'reserved'):
                contract.property_id.state = 'available'

    def action_cancel(self):
        for contract in self:
            contract.payment_ids.filtered(
                lambda p: p.state in ('pending', 'overdue')).write({'state': 'cancelled'})
            contract.state = 'cancelled'

    def action_set_to_draft(self):
        self.write({'state': 'draft'})

    def action_view_payments(self):
        self.ensure_one()
        return {
            'name': _('Collections'),
            'type': 'ir.actions.act_window',
            'res_model': 'real.estate.payment',
            'view_mode': 'list,form',
            'domain': [('contract_id', '=', self.id)],
            'context': {'default_contract_id': self.id},
        }
