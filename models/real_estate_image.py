# -*- coding: utf-8 -*-
from odoo import fields, models


class RealEstateImage(models.Model):
    """Single image record reused as a gallery item by properties and
    maintenance tickets. Each row points to exactly one parent through
    a nullable Many2one — the parent's One2many picks the rows it owns."""
    _name = 'real.estate.image'
    _description = 'Real Estate Image'
    _order = 'sequence, id'

    name = fields.Char(string='Title')
    sequence = fields.Integer(default=10)
    image = fields.Image(
        string='Image', required=True, max_width=1920, max_height=1920)
    image_medium = fields.Image(
        related='image', max_width=512, max_height=512, store=False,
        string='Image (medium)')

    property_id = fields.Many2one(
        'real.estate.property', string='Property', ondelete='cascade',
        index=True)
    maintenance_id = fields.Many2one(
        'real.estate.maintenance', string='Maintenance Ticket',
        ondelete='cascade', index=True)
