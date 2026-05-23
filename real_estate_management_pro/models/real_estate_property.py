# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _


class RealEstateProperty(models.Model):
    """Core record of a real estate asset (the property file)."""
    _name = 'real.estate.property'
    _description = 'Real Estate Property'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'code desc, name'

    # ------------------------------------------------------------------
    # Identification
    # ------------------------------------------------------------------
    name = fields.Char(string='Property Name', required=True, tracking=True, index=True)
    code = fields.Char(
        string='Reference', copy=False, readonly=True, index=True,
        default=lambda self: _('New'))
    active = fields.Boolean(string='Active', default=True)
    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company)
    currency_id = fields.Many2one(
        'res.currency', related='company_id.currency_id', string='Currency')
    image = fields.Image(string='Photo', max_width=1920, max_height=1920)
    description = fields.Html(string='Description')

    property_type_id = fields.Many2one(
        'real.estate.property.type', string='Property Type', tracking=True)

    # ------------------------------------------------------------------
    # Commercial state / operation
    # ------------------------------------------------------------------
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('available', 'Available'),
            ('reserved', 'Reserved'),
            ('rented', 'Rented'),
            ('sold', 'Sold'),
            ('maintenance', 'Under Maintenance'),
            ('unavailable', 'Unavailable'),
        ],
        string='Status', default='draft', required=True, tracking=True)
    operation_type = fields.Selection(
        selection=[
            ('rent', 'For Rent'),
            ('sale', 'For Sale'),
            ('both', 'Rent & Sale'),
        ],
        string='Operation', default='rent', required=True, tracking=True)

    # ------------------------------------------------------------------
    # Address & Geolocation (latitude/longitude feed the Map view)
    # ------------------------------------------------------------------
    street = fields.Char(string='Street')
    street2 = fields.Char(string='Street 2')
    city = fields.Char(string='City')
    zip = fields.Char(string='ZIP')
    state_id = fields.Many2one('res.country.state', string='State/Province')
    country_id = fields.Many2one(
        'res.country', string='Country',
        default=lambda self: self.env.company.country_id)
    latitude = fields.Float(string='Latitude', digits=(10, 7))
    longitude = fields.Float(string='Longitude', digits=(10, 7))

    # ------------------------------------------------------------------
    # Legal / registry data (used by the printed rental contract under LAU)
    # ------------------------------------------------------------------
    cadastral_reference = fields.Char(
        string='Cadastral Reference', size=30,
        help='Spanish "Referencia Catastral" (20 alphanumeric characters).')
    property_registry_ref = fields.Char(
        string='Property Registry Reference',
        help='Inscription details at the Property Registry '
             '("Registro de la Propiedad").')
    annexes = fields.Char(
        string='Annexes',
        help='Storage room, parking space, garden, etc. attached to the dwelling.')
    has_energy_certificate = fields.Boolean(
        string='Energy Certificate', default=True,
        help='True if the dwelling has the mandatory energy efficiency '
             'certificate (Royal Decree 235/2013).')

    # ------------------------------------------------------------------
    # Physical characteristics
    # ------------------------------------------------------------------
    bedrooms = fields.Integer(string='Bedrooms', default=1)
    bathrooms = fields.Integer(string='Bathrooms', default=1)
    living_area = fields.Float(string='Living Area (m²)')
    total_area = fields.Float(string='Total Area (m²)')
    floor = fields.Char(string='Floor')
    year_built = fields.Integer(string='Year Built')
    has_garage = fields.Boolean(string='Garage')
    has_garden = fields.Boolean(string='Garden')
    has_elevator = fields.Boolean(string='Elevator')
    is_furnished = fields.Boolean(string='Furnished')

    # ------------------------------------------------------------------
    # Pricing
    # ------------------------------------------------------------------
    sale_price = fields.Monetary(string='Sale Price', currency_field='currency_id')
    rent_price = fields.Monetary(string='Monthly Rent', currency_field='currency_id')
    current_value = fields.Monetary(string='Current Market Value', currency_field='currency_id')
    gross_yield = fields.Float(
        string='Gross Yield (%)', compute='_compute_gross_yield', store=True,
        help='Annual rent divided by sale price, as a percentage.')

    # ------------------------------------------------------------------
    # Parties
    # ------------------------------------------------------------------
    owner_id = fields.Many2one(
        'res.partner', string='Owner', tracking=True,
        domain=[('is_property_owner', '=', True)])
    current_tenant_id = fields.Many2one(
        'res.partner', string='Current Tenant',
        compute='_compute_active_contract', store=True)
    active_contract_id = fields.Many2one(
        'real.estate.contract', string='Active Contract',
        compute='_compute_active_contract', store=True)

    # ------------------------------------------------------------------
    # Related operations
    # ------------------------------------------------------------------
    contract_ids = fields.One2many('real.estate.contract', 'property_id', string='Contracts')
    maintenance_ids = fields.One2many('real.estate.maintenance', 'property_id', string='Tickets')
    renovation_ids = fields.One2many('real.estate.renovation', 'property_id', string='Renovations')
    image_ids = fields.One2many('real.estate.image', 'property_id', string='Photos')
    visit_ids = fields.One2many('real.estate.visit', 'property_id', string='Visits')
    is_new = fields.Boolean(
        compute='_compute_is_new', string='Recently Added',
        help='True when this property was created in the last 7 days.')

    contract_count = fields.Integer(compute='_compute_counts', string='Contract Count')
    maintenance_count = fields.Integer(compute='_compute_counts', string='Ticket Count')
    renovation_count = fields.Integer(compute='_compute_counts', string='Renovation Count')
    visit_count = fields.Integer(compute='_compute_counts', string='Visit Count')

    # ------------------------------------------------------------------
    # Financial summary (feeds dashboard & balance report)
    # ------------------------------------------------------------------
    total_collected = fields.Monetary(
        string='Total Collected', compute='_compute_financials',
        store=True, currency_field='currency_id')
    total_pending = fields.Monetary(
        string='Pending Collections', compute='_compute_financials',
        store=True, currency_field='currency_id')
    total_overdue = fields.Monetary(
        string='Overdue Amount', compute='_compute_financials',
        store=True, currency_field='currency_id')
    maintenance_cost = fields.Monetary(
        string='Maintenance Cost', compute='_compute_financials',
        store=True, currency_field='currency_id')
    renovation_cost = fields.Monetary(
        string='Renovation Cost', compute='_compute_financials',
        store=True, currency_field='currency_id')
    net_balance = fields.Monetary(
        string='Net Balance', compute='_compute_financials',
        store=True, currency_field='currency_id',
        help='Collected income minus maintenance and renovation costs.')

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------
    @api.depends('rent_price', 'sale_price')
    def _compute_gross_yield(self):
        for prop in self:
            if prop.sale_price:
                prop.gross_yield = (prop.rent_price * 12) / prop.sale_price * 100
            else:
                prop.gross_yield = 0.0

    @api.depends('contract_ids.state', 'contract_ids.tenant_id')
    def _compute_active_contract(self):
        for prop in self:
            active = prop.contract_ids.filtered(lambda c: c.state == 'running')[:1]
            prop.active_contract_id = active
            prop.current_tenant_id = active.tenant_id

    @api.depends('contract_ids', 'maintenance_ids', 'renovation_ids', 'visit_ids')
    def _compute_counts(self):
        for prop in self:
            prop.contract_count = len(prop.contract_ids)
            prop.maintenance_count = len(prop.maintenance_ids)
            prop.renovation_count = len(prop.renovation_ids)
            prop.visit_count = len(prop.visit_ids)

    @api.depends(
        'contract_ids.payment_ids.state', 'contract_ids.payment_ids.amount',
        'maintenance_ids.cost', 'renovation_ids.actual_cost')
    def _compute_financials(self):
        for prop in self:
            payments = prop.contract_ids.payment_ids
            prop.total_collected = sum(
                payments.filtered(lambda p: p.state == 'paid').mapped('amount'))
            prop.total_pending = sum(
                payments.filtered(lambda p: p.state in ('pending', 'overdue')).mapped('amount'))
            prop.total_overdue = sum(
                payments.filtered(lambda p: p.state == 'overdue').mapped('amount'))
            prop.maintenance_cost = sum(prop.maintenance_ids.mapped('cost'))
            prop.renovation_cost = sum(prop.renovation_ids.mapped('actual_cost'))
            prop.net_balance = (
                prop.total_collected - prop.maintenance_cost - prop.renovation_cost)

    # ------------------------------------------------------------------
    # ORM overrides
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('code', _('New')) == _('New'):
                vals['code'] = self.env['ir.sequence'].next_by_code(
                    'real.estate.property') or _('New')
        return super().create(vals_list)

    def action_view_visits(self):
        self.ensure_one()
        return {
            'name': _('Visits'),
            'type': 'ir.actions.act_window',
            'res_model': 'real.estate.visit',
            'view_mode': 'calendar,list,kanban,form',
            'domain': [('property_id', '=', self.id)],
            'context': {'default_property_id': self.id},
        }

    @api.depends('create_date')
    def _compute_is_new(self):
        cutoff = fields.Datetime.now() - relativedelta(days=7)
        for prop in self:
            prop.is_new = bool(prop.create_date and prop.create_date >= cutoff)

    @api.depends('code', 'name')
    def _compute_display_name(self):
        for prop in self:
            if prop.code and prop.code != _('New'):
                prop.display_name = '[%s] %s' % (prop.code, prop.name or '')
            else:
                prop.display_name = prop.name or _('New Property')

    # ------------------------------------------------------------------
    # Actions (smart buttons)
    # ------------------------------------------------------------------
    def action_view_contracts(self):
        self.ensure_one()
        return {
            'name': _('Contracts'),
            'type': 'ir.actions.act_window',
            'res_model': 'real.estate.contract',
            'view_mode': 'list,form',
            'domain': [('property_id', '=', self.id)],
            'context': {'default_property_id': self.id},
        }

    def action_view_maintenance(self):
        self.ensure_one()
        return {
            'name': _('Maintenance Tickets'),
            'type': 'ir.actions.act_window',
            'res_model': 'real.estate.maintenance',
            'view_mode': 'list,form',
            'domain': [('property_id', '=', self.id)],
            'context': {'default_property_id': self.id},
        }

    def action_view_renovations(self):
        self.ensure_one()
        return {
            'name': _('Renovations'),
            'type': 'ir.actions.act_window',
            'res_model': 'real.estate.renovation',
            'view_mode': 'list,form',
            'domain': [('property_id', '=', self.id)],
            'context': {'default_property_id': self.id},
        }

    def action_set_available(self):
        self.write({'state': 'available'})

    def action_set_unavailable(self):
        self.write({'state': 'unavailable'})
