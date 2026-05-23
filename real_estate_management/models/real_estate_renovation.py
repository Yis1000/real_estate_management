# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class RealEstateRenovation(models.Model):
    """Renovation project for a property (refurbishment, furniture purchase...)
    organised as a set of pending tasks."""
    _name = 'real.estate.renovation'
    _description = 'Real Estate Renovation Project'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_start desc, id desc'

    name = fields.Char(string='Project Name', required=True, tracking=True)
    active = fields.Boolean(string='Active', default=True)
    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company)
    currency_id = fields.Many2one(
        'res.currency', related='company_id.currency_id', string='Currency')

    property_id = fields.Many2one(
        'real.estate.property', string='Property', required=True,
        ondelete='cascade', tracking=True, index=True)
    manager_id = fields.Many2one(
        'res.users', string='Project Manager',
        default=lambda self: self.env.user)
    description = fields.Html(string='Scope')

    state = fields.Selection(
        selection=[
            ('draft', 'Planned'),
            ('in_progress', 'In Progress'),
            ('done', 'Completed'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status', default='draft', required=True, tracking=True)
    date_start = fields.Date(string='Start Date', default=fields.Date.context_today)
    date_end = fields.Date(string='Target End Date')

    budget = fields.Monetary(string='Budget', currency_field='currency_id')
    actual_cost = fields.Monetary(
        string='Actual Cost', compute='_compute_costs', store=True,
        currency_field='currency_id')
    budget_variance = fields.Monetary(
        string='Budget Variance', compute='_compute_costs', store=True,
        currency_field='currency_id',
        help='Budget minus actual cost. Negative means over budget.')

    task_ids = fields.One2many(
        'real.estate.renovation.task', 'renovation_id', string='Tasks')
    task_count = fields.Integer(
        compute='_compute_costs', string='Number of Tasks', store=True)
    task_done_count = fields.Integer(
        compute='_compute_costs', string='Tasks Done', store=True)
    progress = fields.Float(
        string='Progress (%)', compute='_compute_costs', store=True)

    @api.depends('task_ids.actual_cost', 'task_ids.state', 'budget')
    def _compute_costs(self):
        for project in self:
            tasks = project.task_ids
            done = tasks.filtered(lambda t: t.state == 'done')
            project.actual_cost = sum(tasks.mapped('actual_cost'))
            project.budget_variance = project.budget - project.actual_cost
            project.task_count = len(tasks)
            project.task_done_count = len(done)
            project.progress = (len(done) / len(tasks) * 100) if tasks else 0.0

    def action_start(self):
        self.write({'state': 'in_progress'})

    def action_done(self):
        self.write({'state': 'done'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_view_tasks(self):
        self.ensure_one()
        return {
            'name': _('Renovation Tasks'),
            'type': 'ir.actions.act_window',
            'res_model': 'real.estate.renovation.task',
            'view_mode': 'kanban,list,form',
            'domain': [('renovation_id', '=', self.id)],
            'context': {'default_renovation_id': self.id},
        }


class RealEstateRenovationTask(models.Model):
    """An individual pending task inside a renovation project."""
    _name = 'real.estate.renovation.task'
    _description = 'Real Estate Renovation Task'
    _order = 'sequence, deadline, id'

    name = fields.Char(string='Task', required=True)
    sequence = fields.Integer(string='Sequence', default=10)
    renovation_id = fields.Many2one(
        'real.estate.renovation', string='Renovation Project', required=True,
        ondelete='cascade', index=True)
    property_id = fields.Many2one(
        'real.estate.property', related='renovation_id.property_id',
        store=True, string='Property')
    currency_id = fields.Many2one(
        'res.currency', related='renovation_id.currency_id', string='Currency')

    task_type = fields.Selection(
        selection=[
            ('works', 'Works / Refurbishment'),
            ('furniture', 'Furniture Purchase'),
            ('appliance', 'Appliances'),
            ('decoration', 'Decoration'),
            ('other', 'Other'),
        ],
        string='Task Type', default='works', required=True)
    state = fields.Selection(
        selection=[
            ('todo', 'To Do'),
            ('in_progress', 'In Progress'),
            ('done', 'Done'),
        ],
        string='Status', default='todo', required=True,
        group_expand='_group_expand_states')

    assigned_to_id = fields.Many2one('res.partner', string='Assigned To')
    deadline = fields.Date(string='Deadline')
    estimated_cost = fields.Monetary(string='Estimated Cost', currency_field='currency_id')
    actual_cost = fields.Monetary(string='Actual Cost', currency_field='currency_id')
    notes = fields.Text(string='Notes')

    @api.model
    def _group_expand_states(self, *args):
        # *args keeps this method compatible across Odoo 16-19 (the 'order'
        # argument was removed from group_expand in Odoo 18).
        return [key for key, _label in self._fields['state'].selection]
