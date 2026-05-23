# -*- coding: utf-8 -*-
from odoo import api, fields, models


class RealEstatePropertyType(models.Model):
    """Classification of properties (Apartment, House, Office, Land...)."""
    _name = 'real.estate.property.type'
    _description = 'Real Estate Property Type'
    _order = 'sequence, name'

    name = fields.Char(string='Type', required=True, translate=True)
    sequence = fields.Integer(string='Sequence', default=10)
    color = fields.Integer(string='Color')
    active = fields.Boolean(string='Active', default=True)

    property_ids = fields.One2many(
        'real.estate.property', 'property_type_id', string='Properties')
    property_count = fields.Integer(
        string='Property Count', compute='_compute_property_count')

    _sql_constraints = [
        ('name_uniq', 'UNIQUE(name)', 'A property type with this name already exists.'),
    ]

    @api.depends('property_ids')
    def _compute_property_count(self):
        for ptype in self:
            ptype.property_count = len(ptype.property_ids)
