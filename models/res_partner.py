# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class ResPartner(models.Model):
    """Extends contacts so the directory can clearly tell apart tenants,
    owners, maintenance providers and the agency's own employees."""
    _inherit = 'res.partner'

    is_property_owner = fields.Boolean(string='Property Owner')
    is_property_tenant = fields.Boolean(string='Tenant')
    is_maintenance_provider = fields.Boolean(string='Maintenance Provider')
    is_real_estate_employee = fields.Boolean(string='Agency Employee')

    real_estate_role = fields.Char(
        string='Real Estate Role', compute='_compute_real_estate_role')

    # Properties owned by this contact
    owned_property_ids = fields.One2many(
        'real.estate.property', 'owner_id', string='Owned Properties')
    owned_property_count = fields.Integer(
        string='Number of Owned Properties', compute='_compute_real_estate_counts')
    # Contracts where this contact is the tenant / buyer
    tenant_contract_ids = fields.One2many(
        'real.estate.contract', 'tenant_id', string='Contracts as Tenant')
    tenant_contract_count = fields.Integer(
        string='Contracts', compute='_compute_real_estate_counts')

    @api.depends('is_property_owner', 'is_property_tenant',
                 'is_maintenance_provider', 'is_real_estate_employee')
    def _compute_real_estate_role(self):
        for partner in self:
            roles = []
            if partner.is_property_owner:
                roles.append(_('Owner'))
            if partner.is_property_tenant:
                roles.append(_('Tenant'))
            if partner.is_maintenance_provider:
                roles.append(_('Provider'))
            if partner.is_real_estate_employee:
                roles.append(_('Employee'))
            partner.real_estate_role = ', '.join(roles)

    @api.depends('owned_property_ids', 'tenant_contract_ids')
    def _compute_real_estate_counts(self):
        for partner in self:
            partner.owned_property_count = len(partner.owned_property_ids)
            partner.tenant_contract_count = len(partner.tenant_contract_ids)

    def action_view_owned_properties(self):
        self.ensure_one()
        return {
            'name': _('Owned Properties'),
            'type': 'ir.actions.act_window',
            'res_model': 'real.estate.property',
            'view_mode': 'list,form',
            'domain': [('owner_id', '=', self.id)],
            'context': {'default_owner_id': self.id},
        }

    def action_view_tenant_contracts(self):
        self.ensure_one()
        return {
            'name': _('Contracts'),
            'type': 'ir.actions.act_window',
            'res_model': 'real.estate.contract',
            'view_mode': 'list,form',
            'domain': [('tenant_id', '=', self.id)],
            'context': {'default_tenant_id': self.id},
        }
