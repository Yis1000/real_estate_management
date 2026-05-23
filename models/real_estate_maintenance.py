# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class RealEstateMaintenance(models.Model):
    """Maintenance ticket: an incident or repair reported on a property."""
    _name = 'real.estate.maintenance'
    _description = 'Real Estate Maintenance Ticket'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'priority desc, create_date desc'

    name = fields.Char(
        string='Ticket', copy=False, readonly=True, index=True,
        default=lambda self: _('New'))
    active = fields.Boolean(string='Active', default=True)
    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company)
    currency_id = fields.Many2one(
        'res.currency', related='company_id.currency_id', string='Currency')

    property_id = fields.Many2one(
        'real.estate.property', string='Property', required=True,
        ondelete='cascade', tracking=True, index=True)
    title = fields.Char(string='Subject', required=True, tracking=True)
    description = fields.Html(string='Description')

    maintenance_type = fields.Selection(
        selection=[
            ('plumbing', 'Plumbing'),
            ('electrical', 'Electrical'),
            ('appliance', 'Appliances'),
            ('structural', 'Structural'),
            ('hvac', 'Heating / AC'),
            ('cleaning', 'Cleaning'),
            ('other', 'Other'),
        ],
        string='Type', default='other', required=True)
    priority = fields.Selection(
        selection=[('0', 'Low'), ('1', 'Normal'), ('2', 'High'), ('3', 'Urgent')],
        string='Priority', default='1', tracking=True)
    state = fields.Selection(
        selection=[
            ('new', 'New'),
            ('in_progress', 'In Progress'),
            ('done', 'Resolved'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status', default='new', required=True, tracking=True, group_expand='_group_expand_states')

    reported_by_id = fields.Many2one(
        'res.partner', string='Reported By',
        help='Usually the tenant living in the property.')
    provider_id = fields.Many2one(
        'res.partner', string='Assigned Provider',
        domain=['|', ('is_maintenance_provider', '=', True),
                ('is_real_estate_employee', '=', True)],
        tracking=True)

    date_reported = fields.Date(string='Reported On', default=fields.Date.context_today)
    date_resolved = fields.Date(string='Resolved On')
    cost = fields.Monetary(string='Repair Cost', currency_field='currency_id', tracking=True)

    image_ids = fields.One2many(
        'real.estate.image', 'maintenance_id', string='Photos')

    @api.model
    def _group_expand_states(self, *args):
        # *args absorbs the extra 'order' arg passed by Odoo 16/17 (3 args)
        # vs Odoo 18/19 (2 args), keeping this model identical across versions.
        return [key for key, _label in self._fields['state'].selection]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'real.estate.maintenance') or _('New')
        return super().create(vals_list)

    def action_start(self):
        self.write({'state': 'in_progress'})

    def action_done(self):
        self.write({
            'state': 'done',
            'date_resolved': fields.Date.context_today(self),
        })

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_reset(self):
        self.write({'state': 'new', 'date_resolved': False})
