# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import api, fields, models, _


class RealEstateVisit(models.Model):
    """Scheduled property visit — a viewing with a prospective tenant or buyer.
    Each visit is owned by an agent, points to one property and one contact,
    and shows up in the user's calendar via the <calendar> view."""
    _name = 'real.estate.visit'
    _description = 'Real Estate Visit'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_start desc, id desc'

    name = fields.Char(
        string='Reference', copy=False, readonly=True, index=True,
        default=lambda self: _('New'))
    active = fields.Boolean(string='Active', default=True)
    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company)

    property_id = fields.Many2one(
        'real.estate.property', string='Property', required=True,
        ondelete='cascade', tracking=True, index=True)
    contact_id = fields.Many2one(
        'res.partner', string='Visitor', required=True, tracking=True,
        help='Prospective tenant or buyer attending the visit.')
    agent_id = fields.Many2one(
        'res.users', string='Agent', required=True, tracking=True,
        default=lambda self: self.env.user)

    visit_type = fields.Selection(
        selection=[
            ('rent', 'Rental'),
            ('sale', 'Sale'),
            ('both', 'Rent or Sale'),
        ],
        string='Visit Type', default='rent', required=True, tracking=True)

    date_start = fields.Datetime(
        string='Date & Time', required=True, tracking=True,
        default=lambda self: fields.Datetime.now() + timedelta(hours=1))
    duration = fields.Float(
        string='Duration (hours)', default=0.5,
        help='Visit duration in hours. 0.5 = 30 minutes.')
    date_end = fields.Datetime(
        string='End', compute='_compute_date_end', store=True)

    state = fields.Selection(
        selection=[
            ('scheduled', 'Scheduled'),
            ('confirmed', 'Confirmed'),
            ('done', 'Done'),
            ('no_show', 'No-show'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status', default='scheduled', required=True, tracking=True,
        group_expand='_group_expand_states')

    interest_level = fields.Selection(
        selection=[
            ('cold', 'Cold'),
            ('warm', 'Warm'),
            ('hot', 'Hot'),
        ],
        string='Interest', tracking=True,
        help='Visitor interest level captured after the visit.')

    feedback = fields.Html(
        string='Feedback', help='Notes captured after the visit took place.')
    notes = fields.Html(string='Internal Notes')
    color = fields.Integer(
        string='Color', compute='_compute_color', store=False)

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------
    @api.depends('date_start', 'duration')
    def _compute_date_end(self):
        for v in self:
            if v.date_start:
                v.date_end = v.date_start + timedelta(hours=v.duration or 0.0)
            else:
                v.date_end = False

    @api.depends('state', 'interest_level')
    def _compute_color(self):
        # Drives the calendar / kanban colour. Maps to Odoo's 11 colours.
        state_color = {
            'scheduled': 4,    # light blue
            'confirmed': 10,   # green
            'done': 7,         # teal
            'no_show': 2,      # orange
            'cancelled': 1,    # red
        }
        for v in self:
            v.color = state_color.get(v.state, 0)

    @api.model
    def _group_expand_states(self, *args):
        return [key for key, _label in self._fields['state'].selection]

    # ------------------------------------------------------------------
    # ORM
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'real.estate.visit') or _('New')
        return super().create(vals_list)

    # ------------------------------------------------------------------
    # Workflow actions
    # ------------------------------------------------------------------
    def action_confirm(self):
        self.write({'state': 'confirmed'})

    def action_done(self):
        self.write({'state': 'done'})

    def action_no_show(self):
        self.write({'state': 'no_show'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_reset(self):
        self.write({'state': 'scheduled'})
