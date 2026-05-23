# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _


class RealEstateDashboard(models.Model):
    """Singleton record that exposes all the real-estate KPIs as computed
    fields. The dashboard form view (kanban-of-cards style) reads from here."""
    _name = 'real.estate.dashboard'
    _description = 'Real Estate Dashboard'

    name = fields.Char(default='Dashboard', readonly=True)
    currency_id = fields.Many2one(
        'res.currency', compute='_compute_kpis', string='Currency')

    # ------------------------------------------------------------------
    # Top KPI row
    # ------------------------------------------------------------------
    property_count = fields.Integer(compute='_compute_kpis')
    available_count = fields.Integer(compute='_compute_kpis')
    contract_count = fields.Integer(compute='_compute_kpis')
    active_contract_count = fields.Integer(compute='_compute_kpis')
    active_rate = fields.Float(compute='_compute_kpis', digits=(5, 1))

    # ------------------------------------------------------------------
    # Directory row
    # ------------------------------------------------------------------
    tenant_count = fields.Integer(compute='_compute_kpis')
    owner_count = fields.Integer(compute='_compute_kpis')
    provider_count = fields.Integer(compute='_compute_kpis')

    # ------------------------------------------------------------------
    # Rental analytics (contract_type='rent')
    # ------------------------------------------------------------------
    rent_draft = fields.Integer(compute='_compute_kpis')
    rent_running = fields.Integer(compute='_compute_kpis')
    rent_expired = fields.Integer(compute='_compute_kpis')
    rent_done = fields.Integer(compute='_compute_kpis')
    rent_cancelled = fields.Integer(compute='_compute_kpis')

    # ------------------------------------------------------------------
    # Sales analytics (contract_type='sale')
    # ------------------------------------------------------------------
    sale_draft = fields.Integer(compute='_compute_kpis')
    sale_running = fields.Integer(compute='_compute_kpis')
    sale_expired = fields.Integer(compute='_compute_kpis')
    sale_done = fields.Integer(compute='_compute_kpis')
    sale_cancelled = fields.Integer(compute='_compute_kpis')

    # ------------------------------------------------------------------
    # Collections & operations
    # ------------------------------------------------------------------
    overdue_count = fields.Integer(compute='_compute_kpis')
    overdue_amount = fields.Monetary(
        compute='_compute_kpis', currency_field='currency_id')
    pending_count = fields.Integer(compute='_compute_kpis')
    pending_amount = fields.Monetary(
        compute='_compute_kpis', currency_field='currency_id')
    open_tickets = fields.Integer(compute='_compute_kpis')
    active_renovations = fields.Integer(compute='_compute_kpis')
    visits_today = fields.Integer(compute='_compute_kpis')
    visits_week = fields.Integer(compute='_compute_kpis')

    # ------------------------------------------------------------------
    # Compute everything in a single pass — cheaper than one method per KPI.
    # ------------------------------------------------------------------
    def _compute_kpis(self):
        Property = self.env['real.estate.property']
        Contract = self.env['real.estate.contract']
        Payment = self.env['real.estate.payment']
        Partner = self.env['res.partner']
        Maint = self.env['real.estate.maintenance']
        Renov = self.env['real.estate.renovation']
        Visit = self.env['real.estate.visit']
        currency = self.env.company.currency_id

        rent_states = ('draft', 'running', 'expired', 'done', 'cancelled')

        today = fields.Date.context_today(self)
        today_start = fields.Datetime.to_datetime(today)
        today_end = today_start + relativedelta(days=1)
        week_end = today_start + relativedelta(days=7)

        for rec in self:
            rec.currency_id = currency.id
            rec.property_count = Property.search_count([])
            rec.available_count = Property.search_count([('state', '=', 'available')])
            rec.contract_count = Contract.search_count([])
            rec.active_contract_count = Contract.search_count([('state', '=', 'running')])
            rec.active_rate = (
                (rec.active_contract_count / rec.contract_count) * 100.0
                if rec.contract_count else 0.0)

            rec.tenant_count = Partner.search_count([('is_property_tenant', '=', True)])
            rec.owner_count = Partner.search_count([('is_property_owner', '=', True)])
            rec.provider_count = Partner.search_count([('is_maintenance_provider', '=', True)])

            for st in rent_states:
                setattr(rec, f'rent_{st}', Contract.search_count(
                    [('contract_type', '=', 'rent'), ('state', '=', st)]))
                setattr(rec, f'sale_{st}', Contract.search_count(
                    [('contract_type', '=', 'sale'), ('state', '=', st)]))

            overdue = Payment.search([('state', '=', 'overdue')])
            pending = Payment.search([('state', '=', 'pending')])
            rec.overdue_count = len(overdue)
            rec.overdue_amount = sum(overdue.mapped('amount'))
            rec.pending_count = len(pending)
            rec.pending_amount = sum(pending.mapped('amount'))

            rec.open_tickets = Maint.search_count(
                [('state', 'in', ('new', 'in_progress'))])
            rec.active_renovations = Renov.search_count(
                [('state', 'in', ('draft', 'in_progress'))])
            rec.visits_today = Visit.search_count([
                ('date_start', '>=', today_start),
                ('date_start', '<', today_end),
                ('state', 'in', ('scheduled', 'confirmed')),
            ])
            rec.visits_week = Visit.search_count([
                ('date_start', '>=', today_start),
                ('date_start', '<', week_end),
                ('state', 'in', ('scheduled', 'confirmed')),
            ])

    # ------------------------------------------------------------------
    # Singleton bootstrap — called from the menu action
    # ------------------------------------------------------------------
    @api.model
    def action_open_dashboard(self):
        rec = self.search([], limit=1)
        if not rec:
            rec = self.create({'name': 'Dashboard'})
        return {
            'type': 'ir.actions.act_window',
            'name': _('Real Estate Dashboard'),
            'res_model': 'real.estate.dashboard',
            'res_id': rec.id,
            'view_mode': 'form',
            'view_id': self.env.ref(
                'real_estate_management_pro.view_dashboard_form').id,
            'target': 'current',
        }

    # ------------------------------------------------------------------
    # Drill-down helpers — every card on the dashboard calls one of these
    # ------------------------------------------------------------------
    def _open(self, name, model, domain=None, view_mode='list,form'):
        return {
            'type': 'ir.actions.act_window',
            'name': name,
            'res_model': model,
            'view_mode': view_mode,
            'domain': domain or [],
            'target': 'current',
        }

    def action_open_properties(self):
        return self._open(_('Properties'), 'real.estate.property',
                          view_mode='kanban,list,form')

    def action_open_available(self):
        return self._open(_('Available Properties'), 'real.estate.property',
                          [('state', '=', 'available')], view_mode='kanban,list,form')

    def action_open_contracts(self):
        return self._open(_('Contracts'), 'real.estate.contract')

    def action_open_running_contracts(self):
        return self._open(_('Active Contracts'), 'real.estate.contract',
                          [('state', '=', 'running')])

    def action_open_tenants(self):
        return self._open(_('Active Tenants'), 'res.partner',
                          [('is_property_tenant', '=', True)],
                          view_mode='kanban,list,form')

    def action_open_owners(self):
        return self._open(_('Landlords / Owners'), 'res.partner',
                          [('is_property_owner', '=', True)],
                          view_mode='kanban,list,form')

    def action_open_providers(self):
        return self._open(_('Maintenance Providers'), 'res.partner',
                          [('is_maintenance_provider', '=', True)],
                          view_mode='kanban,list,form')

    # Rental
    def action_open_rent_draft(self):
        return self._open(_('Rental — Draft'), 'real.estate.contract',
                          [('contract_type', '=', 'rent'), ('state', '=', 'draft')])

    def action_open_rent_running(self):
        return self._open(_('Rental — Running'), 'real.estate.contract',
                          [('contract_type', '=', 'rent'), ('state', '=', 'running')])

    def action_open_rent_expired(self):
        return self._open(_('Rental — Expired'), 'real.estate.contract',
                          [('contract_type', '=', 'rent'), ('state', '=', 'expired')])

    def action_open_rent_done(self):
        return self._open(_('Rental — Closed'), 'real.estate.contract',
                          [('contract_type', '=', 'rent'), ('state', '=', 'done')])

    def action_open_rent_cancelled(self):
        return self._open(_('Rental — Cancelled'), 'real.estate.contract',
                          [('contract_type', '=', 'rent'), ('state', '=', 'cancelled')])

    # Sale
    def action_open_sale_draft(self):
        return self._open(_('Sale — Draft'), 'real.estate.contract',
                          [('contract_type', '=', 'sale'), ('state', '=', 'draft')])

    def action_open_sale_running(self):
        return self._open(_('Sale — Running'), 'real.estate.contract',
                          [('contract_type', '=', 'sale'), ('state', '=', 'running')])

    def action_open_sale_expired(self):
        return self._open(_('Sale — Expired'), 'real.estate.contract',
                          [('contract_type', '=', 'sale'), ('state', '=', 'expired')])

    def action_open_sale_done(self):
        return self._open(_('Sale — Closed'), 'real.estate.contract',
                          [('contract_type', '=', 'sale'), ('state', '=', 'done')])

    def action_open_sale_cancelled(self):
        return self._open(_('Sale — Cancelled'), 'real.estate.contract',
                          [('contract_type', '=', 'sale'), ('state', '=', 'cancelled')])

    # Collections & ops
    def action_open_overdue(self):
        return self._open(_('Overdue Collections'), 'real.estate.payment',
                          [('state', '=', 'overdue')])

    def action_open_pending(self):
        return self._open(_('Pending Collections'), 'real.estate.payment',
                          [('state', '=', 'pending')])

    def action_open_tickets(self):
        return self._open(_('Open Tickets'), 'real.estate.maintenance',
                          [('state', 'in', ('new', 'in_progress'))])

    def action_open_renovations(self):
        return self._open(_('Active Renovations'), 'real.estate.renovation',
                          [('state', 'in', ('draft', 'in_progress'))])

    def action_open_visits_today(self):
        today = fields.Date.context_today(self)
        start = fields.Datetime.to_datetime(today)
        end = start + relativedelta(days=1)
        return self._open(_("Today's Visits"), 'real.estate.visit',
                          [('date_start', '>=', start),
                           ('date_start', '<', end),
                           ('state', 'in', ('scheduled', 'confirmed'))],
                          view_mode='calendar,list,kanban,form')

    def action_open_visits_week(self):
        today = fields.Date.context_today(self)
        start = fields.Datetime.to_datetime(today)
        end = start + relativedelta(days=7)
        return self._open(_("This Week's Visits"), 'real.estate.visit',
                          [('date_start', '>=', start),
                           ('date_start', '<', end),
                           ('state', 'in', ('scheduled', 'confirmed'))],
                          view_mode='calendar,list,kanban,form')
